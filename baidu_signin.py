"""百度网盘每日签到（GitHub Actions 定时任务用）。"""

import os
import re
import sys
import time

import requests


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
            # 必须显式声明不要压缩：百度部分接口会返回 Content-Encoding: gzip，
            # 但响应体并不是 gzip，交给 requests 自动解压会抛 ContentDecodingError。
            "Accept-Encoding": "identity",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cookie": self.cookie,
        }

    def _get(self, url):
        """安全 GET，返回 (status_code, text)。任何异常都不抛出，失败返回 (0, "")。"""
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
