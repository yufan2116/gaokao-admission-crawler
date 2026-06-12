"""
录取批次标准化。
"""

BATCH_ALIASES: dict[str, str] = {
    "普通类本科": "普通类本科",
    "特殊类型招生控制线": "特殊类型招生控制线",
    "特殊类型控制线": "特殊类型招生控制线",
    "本科一批": "本科批",
    "本一": "本科批",
    "本二": "本科批",
    "本科二批": "本科批",
    "本科批": "本科批",
    "本科": "本科批",
    "专科批": "专科批",
    "高职专科": "专科批",
    "专科": "专科批",
    "提前批次": "提前批",
    "提前批": "提前批",
    "艺术本科": "艺术批",
    "体育本科": "体育批",
}


def normalize_batch(value: str | None) -> str:
    """统一批次名称。"""
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""

    for key, standard in BATCH_ALIASES.items():
        if key in text:
            return standard
    return text
