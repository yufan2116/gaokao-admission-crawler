"""
HTML 表格解析：省控线、一分一段等公告页内嵌 table。
"""

from __future__ import annotations

import io
import logging
import re
from pathlib import Path
from typing import Any

import pandas as pd
from bs4 import BeautifulSoup

from config import DEFAULT_PROVINCE
from normalizers.batch import normalize_batch
from normalizers.province import normalize_province
from normalizers.subject_type import normalize_subject_type
from parsers.parse_excel import (
    _clean_column_name,
    _coerce_numeric,
    _drop_empty,
    detect_header_row,
)
from parsers.subject_infer import _infer_subject_type_from_text

logger = logging.getLogger(__name__)

CONTROL_SUBJECT_ALIASES = ["科类", "科目", "选科", "科目类别"]
CONTROL_BATCH_ALIASES = [
    "批次",
    "录取批次",
    "类型",
    "普通类本科",
    "特殊类型招生控制线",
    "本科",
    "专科",
]
CONTROL_SCORE_ALIASES = ["分数线", "控制线", "分数", "录取控制分数线", "控制分数线"]

RANK_SCORE_ALIASES = ["分数", "成绩", "分值"]
RANK_COUNT_ALIASES = ["人数", "本段人数", "同分人数"]
RANK_CUMULATIVE_ALIASES = ["累计人数", "累计", "累计数"]

SUBJECT_MARKERS = ("历史", "物理", "文科", "理科", "综合改革")
RANK_SUBJECT_BLOCKS = (
    ("历史等科目类", "历史类"),
    ("历史类", "历史类"),
    ("物理等科目类", "物理类"),
    ("物理类", "物理类"),
)


def _read_html_content(path_or_html: str | Path) -> str:
    if isinstance(path_or_html, Path):
        path = path_or_html
    else:
        text = str(path_or_html)
        if len(text) < 260 and Path(text).exists():
            path = Path(text)
        else:
            return text

    for encoding in ("utf-8", "utf-8-sig", "gbk", "gb2312"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def _find_column_by_aliases(columns: list[str], aliases: list[str]) -> str | None:
    cleaned = {_clean_column_name(c).lower(): c for c in columns}
    for alias in aliases:
        key = _clean_column_name(alias).lower()
        if key in cleaned:
            return cleaned[key]
    for alias in aliases:
        for col in columns:
            if _clean_column_name(alias).lower() in _clean_column_name(col).lower():
                return col
    return None


def _numeric_cell(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    num = pd.to_numeric(re.sub(r"[^\d.\-]", "", str(value)), errors="coerce")
    if pd.isna(num):
        return None
    return float(num)


def _apply_detected_header(df: pd.DataFrame) -> pd.DataFrame:
    """read_html 常把表头当作数据行，需自动识别表头。"""
    work = _drop_empty(df)
    if work.empty:
        return work
    header_row = detect_header_row(work)
    header = [
        _clean_column_name(v) or f"col_{i}"
        for i, v in enumerate(work.iloc[header_row].tolist())
    ]
    body = work.iloc[header_row + 1 :].copy()
    body.columns = header[: body.shape[1]]
    return body.reset_index(drop=True)


def _apply_rank_header(df: pd.DataFrame) -> pd.DataFrame:
    """一分一段表：支持「科类行 + 分数/人数/累计行」双层表头。"""
    work = _drop_empty(df)
    if work.empty:
        return work

    header_row: int | None = None
    subject_row: int | None = None
    scan_limit = min(6, len(work))
    for idx in range(scan_limit):
        row_text = " ".join(str(v) for v in work.iloc[idx].tolist() if v is not None)
        if "分数" in row_text and ("人数" in row_text or "累计" in row_text):
            header_row = idx
            if idx > 0:
                prev_text = " ".join(str(v) for v in work.iloc[idx - 1].tolist() if v is not None)
                if any(m in prev_text for m in ("历史", "物理")):
                    subject_row = idx - 1
            break

    if header_row is None:
        return _apply_detected_header(work)

    subject_cells = (
        work.iloc[subject_row].tolist()
        if subject_row is not None
        else [None] * work.shape[1]
    )
    header_cells = work.iloc[header_row].tolist()
    current_subject = ""
    columns: list[str] = []
    for i, header_cell in enumerate(header_cells):
        sub_val = subject_cells[i] if i < len(subject_cells) else None
        sub_text = _clean_column_name(sub_val)
        if sub_text and any(m in sub_text for m in ("历史", "物理")):
            current_subject = sub_text
        header_text = _clean_column_name(header_cell)
        if current_subject and header_text:
            columns.append(f"{current_subject}_{header_text}")
        else:
            columns.append(header_text or f"col_{i}")

    body = work.iloc[header_row + 1 :].copy()
    body.columns = columns[: body.shape[1]]
    return body.reset_index(drop=True)


def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    if isinstance(work.columns, pd.MultiIndex):
        work.columns = [
            _clean_column_name("".join(str(part) for part in col if str(part) not in ("", "nan")))
            or f"col_{i}"
            for i, col in enumerate(work.columns)
        ]
    else:
        work.columns = [_clean_column_name(c) or f"col_{i}" for i, c in enumerate(work.columns)]
    return work


def _looks_like_matrix(df: pd.DataFrame) -> bool:
    if df.shape[1] < 2 or df.shape[0] < 2:
        return False
    first_col = df.iloc[:, 0].astype(str).str.cat(sep=" ")
    return any(m in first_col for m in SUBJECT_MARKERS)


def _unpivot_control_matrix(
    df: pd.DataFrame,
    default_year: int | None,
    default_province: str,
) -> pd.DataFrame:
    """将「科类 × 批次」矩阵表展开为行。"""
    work = _flatten_columns(df)
    subject_col = work.columns[0]
    batch_cols = list(work.columns[1:])
    rows: list[dict[str, Any]] = []

    for _, row in work.iterrows():
        subject_raw = str(row[subject_col]).strip()
        if not subject_raw or subject_raw in ("科类", "科目", "nan"):
            continue
        subject_type = normalize_subject_type(subject_raw)
        if not subject_type:
            subject_type = _infer_subject_type_from_text(subject_raw)
        if not subject_type:
            continue

        for batch_col in batch_cols:
            score_num = _numeric_cell(row[batch_col])
            if score_num is None:
                continue
            batch_name = normalize_batch(str(batch_col)) or str(batch_col).strip()
            rows.append(
                {
                    "year": default_year,
                    "province": default_province,
                    "subject_type": subject_type,
                    "batch": batch_name,
                    "score": score_num,
                }
            )

    return pd.DataFrame(rows)


def _map_control_long_table(
    df: pd.DataFrame,
    default_year: int | None,
    default_province: str,
) -> pd.DataFrame:
    """解析标准三列（科类/批次/分数线）长表。"""
    work = _flatten_columns(df)
    subject_col = _find_column_by_aliases(list(work.columns), CONTROL_SUBJECT_ALIASES)
    batch_col = _find_column_by_aliases(list(work.columns), CONTROL_BATCH_ALIASES)
    score_col = _find_column_by_aliases(list(work.columns), CONTROL_SCORE_ALIASES)

    if not score_col:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    for _, row in work.iterrows():
        score_num = _numeric_cell(row.get(score_col))
        if score_num is None:
            continue

        subject_type = None
        if subject_col and not pd.isna(row.get(subject_col)):
            subject_type = normalize_subject_type(str(row[subject_col]))
            if not subject_type:
                subject_type = _infer_subject_type_from_text(str(row[subject_col]))
        batch_name = None
        if batch_col and not pd.isna(row.get(batch_col)):
            batch_name = normalize_batch(str(row[batch_col])) or str(row[batch_col]).strip()

        if not subject_type and not batch_name:
            continue
        if not subject_type:
            subject_type = "综合改革"
        if not batch_name:
            batch_name = "普通类本科"

        rows.append(
            {
                "year": default_year,
                "province": default_province,
                "subject_type": subject_type,
                "batch": batch_name,
                "score": score_num,
            }
        )

    return pd.DataFrame(rows)


def _parse_single_control_table(
    table_html: str,
    default_year: int | None,
    default_province: str,
) -> pd.DataFrame:
    try:
        tables = pd.read_html(io.StringIO(table_html), header=None)
    except ValueError:
        return pd.DataFrame()
    if not tables:
        return pd.DataFrame()

    frames: list[pd.DataFrame] = []
    for raw in tables:
        raw = _apply_detected_header(raw)
        if raw.empty:
            continue
        if _looks_like_matrix(raw):
            parsed = _unpivot_control_matrix(raw, default_year, default_province)
        else:
            parsed = _map_control_long_table(raw, default_year, default_province)
        if not parsed.empty:
            frames.append(parsed)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _resolve_rank_subject(label: str, fallback: str | None = None) -> str | None:
    text = _clean_column_name(label)
    for marker, standard in RANK_SUBJECT_BLOCKS:
        if marker in text:
            return standard
    resolved = normalize_subject_type(text)
    if resolved:
        return resolved
    inferred = _infer_subject_type_from_text(text)
    if inferred:
        return inferred
    return fallback


def _find_rank_triplet(columns: list[str]) -> tuple[str | None, str | None, str | None]:
    score_col = _find_column_by_aliases(columns, RANK_SCORE_ALIASES)
    count_col = _find_column_by_aliases(columns, RANK_COUNT_ALIASES)
    cumulative_col = _find_column_by_aliases(columns, RANK_CUMULATIVE_ALIASES)
    return score_col, count_col, cumulative_col


def _extract_rank_rows(
    df: pd.DataFrame,
    score_col: str,
    count_col: str | None,
    cumulative_col: str | None,
    subject_type: str,
    default_year: int | None,
    default_province: str,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        score_num = _numeric_cell(row.get(score_col))
        if score_num is None:
            continue
        score_int = int(score_num)
        if score_int < 0 or score_int > 900:
            continue

        same_count = None
        cumulative = None
        if count_col:
            val = _numeric_cell(row.get(count_col))
            if val is not None:
                same_count = int(val)
        if cumulative_col:
            val = _numeric_cell(row.get(cumulative_col))
            if val is not None:
                cumulative = int(val)

        if same_count is None and cumulative is None:
            continue

        rows.append(
            {
                "year": default_year,
                "province": default_province,
                "subject_type": subject_type,
                "score": score_int,
                "same_score_count": same_count,
                "cumulative_count": cumulative,
            }
        )
    return pd.DataFrame(rows)


def _parse_rank_subject_long_table(
    df: pd.DataFrame,
    default_year: int | None,
    default_province: str,
    subject_type_hint: str | None,
) -> pd.DataFrame:
    """科类 | 分数 | 人数 | 累计人数 长表。"""
    work = _flatten_columns(df)
    subject_col = _find_column_by_aliases(list(work.columns), CONTROL_SUBJECT_ALIASES)
    score_col, count_col, cumulative_col = _find_rank_triplet(list(work.columns))
    if not score_col:
        return pd.DataFrame()

    frames: list[pd.DataFrame] = []
    if subject_col:
        for subject_raw, group in work.groupby(subject_col, dropna=True):
            subject_type = _resolve_rank_subject(str(subject_raw), subject_type_hint)
            if not subject_type:
                continue
            parsed = _extract_rank_rows(
                group,
                score_col,
                count_col,
                cumulative_col,
                subject_type,
                default_year,
                default_province,
            )
            if not parsed.empty:
                frames.append(parsed)
    else:
        subject_type = normalize_subject_type(subject_type_hint) if subject_type_hint else None
        if not subject_type:
            return pd.DataFrame()
        parsed = _extract_rank_rows(
            work,
            score_col,
            count_col,
            cumulative_col,
            subject_type,
            default_year,
            default_province,
        )
        if not parsed.empty:
            frames.append(parsed)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _parse_rank_dual_subject_table(
    df: pd.DataFrame,
    default_year: int | None,
    default_province: str,
) -> pd.DataFrame:
    """历史/物理双科类横向表（各含 分数/人数/累计人数）。"""
    work = _flatten_columns(df)
    columns = list(work.columns)
    col_text = " ".join(columns)

    blocks: list[tuple[str, list[str]]] = []
    for marker, standard in RANK_SUBJECT_BLOCKS:
        matched = [c for c in columns if marker in str(c)]
        if matched:
            blocks.append((standard, matched))

    if len(blocks) < 2:
        # 按列位置切分：常见 6 列 = 历史三列 + 物理三列
        if len(columns) >= 6:
            blocks = [
                ("历史类", columns[0:3]),
                ("物理类", columns[3:6]),
            ]
        else:
            return pd.DataFrame()

    frames: list[pd.DataFrame] = []
    for subject_type, block_cols in blocks:
        if len(block_cols) < 2:
            continue
        sub = work[block_cols].copy()
        sub.columns = [_clean_column_name(c) for c in sub.columns]
        score_col, count_col, cumulative_col = _find_rank_triplet(list(sub.columns))
        if not score_col:
            # 按位置：第 1 列分数、第 2 列人数、第 3 列累计
            if len(sub.columns) >= 3:
                score_col, count_col, cumulative_col = sub.columns[0], sub.columns[1], sub.columns[2]
            else:
                continue
        parsed = _extract_rank_rows(
            sub,
            score_col,
            count_col,
            cumulative_col,
            subject_type,
            default_year,
            default_province,
        )
        if not parsed.empty:
            frames.append(parsed)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _parse_single_rank_table(
    table_html: str,
    default_year: int | None,
    default_province: str,
    subject_type_hint: str | None,
) -> pd.DataFrame:
    try:
        tables = pd.read_html(io.StringIO(table_html), header=None)
    except ValueError:
        return pd.DataFrame()
    if not tables:
        return pd.DataFrame()

    frames: list[pd.DataFrame] = []
    for raw in tables:
        raw = _apply_rank_header(raw)
        if raw.empty:
            continue

        flat = _flatten_columns(raw)
        col_text = " ".join(str(c) for c in flat.columns)
        has_history = any(m in col_text for m in ("历史等科目", "历史类"))
        has_physics = any(m in col_text for m in ("物理等科目", "物理类"))

        if has_history and has_physics:
            parsed = _parse_rank_dual_subject_table(raw, default_year, default_province)
        else:
            subject_col = _find_column_by_aliases(list(flat.columns), CONTROL_SUBJECT_ALIASES)
            score_col, _, _ = _find_rank_triplet(list(flat.columns))
            if subject_col and score_col:
                parsed = _parse_rank_subject_long_table(
                    raw, default_year, default_province, subject_type_hint
                )
            elif score_col:
                parsed = _parse_rank_subject_long_table(
                    raw, default_year, default_province, subject_type_hint
                )
            else:
                parsed = pd.DataFrame()

        if not parsed.empty:
            frames.append(parsed)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _finalize_control_df(
    result: pd.DataFrame,
    default_year: int | None,
    default_province: str,
    subject_type_hint: str | None,
    source_name: str,
) -> pd.DataFrame:
    if "year" not in result.columns or result["year"].isna().all():
        result["year"] = default_year
    if "province" not in result.columns:
        result["province"] = default_province
    result["province"] = result["province"].apply(normalize_province)
    result["subject_type"] = result["subject_type"].apply(normalize_subject_type)
    result["batch"] = result["batch"].apply(normalize_batch)
    result["score"] = _coerce_numeric(result["score"])

    if subject_type_hint:
        hint = normalize_subject_type(subject_type_hint)
        mask = result["subject_type"].isna() | (result["subject_type"] == "")
        result.loc[mask, "subject_type"] = hint

    result["source_file"] = source_name
    return result


def _finalize_rank_df(
    result: pd.DataFrame,
    default_year: int | None,
    default_province: str,
    subject_type_hint: str | None,
    source_name: str,
) -> pd.DataFrame:
    if "year" not in result.columns or result["year"].isna().all():
        result["year"] = default_year
    if "province" not in result.columns:
        result["province"] = default_province
    result["province"] = result["province"].apply(normalize_province)
    result["subject_type"] = result["subject_type"].apply(normalize_subject_type)

    if subject_type_hint:
        hint = normalize_subject_type(subject_type_hint)
        mask = result["subject_type"].isna() | (result["subject_type"] == "")
        result.loc[mask, "subject_type"] = hint

    result["source_file"] = source_name
    return result


def parse_html_tables(
    path_or_html: str | Path,
    data_type: str = "control",
    default_year: int | None = None,
    default_province: str = DEFAULT_PROVINCE,
    subject_type_hint: str | None = None,
) -> pd.DataFrame:
    """
    解析本地 HTML 或 HTML 字符串中的 table。

    control 输出：year, province, subject_type, batch, score
    rank 输出：year, province, subject_type, score, same_score_count, cumulative_count
    """
    if data_type not in ("control", "rank"):
        raise ValueError(f"parse_html_tables 暂不支持 data_type={data_type}")

    html = _read_html_content(path_or_html)
    soup = BeautifulSoup(html, "lxml")
    tables = soup.find_all("table")
    if not tables:
        logger.debug("HTML 中未发现 table: %s", path_or_html)
        return pd.DataFrame()

    source_name = path_or_html.name if isinstance(path_or_html, Path) else "inline.html"
    frames: list[pd.DataFrame] = []

    for table in tables:
        if data_type == "control":
            df = _parse_single_control_table(str(table), default_year, default_province)
            if not df.empty:
                frames.append(df)
        else:
            df = _parse_single_rank_table(
                str(table), default_year, default_province, subject_type_hint
            )
            if not df.empty:
                frames.append(df)

    if not frames:
        return pd.DataFrame()

    result = pd.concat(frames, ignore_index=True)
    if data_type == "control":
        result = _finalize_control_df(
            result, default_year, default_province, subject_type_hint, source_name
        )
        logger.info("从 HTML 解析 control %d 行: %s", len(result), source_name)
    else:
        result = _finalize_rank_df(
            result, default_year, default_province, subject_type_hint, source_name
        )
        logger.info("从 HTML 解析 rank %d 行: %s", len(result), source_name)
    return result
