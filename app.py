from flask import Flask, request, jsonify
import imaplib
import email
from email.header import decode_header
import smtplib
from email.mime.text import MIMEText
import os

app = Flask(__name__)

IMAP_SERVER = "imap.163.com"
IMAP_PORT = 993
SMTP_SERVER = "smtp.163.com"
SMTP_PORT = 465

EMAIL_USER = os.environ.get("IMAP_USER")
EMAIL_PASS = os.environ.get("IMAP_PASS")

@app.route('/mcp', methods=['POST', 'GET'])
def mcp_handler():
    if request.method == 'GET':
        return jsonify({"status": "ok"}), 200

    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid request"}), 400

        method = data.get("method")
        if method == "list_tools":
            return jsonify({
                "tools": [
                    {
                        "name": "list_emails",
                        "description": "列出最近的5封邮件",
                        "parameters": {}
                    },
                    {
                        "name": "send_email",
                        "description": "发送邮件",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "to": {"type": "string", "description": "收件人邮箱"},
                                "subject": {"type": "string", "description": "邮件主题"},
                                "body": {"type": "string", "description": "邮件内容"}
                            },
                            "required": ["to", "subject", "body"]
                        }
                    }
                ]
            })

        elif method == "call_tool":
            tool_name = data.get("name")
            params = data.get("parameters", {})
            if tool_name == "list_emails":
                return list_emails()
            elif tool_name == "send_email":
                return send_email(params)
            else:
                return jsonify({"error": "Unknown tool"}), 400
        else:
            return jsonify({"error": "Unknown method"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def list_emails():
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("inbox")
        status, messages = mail.search(None, "ALL")
        email_ids = messages[0].split()[-5:]
        emails = []
        for eid in email_ids:
            status, msg_data = mail.fetch(eid, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    subject, encoding = decode_header(msg["Subject"])[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(encoding if encoding else "utf-8")
                    from_ = msg.get("From")
                    date_ = msg.get("Date")
                    emails.append({"from": from_, "subject": subject, "date": date_})
        mail.logout()
        return jsonify({"content": emails})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def send_email(params):
    try:
        to = params.get("to")
        subject = params.get("subject")
        body = params.get("body")

        msg = MIMEText(body, "plain", "utf-8")
        msg["From"] = EMAIL_USER
        msg["To"] = to
        msg["Subject"] = subject

        server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT)
        server.login(EMAIL_USER, EMAIL_PASS)
        server.sendmail(EMAIL_USER, to, msg.as_string())
        server.quit()
        return jsonify({"content": "邮件发送成功"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run()
