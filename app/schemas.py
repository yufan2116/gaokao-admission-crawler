"""
API 响应模型（Pydantic）。
"""

from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str = "ok"


class SchoolItem(BaseModel):
    year: int
    province: str
    subject_type: str
    school_code: str
    school_name: str
    major_group: str | None = None
    min_score: float | None = None
    min_rank: int | None = None
    tie_breaker_text: str | None = None
    plan_count: int | None = None


class SchoolMetadataItem(BaseModel):
    standard_name: str | None = None
    city: str | None = None
    is_985: bool | None = None
    is_211: bool | None = None
    is_double_first_class: bool | None = None
    school_type: str | None = None
    ownership: str | None = None
    source: str | None = None


class EnrichedSchoolItem(SchoolItem):
    metadata: SchoolMetadataItem | None = None


class EnrichedSchoolListResponse(BaseModel):
    total: int
    items: list[EnrichedSchoolItem]


class SchoolListResponse(BaseModel):
    total: int
    items: list[SchoolItem]


class RankItem(BaseModel):
    year: int
    province: str
    subject_type: str
    score: float
    same_score_count: int | None = None
    cumulative_count: int | None = None


class RankListResponse(BaseModel):
    total: int
    items: list[RankItem]


class RankScoreResponse(BaseModel):
    year: int
    province: str
    subject_type: str
    score: float
    same_score_count: int | None = None
    cumulative_count: int | None = None


class ControlItem(BaseModel):
    year: int
    province: str
    subject_type: str
    batch: str
    score: float


class ControlListResponse(BaseModel):
    total: int
    items: list[ControlItem]


class StatsSummaryResponse(BaseModel):
    school_admission_line_count: int
    rank_table_count: int
    control_line_count: int
    major_line_count: int
    years_available: list[int]
    provinces_available: list[str]


class ProvinceAvailabilityItem(BaseModel):
    province: str
    year: int
    school_discovery_status: str
    school_download_status: str
    school_import_status: str
    source_format: str
    machine_readable: bool
    query_mode: str
    notes: str
    access_status: str
    machine_readable_level: str | None = None


class ProvinceAvailabilityResponse(BaseModel):
    total: int
    items: list[ProvinceAvailabilityItem]


class ScoreToRankResponse(BaseModel):
    year: int
    province: str
    subject_type: str
    score: int
    rank: int
    exact_match: bool = True
    matched_score: float | None = None


class RankToScoreResponse(BaseModel):
    year: int
    province: str
    subject_type: str
    rank: int
    score: int
    matched_cumulative_count: int


class EquivalentScoreResponse(BaseModel):
    province: str
    subject_type: str
    from_year: int
    from_score: int
    estimated_rank: int
    from_exact_match: bool = True
    from_matched_score: float | None = None
    to_year: int
    equivalent_score: int
    to_matched_cumulative_count: int


class SchoolsByScoreInput(BaseModel):
    year: int
    province: str
    subject_type: str
    score: int
    tolerance: int = 10


class SchoolsByScoreResponse(BaseModel):
    input: SchoolsByScoreInput
    min_score: float
    max_score: float
    total: int
    matched_schools: list[SchoolItem]


class SchoolsByRankInput(BaseModel):
    year: int
    province: str
    subject_type: str
    rank: int
    tolerance: int = 1000


class SchoolsByRankResponse(BaseModel):
    input: SchoolsByRankInput
    rank_min: int
    rank_max: int
    total: int
    matched_schools: list[SchoolItem]


class EquivalentConversionDetail(BaseModel):
    province: str
    subject_type: str
    from_year: int
    from_score: int
    estimated_rank: int
    to_year: int
    equivalent_score: int


class SchoolsByEquivalentScoreResponse(BaseModel):
    input: dict
    conversion: EquivalentConversionDetail
    tolerance: int
    min_score: float
    max_score: float
    total: int
    matched_schools: list[SchoolItem]
