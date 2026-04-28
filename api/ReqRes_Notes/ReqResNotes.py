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

from api.ReqRes_Notes import MailFetcher


# 保存 response 数据到 JSON 文件中
def save_response_to_json(response, file_path, file_name):
    with open(file_path+file_name, "w", encoding="utf-8") as f:
        json.dump(
            {
                "exported_at": datetime.datetime.now().isoformat(),
                "response": response.json()
            },
            f,
            ensure_ascii=False,
            indent=4
        )
    print(f"✅ 响应数据已保存到 {file_path+file_name} 文件中")

def confirm_response(response, expected_status_code=200):
    if response.status_code == expected_status_code:
        print(f"✅ 响应状态码正确: {response.status_code}")
    else:
        print(f"❌ 响应状态码错误: {response.status_code}, 预期: {expected_status_code}")

class ReqResNotes:

    def __init__(self):
        self.base_url = "https://reqres.in/api"
        self.notes_url = "https://reqres.in/app/collections/notes/records"
        self.public_key = "pub_388381eee8017cdfc2d23858a635eff985d0f79fd26d5882bffbb47b30d22c3d"
        self.email = "kellyzxh@foxmail.com"
    
    def send_verify_email(self):
        url = f"{self.base_url}/app-users/login"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.public_key
        }
        body = {
            "email": self.email
        }

        response = requests.post(url, headers=headers, json=body)
        confirm_response(response)

        return response
    
    def get_verify_session(self, verify_token):
        url = f"{self.base_url}/app-users/verify"
        headers = {
            "Content-Type": "application/json"
        }
        body = {
            "token": verify_token
        }

        response = requests.post(url, headers=headers, json=body)
        confirm_response(response)
        
        data = response.json()
        session_token = data.get("data", {}).get("session_token")
        
        if session_token:
            print(f"✅ 成功获取 session_token: {session_token}, 长度: {len(session_token)}")
            print(f"⏰ 过期时间: {data.get('data', {}).get('expires_at', 'N/A')}")
            print(f"📧 用户邮箱: {data.get('data', {}).get('email', 'N/A')}")
            print(f"📝 使用说明: {data.get('data', {}).get('note', 'N/A')}")
        else:
            print("❌ 响应中未找到 session_token")
            print(f"完整响应: {json.dumps(data, indent=2, ensure_ascii=False)}")
    
        return session_token
    
    def get_all_notes(self, session_token):
        url = self.notes_url
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {session_token}"
        }
        
        response = requests.get(url, headers=headers)
        confirm_response(response)

        return response
    
    def create_note(self, session_token, title, content):
        url = self.notes_url
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {session_token}"
        }
        body = {
            "data": {  # 关键修正：添加外层data对象
                "title": title,
                "content": content
            }
        }

        response = requests.post(url, headers=headers, json=body)
        confirm_response(response, expected_status_code=201)

        return response
    
    def delete_note(self, session_token, note_id):
        url = f"{self.notes_url}/{note_id}"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {session_token}"
        }

        response = requests.delete(url, headers=headers)
        confirm_response(response, expected_status_code=204)
        print(f"✅ 该笔记已删除")

        return "Note deleted successfully"
    
if __name__ == "__main__":
    print("🚀 开始执行 ReqRes API 测试流程...")

    logpath = "E:/MyProjects/API_AITest_Practice/ReqRes_notes/logs/"

    print(" 1️⃣   发送验证邮件请求...")

    send_email_response = ReqResNotes().send_verify_email()
    save_response_to_json(send_email_response, logpath, "send_verify_email_response.json")

    try:
        print(" 2️⃣   获取验证码...")
        fetcher = MailFetcher(email_address="your_email@qq.com", auth_code="your_auth_code")
        verification_code = fetcher.get_verification_code(timeout_seconds=300)  # 增加超时时间到5分钟
        if not verification_code:
            raise Exception("未能获取到验证码，请检查邮箱设置和邮件内容")
        print(f"✅ 获取到的验证码: {verification_code}")

    except Exception as e:
        print(f"❌ 获取验证码时发生错误: {e}")
    
    else:
        try:
            print(" 3️⃣   使用验证码获取 session_token...")
            get_session_response = ReqResNotes().get_verify_session(verification_code)
            session_code = get_session_response
            if not session_code:
                raise Exception("未能获取到 session_token，请检查验证码是否正确以及API响应")
            print(f"✅ 获取到的 session_token: {session_code}")

            session_code_path = "E:\\MyProjects\\API_AITest_Practice\\ReqRes_notes\\logs\\session_token.txt"
            with open(session_code_path, "w", encoding="utf-8") as f:
                f.write(session_code)
            
            print(f"✅ session_token 已保存到 {session_code_path} 文件中")
        
        except Exception as e:
            print(f"❌ 获取 session_token 时发生错误: {e}")

        else:
            print(" 4️⃣   获取所有笔记...")
            get_notes_response = ReqResNotes().get_all_notes(session_code)
            save_response_to_json(get_notes_response, logpath, "get_all_notes_response.json")

            print(" 5️⃣   创建新笔记...")
            create_note_response = ReqResNotes().create_note(session_code, "测试笔记", "这是通过API创建的测试笔记。")
            
            node_id = create_note_response.json().get("data", {}).get("id")
            print(f"✅ 创建的笔记ID: {node_id}")
            save_response_to_json(create_note_response, logpath, "create_note_response.json")

            print("再次获取所有笔记...")
            get_notes_response = ReqResNotes().get_all_notes(session_code)
            save_response_to_json(get_notes_response, logpath, "get_all_notes2_response.json")

            print(" 6️⃣   删除笔记...")
            delete_note_response = ReqResNotes().delete_note(session_code, node_id)
            print(f"❌ 删除笔记响应: {delete_note_response}")

            print("最后获取所有笔记...")
            get_notes_response = ReqResNotes().get_all_notes(session_code)
            save_response_to_json(get_notes_response, logpath, "get_all_notes3_response.json")
            
            print(" 7️⃣   测试流程完成。")

    finally:
        print("🔚 测试结束。")