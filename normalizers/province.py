"""
省份名称标准化。
"""

# 常见简称 -> 标准全称
PROVINCE_ALIASES: dict[str, str] = {
    "江苏": "江苏",
    "江苏省": "江苏",
    "js": "江苏",
    "jiangsu": "江苏",
    "广东": "广东",
    "广东省": "广东",
    "gd": "广东",
    "guangdong": "广东",
}


def normalize_province(value: str | None) -> str:
    """
    将省份字段统一为短名称（如「江苏」）。

    空值返回空字符串。
    """
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    key = text.lower()
    if key in PROVINCE_ALIASES:
        return PROVINCE_ALIASES[key]
    # 去掉「省」「市」「自治区」等后缀
    for suffix in ("省", "市", "壮族自治区", "回族自治区", "维吾尔自治区", "自治区"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    return PROVINCE_ALIASES.get(text.lower(), text)
