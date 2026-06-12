"""
机器可读 PDF 表格解析（Phase 13）。

流程：检测可提取文本 → pdfplumber → camelot → tabula → unsupported_pdf_table
不使用 OCR（无 PaddleOCR / Tesseract）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from config import DEFAULT_PROVINCE
from normalizers.batch import normalize_batch
from normalizers.province import normalize_province
from normalizers.school_batch import normalize_school_batch
from normalizers.school_name import normalize_school_name
from normalizers.subject_type import normalize_subject_type
from parsers.parse_excel import (
    DEFAULT_BATCH_BY_TYPE,
    HEADER_KEYWORDS,
    _clean_column_name,
    _coerce_numeric,
    _coerce_score,
    _drop_empty,
    _is_note_row,
    _rename_columns,
    detect_header_row,
)
from parsers.parse_html_tables import _finalize_control_df, _finalize_rank_df
from parsers.subject_infer import resolve_subject_type

logger = logging.getLogger(__name__)

PdfParseStatus = Literal["parsed", "unsupported_pdf_table", "no_extractable_text"]
SUPPORTED_DATA_TYPES = frozenset({"school", "control", "rank"})


@dataclass
class PdfTableParseResult:
    """PDF 表格解析结果。"""

    status: PdfParseStatus
    df: pd.DataFrame
    parser_used: str | None = None
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "parsed" and not self.df.empty


def has_extractable_text(file_path: str | Path, *, min_chars: int = 30) -> bool:
    """判断 PDF 是否含可提取文本（非纯扫描件）。"""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {path}")

    try:
        import pdfplumber
    except ImportError:
        logger.warning("pdfplumber 未安装，无法检测 PDF 文本")
        return False

    total = 0
    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages[:5]:
                text = page.extract_text() or ""
                total += len(text.strip())
                if total >= min_chars:
                    return True
    except Exception as exc:
        logger.debug("PDF 文本检测失败 [%s]: %s", path.name, exc)
        return False
    return total >= min_chars


def _table_cells_to_df(table: list[list[Any]]) -> pd.DataFrame:
    if not table:
        return pd.DataFrame()
    normalized = [
        [("" if c is None else str(c).strip()) for c in row]
        for row in table
        if any(c is not None and str(c).strip() for c in row)
    ]
    if not normalized:
        return pd.DataFrame()
    return pd.DataFrame(normalized)


def _raw_df_to_typed_df(
    raw: pd.DataFrame,
    data_type: str,
    *,
    default_year: int | None,
    default_province: str,
    subject_type_hint: str | None,
    subject_mode: object | None,
    source_name: str,
) -> pd.DataFrame:
    if raw.empty:
        return raw

    header_row = detect_header_row(raw)
    header = [
        _clean_column_name(v) or f"col_{i}"
        for i, v in enumerate(raw.iloc[header_row].tolist())
    ]
    df = raw.iloc[header_row + 1 :].copy()
    df.columns = header[: df.shape[1]]
    df = _drop_empty(df)
    if not df.empty:
        mask = df.apply(_is_note_row, axis=1)
        df = df[~mask].copy()
    if df.empty:
        return df

    df = _rename_columns(df, data_type=data_type)

    if "year" not in df.columns and default_year is not None:
        df["year"] = default_year
    if "province" not in df.columns:
        df["province"] = default_province

    resolved_subject = resolve_subject_type(
        subject_type_hint,
        Path(source_name),
        0,
        df,
        prefer_sheet=data_type == "rank",
        subject_mode=subject_mode,
    )
    if resolved_subject:
        df["subject_type"] = resolved_subject

    if data_type in DEFAULT_BATCH_BY_TYPE and "batch" not in df.columns:
        df["batch"] = DEFAULT_BATCH_BY_TYPE[data_type]

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

    score_cols = {"min_score", "score", "avg_score", "max_score"}
    numeric_cols = (
        "min_score", "avg_score", "max_score", "score", "min_rank",
        "plan_count", "same_score_count", "cumulative_count",
    )
    for col in numeric_cols:
        if col in df.columns:
            if col in score_cols:
                df[col] = _coerce_score(df[col])
            else:
                df[col] = _coerce_numeric(df[col])

    if data_type == "school":
        if "school_name" not in df.columns and "school_code" in df.columns:
            df["school_name"] = df["school_code"].astype(str)
        if "school_code" not in df.columns and "school_name" in df.columns:
            df["school_code"] = df["school_name"].astype(str)

    if data_type == "control":
        df = _finalize_control_df(
            df, default_year, default_province, subject_type_hint, source_name
        )
    elif data_type == "rank":
        df = _finalize_rank_df(
            df, default_year, default_province, subject_type_hint, source_name
        )
    else:
        df["source_file"] = source_name

    return df


def _score_parsed_df(df: pd.DataFrame, data_type: str) -> int:
    if df.empty:
        return 0
    score = min(len(df), 500)
    if data_type == "school":
        if "school_name" in df.columns or "school_code" in df.columns:
            score += 200
        if "min_score" in df.columns or "min_rank" in df.columns:
            score += 100
    elif data_type == "control":
        if "batch" in df.columns and "score" in df.columns:
            score += 200
    elif data_type == "rank":
        if "score" in df.columns:
            score += 150
        if "cumulative_count" in df.columns or "same_score_count" in df.columns:
            score += 50
    header_hits = sum(
        1 for kw in HEADER_KEYWORDS if kw in " ".join(str(c) for c in df.columns)
    )
    score += header_hits * 5
    return score


def _pick_best_from_tables(
    tables: list[list[list[Any]]],
    data_type: str,
    *,
    default_year: int | None,
    default_province: str,
    subject_type_hint: str | None,
    subject_mode: object | None,
    source_name: str,
) -> pd.DataFrame:
    best_df = pd.DataFrame()
    best_score = 0
    for table in tables:
        raw = _table_cells_to_df(table)
        if raw.empty or len(raw) < 2:
            continue
        parsed = _raw_df_to_typed_df(
            raw,
            data_type,
            default_year=default_year,
            default_province=default_province,
            subject_type_hint=subject_type_hint,
            subject_mode=subject_mode,
            source_name=source_name,
        )
        quality = _score_parsed_df(parsed, data_type)
        if quality > best_score:
            best_score = quality
            best_df = parsed
    return best_df


def _extract_tables_pdfplumber(path: Path) -> list[list[list[Any]]]:
    import pdfplumber

    tables: list[list[list[Any]]] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            page_tables = page.extract_tables() or []
            tables.extend(page_tables)
    return tables


def _extract_tables_camelot(path: Path) -> list[list[list[Any]]]:
    import camelot

    tables: list[list[list[Any]]] = []
    for flavor in ("lattice", "stream"):
        try:
            result = camelot.read_pdf(str(path), pages="all", flavor=flavor)
        except Exception as exc:
            logger.debug("camelot %s 失败 [%s]: %s", flavor, path.name, exc)
            continue
        for table in result:
            if table.df is not None and not table.df.empty:
                tables.append(table.df.values.tolist())
        if tables:
            break
    return tables


def _extract_tables_tabula(path: Path) -> list[list[list[Any]]]:
    import tabula

    tables: list[list[list[Any]]] = []
    for lattice in (True, False):
        try:
            dfs = tabula.read_pdf(
                str(path),
                pages="all",
                multiple_tables=True,
                lattice=lattice,
                pandas_options={"header": None},
            )
        except Exception as exc:
            logger.debug("tabula lattice=%s 失败 [%s]: %s", lattice, path.name, exc)
            continue
        if not dfs:
            continue
        for df in dfs:
            if df is not None and not df.empty:
                tables.append(df.values.tolist())
        if tables:
            break
    return tables


def _try_parser(
    name: str,
    extractor,
    path: Path,
    data_type: str,
    *,
    default_year: int | None,
    default_province: str,
    subject_type_hint: str | None,
    subject_mode: object | None,
) -> PdfTableParseResult | None:
    try:
        raw_tables = extractor(path)
    except ImportError:
        logger.debug("%s 未安装，跳过", name)
        return None
    except Exception as exc:
        logger.debug("%s 提取失败 [%s]: %s", name, path.name, exc)
        return None

    if not raw_tables:
        return None

    df = _pick_best_from_tables(
        raw_tables,
        data_type,
        default_year=default_year,
        default_province=default_province,
        subject_type_hint=subject_type_hint,
        subject_mode=subject_mode,
        source_name=path.name,
    )
    if df.empty or _score_parsed_df(df, data_type) < 50:
        return None

    logger.info(
        "PDF 表格解析成功 [%s] parser=%s data_type=%s rows=%d",
        path.name,
        name,
        data_type,
        len(df),
    )
    return PdfTableParseResult(
        status="parsed",
        df=df,
        parser_used=name,
        message=f"extracted by {name}",
    )


def parse_pdf_tables(
    file_path: str | Path,
    data_type: str = "school",
    *,
    default_year: int | None = None,
    default_province: str = DEFAULT_PROVINCE,
    subject_type_hint: str | None = None,
    subject_mode: object | None = None,
) -> PdfTableParseResult:
    """
    解析机器可读 PDF 表格。

    支持 data_type: school | control | rank
    失败时 status=unsupported_pdf_table 或 no_extractable_text。
    """
    if data_type not in SUPPORTED_DATA_TYPES:
        raise ValueError(f"parse_pdf_tables 不支持 data_type={data_type}")

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"非 PDF 文件: {path}")

    logger.info("解析 PDF 表格: %s (data_type=%s)", path, data_type)

    if not has_extractable_text(path):
        logger.info("PDF 无可提取文本（可能为扫描件）: %s", path.name)
        return PdfTableParseResult(
            status="no_extractable_text",
            df=pd.DataFrame(),
            message="PDF 无可提取文本，跳过 OCR",
        )

    parsers = (
        ("pdfplumber", _extract_tables_pdfplumber),
        ("camelot", _extract_tables_camelot),
        ("tabula", _extract_tables_tabula),
    )
    for name, extractor in parsers:
        result = _try_parser(
            name,
            extractor,
            path,
            data_type,
            default_year=default_year,
            default_province=default_province,
            subject_type_hint=subject_type_hint,
            subject_mode=subject_mode,
        )
        if result is not None:
            return result

    logger.warning("PDF 表格解析失败，全部后端均未提取有效表格: %s", path.name)
    return PdfTableParseResult(
        status="unsupported_pdf_table",
        df=pd.DataFrame(),
        message="pdfplumber / camelot / tabula 均未提取有效表格",
    )
