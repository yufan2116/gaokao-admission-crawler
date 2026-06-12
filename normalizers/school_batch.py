"""
院校投档批次标准化（school 专用）。

标准值：本科批 / 专科批 / 本科提前批
"""

SCHOOL_BATCH_ALIASES: dict[str, str] = {
    "本科一批": "本科一批",
    "本科二批": "本科二批",
    "高职高专批": "高职高专批",
    "高职高专": "高职高专批",
    "普通类本科批次": "本科批",
    "本科批次平行志愿": "本科批",
    "本科批次": "本科批",
    "本科批": "本科批",
    "第一段": "本科批",
    "第1次志愿": "本科批",
    "普通类专科批次": "专科批",
    "专科批次平行志愿": "专科批",
    "专科批次": "专科批",
    "专科批": "专科批",
    "第二段": "专科批",
    "第2次志愿": "专科批",
    "第3次志愿": "专科批",
    "本科提前批次": "本科提前批",
    "本科提前批": "本科提前批",
    "提前批次": "本科提前批",
}


def normalize_school_batch(value: str | None) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    for key, standard in SCHOOL_BATCH_ALIASES.items():
        if key in text:
            return standard
    return text
