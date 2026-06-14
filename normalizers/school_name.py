"""
院校名称标准化：去空格、统一括号、去除常见后缀冗余。
"""

import re

_INVALID_CATEGORY_TOKENS = frozenset(
    {
        "普通类",
        "少数民族预科班",
        "不限",
        "无",
        "历史类",
        "物理类",
        "综合改革",
    }
)


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


def looks_like_valid_school_name(value: str | None) -> bool:
    """校名是否像真实院校名称（非代号碎片、分数、类别等）。"""
    if value is None:
        return False
    text = str(value).strip()
    if not text:
        return False
    if len(text) <= 1:
        return False
    if re.fullmatch(r"\d+", text):
        return False
    if re.fullmatch(r"[\W_]+", text):
        return False
    if re.fullmatch(r"\d{3,4}", text):
        return False
    if text in _INVALID_CATEGORY_TOKENS:
        return False
    if not re.search(r"[\u4e00-\u9fff]", text):
        return False
    return True


def is_invalid_school_name(value: str | None) -> bool:
    """非空校名是否命中无效模式（用于 OCR 质量审计）。"""
    if value is None:
        return False
    text = str(value).strip()
    if not text:
        return False
    return not looks_like_valid_school_name(text)
