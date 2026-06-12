"""
数据库批量写入与去重逻辑。

去重规则（与业务键一致，重复则跳过不报错）：
- province_control_line: year + province + subject_type + batch
- school_admission_line: year + province + school_name + subject_type + admission_category + batch + major_group
- major_admission_line: year + province + school_name + major_name + subject_type + major_group
- score_rank_table: year + province + subject_type + score
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from db.models import (
    MajorAdmissionLine,
    ProvinceControlLine,
    SchoolAdmissionLine,
    SchoolMetadata,
    ScoreRankTable,
)

logger = logging.getLogger(__name__)


@dataclass
class InsertResult:
    """批量插入统计结果。"""

    inserted: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)

    def merge(self, other: InsertResult) -> None:
        self.inserted += other.inserted
        self.skipped += other.skipped
        self.failed += other.failed
        self.errors.extend(other.errors)


def _norm_group(value: Any) -> str:
    """专业组空值统一为空字符串，便于去重。"""
    if value is None:
        return ""
    text = str(value).strip()
    return text


def _norm_batch(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _load_control_keys(session: Session, rows: list[dict]) -> set[tuple]:
    years = {int(r["year"]) for r in rows if r.get("year") is not None}
    provinces = {str(r["province"]) for r in rows if r.get("province")}
    if not years or not provinces:
        return set()

    records = (
        session.query(
            ProvinceControlLine.year,
            ProvinceControlLine.province,
            ProvinceControlLine.subject_type,
            ProvinceControlLine.batch,
        )
        .filter(
            ProvinceControlLine.year.in_(years),
            ProvinceControlLine.province.in_(provinces),
        )
        .all()
    )
    return {(r.year, r.province, r.subject_type, r.batch) for r in records}


def _load_school_keys(session: Session, rows: list[dict]) -> set[tuple]:
    years = {int(r["year"]) for r in rows if r.get("year") is not None}
    provinces = {str(r["province"]) for r in rows if r.get("province")}
    if not years or not provinces:
        return set()

    records = (
        session.query(
            SchoolAdmissionLine.year,
            SchoolAdmissionLine.province,
            SchoolAdmissionLine.school_code,
            SchoolAdmissionLine.subject_type,
            SchoolAdmissionLine.admission_category,
            SchoolAdmissionLine.batch,
            SchoolAdmissionLine.major_group,
        )
        .filter(
            SchoolAdmissionLine.year.in_(years),
            SchoolAdmissionLine.province.in_(provinces),
        )
        .all()
    )
    return {
        (
            r.year,
            r.province,
            r.school_code,
            r.subject_type,
            r.admission_category,
            r.batch,
            _norm_group(r.major_group),
        )
        for r in records
    }


def _load_major_keys(session: Session, rows: list[dict]) -> set[tuple]:
    years = {int(r["year"]) for r in rows if r.get("year") is not None}
    provinces = {str(r["province"]) for r in rows if r.get("province")}
    if not years or not provinces:
        return set()

    records = (
        session.query(
            MajorAdmissionLine.year,
            MajorAdmissionLine.province,
            MajorAdmissionLine.school_name,
            MajorAdmissionLine.major_name,
            MajorAdmissionLine.subject_type,
            MajorAdmissionLine.major_group,
        )
        .filter(
            MajorAdmissionLine.year.in_(years),
            MajorAdmissionLine.province.in_(provinces),
        )
        .all()
    )
    return {
        (
            r.year,
            r.province,
            r.school_name,
            r.major_name,
            r.subject_type,
            _norm_group(r.major_group),
        )
        for r in records
    }


def _load_rank_keys(session: Session, rows: list[dict]) -> set[tuple]:
    years = {int(r["year"]) for r in rows if r.get("year") is not None}
    provinces = {str(r["province"]) for r in rows if r.get("province")}
    if not years or not provinces:
        return set()

    records = (
        session.query(
            ScoreRankTable.year,
            ScoreRankTable.province,
            ScoreRankTable.subject_type,
            ScoreRankTable.score,
        )
        .filter(
            ScoreRankTable.year.in_(years),
            ScoreRankTable.province.in_(provinces),
        )
        .all()
    )
    return {(r.year, r.province, r.subject_type, float(r.score)) for r in records}


def insert_province_control_lines(session: Session, rows: list[dict]) -> InsertResult:
    """批量写入省控线，重复记录跳过。"""
    result = InsertResult()
    if not rows:
        return result

    existing = _load_control_keys(session, rows)

    for idx, row in enumerate(rows, start=1):
        try:
            year = int(row["year"])
            province = str(row["province"]).strip()
            subject_type = str(row["subject_type"]).strip()
            batch = _norm_batch(row.get("batch"))
            score = float(row["score"])
            key = (year, province, subject_type, batch)

            if key in existing:
                result.skipped += 1
                continue

            session.add(
                ProvinceControlLine(
                    year=year,
                    province=province,
                    subject_type=subject_type,
                    batch=batch,
                    score=score,
                    source_url=row.get("source_url"),
                )
            )
            existing.add(key)
            result.inserted += 1
        except (KeyError, TypeError, ValueError) as exc:
            result.failed += 1
            msg = f"第 {idx} 行写入失败: {exc}"
            result.errors.append(msg)
            logger.warning(msg)

    try:
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        logger.error("省控线批量提交失败: %s", exc)
        raise

    logger.info(
        "province_control_line: inserted=%d skipped=%d failed=%d",
        result.inserted,
        result.skipped,
        result.failed,
    )
    return result


def insert_school_admission_lines(session: Session, rows: list[dict]) -> InsertResult:
    """批量写入院校投档线，重复记录跳过。"""
    result = InsertResult()
    if not rows:
        return result

    existing = _load_school_keys(session, rows)

    for idx, row in enumerate(rows, start=1):
        try:
            year = int(row["year"])
            province = str(row["province"]).strip()
            school_name = str(row["school_name"]).strip()
            subject_type = str(row["subject_type"]).strip()
            admission_category = _norm_batch(row.get("admission_category")) or "普通类"
            batch = _norm_batch(row.get("batch")) or "本科批"
            major_group = _norm_group(row.get("major_group"))
            school_code = str(row.get("school_code") or "").strip() or school_name
            key = (
                year,
                province,
                school_code,
                subject_type,
                admission_category,
                batch,
                major_group,
            )

            if key in existing:
                result.skipped += 1
                continue

            min_rank = row.get("min_rank")
            plan_count = row.get("plan_count")
            tie_breaker = row.get("tie_breaker_text")
            session.add(
                SchoolAdmissionLine(
                    year=year,
                    province=province,
                    school_name=school_name,
                    school_code=school_code,
                    subject_type=subject_type,
                    admission_category=admission_category,
                    batch=batch,
                    major_group=major_group or None,
                    min_score=float(row["min_score"]) if row.get("min_score") is not None else None,
                    min_rank=int(min_rank) if min_rank is not None else None,
                    plan_count=int(plan_count) if plan_count is not None else None,
                    tie_breaker_text=str(tie_breaker).strip() if tie_breaker else None,
                    source_url=row.get("source_url") or None,
                )
            )
            existing.add(key)
            result.inserted += 1
        except (KeyError, TypeError, ValueError) as exc:
            result.failed += 1
            msg = f"第 {idx} 行写入失败: {exc}"
            result.errors.append(msg)
            logger.warning(msg)

    try:
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        logger.error("院校投档线批量提交失败: %s", exc)
        raise

    logger.info(
        "school_admission_line: inserted=%d skipped=%d failed=%d",
        result.inserted,
        result.skipped,
        result.failed,
    )
    return result


def insert_major_admission_lines(session: Session, rows: list[dict]) -> InsertResult:
    """批量写入专业录取线，重复记录跳过。"""
    result = InsertResult()
    if not rows:
        return result

    existing = _load_major_keys(session, rows)

    for idx, row in enumerate(rows, start=1):
        try:
            year = int(row["year"])
            province = str(row["province"]).strip()
            school_name = str(row["school_name"]).strip()
            major_name = str(row["major_name"]).strip()
            subject_type = str(row["subject_type"]).strip()
            major_group = _norm_group(row.get("major_group"))
            key = (year, province, school_name, major_name, subject_type, major_group)

            if key in existing:
                result.skipped += 1
                continue

            min_rank = row.get("min_rank")
            school_code = str(row.get("school_code") or "").strip() or school_name
            major_code = str(row.get("major_code") or "").strip() or major_name
            session.add(
                MajorAdmissionLine(
                    year=year,
                    province=province,
                    school_name=school_name,
                    school_code=school_code,
                    major_name=major_name,
                    major_code=major_code,
                    subject_type=subject_type,
                    major_group=major_group or None,
                    min_score=float(row["min_score"]),
                    avg_score=float(row["avg_score"]) if row.get("avg_score") is not None else None,
                    max_score=float(row["max_score"]) if row.get("max_score") is not None else None,
                    min_rank=int(min_rank) if min_rank is not None else None,
                    source_url=row.get("source_url"),
                )
            )
            existing.add(key)
            result.inserted += 1
        except (KeyError, TypeError, ValueError) as exc:
            result.failed += 1
            msg = f"第 {idx} 行写入失败: {exc}"
            result.errors.append(msg)
            logger.warning(msg)

    try:
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        logger.error("专业录取线批量提交失败: %s", exc)
        raise

    logger.info(
        "major_admission_line: inserted=%d skipped=%d failed=%d",
        result.inserted,
        result.skipped,
        result.failed,
    )
    return result


def insert_score_rank_rows(session: Session, rows: list[dict]) -> InsertResult:
    """批量写入一分一段表，重复记录跳过。"""
    result = InsertResult()
    if not rows:
        return result

    existing = _load_rank_keys(session, rows)

    for idx, row in enumerate(rows, start=1):
        try:
            year = int(row["year"])
            province = str(row["province"]).strip()
            subject_type = str(row["subject_type"]).strip()
            score = float(row["score"])
            key = (year, province, subject_type, score)

            if key in existing:
                result.skipped += 1
                continue

            same_count = row.get("same_score_count")
            cumulative = row["cumulative_count"]
            session.add(
                ScoreRankTable(
                    year=year,
                    province=province,
                    subject_type=subject_type,
                    score=score,
                    same_score_count=int(same_count) if same_count is not None else None,
                    cumulative_count=int(cumulative),
                    source_url=row.get("source_url"),
                )
            )
            existing.add(key)
            result.inserted += 1
        except (KeyError, TypeError, ValueError) as exc:
            result.failed += 1
            msg = f"第 {idx} 行写入失败: {exc}"
            result.errors.append(msg)
            logger.warning(msg)

    try:
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        logger.error("一分一段表批量提交失败: %s", exc)
        raise

    logger.info(
        "score_rank_table: inserted=%d skipped=%d failed=%d",
        result.inserted,
        result.skipped,
        result.failed,
    )
    return result


@dataclass
class MetadataUpsertResult:
    """school_metadata CSV 导入统计。"""

    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


def _metadata_row_equal(existing: SchoolMetadata, data: dict[str, Any]) -> bool:
    fields = (
        "school_name",
        "standard_name",
        "province",
        "city",
        "is_985",
        "is_211",
        "is_double_first_class",
        "school_type",
        "ownership",
        "source",
    )
    for key in fields:
        if getattr(existing, key) != data.get(key):
            return False
    return True


def upsert_school_metadata(session: Session, rows: list[dict[str, Any]]) -> MetadataUpsertResult:
    """
    按 standard_name 或 school_name 匹配已有记录，存在则更新，无变化则跳过。
    """
    result = MetadataUpsertResult()
    if not rows:
        return result

    existing_rows = session.query(SchoolMetadata).all()
    by_standard: dict[str, SchoolMetadata] = {
        r.standard_name: r for r in existing_rows
    }
    by_school_name: dict[str, SchoolMetadata] = {
        r.school_name: r for r in existing_rows if r.school_name
    }

    for idx, row in enumerate(rows, start=1):
        try:
            standard_name = str(row["standard_name"]).strip()
            school_name = str(row.get("school_name") or standard_name).strip()
            if not standard_name:
                raise ValueError("standard_name 不能为空")

            data = {
                "school_name": school_name,
                "standard_name": standard_name,
                "province": str(row["province"]).strip(),
                "city": (str(row["city"]).strip() if row.get("city") else None) or None,
                "is_985": bool(row.get("is_985")),
                "is_211": bool(row.get("is_211")),
                "is_double_first_class": bool(row.get("is_double_first_class")),
                "school_type": (str(row["school_type"]).strip() if row.get("school_type") else None) or None,
                "ownership": (str(row["ownership"]).strip() if row.get("ownership") else None) or None,
                "source": (str(row["source"]).strip() if row.get("source") else None) or None,
            }

            record = by_standard.get(standard_name) or by_school_name.get(school_name)
            if record is None and school_name != standard_name:
                record = by_school_name.get(standard_name) or by_standard.get(school_name)

            if record is None:
                entity = SchoolMetadata(**data)
                session.add(entity)
                by_standard[standard_name] = entity
                by_school_name[school_name] = entity
                result.inserted += 1
                continue

            if _metadata_row_equal(record, data):
                result.skipped += 1
                continue

            for key, value in data.items():
                setattr(record, key, value)
            by_standard[standard_name] = record
            by_school_name[school_name] = record
            result.updated += 1
        except (KeyError, TypeError, ValueError) as exc:
            result.errors.append(f"第 {idx} 行: {exc}")

    try:
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        logger.error("school_metadata 提交失败: %s", exc)
        raise

    logger.info(
        "school_metadata: inserted=%d updated=%d skipped=%d errors=%d",
        result.inserted,
        result.updated,
        result.skipped,
        len(result.errors),
    )
    return result
