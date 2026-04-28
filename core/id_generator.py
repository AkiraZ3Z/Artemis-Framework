"""
Artemis Framework 任务 session id 生成器
线程安全的全局唯一 session_id，支持外部传入和自动生成
"""

import uuid
import threading
from typing import Optional

# 全局唯一的 session_id
_GLOBAL_SESSION_ID: Optional[str] = None
_lock = threading.Lock()


def get_global_session_id() -> str:
    """获取全局唯一的 session_id（12位十六进制），如果不存在则自动生成"""
    global _GLOBAL_SESSION_ID
    if _GLOBAL_SESSION_ID is None:
        with _lock:
            if _GLOBAL_SESSION_ID is None:
                _GLOBAL_SESSION_ID = uuid.uuid4().hex[:12]
    return _GLOBAL_SESSION_ID


def set_global_session_id(session_id: str) -> None:
    """从外部手动设置全局 session_id"""
    global _GLOBAL_SESSION_ID
    with _lock:
        _GLOBAL_SESSION_ID = session_id


def reset_global_session_id() -> None:
    """重置全局 session_id，主要用于测试"""
    global _GLOBAL_SESSION_ID
    with _lock:
        _GLOBAL_SESSION_ID = None