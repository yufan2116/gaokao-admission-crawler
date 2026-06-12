"""数据库模块。"""

from db.database import SessionLocal, engine, get_db
from db.models import (
    Base,
    MajorAdmissionLine,
    ProvinceControlLine,
    SchoolAdmissionLine,
    SchoolMetadata,
    ScoreRankTable,
)
from db.repository import (
    InsertResult,
    MetadataUpsertResult,
    insert_major_admission_lines,
    insert_province_control_lines,
    insert_school_admission_lines,
    insert_score_rank_rows,
    upsert_school_metadata,
)

__all__ = [
    "Base",
    "engine",
    "SessionLocal",
    "get_db",
    "ProvinceControlLine",
    "SchoolAdmissionLine",
    "SchoolMetadata",
    "ScoreRankTable",
    "InsertResult",
    "MetadataUpsertResult",
    "insert_province_control_lines",
    "insert_school_admission_lines",
    "insert_major_admission_lines",
    "insert_score_rank_rows",
    "upsert_school_metadata",
]
