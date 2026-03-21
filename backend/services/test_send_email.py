import smtplib
from email.mime.text import MIMEText
from email.header import Header

def send_email():
    # --- 1. 配置参数 ---
    smtp_server = "smtp.feishu.cn"      # 网易 163 邮箱服务器地址
    # 如果是 126 邮箱，请改为 "smtp.126.com"
    #{"host":"smtp.feishu.cn","port":"465","account":"service@9z.cloud","password":"4FkZkJDk1lv1rHCe"}
    sender = "service@9z.cloud"     # 你的邮箱地址
    password = "4FkZkJDk1lv1rHCe"     # 注意：这里填的是【授权码】，不是登录密码
    receiver = "yzs@ninedata.cloud" # 收件人地址

    # --- 2. 构建邮件内容 ---
    # 三个参数：内容、文本格式(plain或html)、编码
    message = MIMEText('这是一封来自 Python 脚本的自动测试邮件。', 'plain', 'utf-8')
    message['From'] = sender          # 发件人显示
    message['To'] = receiver          # 收件人显示
    message['Subject'] = Header('Python SMTP 测试', 'utf-8') # 邮件主题

    try:
        # --- 3. 连接服务器并发送 ---
        # 网易 SMTP 端口通常为 465 (SSL) 或 25 (非SSL，不建议)
        server = smtplib.SMTP_SSL(smtp_server, 465) 
        
        # 登录
        server.login(sender, password)
        
        # 发送邮件
        server.sendmail(sender, [receiver], message.as_string())
        print("邮件发送成功！")
        
        # 退出
        server.quit()
        
    except Exception as e:
        print(f"发送失败，错误原因: {e}")

if __name__ == "__main__":
    send_email()