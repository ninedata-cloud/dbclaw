import requests
import json

def send_feishu_message(webhook_url, text):
    # 构建消息体（这里以最简单的文本消息为例）
    payload = {
        "msg_type": "text",
        "content": {
            "text": text
        }
    }
    
    headers = {
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(webhook_url, data=json.dumps(payload), headers=headers)
        result = response.json()
        
        if result.get("code") == 0:
            print("消息发送成功！")
        else:
            print(f"发送失败，错误码：{result.get('code')}, 错误信息：{result.get('msg')}")
            
    except Exception as e:
        print(f"请求出错: {e}")

def send_feishu_card(webhook_url):
    # 这里就是从可视化工具里复制出来的卡片 JSON 结构
    card_content = {
        "config": {
            "wide_screen_mode": True
        },
        "header": {
            "title": {
                "tag": "plain_text",
                "content": "🚀 任务提醒"
            },
            "template": "blue" # 标题颜色：blue, wathet, turquoise, green, yellow, orange, red, violet, carmine, grey
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "**项目名称：** 自动化脚本部署\n**状态：** <font color='green'>运行中</font>\n**负责人：** @张三"
                }
            },
            {
                "tag": "hr" # 分割线
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {
                            "tag": "plain_text",
                            "content": "查看详情"
                        },
                        "type": "primary",
                        "multi_url": {
                            "url": "https://www.example.com",
                            "pc_url": "",
                            "android_url": "",
                            "ios_url": ""
                        }
                    }
                ]
            }
        ]
    }

    payload = {
        "msg_type": "interactive",
        "card": card_content
    }

    response = requests.post(webhook_url, json=payload)
    print(response.json())

# 使用你的 Webhook 地址替换这里
WEBHOOK_URL = "https://open.feishu.cn/open-apis/bot/v2/hook/2fc2f4b4-cbd6-4d7c-83a4-b2645994fad7"
# 注意：如果设置了关键词，消息内容必须包含该关键词
# send_feishu_message(WEBHOOK_URL, "通知：这是一条来自 Python 的测试信息！")
send_feishu_card(WEBHOOK_URL)
