"""
Excel 解析：读取院校/专业录取线、一分一段表并标准化字段。

Phase 3：自动识别表头、清洗江苏真实 Excel 格式。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import pandas as pd

from config import CLEANED_DIR, DEFAULT_PROVINCE, EXCEL_COLUMN_ALIASES
from normalizers.batch import normalize_batch
from normalizers.school_batch import normalize_school_batch
from normalizers.province import normalize_province
from normalizers.school_name import normalize_school_name
from normalizers.subject_type import normalize_subject_type
from parsers.subject_infer import resolve_subject_type

logger = logging.getLogger(__name__)

# 表头行检测关键词
HEADER_KEYWORDS = (
    "院校",
    "院校代号",
    "院校名称",
    "专业组",
    "专业组代码",
    "专业代码",
    "专业名称",
    "投档最低分",
    "投档最低分同分考生排序项",
    "辅助排序分",
    "分数线",
    "位次",
    "名次号",
    "最低位次",
    "分数",
    "人数",
    "累计人数",
)

# 按 data_type 扩展列名别名（合并到全局映射）
DATA_TYPE_ALIASES: dict[str, dict[str, list[str]]] = {
    "school": {
        "school_code": ["院校代号", "院校代码", "学校代码", "学校代号", "代号"],
        "school_name": [
            "院校名称",
            "院校",
            "学校名称",
            "院校代号及名称",
            "院校、专业组名称及选科要求",
            "名称及选科要求",
        ],
        "major_code": ["专业代号", "专业代码"],
        "major_name": ["专业名称", "专业", "专业代号及名称"],
        "major_group": ["专业组代码", "院校专业组", "专业组", "院校、专业组"],
        "min_score": [
            "投档最低分",
            "最低投档分",
            "最低分",
            "投档分",
            "分数线",
            "投档分数线",
        ],
        "tie_breaker_text": [
            "投档最低分同分考生排序项",
            "同分排序",
            "辅助排序分",
            "同分考生排序项",
        ],
        "min_rank": ["位次", "最低位次", "投档最低排位", "投档最低位次", "排名", "名次号"],
        "plan_count": ["计划数", "招生计划", "招生人数", "投档计划数", "计划人数"],
    },
    "rank": {
        "score": ["分数", "成绩", "分值"],
        "same_score_count": ["人数", "本段人数", "同分人数"],
        "cumulative_count": ["累计人数", "累计", "累计数"],
    },
    "control": {
        "batch": ["批次", "录取批次"],
        "score": ["分数线", "控制线", "分数", "录取控制分数线"],
        "subject_type": ["科类", "科目类别", "选科"],
    },
    "major": {
        "school_code": ["院校代号", "院校代码", "学校代码"],
        "school_name": ["院校名称", "院校", "学校名称"],
        "major_name": ["专业名称", "专业"],
        "major_code": ["专业代号", "专业代码"],
        "major_group": ["专业组代码", "专业组"],
        "min_score": ["投档最低分", "最低分", "最低投档分"],
        "min_rank": ["位次", "最低位次"],
    },
}

# 非数据行标记
NOTE_ROW_MARKERS = ("说明", "备注", "注：", "注:", "合计", "总计", "单位：", "单位:")

DEFAULT_BATCH_BY_TYPE = {
    "school": "本科批",
    "major": "本科批",
}


def detect_header_row(df_raw: pd.DataFrame, max_scan_rows: int = 30) -> int:
    """
    从前 N 行中寻找包含关键字段最多的行作为表头。

    Returns:
        最可能的 header 行索引（0-based）
    """
    if df_raw.empty:
        return 0

    best_row = 0
    best_score = -1
    scan_limit = min(max_scan_rows, len(df_raw))

    for idx in range(scan_limit):
        row_text = " ".join(str(v) for v in df_raw.iloc[idx].tolist() if pd.notna(v))
        score = sum(1 for kw in HEADER_KEYWORDS if kw in row_text)
        if score > best_score:
            best_score = score
            best_row = idx

    return best_row


def _clean_column_name(name: Any) -> str:
    """清洗列名：去换行、多余空格、全角括号。"""
    if name is None or (isinstance(name, float) and pd.isna(name)):
        return ""
    text = str(name).replace("\n", "").replace("\r", "")
    text = text.replace("（", "(").replace("）", ")")
    text = re.sub(r"\s+", "", text)
    return text.strip()


def _get_aliases_for_type(data_type: str | None) -> dict[str, list[str]]:
    """合并全局与 data_type 专用列名映射。"""
    merged: dict[str, list[str]] = {k: list(v) for k, v in EXCEL_COLUMN_ALIASES.items()}
    if data_type and data_type in DATA_TYPE_ALIASES:
        for key, aliases in DATA_TYPE_ALIASES[data_type].items():
            existing = merged.get(key, [])
            merged[key] = list(dict.fromkeys(existing + aliases))
    return merged


def _find_column(df: pd.DataFrame, canonical_name: str, aliases_map: dict[str, list[str]]) -> str | None:
    """根据别名映射找到 DataFrame 中的实际列名。"""
    aliases = aliases_map.get(canonical_name, [])
    columns_clean = {_clean_column_name(c).lower(): c for c in df.columns}

    for alias in aliases:
        key = _clean_column_name(alias).lower()
        if key in columns_clean:
            return str(columns_clean[key])

    for alias in aliases:
        for col in df.columns:
            col_clean = _clean_column_name(col).lower()
            if _clean_column_name(alias).lower() in col_clean:
                return str(col)
    return None


def _rename_columns(df: pd.DataFrame, data_type: str | None = None) -> pd.DataFrame:
    """将原始列名映射为标准字段名。"""
    aliases_map = _get_aliases_for_type(data_type)
    rename_map: dict[str, str] = {}
    for canonical in aliases_map:
        actual = _find_column(df, canonical, aliases_map)
        if actual and actual not in rename_map:
            rename_map[actual] = canonical
    df = df.rename(columns=rename_map)
    if data_type == "school" and "min_score" not in df.columns and "score" in df.columns:
        df["min_score"] = df["score"]
    return df


def _parse_score_value(value: Any) -> float | None:
    """
    解析投档分/分数线单元格。

    艺术类等表格常见「606\\n(文化总分478，专业…)」，不可 strip 全部非数字字符。
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (int, float)) and not pd.isna(value):
        return float(value)

    text = str(value).strip()
    if not text:
        return None

    head = re.split(r"[\n(（]", text, maxsplit=1)[0].strip()
    match = re.search(r"[\d.]+", head)
    if match:
        try:
            return float(match.group())
        except ValueError:
            pass

    cleaned = re.sub(r"[^\d.\-]", "", text)
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _coerce_numeric(series: pd.Series) -> pd.Series:
    """将位次/人数等列转为数值（允许 strip 非数字）。"""
    return pd.to_numeric(
        series.astype(str).str.replace(r"[^\d.\-]", "", regex=True),
        errors="coerce",
    )


def _coerce_score(series: pd.Series) -> pd.Series:
    """将投档分/分数线列转为数值。"""
    return series.apply(_parse_score_value)


def _is_note_row(row: pd.Series) -> bool:
    """判断是否为说明/备注等非数据行。"""
    text = " ".join(str(v) for v in row.tolist() if pd.notna(v) and str(v).strip())
    if not text:
        return True
    return any(marker in text for marker in NOTE_ROW_MARKERS)


def _drop_empty(df: pd.DataFrame) -> pd.DataFrame:
    """去除全空行、全空列。"""
    df = df.dropna(how="all", axis=0)
    df = df.dropna(how="all", axis=1)
    return df


def _excel_engine(path: Path) -> str | None:
    if path.suffix.lower() == ".xls":
        return "xlrd"
    return "openpyxl"


def list_excel_sheet_names(path: Path) -> list[str]:
    """列出 Excel 全部 sheet 名。"""
    engine = _excel_engine(path)
    xl = pd.ExcelFile(path, engine=engine)
    return list(xl.sheet_names)


def _read_raw_sheet(path: Path, sheet_name: str | int) -> pd.DataFrame:
    return pd.read_excel(
        path,
        sheet_name=sheet_name,
        header=None,
        engine=_excel_engine(path),
    )


def parse_excel(
    file_path: str | Path,
    data_type: str | None = None,
    sheet_name: str | int = 0,
    default_year: int | None = None,
    default_province: str = DEFAULT_PROVINCE,
    subject_type_hint: str | None = None,
    prefer_sheet: bool = False,
    subject_mode: object | None = None,
) -> pd.DataFrame:
    """
    解析 Excel 文件，返回标准化后的 DataFrame。

    Args:
        file_path: Excel 路径
        data_type: school | rank | control | major
        sheet_name: 工作表名或索引
        default_year: 默认年份
        default_province: 默认省份
        subject_type_hint: 科类提示（如 历史类/物理类）

    Returns:
        列名已标准化的 DataFrame
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {path}")

    logger.info("解析 Excel: %s (data_type=%s)", path, data_type)

    df_raw = _read_raw_sheet(path, sheet_name)
    if df_raw.empty:
        logger.warning("Excel 为空: %s", path)
        return df_raw

    header_row = detect_header_row(df_raw)
    logger.info("识别表头行: 第 %d 行 (0-based)", header_row)

    # 用识别出的表头重建 DataFrame
    header = [_clean_column_name(c) for c in df_raw.iloc[header_row].tolist()]
    df = df_raw.iloc[header_row + 1 :].copy()
    df.columns = header
    df = _drop_empty(df)

    # 去除非数据行
    if not df.empty:
        mask = df.apply(_is_note_row, axis=1)
        df = df[~mask].copy()

    if df.empty:
        logger.warning("清洗后无数据行: %s", path)
        return df

    df = _rename_columns(df, data_type=data_type)

    # 默认年份/省份
    if "year" not in df.columns and default_year is not None:
        df["year"] = default_year
    if "province" not in df.columns:
        df["province"] = default_province

    # 科类推断
    use_sheet_priority = prefer_sheet or data_type == "rank"
    resolved_subject = resolve_subject_type(
        subject_type_hint,
        path,
        sheet_name,
        df,
        prefer_sheet=use_sheet_priority,
        subject_mode=subject_mode,
    )
    if resolved_subject:
        df["subject_type"] = resolved_subject

    # 默认批次
    if data_type in DEFAULT_BATCH_BY_TYPE and "batch" not in df.columns:
        df["batch"] = DEFAULT_BATCH_BY_TYPE[data_type]

    # 标准化字段
    if "province" in df.columns:
        df["province"] = df["province"].apply(normalize_province)
    if "subject_type" in df.columns:
        df["subject_type"] = df["subject_type"].apply(
            lambda x: normalize_subject_type(x, subject_mode=subject_mode)
        )
    if "batch" in df.columns:
        batch_norm = normalize_school_batch if data_type == "school" else normalize_batch
        df["batch"] = df["batch"].apply(batch_norm)
    if "school_name" in df.columns:
        df["school_name"] = df["school_name"].apply(normalize_school_name)

    # 数值列清洗
    numeric_cols = (
        "min_score", "avg_score", "max_score", "score", "min_rank",
        "plan_count", "same_score_count", "cumulative_count",
    )
    score_cols = {"min_score", "score", "avg_score", "max_score"}
    for col in numeric_cols:
        if col in df.columns:
            if col in score_cols:
                df[col] = _coerce_score(df[col])
            else:
                df[col] = _coerce_numeric(df[col])

    # school：仅有 school_code 无 school_name 时互补
    if data_type == "school":
        if "school_name" not in df.columns and "school_code" in df.columns:
            df["school_name"] = df["school_code"].astype(str)
        if "school_code" not in df.columns and "school_name" in df.columns:
            df["school_code"] = df["school_name"].astype(str)

    # tie_breaker_text 保留为字符串
    if "tie_breaker_text" in df.columns:
        df["tie_breaker_text"] = df["tie_breaker_text"].apply(
            lambda x: None if pd.isna(x) else str(x).strip()
        )

    df["source_file"] = path.name
    return df


def parse_excel_all_sheets(
    file_path: str | Path,
    data_type: str,
    default_year: int | None = None,
    default_province: str = DEFAULT_PROVINCE,
    subject_type_hint: str | None = None,
) -> pd.DataFrame:
    """解析 Excel 全部 sheet 并合并（用于 rank/control 多科类分 sheet）。"""
    path = Path(file_path)
    sheet_names = list_excel_sheet_names(path)
    if not sheet_names:
        return pd.DataFrame()

    prefer_sheet = data_type in ("rank", "control")
    frames: list[pd.DataFrame] = []
    for sheet_name in sheet_names:
        df = parse_excel(
            path,
            data_type=data_type,
            sheet_name=sheet_name,
            default_year=default_year,
            default_province=default_province,
            subject_type_hint=subject_type_hint,
            prefer_sheet=prefer_sheet,
        )
        if not df.empty:
            df["source_sheet"] = sheet_name
            frames.append(df)

    if not frames:
        return pd.DataFrame()
    merged = pd.concat(frames, ignore_index=True)
    logger.info("多 sheet 合并 [%s]: %d sheets → %d 行", path.name, len(frames), len(merged))
    return merged


def parse_excel_file(
    file_path: str | Path,
    sheet_name: str | int = 0,
    default_year: int | None = None,
    default_province: str = DEFAULT_PROVINCE,
    data_type: str | None = None,
    subject_type_hint: str | None = None,
    **kwargs: Any,
) -> pd.DataFrame:
    """兼容旧接口，转发到 parse_excel。"""
    return parse_excel(
        file_path,
        data_type=data_type or kwargs.get("record_type"),
        sheet_name=sheet_name,
        default_year=default_year,
        default_province=default_province,
        subject_type_hint=subject_type_hint,
    )


def parse_excel_to_records(
    file_path: str | Path,
    record_type: str = "school",
    **kwargs: Any,
) -> list[dict]:
    """解析 Excel 并转为字典列表。"""
    df = parse_excel(file_path, data_type=record_type, **kwargs)
    if df.empty:
        return []

    records: list[dict] = []
    for _, row in df.iterrows():
        cleaned = {k: (None if pd.isna(v) else v) for k, v in row.to_dict().items()}
        cleaned["_record_type"] = record_type
        records.append(cleaned)

    logger.info("从 %s 解析出 %d 条记录", file_path, len(records))
    return records


def save_cleaned_csv(
    df: pd.DataFrame,
    output_name: str,
    cleaned_dir: Path | None = None,
) -> Path:
    """将清洗后的 DataFrame 保存为 CSV。"""
    out_dir = cleaned_dir or CLEANED_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / output_name
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    logger.info("已保存清洗数据: %s", out_path)
    return out_path
