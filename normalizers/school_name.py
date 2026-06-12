"""
院校名称标准化：去空格、统一括号、去除常见后缀冗余。
"""

import re


def normalize_school_name(value: str | None) -> str:
    """
    清洗院校名称。

    - 去除首尾空白
    - 全角括号转半角
    - 合并多余空格
    """
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""

    text = text.replace("（", "(").replace("）", ")")
    text = re.sub(r"\s+", "", text)

    # 去掉尾部常见冗余标记（保留主体校名）
    for suffix in ("(中外合作)", "(联合培养)", "(师范)"):
        if text.endswith(suffix):
            break  # 保留合作类型信息，仅做标记不删除

    return text
