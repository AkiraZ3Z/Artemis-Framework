import os
import sys
import datetime
import requests
import json
import imaplib
import email
import re
import time
from email.header import decode_header
from typing import Dict, Optional, List
import ssl
from core.testcase_loader import get_loader

loader = get_loader()

class MailFetcher:
    """邮箱邮件获取器，专门用于提取验证码"""
    
    def __init__(self, email_address: str, auth_code: str):
        """
        初始化邮箱连接
        
        Args:
            email_address: 邮箱地址
            auth_code: 邮箱的授权码（不是登录密码）
        """
        self.email_address = email_address
        self.auth_code = auth_code
        self.imap_server = "imap.qq.com"
        self.imap_port = 993
        
    def connect_to_mailbox(self) -> Optional[imaplib.IMAP4_SSL]:
        """
        连接到QQ邮箱
        
        Returns:
            IMAP连接对象，失败返回None
        """
        try:
            # 创建SSL上下文
            context = ssl.create_default_context()
            
            # 连接到QQ邮箱IMAP服务器
            print(f"🔗 正在连接到 {self.imap_server}:{self.imap_port}...")
            mail = imaplib.IMAP4_SSL(
                self.imap_server, 
                self.imap_port,
                ssl_context=context
            )
            
            # 登录邮箱
            print(f"🔐 正在登录邮箱 {self.email_address}...")
            mail.login(self.email_address, self.auth_code)
            print("✅ 邮箱登录成功")
            
            return mail
            
        except imaplib.IMAP4.error as e:
            print(f"❌ IMAP登录失败: {e}")
            print("请检查：")
            print("1. 邮箱地址是否正确")
            print("2. 授权码是否正确（不是邮箱密码）")
            print("3. 是否已开启IMAP服务")
            return None
        except Exception as e:
            print(f"❌ 连接失败: {e}")
            return None
    
    def search_verification_email(self, mail: imaplib.IMAP4_SSL, 
                                sender_filter: str = "ReqRes", 
                                timeout_seconds: int = 120) -> Optional[str]:
        """
        搜索并提取验证码邮件
        
        Args:
            mail: IMAP连接对象
            sender_filter: 发件人过滤关键词
            timeout_seconds: 超时时间（秒）
            
        Returns:
            验证码字符串，未找到返回None
        """
        start_time = time.time()
        last_email_count = 0
        
        print(f"📧 正在搜索验证码邮件（最多等待{timeout_seconds}秒）...")
        
        while time.time() - start_time < timeout_seconds:
            try:
                # 选择收件箱
                mail.select("INBOX")
                
                # 搜索未读邮件（按时间倒序）
                status, messages = mail.search(None, 'UNSEEN')
                
                if status != 'OK':
                    print("⚠️ 搜索邮件失败")
                    time.sleep(5)
                    continue
                
                email_ids = messages[0].split()
                current_count = len(email_ids)
                
                # 如果有新邮件
                if current_count > last_email_count:
                    print(f"📨 发现 {current_count - last_email_count} 封新邮件")
                    last_email_count = current_count
                    
                    # 从最新的邮件开始检查
                    for email_id in reversed(email_ids[-10:]):  # 检查最新的10封
                        verification_code = self._extract_verification_from_email(mail, email_id, sender_filter)
                        if verification_code:
                            return verification_code
                
                # 等待5秒后再次检查
                time.sleep(10)
                
            except Exception as e:
                print(f"⚠️ 搜索过程中出错: {e}")
                time.sleep(10)
        
        print("⏰ 超时，未找到验证码邮件")
        return None
    
    def _extract_verification_from_email(self, mail: imaplib.IMAP4_SSL, 
                                        email_id: bytes, 
                                        sender_filter: str) -> Optional[str]:
        """
        从单封邮件中提取验证码
        
        Args:
            mail: IMAP连接对象
            email_id: 邮件ID
            sender_filter: 发件人过滤关键词
            
        Returns:
            验证码字符串
        """
        try:
            # 获取邮件内容
            status, msg_data = mail.fetch(email_id, '(RFC822)')
            
            if status != 'OK':
                return None
            
            # 解析邮件
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    # 解析邮件原始数据
                    msg = email.message_from_bytes(response_part[1])
                    
                    # 解码邮件主题
                    subject, encoding = decode_header(msg["Subject"])[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(encoding if encoding else 'utf-8')
                    
                    # 获取发件人
                    from_header = msg.get("From", "")
                
                    # 检查是否是目标邮件 (放宽了过滤条件，只要包含 ReqRes 或 verification 关键字)
                    is_target_email = (
                        sender_filter.lower() in from_header.lower() or 
                        "verification" in subject.lower() or
                        "code" in subject.lower()
                    )
                
                    if not is_target_email:
                        continue
                    
                    print(f"📩 找到目标邮件: {subject}")
                    print(f"  发件人: {from_header}")
                    
                    # 提取验证码
                    verification_code = self._find_verification_code_in_email(msg)
                    
                    if verification_code:
                        print(f"✅ 提取到验证码: {verification_code}")
                        
                        # 标记邮件为已读（可选）
                        mail.store(email_id, '+FLAGS', '\\Seen')
                        
                        return verification_code
                    
        except Exception as e:
            print(f"⚠️ 解析邮件时出错: {e}")
        
        return None
    
    def _find_verification_code_in_email(self, msg: email.message.Message) -> Optional[str]:
        """
        从邮件内容中查找验证码
        
        Args:
            msg: 邮件消息对象
            
        Returns:
            验证码字符串
        """
        verification_code = None
        
        # 如果是多部分邮件
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))
                
                # 跳过附件
                if "attachment" in content_disposition:
                    continue
                
                # 只处理文本内容
                if content_type in ["text/plain", "text/html"]:
                    try:
                        body = part.get_payload(decode=True).decode()
                    
                        # 调试：保存邮件内容到文件
                        debug_file = f"E:\MyProjects\API_AITest_Practice\ReqRes_notes\logs\email_debug.txt"
                        with open(debug_file, "w", encoding="utf-8") as f:
                            f.write(body)
                        print(f"💾 调试：邮件内容已保存到 {debug_file}")
                        
                        # 获取字符集并解码
                        charset = part.get_content_charset() or 'utf-8'
                        payload = part.get_payload(decode=True)
                        if payload:
                            body = payload.decode(charset, errors='ignore')
                            
                            # 调用提取方法
                            code = self._extract_code_from_text(body)
                            if code:
                                verification_code = code
                                break
                    except Exception as e:
                        # 忽略单个部分的解析错误，继续下一个
                        continue
        else:
            # 单部分邮件
            try:
                charset = msg.get_content_charset() or 'utf-8'
                body = msg.get_payload(decode=True).decode(charset, errors='ignore')
                verification_code = self._extract_code_from_text(body)
            except:
                pass
        
        return verification_code
    
    def _extract_code_from_text(self, text: str) -> Optional[str]:
        """
        针对特定邮件格式优化的验证码提取逻辑
        """
        # 1. 精确匹配：特定样式的p标签（与您提供的HTML完全一致）
        # 匹配: <p style="font-size:24px;font-weight:bold;letter-spacing:4px;background:#0f172a;color:#e5e7eb;padding:12px 16px;border-radius:8px;display:inline-block;">82257212</p>
        pattern_exact = r'<p\s+style="[^"]*?font-size:24px[^"]*?font-weight:bold[^"]*?letter-spacing:4px[^"]*?background:#0f172a[^"]*?color:#e5e7eb[^"]*?padding:12px\s+16px[^"]*?border-radius:8px[^"]*?display:inline-block[^"]*?"[^>]*?>\s*(\d{8})\s*</p>'
        match = re.search(pattern_exact, text, re.IGNORECASE)
        if match:
            return match.group(1)
        
        # 2. 放宽条件：匹配包含关键样式属性的p标签
        pattern_key_styles = r'<p\s+style="[^"]*?(font-size:24px|background:#0f172a)[^"]*?"[^>]*?>\s*(\d{8})\s*</p>'
        match = re.search(pattern_key_styles, text, re.IGNORECASE)
        if match and len(match.groups()) >= 2:
            return match.group(2)
        
        # 3. 进一步放宽：匹配任何包含验证码的p标签
        pattern_any_p = r'<p[^>]*?>\s*(\d{8})\s*</p>'
        match = re.search(pattern_any_p, text, re.IGNORECASE)
        if match:
            return match.group(1)
        
        # 4. 文本匹配：匹配 "Your verification code for Artemis-Framework is: 67469321"
        pattern_text = r'Your verification code for [Aa]rtemis-[Ff]ramework is:\s*(\d{8})'
        match = re.search(pattern_text, text, re.IGNORECASE)
        if match:
            return match.group(1)
        
        # 5. 其他HTML标签匹配
        tags_to_check = ['strong', 'div', 'span', 'h1', 'h2', 'h3', 'td']
        for tag in tags_to_check:
            pattern = f'<{tag}[^>]*?>\\s*(\\d{{8}})\\s*</{tag}>'
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        
        # 6. 匹配包含样式的任何标签
        pattern_styled = r'<[^>]*?style="[^"]*?(background|color|font)[^"]*?"[^>]*?>\s*(\d{8})\s*</[^>]*?>'
        matches = re.findall(pattern_styled, text, re.IGNORECASE)
        for match in matches:
            if len(match) >= 2 and match[1].isdigit() and len(match[1]) == 8:
                return match[1]
        
        # 7. 兜底：查找独立的8位数字
        matches = re.findall(r'\b(\d{8})\b', text)
        if matches:
            return matches[0]
        
        return None

    def get_verification_code(self, timeout_seconds: int = 120) -> Optional[str]:
        """
        主方法：获取验证码
        
        Args:
            timeout_seconds: 超时时间
            
        Returns:
            验证码字符串
        """
        mail = self.connect_to_mailbox()
        if not mail:
            return None
        
        try:
            verification_code = self.search_verification_email(mail, timeout_seconds=timeout_seconds)
            return verification_code
        finally:
            # 关闭连接
            try:
                mail.close()
                mail.logout()
                print("🔒 邮箱连接已关闭")
            except:
                pass