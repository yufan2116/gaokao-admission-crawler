"""
图片表格 OCR 解析（Phase 20，实验功能）。

默认关闭；优先 PaddleOCR，未安装时返回 ocr_not_installed。
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from config import CLEANED_DIR
from normalizers.school_name import normalize_school_name
from normalizers.subject_type import normalize_subject_type
from parsers.ocr_engine import (
    normalize_ocr_engine,
    normalize_ocr_engine_mode,
    ocr_engine_available,
    run_ocr_inference,
)
from parsers.subject_infer import infer_subject_from_sheet_context

logger = logging.getLogger(__name__)

OCR_SOURCE_PREFIX = "ocr_experimental:"
OCR_RAW_DIR = CLEANED_DIR / "ocr_raw"
OCR_PREVIEW_DIR = CLEANED_DIR / "ocr_preview"
OCR_TMP_DIR = CLEANED_DIR / "ocr_tmp"
OCR_MAX_SIDE_PX = 1400

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}

HUBEI_HEADER_MARKERS = (
    "院校专业组代号",
    "院校专业组名称",
    "类别",
    "投档线",
    "备注",
)

HUBEI_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "school_code": ("院校专业组代号", "院校代号", "代号"),
    "major_group_name": ("院校专业组名称", "院校专业组"),
    "subject_type": ("类别",),
    "min_score": ("投档线", "最低分"),
    "notes": ("备注",),
}

# parse_image_table 湖北 school 输出列（与 SCHOOL_COLUMNS 对齐，notes 供审计）
HUBEI_SCHOOL_OUTPUT_COLUMNS = (
    "year",
    "province",
    "school_code",
    "school_name",
    "major_group",
    "subject_type",
    "batch",
    "min_score",
    "admission_category",
    "notes",
)


@dataclass
class ImageTableParseResult:
    status: str
    parser_used: str | None = None
    df: pd.DataFrame = field(default_factory=pd.DataFrame)
    raw_ocr_json_path: str | None = None
    message: str = ""
    hybrid: dict[str, Any] | None = None


def is_image_table_file(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTENSIONS


def ocr_source_url(path: Path) -> str:
    return f"{OCR_SOURCE_PREFIX}{path.resolve()}"


def is_ocr_experimental_source(source_url: str | None) -> bool:
    return bool(source_url and str(source_url).startswith(OCR_SOURCE_PREFIX))


logger = logging.getLogger(__name__)


def paddleocr_available() -> bool:
    from parsers.ocr_engine import paddleocr_available as _paddle

    return _paddle()


def _ocr_parser_label(engine: str) -> str:
    return "rapidocr" if normalize_ocr_engine(engine) == "rapidocr" else "paddleocr"


def _configure_paddle_runtime() -> None:
    """已迁移至 parsers.ocr_engine；保留别名避免外部引用断裂。"""
    from parsers.ocr_engine import _configure_paddle_runtime as _cfg

    _cfg()


def _get_paddle_ocr_engine() -> Any:
    """已迁移至 parsers.ocr_engine.get_ocr_engine；保留别名。"""
    from parsers.ocr_engine import get_ocr_engine

    return get_ocr_engine()


def _box_centers(box: Any) -> tuple[float, float]:
    if box is None:
        return 0.0, 0.0
    if hasattr(box, "tolist"):
        box = box.tolist()
    if isinstance(box, (list, tuple)) and len(box) == 4 and all(
        isinstance(v, (int, float)) for v in box
    ):
        x_center = (float(box[0]) + float(box[2])) / 2
        y_center = (float(box[1]) + float(box[3])) / 2
        return x_center, y_center
    xs: list[float] = []
    ys: list[float] = []
    for point in box:
        if isinstance(point, (list, tuple)) and len(point) >= 2:
            xs.append(float(point[0]))
            ys.append(float(point[1]))
    if not xs:
        return 0.0, 0.0
    return sum(xs) / len(xs), sum(ys) / len(ys)


def _ocr_item(text: str, box: Any, score: float | None) -> dict[str, Any]:
    x_center, y_center = _box_centers(box)
    return {
        "text": text,
        "score": score,
        "box": box,
        "x_center": x_center,
        "y_center": y_center,
    }


def _items_from_legacy_result(raw: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not raw:
        return items
    for block in raw:
        if not block:
            continue
        for line in block:
            if not line or len(line) < 2:
                continue
            box, text_info = line[0], line[1]
            text = (text_info[0] or "").strip()
            score = float(text_info[1]) if len(text_info) > 1 else None
            if text:
                items.append(_ocr_item(text, box, score))
    return items


def _items_from_modern_page(page: Any) -> list[dict[str, Any]]:
    if hasattr(page, "get"):
        data = page
    elif isinstance(page, dict):
        data = page
    else:
        return []
    texts = data.get("rec_texts") or data.get("rec_text") or []
    scores = data.get("rec_scores") or data.get("rec_score") or []
    polys = data.get("rec_polys") or data.get("dt_polys") or data.get("rec_boxes") or []
    items: list[dict[str, Any]] = []
    for idx, text in enumerate(texts):
        text = (text or "").strip()
        if not text:
            continue
        box = polys[idx] if idx < len(polys) else None
        score = float(scores[idx]) if idx < len(scores) else None
        items.append(_ocr_item(text, box, score))
    return items


def _normalize_paddle_output(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, list):
        if not raw:
            return []
        first = raw[0]
        if isinstance(first, list):
            return _items_from_legacy_result(raw)
        return _items_from_modern_page(first)
    return _items_from_modern_page(raw)


def _prepare_image_for_ocr(image_path: Path) -> Path:
    """过大图片在 Windows CPU 上易触发 Paddle 原生崩溃，先等比缩小。"""
    try:
        from PIL import Image
    except ImportError:
        return image_path
    try:
        with Image.open(image_path) as im:
            width, height = im.size
            longest = max(width, height)
            if longest <= OCR_MAX_SIDE_PX:
                return image_path
            scale = OCR_MAX_SIDE_PX / longest
            new_size = (int(width * scale), int(height * scale))
            OCR_TMP_DIR.mkdir(parents=True, exist_ok=True)
            out_path = OCR_TMP_DIR / f"{image_path.stem}_ocr.jpg"
            im.convert("RGB").resize(new_size, Image.Resampling.LANCZOS).save(
                out_path, format="JPEG", quality=92
            )
            logger.info(
                "OCR 输入缩放 [%s]: %dx%d -> %dx%d",
                image_path.name,
                width,
                height,
                new_size[0],
                new_size[1],
            )
            return out_path
    except OSError as exc:
        logger.warning("OCR 图片预处理失败 [%s]: %s", image_path.name, exc)
        return image_path


def _run_paddle_ocr(
    image_path: Path,
    *,
    use_ocr_cache: bool = True,
    ocr_engine: str = "paddle",
) -> list[dict[str, Any]]:
    prepared = _prepare_image_for_ocr(image_path)
    result = run_ocr_inference(
        image_path, prepared, use_cache=use_ocr_cache, engine=ocr_engine
    )
    return result.items


def _cluster_rows(
    boxes: list[dict[str, Any]],
    *,
    y_tolerance: float = 18.0,
) -> list[list[dict[str, Any]]]:
    if not boxes:
        return []
    sorted_boxes = sorted(boxes, key=lambda b: (b["y_center"], b["x_center"]))
    rows: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    row_y: float | None = None
    for box in sorted_boxes:
        if row_y is None or abs(box["y_center"] - row_y) <= y_tolerance:
            current.append(box)
            if row_y is None:
                row_y = box["y_center"]
            else:
                row_y = (row_y * (len(current) - 1) + box["y_center"]) / len(current)
        else:
            rows.append(sorted(current, key=lambda b: b["x_center"]))
            current = [box]
            row_y = box["y_center"]
    if current:
        rows.append(sorted(current, key=lambda b: b["x_center"]))
    return rows


def _row_text(row: list[dict[str, Any]]) -> str:
    return " ".join(cell["text"] for cell in row)


def _detect_header_row_index(rows: list[list[dict[str, Any]]]) -> int | None:
    for idx, row in enumerate(rows[:12]):
        text = _row_text(row)
        if "湖北省" in text and "投档" in text:
            continue
        if sum(1 for marker in HUBEI_HEADER_MARKERS if marker in text) >= 2:
            return idx
        if "院校" in text and ("投档" in text or "代号" in text):
            return idx
    return None


HUBEI_DATA_ROW_RE = re.compile(
    r"^(?P<code>[A-Z]\d{3,})\s+"
    r"(?P<name>.+?)\s+"
    r"(?P<requirement>[\u4e00-\u9fff]{1,4})\s+"
    r"(?P<min_score>\d{3,})"
    r"(?P<rest>.*)$"
)


def _parse_hubei_row_text(text_line: str) -> dict[str, Any] | None:
    text = text_line.strip()
    if not text:
        return None
    match = HUBEI_DATA_ROW_RE.match(text)
    if not match:
        return None
    try:
        score = float(match.group("min_score"))
    except ValueError:
        return None
    if score < 100:
        return None
    name = match.group("name").strip()
    school_name, major_group = _split_major_group_name(name)
    rest = (match.group("rest") or "").strip()
    notes_parts: list[str] = []
    requirement = (match.group("requirement") or "").strip()
    if requirement and requirement not in ("不限", "无"):
        notes_parts.append(f"再选:{requirement}")
    note_match = re.search(r"([\u4e00-\u9fff][\u4e00-\u9fff\w（）()·]{1,30})$", rest)
    if note_match:
        candidate = note_match.group(1)
        if not re.fullmatch(r"\d+", candidate):
            notes_parts.append(candidate)
    return {
        "school_code": match.group("code"),
        "school_name": school_name or name,
        "major_group": major_group or None,
        "min_score": score,
        "notes": "；".join(notes_parts) if notes_parts else None,
    }


def _rows_to_hubei_dataframe(
    rows: list[list[dict[str, Any]]],
    *,
    year: int,
    province: str,
    subject_type: str | None,
    batch: str,
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for row in rows:
        text_line = _row_text(row)
        if not text_line.strip():
            continue
        if any(
            marker in text_line
            for marker in ("说明", "备注：", "合计", "单位：", "平行志愿投档线", "末位投档")
        ):
            continue
        if "院校专业" in text_line and ("代号" in text_line or "名称" in text_line):
            continue
        parsed = _parse_hubei_row_text(text_line)
        if not parsed:
            continue
        records.append(
            {
                "year": year,
                "province": province,
                "school_code": parsed["school_code"],
                "school_name": normalize_school_name(parsed["school_name"]),
                "major_group": parsed.get("major_group"),
                "subject_type": normalize_subject_type(subject_type) if subject_type else subject_type,
                "batch": batch,
                "min_score": parsed["min_score"],
                "admission_category": "普通类",
                "notes": parsed.get("notes"),
            }
        )
    return pd.DataFrame(records)


def _assign_columns(header_row: list[dict[str, Any]], data_row: list[dict[str, Any]]) -> dict[str, str]:
    """按表头 x 中心对齐数据单元格。"""
    headers = [(cell["text"].strip(), cell["x_center"]) for cell in header_row]
    values: dict[str, str] = {}
    for cell in data_row:
        if not headers:
            break
        nearest = min(headers, key=lambda h: abs(h[1] - cell["x_center"]))
        header_text = nearest[0]
        for canonical, aliases in HUBEI_COLUMN_ALIASES.items():
            if any(alias in header_text for alias in aliases):
                values[canonical] = cell["text"].strip()
                break
    return values


def _split_major_group_name(name: str) -> tuple[str, str]:
    text = (name or "").strip()
    if not text:
        return "", ""
    match = re.match(r"^(.+?)(第\d+组)$", text)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    match = re.match(r"^(.+?)([A-Za-z]?\d+组)$", text)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return text, ""


def _parse_min_score(value: str) -> float | None:
    if not value:
        return None
    match = re.search(r"[\d.]+", str(value))
    if not match:
        return None
    try:
        return float(match.group())
    except ValueError:
        return None


def _infer_subject_from_context(
    *,
    subject_type: str | None,
    filename: str,
    page_title: str | None,
    ocr_text: str,
    subject_mode: Any = None,
) -> str | None:
    if subject_type and str(subject_type).strip():
        return normalize_subject_type(subject_type, subject_mode=subject_mode)
    for text in (filename, page_title or "", ocr_text):
        inferred = infer_subject_from_sheet_context(
            header_rows_text=text,
            subject_mode=subject_mode,
        )
        if inferred:
            return inferred
    return None


def _infer_batch_from_context(
    *,
    batch: str | None,
    filename: str,
    page_title: str | None,
    ocr_text: str,
) -> str:
    if batch and str(batch).strip():
        return str(batch).strip()
    blob = " ".join(t for t in (filename, page_title or "", ocr_text) if t)
    if "高职高专" in blob or ("专科" in blob and "本科" not in blob):
        return "专科批"
    if "本科" in blob:
        return "本科批"
    return "本科批"


def _json_safe(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def _save_ocr_audit(image_path: Path, ocr_items: list[dict[str, Any]], df: pd.DataFrame) -> str:
    OCR_RAW_DIR.mkdir(parents=True, exist_ok=True)
    OCR_PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    stem = image_path.stem
    raw_path = OCR_RAW_DIR / f"{stem}.json"
    preview_path = OCR_PREVIEW_DIR / f"{stem}.csv"
    raw_path.write_text(
        json.dumps(_json_safe(ocr_items), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if not df.empty:
        df.to_csv(preview_path, index=False, encoding="utf-8-sig")
    return str(raw_path)


def _rows_to_dataframe(
    rows: list[list[dict[str, Any]]],
    header_idx: int,
    *,
    year: int,
    province: str,
    subject_type: str | None,
    batch: str,
) -> pd.DataFrame:
    header_row = rows[header_idx]
    records: list[dict[str, Any]] = []
    for row in rows[header_idx + 1 :]:
        text_line = _row_text(row)
        if not text_line.strip():
            continue
        if any(marker in text_line for marker in ("说明", "备注：", "合计", "单位：")):
            continue
        mapped = _assign_columns(header_row, row)
        if not mapped.get("min_score") and not mapped.get("major_group_name"):
            continue
        group_name = mapped.get("major_group_name") or mapped.get("school_code") or ""
        school_name, major_group = _split_major_group_name(group_name)
        row_subject = mapped.get("subject_type") or subject_type
        score = _parse_min_score(mapped.get("min_score", ""))
        if score is None and not school_name:
            continue
        records.append(
            {
                "year": year,
                "province": province,
                "school_code": mapped.get("school_code") or school_name or group_name,
                "school_name": normalize_school_name(school_name or group_name),
                "major_group": major_group or None,
                "subject_type": normalize_subject_type(row_subject) if row_subject else subject_type,
                "batch": batch,
                "min_score": score,
                "admission_category": "普通类",
                "notes": mapped.get("notes"),
            }
        )
    return pd.DataFrame(records)


def parse_image_table(
    image_path: str | Path,
    data_type: str,
    province: str,
    year: int,
    subject_type: str | None = None,
    batch: str | None = None,
    *,
    page_title: str | None = None,
    subject_mode: Any = None,
    use_ocr_cache: bool = True,
    ocr_engine: str = "paddle",
    allow_slow_paddle_fallback: bool = False,
) -> ImageTableParseResult:
    """
    OCR 图片表格 → DataFrame（实验）。

    当前主要支持湖北 school 投档 PNG 表。
    """
    path = Path(image_path)
    if not path.exists():
        return ImageTableParseResult(
            status="unsupported_image_table",
            message=f"文件不存在: {path}",
        )
    if data_type != "school":
        return ImageTableParseResult(
            status="unsupported_image_table",
            message=f"OCR 暂仅支持 school，当前 type={data_type}",
        )
    if not is_image_table_file(path):
        return ImageTableParseResult(
            status="unsupported_image_table",
            message=f"非图片格式: {path.suffix}",
        )
    engine_mode = normalize_ocr_engine_mode(ocr_engine)
    if engine_mode == "hybrid":
        from parsers.ocr_hybrid import run_hybrid_image_parse

        return run_hybrid_image_parse(
            path,
            data_type=data_type,
            province=province,
            year=year,
            subject_type=subject_type,
            batch=batch,
            page_title=page_title,
            subject_mode=subject_mode,
            use_ocr_cache=use_ocr_cache,
            allow_slow_paddle_fallback=allow_slow_paddle_fallback,
        )

    engine_key = normalize_ocr_engine(engine_mode)
    parser_label = _ocr_parser_label(engine_key)
    if not ocr_engine_available(engine_key):
        if engine_key == "rapidocr":
            return ImageTableParseResult(status="rapidocr_not_installed")
        return ImageTableParseResult(status="ocr_not_installed")

    try:
        ocr_items = _run_paddle_ocr(
            path, use_ocr_cache=use_ocr_cache, ocr_engine=engine_key
        )
    except RuntimeError as exc:
        code = str(exc)
        if code in ("rapidocr_not_installed", "ocr_not_installed"):
            return ImageTableParseResult(status=code)
        raise
    except Exception as exc:
        logger.exception("OCR 失败 [%s] engine=%s: %s", path, engine_key, exc)
        return ImageTableParseResult(
            status="table_reconstruction_failed",
            parser_used=parser_label,
            message=str(exc),
        )

    if not ocr_items:
        return ImageTableParseResult(
            status="no_text_detected",
            parser_used=parser_label,
        )

    ocr_text = " ".join(item["text"] for item in ocr_items)
    resolved_subject = _infer_subject_from_context(
        subject_type=subject_type,
        filename=path.stem,
        page_title=page_title,
        ocr_text=ocr_text,
        subject_mode=subject_mode,
    )
    resolved_batch = _infer_batch_from_context(
        batch=batch,
        filename=path.stem,
        page_title=page_title,
        ocr_text=ocr_text,
    )

    rows = _cluster_rows(ocr_items)
    if province == "湖北":
        df = _rows_to_hubei_dataframe(
            rows,
            year=year,
            province=province,
            subject_type=resolved_subject,
            batch=resolved_batch,
        )
    else:
        header_idx = _detect_header_row_index(rows)
        if header_idx is None:
            raw_path = _save_ocr_audit(path, ocr_items, pd.DataFrame())
            return ImageTableParseResult(
                status="table_reconstruction_failed",
                parser_used=parser_label,
                raw_ocr_json_path=raw_path,
                message="未识别到表头行",
            )
        df = _rows_to_dataframe(
            rows,
            header_idx,
            year=year,
            province=province,
            subject_type=resolved_subject,
            batch=resolved_batch,
        )
    raw_path = _save_ocr_audit(path, ocr_items, df)
    if df.empty:
        return ImageTableParseResult(
            status="table_reconstruction_failed",
            parser_used=parser_label,
            raw_ocr_json_path=raw_path,
            message="重建表格后无有效数据行",
        )

    return ImageTableParseResult(
        status="parsed",
        parser_used=parser_label,
        df=df,
        raw_ocr_json_path=raw_path,
    )
