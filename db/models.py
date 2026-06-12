"""
SQLAlchemy ORM 模型定义。
四张核心表：省控线、院校投档线、专业录取线、一分一段表。
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """声明式基类。"""


class ProvinceControlLine(Base):
    """省控线（批次控制分数线）。"""

    __tablename__ = "province_control_line"
    __table_args__ = (
        UniqueConstraint(
            "year", "province", "subject_type", "batch",
            name="uq_province_control_line",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    province: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    subject_type: Mapped[str] = mapped_column(String(32), nullable=False)
    batch: Mapped[str] = mapped_column(String(64), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<ProvinceControlLine {self.year} {self.province} "
            f"{self.subject_type} {self.batch}={self.score}>"
        )


class SchoolAdmissionLine(Base):
    """院校投档 / 录取最低分。"""

    __tablename__ = "school_admission_line"
    __table_args__ = (
        UniqueConstraint(
            "year",
            "province",
            "school_code",
            "subject_type",
            "admission_category",
            "batch",
            "major_group",
            name="uq_school_admission_line",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    province: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    school_name: Mapped[str] = mapped_column(String(128), nullable=False)
    school_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    subject_type: Mapped[str] = mapped_column(String(32), nullable=False)
    admission_category: Mapped[str] = mapped_column(
        String(32), nullable=False, default="普通类", index=True
    )
    batch: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    major_group: Mapped[str | None] = mapped_column(String(64), nullable=True)
    min_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    min_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    plan_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tie_breaker_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return f"<SchoolAdmissionLine {self.year} {self.school_name} min={self.min_score}>"


class MajorAdmissionLine(Base):
    """专业录取线。"""

    __tablename__ = "major_admission_line"
    __table_args__ = (
        UniqueConstraint(
            "year", "province", "school_code", "major_code", "subject_type", "major_group",
            name="uq_major_admission_line",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    province: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    school_name: Mapped[str] = mapped_column(String(128), nullable=False)
    school_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    major_name: Mapped[str] = mapped_column(String(128), nullable=False)
    major_code: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(32), nullable=False)
    major_group: Mapped[str | None] = mapped_column(String(64), nullable=True)
    min_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    min_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return f"<MajorAdmissionLine {self.year} {self.school_name}-{self.major_name}>"


class ScoreRankTable(Base):
    """一分一段表。"""

    __tablename__ = "score_rank_table"
    __table_args__ = (
        UniqueConstraint(
            "year", "province", "subject_type", "score",
            name="uq_score_rank_table",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    province: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    subject_type: Mapped[str] = mapped_column(String(32), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    same_score_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cumulative_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return f"<ScoreRankTable {self.year} {self.province} score={self.score}>"


class SchoolMetadata(Base):
    """院校元数据（人工维护 seed，与投档线 join 用于层次分析）。"""

    __tablename__ = "school_metadata"
    __table_args__ = (
        UniqueConstraint("standard_name", name="uq_school_metadata_standard_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    school_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    standard_name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    province: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    city: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    is_985: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_211: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_double_first_class: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    school_type: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    ownership: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return f"<SchoolMetadata {self.standard_name} city={self.city}>"
