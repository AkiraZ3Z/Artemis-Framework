"""
Artemis Framework - JSON 路径解析器
支持点号分隔和方括号索引的路径提取
"""

import re
from typing import Any, List, Union


def resolve_path(data: Any, path: str, default: Any = None) -> Any:
    """
    根据路径字符串从嵌套结构中提取值。

    支持的路径格式:
        "response.data.users[0].name"   # 字典 + 数组索引
        "response.data['key-with-dot']" # 用引号包裹的特殊键
        "items[1]"                      # 数组直接索引

    :param data: 根数据 (dict, list, 或对象)
    :param path: 路径字符串
    :param default: 提取失败时的默认值
    :return: 提取到的值
    """
    if not path or data is None:
        return data if path == "" else default

    # 分词：支持 '.' 和 '[]' 分隔
    tokens = _tokenize(path)
    current = data
    for token in tokens:
        if current is None:
            return default
        current = _get_value(current, token, default)
    return current


def _tokenize(path: str) -> List[str]:
    """将路径字符串分割为路径段列表"""
    tokens = []
    i = 0
    n = len(path)
    while i < n:
        # 跳过点号
        if path[i] == '.':
            i += 1
            continue

        if path[i] == '[':
            # 找到匹配的 ']'
            j = path.index(']', i)
            token = path[i+1:j].strip()
            # 处理带引号的键 ['key']
            if (token.startswith("'") and token.endswith("'")) or \
               (token.startswith('"') and token.endswith('"')):
                token = token[1:-1]
            # 如果是数字，也保留为字符串，后面会尝试转为int
            tokens.append(token)
            i = j + 1
        else:
            # 普通键名，直到遇到 '.' 或 '[' 
            j = i
            while j < n and path[j] not in ('.', '['):
                j += 1
            token = path[i:j]
            tokens.append(token)
            i = j
    return tokens


def _get_value(obj: Any, key: str, default: Any = None) -> Any:
    """从对象中取出单个键的值，自动处理 list 索引和 dict 访问"""
    # 尝试作为列表索引
    if isinstance(obj, list):
        try:
            idx = int(key)
            if 0 <= idx < len(obj):
                return obj[idx]
            return default
        except ValueError:
            return default

    # 尝试作为字典键
    if isinstance(obj, dict):
        return obj.get(key, default)

    # 尝试作为对象属性访问
    if hasattr(obj, key):
        return getattr(obj, key, default)

    return default