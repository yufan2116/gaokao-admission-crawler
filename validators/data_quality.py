"""
数据质量检查（Phase 7）。

检查各表记录数、科类分布、空值与一分一段表累计人数单调性。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import func
from sqlalchemy.orm import Session

from db.models import (
    MajorAdmissionLine,
    ProvinceControlLine,
    SchoolAdmissionLine,
    ScoreRankTable,
)
from services.school_query_mode import (
    compute_school_null_rates,
    get_default_query_mode,
    recommend_query_mode,
)


@dataclass
class DataQualityReport:
    """数据质量报告。"""

    year: int
    province: str
    table_counts: dict[str, int] = field(default_factory=dict)
    school_by_subject: dict[str, int] = field(default_factory=dict)
    rank_by_subject: dict[str, int] = field(default_factory=dict)
    school_min_score_range: tuple[float | None, float | None] = (None, None)
    empty_subject_type: dict[str, int] = field(default_factory=dict)
    empty_school_name: int = 0
    rank_monotonic_violations: list[dict] = field(default_factory=list)
    rank_subject_coverage: list[str] = field(default_factory=list)
    rank_score_ranges: dict[str, tuple[float | None, float | None]] = field(default_factory=dict)
    control_batches: list[str] = field(default_factory=list)
    control_by_batch: dict[str, int] = field(default_factory=dict)
    min_score_null_rate: float = 0.0
    min_rank_null_rate: float = 0.0
    recommended_query_mode: str = "mixed"
    source_quality: str | None = None
    requires_manual_review: bool = False
    ocr_record_count: int = 0
    invalid_school_name_count: int = 0
    invalid_school_name_rate: float = 0.0
    expected_rank_subjects: list[str] = field(
        default_factory=lambda: ["历史类", "物理类"]
    )

    def to_lines(self) -> list[str]:
        """格式化为可打印文本行。"""
        lines: list[str] = []
        lines.append(f"数据质量报告 [{self.year} {self.province}]")
        lines.append("")

        lines.append("## 各表记录数")
        for table, count in self.table_counts.items():
            lines.append(f"  {table}: {count}")
        lines.append("")

        lines.append("## school 按 subject_type 分布")
        if self.school_by_subject:
            for st, cnt in sorted(self.school_by_subject.items()):
                lines.append(f"  {st}: {cnt}")
        else:
            lines.append("  (无数据)")
        lines.append("")

        lines.append("## rank 按 subject_type 分布")
        if self.rank_by_subject:
            for st, cnt in sorted(self.rank_by_subject.items()):
                lines.append(f"  {st}: {cnt}")
        else:
            lines.append("  (无数据)")
        lines.append("")

        lines.append("## rank 科类覆盖（江苏 2021-2024 期望：历史类 + 物理类）")
        present = set(self.rank_by_subject.keys()) - {"(空)"}
        missing = [s for s in self.expected_rank_subjects if s not in present]
        if missing:
            lines.append(f"  缺失科类: {', '.join(missing)}")
        else:
            lines.append("  历史类/物理类均已覆盖")
        lines.append("")

        lines.append("## rank 分数范围（按科类）")
        if self.rank_score_ranges:
            for st, (lo, hi) in sorted(self.rank_score_ranges.items()):
                lines.append(f"  {st}: min={lo}, max={hi}")
        else:
            lines.append("  (无数据)")
        lines.append("")

        lines.append("## control 批次覆盖")
        if self.control_batches:
            for batch in self.control_batches:
                cnt = self.control_by_batch.get(batch, 0)
                lines.append(f"  {batch}: {cnt}")
        else:
            lines.append("  (无数据)")
        lines.append("")

        lo, hi = self.school_min_score_range
        lines.append("## school min_score 范围")
        lines.append(f"  min={lo}, max={hi}")
        lines.append("")

        lines.append("## school 查询模式建议")
        lines.append(f"  min_score_null_rate: {self.min_score_null_rate:.2%}")
        lines.append(f"  min_rank_null_rate: {self.min_rank_null_rate:.2%}")
        lines.append(f"  recommended_query_mode: {self.recommended_query_mode}")
        if self.source_quality:
            lines.append(f"  source_quality: {self.source_quality}")
            lines.append(f"  requires_manual_review: {str(self.requires_manual_review).lower()}")
            lines.append(f"  ocr_record_count: {self.ocr_record_count}")
            lines.append(f"  invalid_school_name_count: {self.invalid_school_name_count}")
            lines.append(f"  invalid_school_name_rate: {self.invalid_school_name_rate:.2%}")
            lines.append("  警告: OCR 实验数据不保证 100% 准确，请人工复核 ocr_preview")
        lines.append("")

        lines.append("## 空值检查")
        for table, cnt in self.empty_subject_type.items():
            lines.append(f"  {table} subject_type 为空: {cnt}")
        lines.append(f"  school school_name 为空: {self.empty_school_name}")
        lines.append("")

        lines.append("## rank cumulative_count 单调性（score 降低时 cumulative 应递增）")
        if not self.rank_monotonic_violations:
            lines.append("  未发现异常")
        else:
            lines.append(f"  异常分段数: {len(self.rank_monotonic_violations)}")
            for v in self.rank_monotonic_violations[:10]:
                lines.append(
                    f"    [{v['subject_type']}] score {v['higher_score']}({v['higher_cum']}) "
                    f"→ {v['lower_score']}({v['lower_cum']})"
                )
            if len(self.rank_monotonic_violations) > 10:
                lines.append(f"    ... 另有 {len(self.rank_monotonic_violations) - 10} 处")

        return lines


def _filter_year_province(q, model, year: int, province: str):
    return q.filter(model.year == year, model.province == province)


def _count_empty_subject(session: Session, model, year: int, province: str) -> int:
    q = session.query(model).filter(
        model.year == year,
        model.province == province,
        (model.subject_type.is_(None)) | (model.subject_type == ""),
    )
    return q.count()


def _check_rank_monotonic(
    session: Session,
    year: int,
    province: str,
) -> list[dict]:
    """
    按 score 降序检查 cumulative_count 是否非递减。
    分数降低时累计人数应增加或持平。
    """
    violations: list[dict] = []
    subject_types = (
        session.query(ScoreRankTable.subject_type)
        .filter(ScoreRankTable.year == year, ScoreRankTable.province == province)
        .distinct()
        .all()
    )

    for (subject_type,) in subject_types:
        rows = (
            session.query(ScoreRankTable)
            .filter(
                ScoreRankTable.year == year,
                ScoreRankTable.province == province,
                ScoreRankTable.subject_type == subject_type,
                ScoreRankTable.cumulative_count.isnot(None),
            )
            .order_by(ScoreRankTable.score.desc())
            .all()
        )
        for i in range(len(rows) - 1):
            higher = rows[i]
            lower = rows[i + 1]
            if higher.cumulative_count > lower.cumulative_count:
                violations.append(
                    {
                        "subject_type": subject_type,
                        "higher_score": higher.score,
                        "higher_cum": higher.cumulative_count,
                        "lower_score": lower.score,
                        "lower_cum": lower.cumulative_count,
                    }
                )
    return violations


def run_data_quality_check(
    session: Session,
    year: int,
    province: str,
) -> DataQualityReport:
    """执行数据质量检查并返回报告。"""
    report = DataQualityReport(year=year, province=province)

    report.table_counts = {
        "province_control_line": _filter_year_province(
            session.query(ProvinceControlLine), ProvinceControlLine, year, province
        ).count(),
        "school_admission_line": _filter_year_province(
            session.query(SchoolAdmissionLine), SchoolAdmissionLine, year, province
        ).count(),
        "major_admission_line": _filter_year_province(
            session.query(MajorAdmissionLine), MajorAdmissionLine, year, province
        ).count(),
        "score_rank_table": _filter_year_province(
            session.query(ScoreRankTable), ScoreRankTable, year, province
        ).count(),
    }

    school_dist = (
        session.query(SchoolAdmissionLine.subject_type, func.count())
        .filter(SchoolAdmissionLine.year == year, SchoolAdmissionLine.province == province)
        .group_by(SchoolAdmissionLine.subject_type)
        .all()
    )
    report.school_by_subject = {st or "(空)": cnt for st, cnt in school_dist}

    rank_dist = (
        session.query(ScoreRankTable.subject_type, func.count())
        .filter(ScoreRankTable.year == year, ScoreRankTable.province == province)
        .group_by(ScoreRankTable.subject_type)
        .all()
    )
    report.rank_by_subject = {st or "(空)": cnt for st, cnt in rank_dist}

    score_range = (
        session.query(func.min(SchoolAdmissionLine.min_score), func.max(SchoolAdmissionLine.min_score))
        .filter(
            SchoolAdmissionLine.year == year,
            SchoolAdmissionLine.province == province,
            SchoolAdmissionLine.min_score.isnot(None),
        )
        .one()
    )
    report.school_min_score_range = (score_range[0], score_range[1])

    report.empty_subject_type = {
        "school_admission_line": _count_empty_subject(session, SchoolAdmissionLine, year, province),
        "score_rank_table": _count_empty_subject(session, ScoreRankTable, year, province),
        "province_control_line": _count_empty_subject(session, ProvinceControlLine, year, province),
    }

    report.empty_school_name = (
        session.query(SchoolAdmissionLine)
        .filter(
            SchoolAdmissionLine.year == year,
            SchoolAdmissionLine.province == province,
            (SchoolAdmissionLine.school_name.is_(None)) | (SchoolAdmissionLine.school_name == ""),
        )
        .count()
    )

    report.rank_monotonic_violations = _check_rank_monotonic(session, year, province)

    present_subjects = set(report.rank_by_subject.keys()) - {"(空)"}
    report.rank_subject_coverage = [
        s for s in report.expected_rank_subjects if s not in present_subjects
    ]

    for subject_type in present_subjects:
        score_range = (
            session.query(func.min(ScoreRankTable.score), func.max(ScoreRankTable.score))
            .filter(
                ScoreRankTable.year == year,
                ScoreRankTable.province == province,
                ScoreRankTable.subject_type == subject_type,
            )
            .one()
        )
        report.rank_score_ranges[subject_type] = (score_range[0], score_range[1])

    control_dist = (
        session.query(ProvinceControlLine.batch, func.count())
        .filter(ProvinceControlLine.year == year, ProvinceControlLine.province == province)
        .group_by(ProvinceControlLine.batch)
        .all()
    )
    report.control_by_batch = {batch or "(空)": cnt for batch, cnt in control_dist}
    report.control_batches = sorted(report.control_by_batch.keys())

    ms_rate, mr_rate, school_total = compute_school_null_rates(session, year, province)
    if school_total > 0:
        report.min_score_null_rate = ms_rate
        report.min_rank_null_rate = mr_rate
        report.recommended_query_mode = recommend_query_mode(ms_rate, mr_rate)
    else:
        report.recommended_query_mode = get_default_query_mode(province)

    from parsers.parse_image_table import OCR_SOURCE_PREFIX

    ocr_count = (
        session.query(SchoolAdmissionLine)
        .filter(
            SchoolAdmissionLine.year == year,
            SchoolAdmissionLine.province == province,
            SchoolAdmissionLine.source_url.like(f"{OCR_SOURCE_PREFIX}%"),
        )
        .count()
    )
    report.ocr_record_count = ocr_count
    if ocr_count > 0:
        report.source_quality = "ocr_experimental"
        report.requires_manual_review = True
        from normalizers.school_name import is_invalid_school_name

        ocr_rows = (
            session.query(SchoolAdmissionLine)
            .filter(
                SchoolAdmissionLine.year == year,
                SchoolAdmissionLine.province == province,
                SchoolAdmissionLine.source_url.like(f"{OCR_SOURCE_PREFIX}%"),
            )
            .all()
        )
        invalid_count = sum(1 for row in ocr_rows if is_invalid_school_name(row.school_name))
        report.invalid_school_name_count = invalid_count
        report.invalid_school_name_rate = invalid_count / ocr_count

    return report
