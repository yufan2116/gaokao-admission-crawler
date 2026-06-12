"""
数据库查询服务层。
"""

from __future__ import annotations

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from db.models import (
    MajorAdmissionLine,
    ProvinceControlLine,
    SchoolAdmissionLine,
    SchoolMetadata,
    ScoreRankTable,
)
from normalizers.province import normalize_province

# limit 上限
SCHOOL_LIMIT_DEFAULT = 50
SCHOOL_LIMIT_MAX = 200
RANK_LIMIT_DEFAULT = 100
RANK_LIMIT_MAX = 500

VALID_SUBJECT_TYPES = frozenset({
    "文科", "理科", "历史类", "物理类", "综合改革",
})

MIN_YEAR = 2000
MAX_YEAR = 2030


class QueryValidationError(ValueError):
    """查询参数校验错误。"""


def clamp_limit(value: int, default: int, maximum: int) -> int:
    if value < 1:
        return default
    return min(value, maximum)


def validate_year(year: int | None, required: bool = False) -> int | None:
    if year is None:
        if required:
            raise QueryValidationError("year 为必填参数")
        return None
    if not (MIN_YEAR <= year <= MAX_YEAR):
        raise QueryValidationError(f"year 须在 {MIN_YEAR}-{MAX_YEAR} 之间")
    return year


def validate_province(province: str | None, required: bool = False) -> str | None:
    if province is None or not province.strip():
        if required:
            raise QueryValidationError("province 为必填参数")
        return None
    return normalize_province(province)


def validate_subject_type(subject_type: str | None, required: bool = False) -> str | None:
    if subject_type is None or not subject_type.strip():
        if required:
            raise QueryValidationError("subject_type 为必填参数")
        return None
    st = subject_type.strip()
    if st not in VALID_SUBJECT_TYPES:
        raise QueryValidationError(
            f"subject_type 无效: {st}，可选: {sorted(VALID_SUBJECT_TYPES)}"
        )
    return st


def validate_score_range(min_score: float | None, max_score: float | None) -> None:
    if min_score is not None and max_score is not None and min_score > max_score:
        raise QueryValidationError("min_score 不能大于 max_score")


def validate_rank_range(rank_min: int | None, rank_max: int | None) -> None:
    if rank_min is not None and rank_max is not None and rank_min > rank_max:
        raise QueryValidationError("rank_min 不能大于 rank_max")


def query_schools(
    db: Session,
    *,
    year: int | None = None,
    province: str | None = None,
    subject_type: str | None = None,
    school_name: str | None = None,
    min_score: float | None = None,
    max_score: float | None = None,
    rank_min: int | None = None,
    rank_max: int | None = None,
    limit: int = SCHOOL_LIMIT_DEFAULT,
) -> tuple[int, list[SchoolAdmissionLine]]:
    year = validate_year(year)
    province = validate_province(province)
    subject_type = validate_subject_type(subject_type)
    validate_score_range(min_score, max_score)
    validate_rank_range(rank_min, rank_max)
    limit = clamp_limit(limit, SCHOOL_LIMIT_DEFAULT, SCHOOL_LIMIT_MAX)

    q = db.query(SchoolAdmissionLine)
    if year is not None:
        q = q.filter(SchoolAdmissionLine.year == year)
    if province:
        q = q.filter(SchoolAdmissionLine.province == province)
    if subject_type:
        q = q.filter(SchoolAdmissionLine.subject_type == subject_type)
    if school_name and school_name.strip():
        q = q.filter(SchoolAdmissionLine.school_name.like(f"%{school_name.strip()}%"))
    if min_score is not None:
        q = q.filter(SchoolAdmissionLine.min_score >= min_score)
    if max_score is not None:
        q = q.filter(SchoolAdmissionLine.min_score <= max_score)
    if rank_min is not None:
        q = q.filter(SchoolAdmissionLine.min_rank >= rank_min)
    if rank_max is not None:
        q = q.filter(SchoolAdmissionLine.min_rank <= rank_max)

    total = q.count()
    use_rank_order = (rank_min is not None or rank_max is not None) and min_score is None and max_score is None
    if use_rank_order:
        order = SchoolAdmissionLine.min_rank.asc().nulls_last()
    else:
        order = SchoolAdmissionLine.min_score.desc().nulls_last()
    items = q.order_by(order).limit(limit).all()
    return total, items


def query_schools_by_rank(
    db: Session,
    *,
    year: int,
    province: str,
    subject_type: str,
    rank: int,
    tolerance: int = 1000,
    limit: int = SCHOOL_LIMIT_DEFAULT,
) -> tuple[int, list[SchoolAdmissionLine], int, int]:
    """按位次区间查询院校投档线。"""
    year = validate_year(year, required=True)
    province = validate_province(province, required=True)
    subject_type = validate_subject_type(subject_type, required=True)
    if rank < 1:
        raise QueryValidationError("rank 须大于 0")
    if tolerance < 0:
        raise QueryValidationError("tolerance 不能为负数")
    limit = clamp_limit(limit, SCHOOL_LIMIT_DEFAULT, SCHOOL_LIMIT_MAX)

    rank_lo = max(1, rank - tolerance)
    rank_hi = rank + tolerance
    total, items = query_schools(
        db,
        year=year,
        province=province,
        subject_type=subject_type,
        rank_min=rank_lo,
        rank_max=rank_hi,
        limit=limit,
    )
    return total, items, rank_lo, rank_hi


def _school_metadata_join():
    """投档线 school_name 与元数据 standard_name 前缀匹配。"""
    return or_(
        SchoolAdmissionLine.school_name == SchoolMetadata.standard_name,
        SchoolAdmissionLine.school_name == SchoolMetadata.school_name,
        SchoolAdmissionLine.school_name.like(func.concat(SchoolMetadata.standard_name, "%")),
    )


def query_schools_enriched(
    db: Session,
    *,
    year: int | None = None,
    province: str | None = None,
    subject_type: str | None = None,
    score_min: float | None = None,
    score_max: float | None = None,
    rank_min: int | None = None,
    rank_max: int | None = None,
    is_985: bool | None = None,
    is_211: bool | None = None,
    is_double_first_class: bool | None = None,
    city: str | None = None,
    school_type: str | None = None,
    limit: int = SCHOOL_LIMIT_DEFAULT,
) -> tuple[int, list[tuple[SchoolAdmissionLine, SchoolMetadata | None]]]:
    """school_admission_line LEFT JOIN school_metadata。"""
    year = validate_year(year)
    province = validate_province(province)
    subject_type = validate_subject_type(subject_type)
    validate_score_range(score_min, score_max)
    validate_rank_range(rank_min, rank_max)
    limit = clamp_limit(limit, SCHOOL_LIMIT_DEFAULT, SCHOOL_LIMIT_MAX)

    q = db.query(SchoolAdmissionLine, SchoolMetadata).outerjoin(
        SchoolMetadata,
        _school_metadata_join(),
    )

    if year is not None:
        q = q.filter(SchoolAdmissionLine.year == year)
    if province:
        q = q.filter(SchoolAdmissionLine.province == province)
    if subject_type:
        q = q.filter(SchoolAdmissionLine.subject_type == subject_type)
    if score_min is not None:
        q = q.filter(SchoolAdmissionLine.min_score >= score_min)
    if score_max is not None:
        q = q.filter(SchoolAdmissionLine.min_score <= score_max)
    if rank_min is not None:
        q = q.filter(SchoolAdmissionLine.min_rank >= rank_min)
    if rank_max is not None:
        q = q.filter(SchoolAdmissionLine.min_rank <= rank_max)
    if is_985 is not None:
        q = q.filter(SchoolMetadata.is_985.is_(is_985))
    if is_211 is not None:
        q = q.filter(SchoolMetadata.is_211.is_(is_211))
    if is_double_first_class is not None:
        q = q.filter(SchoolMetadata.is_double_first_class.is_(is_double_first_class))
    if city and city.strip():
        q = q.filter(SchoolMetadata.city == city.strip())
    if school_type and school_type.strip():
        q = q.filter(SchoolMetadata.school_type == school_type.strip())

    total = q.count()
    use_rank_order = (rank_min is not None or rank_max is not None) and score_min is None and score_max is None
    if use_rank_order:
        order = SchoolAdmissionLine.min_rank.asc().nulls_last()
    else:
        order = SchoolAdmissionLine.min_score.desc().nulls_last()
    items = q.order_by(order).limit(limit).all()
    return total, items


def query_ranks(
    db: Session,
    *,
    year: int,
    province: str,
    subject_type: str,
    score: float | None = None,
    limit: int = RANK_LIMIT_DEFAULT,
) -> tuple[int, list[ScoreRankTable]] | ScoreRankTable | None:
    year = validate_year(year, required=True)
    province = validate_province(province, required=True)
    subject_type = validate_subject_type(subject_type, required=True)

    q = db.query(ScoreRankTable).filter(
        ScoreRankTable.year == year,
        ScoreRankTable.province == province,
        ScoreRankTable.subject_type == subject_type,
    )

    if score is not None:
        row = q.filter(ScoreRankTable.score == score).first()
        if row is None:
            # 尝试近似匹配（整数分）
            row = q.filter(ScoreRankTable.score == int(score)).first()
        return row

    limit = clamp_limit(limit, RANK_LIMIT_DEFAULT, RANK_LIMIT_MAX)
    total = q.count()
    items = q.order_by(ScoreRankTable.score.desc()).limit(limit).all()
    return total, items


def query_controls(
    db: Session,
    *,
    year: int | None = None,
    province: str | None = None,
    subject_type: str | None = None,
    batch: str | None = None,
    limit: int = 100,
) -> tuple[int, list[ProvinceControlLine]]:
    year = validate_year(year)
    province = validate_province(province)
    subject_type = validate_subject_type(subject_type)
    limit = clamp_limit(limit, 100, 200)

    q = db.query(ProvinceControlLine)
    if year is not None:
        q = q.filter(ProvinceControlLine.year == year)
    if province:
        q = q.filter(ProvinceControlLine.province == province)
    if subject_type:
        q = q.filter(ProvinceControlLine.subject_type == subject_type)
    if batch and batch.strip():
        q = q.filter(ProvinceControlLine.batch.like(f"%{batch.strip()}%"))

    total = q.count()
    items = q.order_by(ProvinceControlLine.year.desc(), ProvinceControlLine.score.desc()).limit(limit).all()
    return total, items


def query_stats_summary(db: Session) -> dict:
    school_count = db.query(func.count(SchoolAdmissionLine.id)).scalar() or 0
    rank_count = db.query(func.count(ScoreRankTable.id)).scalar() or 0
    control_count = db.query(func.count(ProvinceControlLine.id)).scalar() or 0
    major_count = db.query(func.count(MajorAdmissionLine.id)).scalar() or 0

    years: set[int] = set()
    provinces: set[str] = set()
    for model in (SchoolAdmissionLine, ScoreRankTable, ProvinceControlLine, MajorAdmissionLine):
        for y, in db.query(model.year).distinct().all():
            if y is not None:
                years.add(int(y))
        for p, in db.query(model.province).distinct().all():
            if p:
                provinces.add(str(p))

    return {
        "school_admission_line_count": school_count,
        "rank_table_count": rank_count,
        "control_line_count": control_count,
        "major_line_count": major_count,
        "years_available": sorted(years),
        "provinces_available": sorted(provinces),
    }
