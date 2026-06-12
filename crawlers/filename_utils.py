"""
文件名清洗工具：将中文标题转为 Windows 安全文件名。
"""

from __future__ import annotations

import re
import unicodedata

# Windows 非法字符
_WINDOWS_INVALID = re.compile(r'[\\/:*?"<>|]')
_MULTI_SPACE = re.compile(r"\s+")
_DEFAULT_MAX_LEN = 120


def sanitize_filename(title: str, ext: str = "", max_len: int = _DEFAULT_MAX_LEN) -> str:
    """
    将标题转为安全文件名。

    - 去除 Windows 非法字符
    - 合并空白为下划线
    - 限制长度
    - 自动补全扩展名（以 . 开头）
    """
    text = unicodedata.normalize("NFKC", title or "untitled").strip()
    text = _WINDOWS_INVALID.sub("", text)
    text = _MULTI_SPACE.sub("_", text)
    text = text.strip("._ ")

    if not text:
        text = "untitled"

    if len(text) > max_len:
        text = text[:max_len].rstrip("._ ")

    if ext and not ext.startswith("."):
        ext = f".{ext}"

    if ext and not text.lower().endswith(ext.lower()):
        # 预留扩展名长度
        base_max = max_len - len(ext)
        if len(text) > base_max:
            text = text[:base_max].rstrip("._ ")
        text = f"{text}{ext}"

    return text
