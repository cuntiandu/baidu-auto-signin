import os
import re
import sys
import time
import json
import requests


# ============================================================================
# 2026-09-16 修复说明
#
# 上一版报错（GitHub Actions 日志）：
#   urllib3.exceptions.DecodeError: ('Received response with content-encoding: gzip,
#       but failed to decode it.', error('Error -3 while decompressing data:
#       incorrect header check'))
#   requests.exceptions.ContentDecodingError: ...
#   崩在 get_userinfo() 那一行，整个脚本直接退出（exit code 1）
#
# 原因：脚本自己把请求头写死成 "Accept-Encoding: gzip, deflate"，
#       而百度这个接口返回了 "Content-Encoding: gzip"，响应体却并不是 gzip。
#       响应头和响应体对不上 → urllib3 解压时抛 DecodeError。
#
# 本次改动（3 处）：
#   1. Accept-Encoding 从 "gzip, deflate" 改成 "identity" → 直接不压缩，绕开解压环节
#   2. 所有请求收进 _get()，任何网络/解码异常都不再抛出；万一仍遇到"头说是 gzip
#      但体不是"，自动改为读原始字节重试
#   3. 一个接口出错不再拖垮整次运行 → 签到结果一定能打印出来
#      （上一版就是崩在最后的查询接口，导致前面签到成没成完全看不到）
#
# 另外把退出码改对了：签到真的失败时 exit 1（红色），成功或今日已签到 exit 0（绿色）。
# 这样 Actions 的绿勾才真的代表"签到了"。
# ============================================================================


def get_cookies():
    cookie = os.getenv("BAIDU_COOKIE", "").strip()
    if not cookie:
        print("错误: 未配置 BAIDU_COOKIE 环境变量")
        sys.exit(1)
    return [c.strip() for c in re.split(r'\n|&&', cookie) if c.strip()]


class BaiduWP:
    def __init__(self, cookie):
        self.cookie = cookie
        self.session = requests.Session()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36",
            "Referer": "https://pan.baidu.com/wap/svip/growth/task",
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
            "Connection": "keep-alive",
            "Accept-Encoding": "identity",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cookie": self.cookie,
        }

    def _get(self, url):
        """安全 GET，返回 (status_code, text)。任何异常都不抛出（返回 0, ""）。"""
        try:
            resp = self.session.get(url, headers=self.headers, timeout=20)
            return resp.status_code, resp.text
        except requests.exceptions.ContentDecodingError:
            print("  提示: 响应头声明了压缩但响应体不是压缩内容，改为读原始字节重试")
        except Exception as e:
            print(f"  请求异常: {type(e).__name__}: {e}")
            return 0, ""

        try:
            resp = self.session.get(url, headers=self.headers, timeout=20, stream=True)
            raw = resp.raw.read(decode_content=False)
            return resp.status_code, raw.decode("utf-8", errors="ignore")
        except Exception as e:
            print(f"  兜底重试也失败: {type(e).__name__}: {e}")
            return 0, ""

    def signin(self):
        url = "https://pan.baidu.com/rest/2.0/membership/level?app_id=250528&web=5&method=signin"
        status, text = self._get(url)
        sign_point = None
        signin_error_msg = ""
        if status == 200:
            m = re.search(r'points":(\d+)', text)
            if m:
                sign_point = m.group(1)
            m2 = re.search(r'"error_msg":"(.*?)",', text)
            if m2:
                signin_error_msg = m2.group(1)
        elif status:
            signin_error_msg = f"签到请求失败: HTTP {status}"
        else:
            signin_error_msg = "签到请求未拿到响应"
        return sign_point, signin_error_msg

    def get_question(self):
        url = "https://pan.baidu.com/act/v2/membergrowv2/getdailyquestion?app_id=250528&web=5"
        status, text = self._get(url)
        answer = None
        ask_id = None
        if status == 200:
            m = re.search(r'"answer":(\d+),', text)
            if m:
                answer = m.group(1)
            m2 = re.search(r'"ask_id":(\d+),', text)
            if m2:
                ask_id = m2.group(1)
        return ask_id, answer

    def answer_question(self, ask_id, answer):
        url = f"https://pan.baidu.com/act/v2/membergrowv2/answerquestion?app_id=250528&web=5&ask_id={ask_id}&answer={answer}"
        status, text = self._get(url)
        answer_score = None
        answer_msg = ""
        if status == 200:
            m = re.search(r'"score":(\d+)', text)
            if m:
                answer_score = m.group(1)
            m2 = re.search(r'"show_msg":"(.*?)"', text)
            if m2:
                answer_msg = m2.group(1)
        return answer_score, answer_msg

    def get_userinfo(self):
        url = "https://pan.baidu.com/rest/2.0/membership/user?app_id=250528&web=5&method=query"
        status, text = self._get(url)
        current_value = None
        current_level = None
        if status == 200:
            m = re.search(r'current_value":(\d+),', text)
            if m:
                current_value = m.group(1)
            m2 = re.search(r'current_level":(\d+),', text)
            if m2:
                current_level = m2.group(1)
        return current_level, current_value

    def main(self):
        log = ""
        signed = False

        sign_point, signin_error_msg = self.signin()
        if sign_point:
            log += f"  签到成功，获得成长值 +{sign_point}\n"
            signed = True
        elif signin_error_msg:
            if "已签到" in signin_error_msg or "already" in signin_error_msg.lower():
                log += f"  今日已签到过了\n"
                signed = True
            else:
                log += f"  签到异常: {signin_error_msg}\n"
        else:
            log += f"  签到异常: 未知错误\n"

        time.sleep(3)
        ask_id, answer = self.get_question()
        if ask_id and answer:
            answer_score, answer_msg = self.answer_question(ask_id, answer)
            if answer_score:
                log += f"  每日答题完成，获得 +{answer_score} 分\n"
            elif answer_msg:
                log += f"  答题完成: {answer_msg}\n"
            else:
                log += f"  答题已提交\n"
        else:
            log += f"  今日无答题任务或答题已完成\n"

        current_level, current_value = self.get_userinfo()
        if current_level:
            log += f"  当前会员等级: Lv{current_level}\n"
        if current_value:
            log += f"  当前成长值: {current_value}\n"
        if not current_level and not current_value:
            log += f"  会员信息: 本次没取到（不影响签到结果）\n"

        return log, signed


def main():
    cookie_list = get_cookies()
    print(f"检测到 {len(cookie_list)} 个百度网盘账号\n")
    all_signed = True
    for i, cookie in enumerate(cookie_list):
        print(f"=== 第 {i + 1} 个账号 ===")
        log, signed = BaiduWP(cookie).main()
        print(log)
        if not signed:
            all_signed = False
    print("=== 百度网盘签到完毕 ===")
    return all_signed


if __name__ == "__main__":
    print("----------百度网盘开始签到----------")
    if main():
        print("----------百度网盘签到完毕----------")
        sys.exit(0)
    print("----------百度网盘未签到成功----------")
    sys.exit(1)
