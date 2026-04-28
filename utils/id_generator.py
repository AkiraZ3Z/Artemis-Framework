"""
Artemis Framework 任务 id 生成器
用于生成全局唯一的 session_id，支持外部传入和自动生成
"""

import uuid
import threading


# 全局唯一的 session_id
_GLOBAL_SESSION_ID = None
_GLOBAL_SESSION_ID_LOCK = threading.Lock()

def get_global_session_id() -> str:
    """
    获取全局唯一的 session_id
    如果尚未生成，则创建一个新的
    """
    global _GLOBAL_SESSION_ID
    if _GLOBAL_SESSION_ID is None:
        with _GLOBAL_SESSION_ID_LOCK:
            if _GLOBAL_SESSION_ID is None:  # 双重检查锁定
                # 生成 12 个字符的 session_id，如：abc123def456
                _GLOBAL_SESSION_ID = f"{uuid.uuid4().hex[:12]}"

    return _GLOBAL_SESSION_ID

def set_global_session_id(session_id: str):
    """
    设置全局 session_id（用于从外部传入）
    """
    global _GLOBAL_SESSION_ID
    with _GLOBAL_SESSION_ID_LOCK:
        _GLOBAL_SESSION_ID = session_id

def reset_global_session_id():
    global _GLOBAL_SESSION_ID
    _GLOBAL_SESSION_ID = None