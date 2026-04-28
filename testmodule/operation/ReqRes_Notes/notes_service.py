"""
ReqRes Notes 业务服务
基于 BaseHTTPClient，封装笔记应用的所有 API 操作。
可配合 Artemis 日志系统（注入 CaseLogger）或独立运行。
"""

from typing import Optional, Dict, Any
from testmodule.api_test.base_client import BaseHTTPClient


class NotesService:
    def __init__(self, base_url: str = "https://reqres.in/api",
                 public_key: str = "pub_388381eee8017cdfc2d23858a635eff985d0f79fd26d5882bffbb47b30d22c3d",
                 logger=None):
        """
        :param base_url: 基础 API 地址
        :param public_key: 公共 API Key
        :param logger: 日志器，将传递给 HTTP 客户端（如 CaseLogger）
        """
        self.base_url = base_url
        self.public_key = public_key
        self.client = BaseHTTPClient(base_url=base_url, logger=logger)
        self.email: Optional[str] = None
        self.session_token: Optional[str] = None

    def set_email(self, email: str):
        self.email = email

    # ----------------- 认证相关 -----------------
    def send_verify_email(self, email: str = None) -> Dict[str, Any]:
        """发送验证邮件"""
        target_email = email or self.email
        if not target_email:
            raise ValueError("邮箱地址不能为空")
        body = {"email": target_email}
        headers = {"x-api-key": self.public_key}
        resp = self.client.post("/app-users/login", json_data=body, headers=headers)
        return {"status_code": resp.status_code, "data": resp.json()}

    def get_verify_session(self, token: str) -> Optional[str]:
        """使用验证码获取 session_token"""
        body = {"token": token}
        resp = self.client.post("/app-users/verify", json_data=body)
        data = resp.json()
        self.session_token = data.get("data", {}).get("session_token")
        return self.session_token

    # ----------------- 笔记 CRUD -----------------
    def _auth_headers(self) -> Dict[str, str]:
        if not self.session_token:
            raise RuntimeError("尚未获取 session_token，请先登录")
        return {"Authorization": f"Bearer {self.session_token}"}

    def get_all_notes(self) -> Dict[str, Any]:
        headers = self._auth_headers()
        resp = self.client.get("/app/collections/notes/records", headers=headers)
        return {"status_code": resp.status_code, "data": resp.json()}

    def create_note(self, title: str, content: str) -> Dict[str, Any]:
        headers = self._auth_headers()
        body = {"data": {"title": title, "content": content}}
        resp = self.client.post("/app/collections/notes/records", json_data=body, headers=headers)
        return {"status_code": resp.status_code, "data": resp.json()}

    def delete_note(self, note_id: str) -> str:
        headers = self._auth_headers()
        self.client.delete(f"/app/collections/notes/records/{note_id}", headers=headers)
        return "Note deleted successfully"

    def close(self):
        self.client.close()