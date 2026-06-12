"""
位次换算服务（Phase 6）。

基于一分一段表实现：分数↔位次、跨年等效分换算。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.services import (
    QueryValidationError,
    validate_province,
    validate_subject_type,
    validate_year,
)
from db.models import ScoreRankTable

MIN_SCORE = 0
MAX_SCORE = 750


class RankTableNotFoundError(Exception):
    """指定年份/省份/科类无一分一段数据。"""

    def __init__(self, year: int, province: str, subject_type: str) -> None:
        self.year = year
        self.province = province
        self.subject_type = subject_type
        super().__init__(
            f"未找到一分一段表: {year} {province} {subject_type}"
        )


def _validate_score(score: int) -> int:
    if not (MIN_SCORE <= score <= MAX_SCORE):
        raise QueryValidationError(f"score 须在 {MIN_SCORE}-{MAX_SCORE} 之间")
    return score


def _validate_rank(rank: int) -> int:
    if rank <= 0:
        raise QueryValidationError("rank 必须大于 0")
    return rank


def _base_query(
    session: Session,
    year: int,
    province: str,
    subject_type: str,
):
    year = validate_year(year, required=True)
    province = validate_province(province, required=True)
    subject_type = validate_subject_type(subject_type, required=True)

    q = session.query(ScoreRankTable).filter(
        ScoreRankTable.year == year,
        ScoreRankTable.province == province,
        ScoreRankTable.subject_type == subject_type,
    )
    if q.count() == 0:
        raise RankTableNotFoundError(year, province, subject_type)
    return q


def get_rank_by_score(
    session: Session,
    year: int,
    province: str,
    subject_type: str,
    score: int,
) -> dict:
    """
    分数查位次（累计人数即位次近似值）。

    无精确分数时，取 <= score 的最近分段。
    """
    score = _validate_score(score)
    q = _base_query(session, year, province, subject_type)

    exact = q.filter(ScoreRankTable.score == score).first()
    if exact and exact.cumulative_count is not None:
        return {
            "year": year,
            "province": province,
            "subject_type": subject_type,
            "score": score,
            "rank": int(exact.cumulative_count),
            "exact_match": True,
            "matched_score": float(exact.score),
        }

    # 找 <= score 的最高分段
    nearest = (
        q.filter(ScoreRankTable.score <= score)
        .order_by(ScoreRankTable.score.desc())
        .first()
    )
    if nearest is None or nearest.cumulative_count is None:
        raise RankTableNotFoundError(year, province, subject_type)

    return {
        "year": year,
        "province": province,
        "subject_type": subject_type,
        "score": score,
        "rank": int(nearest.cumulative_count),
        "exact_match": False,
        "matched_score": float(nearest.score),
    }


def get_score_by_rank(
    session: Session,
    year: int,
    province: str,
    subject_type: str,
    rank: int,
) -> dict:
    """
    位次查分数。

    找 cumulative_count >= rank 的最高分（该位次对应的分数段）。
    """
    rank = _validate_rank(rank)
    q = _base_query(session, year, province, subject_type)

    row = (
        q.filter(
            ScoreRankTable.cumulative_count.isnot(None),
            ScoreRankTable.cumulative_count >= rank,
        )
        .order_by(ScoreRankTable.score.desc())
        .first()
    )
    if row is None:
        raise RankTableNotFoundError(year, province, subject_type)

    return {
        "year": year,
        "province": province,
        "subject_type": subject_type,
        "rank": rank,
        "score": int(row.score),
        "matched_cumulative_count": int(row.cumulative_count),
    }


def convert_score_between_years(
    session: Session,
    province: str,
    subject_type: str,
    from_year: int,
    to_year: int,
    score: int,
) -> dict:
    """
    跨年等效分换算：from_year 分数 → 位次 → to_year 等效分。
    """
    score = _validate_score(score)
    validate_year(from_year, required=True)
    validate_year(to_year, required=True)
    province = validate_province(province, required=True)
    subject_type = validate_subject_type(subject_type, required=True)

    if from_year == to_year:
        raise QueryValidationError("from_year 与 to_year 不能相同")

    rank_info = get_rank_by_score(session, from_year, province, subject_type, score)
    estimated_rank = rank_info["rank"]

    score_info = get_score_by_rank(session, to_year, province, subject_type, estimated_rank)

    return {
        "province": province,
        "subject_type": subject_type,
        "from_year": from_year,
        "from_score": score,
        "estimated_rank": estimated_rank,
        "from_exact_match": rank_info.get("exact_match", True),
        "from_matched_score": rank_info.get("matched_score"),
        "to_year": to_year,
        "equivalent_score": score_info["score"],
        "to_matched_cumulative_count": score_info["matched_cumulative_count"],
    }
