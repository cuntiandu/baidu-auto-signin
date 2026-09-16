import os
import re
import sys
import time
import json
import requests


def get_cookie():
    cookie = os.getenv("BAIDU_COOKIE", "").strip()
    if not cookie:
        print("错误: 未配置 BAIDU_COOKIE 环境变量")
        sys.exit(0)
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
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cookie": self.cookie,
        }

    def signin(self):
        url = "https://pan.baidu.com/rest/2.0/membership/level?app_id=250528&web=5&method=signin"
        resp = self.session.get(url, headers=self.headers, timeout=15)
        sign_point = None
        signin_error_msg = ""
        if resp.status_code == 200:
            m = re.search(r'points":(\d+)', resp.text)
            if m:
                sign_point = m.group(1)
            m2 = re.search(r'"error_msg":"(.*?)",', resp.text)
            if m2:
                signin_error_msg = m2.group(1)
        else:
            signin_error_msg = f"签到请求失败: HTTP {resp.status_code}"
        return sign_point, signin_error_msg

    def get_question(self):
        url = "https://pan.baidu.com/act/v2/membergrowv2/getdailyquestion?app_id=250528&web=5"
        resp = self.session.get(url, headers=self.headers, timeout=15)
        answer = None
        ask_id = None
        if resp.status_code == 200:
            m = re.search(r'"answer":(\d+),', resp.text)
            if m:
                answer = m.group(1)
            m2 = re.search(r'"ask_id":(\d+),', resp.text)
            if m2:
                ask_id = m2.group(1)
        return ask_id, answer

    def answer_question(self, ask_id, answer):
        url = f"https://pan.baidu.com/act/v2/membergrowv2/answerquestion?app_id=250528&web=5&ask_id={ask_id}&answer={answer}"
        resp = self.session.get(url, headers=self.headers, timeout=15)
        answer_score = None
        answer_msg = ""
        if resp.status_code == 200:
            m = re.search(r'"score":(\d+)', resp.text)
            if m:
                answer_score = m.group(1)
            m2 = re.search(r'"show_msg":"(.*?)"', resp.text)
            if m2:
                answer_msg = m2.group(1)
        return answer_score, answer_msg

    def get_userinfo(self):
        url = "https://pan.baidu.com/rest/2.0/membership/user?app_id=250528&web=5&method=query"
        resp = self.session.get(url, headers=self.headers, timeout=15)
        current_value = None
        current_level = None
        if resp.status_code == 200:
            m = re.search(r'current_value":(\d+),', resp.text)
            if m:
                current_value = m.group(1)
            m2 = re.search(r'current_level":(\d+),', resp.text)
            if m2:
                current_level = m2.group(1)
        return current_level, current_value

    def main(self):
        log = ""
        sign_point, signin_error_msg = self.signin()
        if sign_point:
            log += f"  签到成功，获得成长值 +{sign_point}\n"
        elif signin_error_msg:
            if "已签到" in signin_error_msg or "already" in signin_error_msg.lower():
                log += f"  今日已签到过了\n"
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
        return log


def main():
    cookie_list = get_cookie()
    print(f"检测到 {len(cookie_list)} 个百度网盘账号\n")
    for i, cookie in enumerate(cookie_list):
        print(f"=== 第 {i + 1} 个账号 ===")
        result = BaiduWP(cookie).main()
        print(result)
    print("=== 百度网盘签到完毕 ===")


if __name__ == "__main__":
    print("----------百度网盘开始签到----------")
    main()
    print("----------百度网盘签到完毕----------")
