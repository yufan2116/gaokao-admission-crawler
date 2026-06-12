"""
院校投档线查询模式（Phase 10.1）。

按 min_score / min_rank 空值率推荐 score / rank / mixed 查询方式。
"""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from db.models import SchoolAdmissionLine
from normalizers.province import normalize_province

# 省份静态默认（Dashboard Coverage 与无 DB 数据时兜底）
PROVINCE_DEFAULT_QUERY_MODE: dict[str, str] = {
    "江苏": "score",
    "浙江": "score",
    "山东": "rank",
    "河南": "score",
    "广东": "mixed",
    "福建": "score",
    "河北": "score",
}

SCORE_QUERY_UNAVAILABLE_MSG = (
    "score query is not available for this province/year; use rank query instead"
)


def recommend_query_mode(min_score_null_rate: float, min_rank_null_rate: float) -> str:
    """根据空值率推荐查询模式。"""
    if min_score_null_rate < 0.2:
        return "score"
    if min_rank_null_rate < 0.2 and min_score_null_rate >= 0.8:
        return "rank"
    return "mixed"


def compute_school_null_rates(
    session: Session,
    year: int,
    province: str,
) -> tuple[float, float, int]:
    """
    计算指定年份/省份 school 行的 min_score、min_rank 空值率。

    Returns:
        (min_score_null_rate, min_rank_null_rate, total_rows)
    """
    province = normalize_province(province)
    total = (
        session.query(func.count(SchoolAdmissionLine.id))
        .filter(
            SchoolAdmissionLine.year == year,
            SchoolAdmissionLine.province == province,
        )
        .scalar()
        or 0
    )
    if total == 0:
        return 1.0, 1.0, 0

    null_score = (
        session.query(func.count(SchoolAdmissionLine.id))
        .filter(
            SchoolAdmissionLine.year == year,
            SchoolAdmissionLine.province == province,
            SchoolAdmissionLine.min_score.is_(None),
        )
        .scalar()
        or 0
    )
    null_rank = (
        session.query(func.count(SchoolAdmissionLine.id))
        .filter(
            SchoolAdmissionLine.year == year,
            SchoolAdmissionLine.province == province,
            SchoolAdmissionLine.min_rank.is_(None),
        )
        .scalar()
        or 0
    )
    return null_score / total, null_rank / total, total


def get_default_query_mode(province: str) -> str:
    return PROVINCE_DEFAULT_QUERY_MODE.get(normalize_province(province), "mixed")


def resolve_query_mode(
    session: Session,
    year: int | None,
    province: str | None,
) -> str:
    """结合 DB 空值率与省份默认值解析查询模式。"""
    if year is None or not province:
        return "mixed"
    province_norm = normalize_province(province)
    ms_rate, mr_rate, total = compute_school_null_rates(session, year, province_norm)
    if total == 0:
        return get_default_query_mode(province_norm)
    return recommend_query_mode(ms_rate, mr_rate)


def score_query_available(session: Session, year: int, province: str) -> bool:
    """该省该年是否适合按分数查询（min_score 空值率 <= 80%）。"""
    ms_rate, _, total = compute_school_null_rates(session, year, normalize_province(province))
    if total == 0:
        return get_default_query_mode(province) == "score"
    return ms_rate <= 0.8
