import time
import hmac
import hashlib
import base64
import urllib.parse
import requests
import json

def get_dingtalk_url(webhook, secret):
    # 钉钉加签逻辑
    timestamp = str(round(time.time() * 1000))
    secret_enc = secret.encode('utf-8')
    string_to_sign = '{}\n{}'.format(timestamp, secret)
    string_to_sign_enc = string_to_sign.encode('utf-8')
    hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
    return f"{webhook}&timestamp={timestamp}&sign={sign}"

def send_ding_msg(url, content):
    headers = {"Content-Type": "application/json"}
    # 钉钉的消息卡片叫 actionCard
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "title": "任务通知",
            "text": f"### DBClaw 告警通知\n> {content}\n\n[点击查看详情](https://www.dingtalk.com)"
        }
    }
    requests.post(url, data=json.dumps(payload), headers=headers)

# 填入你的 Webhook 和 密钥
WEBHOOK = "https://oapi.dingtalk.com/robot/send?access_token=4941518014d5e3e24e6356b2b13f4fc8d7ca715c497eb52d281c3b5fc772d8df"
SECRET = "SEC7b839b93d17d8f78bf21790274ab6584bda8a8c202b525d60e04b73d16dfa262" 

final_url = get_dingtalk_url(WEBHOOK, SECRET)
send_ding_msg(final_url, "这是一条带加签的钉钉消息！")
