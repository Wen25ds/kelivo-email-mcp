import os
import asyncio
import aioimaplib
import aiosmtplib
from email.mime.text import MIMEText
from contextlib import asynccontextmanager
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
import mcp.server.stdio
import mcp.types as types
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 邮箱配置（从环境变量读取）
IMAP_SERVER = os.getenv("IMAP_SERVER", "imap.qq.com")
IMAP_USER = os.getenv("IMAP_USER")
IMAP_PASSWORD = os.getenv("IMAP_PASSWORD")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.qq.com")
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

# 自动监控间隔（秒）
MONITOR_INTERVAL = 60

class AutoEmailAgent:
    def __init__(self):
        self.server = Server("auto-email-agent")
        self.setup_tools()
        self.setup_resources()
        
    def setup_tools(self):
        """定义 AI 可用的工具"""
        @self.server.list_tools()
        async def list_tools():
            return [
                types.Tool(
                    name="send_email",
                    description="自动发送邮件（无需确认）",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "to": {"type": "string", "description": "收件人邮箱"},
                            "subject": {"type": "string", "description": "邮件主题"},
                            "content": {"type": "string", "description": "邮件正文"},
                        },
                        "required": ["to", "subject", "content"]
                    }
                ),
                types.Tool(
                    name="check_inbox",
                    description="检查收件箱最新邮件（自动执行，无需触发）",
                    inputSchema={"type": "object", "properties": {}}
                )
            ]

        @self.server.call_tool()
        async def call_tool(request):
            if request.name == "send_email":
                return await self._send_email(
                    to=request.arguments["to"],
                    subject=request.arguments["subject"],
                    content=request.arguments["content"]
                )
            elif request.name == "check_inbox":
                return await self._check_inbox()
            return types.TextContent(type="text", text="未知工具")

    def setup_resources(self):
        """定义 AI 可查看的资源"""
        @self.server.list_resources()
        async def list_resources():
            return [
                types.Resource(
                    uri="mcp://email/inbox_status",
                    name="inbox_status",
                    description="收件箱状态（未读邮件数、最新邮件摘要）",
                    mimeType="text/plain"
                )
            ]

        @self.server.read_resource()
        async def read_resource(request):
            if request.uri == "mcp://email/inbox_status":
                status = await self._get_inbox_status()
                return [types.TextContent(type="text", text=status)]

    # 核心功能实现
    async def _send_email(self, to: str, subject: str, content: str):
        """自动发送邮件（无确认）"""
        try:
            message = MIMEText(content, "plain", "utf-8")
            message["From"] = SMTP_USER
            message["To"] = to
            message["Subject"] = subject

            async with aiosmtplib.SMTP(
                hostname=SMTP_SERVER, 
                port=587, 
                use_tls=True
            ) as smtp:
                await smtp.login(SMTP_USER, SMTP_PASSWORD)
                await smtp.send_message(message)
            
            logger.info(f"邮件已自动发送至 {to}: {subject}")
            return types.TextContent(
                type="text", 
                text=f"✅ 邮件已自动发送给 {to}"
            )
        except Exception as e:
            logger.error(f"发送失败: {e}")
            return types.TextContent(
                type="text", 
                text=f"❌ 发送失败: {str(e)}"
            )

    async def _check_inbox(self):
        """检查收件箱（可被 AI 定时触发）"""
        try:
            async with aioimaplib.IMAP4_SSL(IMAP_SERVER) as imap:
                await imap.login(IMAP_USER, IMAP_PASSWORD)
                await imap.select("INBOX")
                
                status, messages = await imap.search("UNSEEN")
                unread_ids = messages[0].split()
                
                if unread_ids:
                    # 获取最新未读邮件
                    latest_id = unread_ids[-1]
                    status, msg_data = await imap.fetch(latest_id, "(RFC822)")
                    
                    # 解析邮件主题和发件人
                    from email import message_from_bytes
                    raw_email = msg_data[0][1]
                    email_message = message_from_bytes(raw_email)
                    
                    subject = email_message.get("Subject", "无主题")
                    sender = email_message.get("From", "未知发件人")
                    
                    summary = f"📧 新邮件来自 {sender}\n主题: {subject}\n"
                    logger.info(f"发现新邮件: {subject}")
                    
                    return types.TextContent(
                        type="text",
                        text=summary
                    )
                else:
                    return types.TextContent(
                        type="text",
                        text="📭 收件箱暂无未读邮件"
                    )
        except Exception as e:
            logger.error(f"检查收件箱失败: {e}")
            return types.TextContent(
                type="text",
                text=f"❌ 检查失败: {str(e)}"
            )

    async def _get_inbox_status(self):
        """获取收件箱状态（供资源读取）"""
        try:
            async with aioimaplib.IMAP4_SSL(IMAP_SERVER) as imap:
                await imap.login(IMAP_USER, IMAP_PASSWORD)
                await imap.select("INBOX")
                
                status, messages = await imap.search("UNSEEN")
                unread_count = len(messages[0].split()) if messages[0] else 0
                
                return f"未读邮件: {unread_count} 封\n服务状态: 运行中"
        except Exception as e:
            return f"状态获取失败: {str(e)}"

    async def auto_monitor(self):
        """自动监控循环（后台运行）"""
        while True:
            try:
                result = await self._check_inbox()
                if "新邮件" in result.text:
                    # 这里可以扩展：自动回复、自动分类等
                    logger.info("检测到新邮件，可触发自动处理")
            except Exception as e:
                logger.error(f"自动监控出错: {e}")
            await asyncio.sleep(MONITOR_INTERVAL)

    async def run(self):
        """启动服务器和自动监控"""
        import threading
        
        # 在后台线程启动自动监控
        monitor_thread = threading.Thread(
            target=lambda: asyncio.run(self.auto_monitor()),
            daemon=True
        )
        monitor_thread.start()
        
        # 启动 MCP 服务器
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="auto-email-agent",
                    server_version="1.0.0",
                    capabilities=self.server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )

if __name__ == "__main__":
    # 检查必要环境变量
    required_vars = ["IMAP_USER", "IMAP_PASSWORD", "SMTP_USER", "SMTP_PASSWORD"]
    missing = [var for var in required_vars if not os.getenv(var)]
    
    if missing:
        print(f"❌ 缺少环境变量: {', '.join(missing)}")
        print("请设置:")
        for var in missing:
            print(f'  $env:{var} = "你的值"')
        exit(1)
    
    agent = AutoEmailAgent()
    asyncio.run(agent.run())
