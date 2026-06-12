"""
school_metadata CSV 导入（Phase 9）。

人工维护 seed，upsert 写入 school_metadata 表。
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from db.repository import MetadataUpsertResult, upsert_school_metadata
from normalizers.province import normalize_province

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = ("standard_name", "province")


def _parse_bool(value: str | None) -> bool:
    if value is None:
        return False
    text = str(value).strip().lower()
    if not text:
        return False
    return text in ("1", "true", "yes", "y", "是", "t")


def load_school_metadata_csv(path: Path) -> list[dict]:
    """读取 CSV 为 dict 列表。"""
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("CSV 无表头")
        missing = [c for c in REQUIRED_COLUMNS if c not in reader.fieldnames]
        if missing:
            raise ValueError(f"CSV 缺少列: {', '.join(missing)}")

        rows: list[dict] = []
        for line_no, raw in enumerate(reader, start=2):
            standard_name = (raw.get("standard_name") or "").strip()
            if not standard_name:
                logger.warning("第 %d 行 standard_name 为空，已跳过", line_no)
                continue
            school_name = (raw.get("school_name") or standard_name).strip()
            province = normalize_province((raw.get("province") or "").strip())
            if not province:
                logger.warning("第 %d 行 province 无效，已跳过", line_no)
                continue

            rows.append(
                {
                    "school_name": school_name,
                    "standard_name": standard_name,
                    "province": province,
                    "city": (raw.get("city") or "").strip() or None,
                    "is_985": _parse_bool(raw.get("is_985")),
                    "is_211": _parse_bool(raw.get("is_211")),
                    "is_double_first_class": _parse_bool(raw.get("is_double_first_class")),
                    "school_type": (raw.get("school_type") or "").strip() or None,
                    "ownership": (raw.get("ownership") or "").strip() or None,
                    "source": (raw.get("source") or "").strip() or None,
                }
            )
    return rows


def import_school_metadata_csv(session: Session, path: Path) -> MetadataUpsertResult:
    """从 CSV upsert 导入 school_metadata。"""
    rows = load_school_metadata_csv(path)
    if not rows:
        logger.warning("CSV 无有效数据行: %s", path)
        return MetadataUpsertResult()
    return upsert_school_metadata(session, rows)
