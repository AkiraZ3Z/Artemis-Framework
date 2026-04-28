"""
Artemis Framework - 邮箱验证码获取工具
基于 IMAP 协议，专门用于提取验证码邮件中的数字验证码
"""

import imaplib
import email
import re
import time
import ssl
import logging
from email.header import decode_header
from typing import Optional


class MailFetcher:
    """邮箱验证码提取器，支持 QQ邮箱 等 IMAP 服务"""

    def __init__(self, email_address: str, auth_code: str, imap_server: str = "imap.qq.com",
                 imap_port: int = 993, logger=None):
        self.email_address = email_address
        self.auth_code = auth_code
        self.imap_server = imap_server
        self.imap_port = imap_port
        self.logger = logger or logging.getLogger(__name__)

    def _log_info(self, msg):
        if hasattr(self.logger, 'info'):
            self.logger.info(msg)
        else:
            logging.info(msg)

    def _log_error(self, msg):
        if hasattr(self.logger, 'error'):
            self.logger.error(msg)
        else:
            logging.error(msg)

    def connect(self) -> Optional[imaplib.IMAP4_SSL]:
        """登录邮箱并返回 IMAP 连接"""
        try:
            context = ssl.create_default_context()
            self._log_info(f"连接到 {self.imap_server}:{self.imap_port}")
            mail = imaplib.IMAP4_SSL(self.imap_server, self.imap_port, ssl_context=context)
            mail.login(self.email_address, self.auth_code)
            self._log_info(f"邮箱登录成功: {self.email_address}")
            return mail
        except imaplib.IMAP4.error as e:
            self._log_error(f"IMAP 登录失败: {e}")
            return None
        except Exception as e:
            self._log_error(f"连接失败: {e}")
            return None

    def fetch_verification_code(self, sender_filter: str = "ReqRes",
                                timeout_seconds: int = 120) -> Optional[str]:
        """主流程：连接邮箱，等待并提取验证码"""
        mail = self.connect()
        if not mail:
            return None

        try:
            start = time.time()
            last_count = 0
            self._log_info(f"开始监听验证码邮件，超时时间: {timeout_seconds}s")
            while time.time() - start < timeout_seconds:
                mail.select("INBOX")
                status, messages = mail.search(None, 'UNSEEN')
                if status != 'OK':
                    time.sleep(5)
                    continue

                email_ids = messages[0].split()
                current_count = len(email_ids)
                if current_count > last_count:
                    self._log_info(f"发现 {current_count - last_count} 封新邮件")
                    last_count = current_count
                    # 检查最新的 10 封
                    for eid in reversed(email_ids[-10:]):
                        code = self._extract_code_from_email(mail, eid, sender_filter)
                        if code:
                            mail.store(eid, '+FLAGS', '\\Seen')
                            return code
                time.sleep(5)
            self._log_info("超时未找到验证码")
            return None
        finally:
            try:
                mail.close()
                mail.logout()
                self._log_info("邮箱连接已关闭")
            except:
                pass

    def _extract_code_from_email(self, mail, eid, sender_filter):
        try:
            status, data = mail.fetch(eid, '(RFC822)')
            if status != 'OK':
                return None
            for response_part in data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    subject = self._decode_header(msg["Subject"])
                    from_ = msg.get("From", "")
                    if (sender_filter.lower() in from_.lower() or
                        "verification" in subject.lower() or "code" in subject.lower()):
                        return self._find_code_in_message(msg)
        except Exception as e:
            self._log_error(f"解析邮件异常: {e}")
            return None

    def _decode_header(self, header_value):
        decoded = decode_header(header_value)
        subject = ""
        for text, encoding in decoded:
            if isinstance(text, bytes):
                subject += text.decode(encoding or 'utf-8', errors='ignore')
            else:
                subject += text
        return subject

    def _find_code_in_message(self, msg):
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() in ("text/plain", "text/html"):
                    charset = part.get_content_charset() or 'utf-8'
                    payload = part.get_payload(decode=True)
                    if payload:
                        body = payload.decode(charset, errors='ignore')
                        code = self._extract_code_from_text(body)
                        if code:
                            return code
        else:
            charset = msg.get_content_charset() or 'utf-8'
            body = msg.get_payload(decode=True).decode(charset, errors='ignore')
            return self._extract_code_from_text(body)
        return None

    def _extract_code_from_text(self, text: str) -> Optional[str]:
        """多规则提取 8 位验证码"""
        # 同之前你提供的精准匹配、模糊匹配、兜底逻辑，此处保留并稍作整理
        patterns = [
            r'<p\s+style="[^"]*?font-size:24px[^"]*?font-weight:bold[^"]*?letter-spacing:4px[^"]*?background:#0f172a[^"]*?color:#e5e7eb[^"]*?padding:12px\s+16px[^"]*?border-radius:8px[^"]*?display:inline-block[^"]*?"[^>]*?>\s*(\d{8})\s*</p>',
            r'<p\s+style="[^"]*?(font-size:24px|background:#0f172a)[^"]*?"[^>]*?>\s*(\d{8})\s*</p>',
            r'<p[^>]*?>\s*(\d{8})\s*</p>',
            r'Your verification code for [Aa]rtemis-[Ff]ramework is:\s*(\d{8})',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1) if len(match.groups()) == 1 else match.group(2)
        # 兜底：独立的8位数字
        matches = re.findall(r'\b(\d{8})\b', text)
        return matches[0] if matches else None