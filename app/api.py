"""
FastAPI 查询接口（Phase 5 / 6）。

启动:
    uvicorn app.api:app --reload
"""

from __future__ import annotations

import logging

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.schemas import (
    ControlItem,
    ControlListResponse,
    EnrichedSchoolItem,
    EnrichedSchoolListResponse,
    EquivalentConversionDetail,
    EquivalentScoreResponse,
    HealthResponse,
    RankItem,
    RankListResponse,
    RankScoreResponse,
    RankToScoreResponse,
    SchoolItem,
    SchoolListResponse,
    SchoolMetadataItem,
    SchoolsByEquivalentScoreResponse,
    SchoolsByRankInput,
    SchoolsByRankResponse,
    SchoolsByScoreInput,
    SchoolsByScoreResponse,
    ScoreToRankResponse,
    StatsSummaryResponse,
)
from app.services import (
    QueryValidationError,
    query_controls,
    query_ranks,
    query_schools,
    query_schools_by_rank,
    query_schools_enriched,
    query_stats_summary,
)
from services.school_query_mode import SCORE_QUERY_UNAVAILABLE_MSG, score_query_available
from db.database import get_db
from services.rank_converter import (
    RankTableNotFoundError,
    convert_score_between_years,
    get_rank_by_score,
    get_score_by_rank,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="gaokao-admission-crawler API",
    description="高考录取线数据查询接口（江苏省 MVP）",
    version="0.6.0",
)


def _school_item(r) -> SchoolItem:
    return SchoolItem(
        year=r.year,
        province=r.province,
        subject_type=r.subject_type,
        school_code=r.school_code,
        school_name=r.school_name,
        major_group=r.major_group,
        min_score=r.min_score,
        min_rank=r.min_rank,
        tie_breaker_text=r.tie_breaker_text,
        plan_count=r.plan_count,
    )


@app.exception_handler(QueryValidationError)
async def validation_error_handler(_request: Request, exc: QueryValidationError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(RankTableNotFoundError)
async def rank_not_found_handler(_request: Request, exc: RankTableNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def generic_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    logger.exception("未处理异常: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "服务器内部错误"})


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    """健康检查。"""
    return HealthResponse(status="ok")


@app.get("/schools", response_model=SchoolListResponse, tags=["admission"])
def list_schools(
    year: int | None = Query(None, ge=2000, le=2030),
    province: str | None = Query(None),
    subject_type: str | None = Query(None),
    school_name: str | None = Query(None, description="院校名称模糊查询"),
    min_score: float | None = Query(None, ge=0, le=750),
    max_score: float | None = Query(None, ge=0, le=750),
    rank_min: int | None = Query(None, ge=1),
    rank_max: int | None = Query(None, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> SchoolListResponse:
    """查询院校投档线。"""
    total, rows = query_schools(
        db,
        year=year,
        province=province,
        subject_type=subject_type,
        school_name=school_name,
        min_score=min_score,
        max_score=max_score,
        rank_min=rank_min,
        rank_max=rank_max,
        limit=limit,
    )
    return SchoolListResponse(total=total, items=[_school_item(r) for r in rows])


def _metadata_item(meta) -> SchoolMetadataItem | None:
    if meta is None:
        return None
    return SchoolMetadataItem(
        standard_name=meta.standard_name,
        city=meta.city,
        is_985=meta.is_985,
        is_211=meta.is_211,
        is_double_first_class=meta.is_double_first_class,
        school_type=meta.school_type,
        ownership=meta.ownership,
        source=meta.source,
    )


def _enriched_item(admission, meta) -> EnrichedSchoolItem:
    base = _school_item(admission)
    return EnrichedSchoolItem(**base.model_dump(), metadata=_metadata_item(meta))


@app.get("/schools/enriched", response_model=EnrichedSchoolListResponse, tags=["admission"])
def list_schools_enriched(
    year: int | None = Query(None, ge=2000, le=2030),
    province: str | None = Query(None),
    subject_type: str | None = Query(None),
    score_min: float | None = Query(None, ge=0, le=750),
    score_max: float | None = Query(None, ge=0, le=750),
    rank_min: int | None = Query(None, ge=1),
    rank_max: int | None = Query(None, ge=1),
    is_985: bool | None = Query(None),
    is_211: bool | None = Query(None),
    is_double_first_class: bool | None = Query(None),
    city: str | None = Query(None),
    school_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> EnrichedSchoolListResponse:
    """查询院校投档线并关联 school_metadata。"""
    total, rows = query_schools_enriched(
        db,
        year=year,
        province=province,
        subject_type=subject_type,
        score_min=score_min,
        score_max=score_max,
        rank_min=rank_min,
        rank_max=rank_max,
        is_985=is_985,
        is_211=is_211,
        is_double_first_class=is_double_first_class,
        city=city,
        school_type=school_type,
        limit=limit,
    )
    return EnrichedSchoolListResponse(
        total=total,
        items=[_enriched_item(a, m) for a, m in rows],
    )


@app.get("/schools/by-score", response_model=SchoolsByScoreResponse, tags=["admission"])
def schools_by_score(
    year: int = Query(..., ge=2000, le=2030),
    province: str = Query(...),
    subject_type: str = Query(...),
    score: int = Query(..., ge=0, le=750),
    tolerance: int = Query(10, ge=0, le=50),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> SchoolsByScoreResponse:
    """按分数区间筛选院校投档线。"""
    if not score_query_available(db, year, province):
        raise HTTPException(status_code=400, detail=SCORE_QUERY_UNAVAILABLE_MSG)
    min_s = float(score - tolerance)
    max_s = float(score + tolerance)
    total, rows = query_schools(
        db,
        year=year,
        province=province,
        subject_type=subject_type,
        min_score=min_s,
        max_score=max_s,
        limit=limit,
    )
    return SchoolsByScoreResponse(
        input=SchoolsByScoreInput(
            year=year,
            province=province,
            subject_type=subject_type,
            score=score,
            tolerance=tolerance,
        ),
        min_score=min_s,
        max_score=max_s,
        total=total,
        matched_schools=[_school_item(r) for r in rows],
    )


@app.get("/schools/by-rank", response_model=SchoolsByRankResponse, tags=["admission"])
def schools_by_rank(
    year: int = Query(..., ge=2000, le=2030),
    province: str = Query(...),
    subject_type: str = Query(...),
    rank: int = Query(..., ge=1),
    tolerance: int = Query(1000, ge=0, le=500000),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> SchoolsByRankResponse:
    """按位次区间筛选院校投档线（适用于山东等仅有最低位次的省份）。"""
    total, rows, rank_lo, rank_hi = query_schools_by_rank(
        db,
        year=year,
        province=province,
        subject_type=subject_type,
        rank=rank,
        tolerance=tolerance,
        limit=limit,
    )
    return SchoolsByRankResponse(
        input=SchoolsByRankInput(
            year=year,
            province=province,
            subject_type=subject_type,
            rank=rank,
            tolerance=tolerance,
        ),
        rank_min=rank_lo,
        rank_max=rank_hi,
        total=total,
        matched_schools=[_school_item(r) for r in rows],
    )


@app.get("/schools/by-equivalent-score", response_model=SchoolsByEquivalentScoreResponse, tags=["admission"])
def schools_by_equivalent_score(
    current_year: int = Query(..., ge=2000, le=2030),
    target_year: int = Query(..., ge=2000, le=2030),
    province: str = Query(...),
    subject_type: str = Query(...),
    score: int = Query(..., ge=0, le=750),
    tolerance: int = Query(10, ge=0, le=50),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> SchoolsByEquivalentScoreResponse:
    """当前年分数换算为往年等效分后，筛选目标年院校投档线。"""
    conversion_raw = convert_score_between_years(
        db,
        province=province,
        subject_type=subject_type,
        from_year=current_year,
        to_year=target_year,
        score=score,
    )
    eq_score = conversion_raw["equivalent_score"]
    min_s = float(eq_score - tolerance)
    max_s = float(eq_score + tolerance)

    total, rows = query_schools(
        db,
        year=target_year,
        province=province,
        subject_type=subject_type,
        min_score=min_s,
        max_score=max_s,
        limit=limit,
    )

    conversion = EquivalentConversionDetail(
        province=conversion_raw["province"],
        subject_type=conversion_raw["subject_type"],
        from_year=conversion_raw["from_year"],
        from_score=conversion_raw["from_score"],
        estimated_rank=conversion_raw["estimated_rank"],
        to_year=conversion_raw["to_year"],
        equivalent_score=conversion_raw["equivalent_score"],
    )

    return SchoolsByEquivalentScoreResponse(
        input={
            "current_year": current_year,
            "target_year": target_year,
            "province": province,
            "subject_type": subject_type,
            "score": score,
        },
        conversion=conversion,
        tolerance=tolerance,
        min_score=min_s,
        max_score=max_s,
        total=total,
        matched_schools=[_school_item(r) for r in rows],
    )


@app.get("/ranks", tags=["rank"])
def list_ranks(
    year: int = Query(..., ge=2000, le=2030),
    province: str = Query(...),
    subject_type: str = Query(...),
    score: float | None = Query(None, ge=0, le=750),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> RankListResponse | RankScoreResponse:
    """查询一分一段表。"""
    result = query_ranks(
        db,
        year=year,
        province=province,
        subject_type=subject_type,
        score=score,
        limit=limit,
    )

    if score is not None:
        if result is None:
            raise HTTPException(status_code=404, detail=f"未找到 score={score} 的记录")
        return RankScoreResponse(
            year=result.year,
            province=result.province,
            subject_type=result.subject_type,
            score=result.score,
            same_score_count=result.same_score_count,
            cumulative_count=result.cumulative_count,
        )

    total, rows = result  # type: ignore[misc]
    items = [
        RankItem(
            year=r.year,
            province=r.province,
            subject_type=r.subject_type,
            score=r.score,
            same_score_count=r.same_score_count,
            cumulative_count=r.cumulative_count,
        )
        for r in rows
    ]
    return RankListResponse(total=total, items=items)


@app.get("/convert/score-to-rank", response_model=ScoreToRankResponse, tags=["convert"])
def convert_score_to_rank(
    year: int = Query(..., ge=2000, le=2030),
    province: str = Query(...),
    subject_type: str = Query(...),
    score: int = Query(..., ge=0, le=750),
    db: Session = Depends(get_db),
) -> ScoreToRankResponse:
    """分数查位次。"""
    data = get_rank_by_score(db, year, province, subject_type, score)
    return ScoreToRankResponse(**data)


@app.get("/convert/rank-to-score", response_model=RankToScoreResponse, tags=["convert"])
def convert_rank_to_score(
    year: int = Query(..., ge=2000, le=2030),
    province: str = Query(...),
    subject_type: str = Query(...),
    rank: int = Query(..., gt=0),
    db: Session = Depends(get_db),
) -> RankToScoreResponse:
    """位次查分数。"""
    data = get_score_by_rank(db, year, province, subject_type, rank)
    return RankToScoreResponse(**data)


@app.get("/convert/equivalent-score", response_model=EquivalentScoreResponse, tags=["convert"])
def convert_equivalent_score(
    province: str = Query(...),
    subject_type: str = Query(...),
    from_year: int = Query(..., ge=2000, le=2030),
    to_year: int = Query(..., ge=2000, le=2030),
    score: int = Query(..., ge=0, le=750),
    db: Session = Depends(get_db),
) -> EquivalentScoreResponse:
    """跨年等效分换算。"""
    data = convert_score_between_years(db, province, subject_type, from_year, to_year, score)
    return EquivalentScoreResponse(**data)


@app.get("/controls", response_model=ControlListResponse, tags=["control"])
def list_controls(
    year: int | None = Query(None, ge=2000, le=2030),
    province: str | None = Query(None),
    subject_type: str | None = Query(None),
    batch: str | None = Query(None),
    limit: int = Query(100, ge=1, le=200),
    db: Session = Depends(get_db),
) -> ControlListResponse:
    """查询省控线。"""
    total, rows = query_controls(
        db,
        year=year,
        province=province,
        subject_type=subject_type,
        batch=batch,
        limit=limit,
    )
    items = [
        ControlItem(
            year=r.year,
            province=r.province,
            subject_type=r.subject_type,
            batch=r.batch,
            score=r.score,
        )
        for r in rows
    ]
    return ControlListResponse(total=total, items=items)


@app.get("/stats/summary", response_model=StatsSummaryResponse, tags=["stats"])
def stats_summary(db: Session = Depends(get_db)) -> StatsSummaryResponse:
    """数据库汇总统计。"""
    data = query_stats_summary(db)
    return StatsSummaryResponse(**data)
