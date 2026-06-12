"""
招生类别标准化（school 专用）。

标准值：普通类 / 艺术类 / 体育类
"""

ADMISSION_CATEGORY_ALIASES: dict[str, str] = {
    "普通类": "普通类",
    "普通": "普通类",
    "艺术类": "艺术类",
    "艺术": "艺术类",
    "体育类": "体育类",
    "体育": "体育类",
}


def normalize_admission_category(value: str | None) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    for key, standard in ADMISSION_CATEGORY_ALIASES.items():
        if key in text:
            return standard
    return text
