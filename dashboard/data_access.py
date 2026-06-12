"""Dashboard 只读数据访问（SQLite）。"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import DATABASE_URL

_engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)


def query_df(sql: str, params: dict | None = None) -> pd.DataFrame:
    with _engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params or {})


def get_coverage_status() -> dict:
    """各数据类型覆盖状态（只读）。"""
    school_years = query_df(
        """
        SELECT year, COUNT(*) AS cnt
        FROM school_admission_line
        GROUP BY year
        ORDER BY year
        """
    )
    quality = get_quality_stats()
    school_year_set = set(int(y) for y in school_years["year"].tolist())
    return {
        "school_years": sorted(school_year_set),
        "school_by_year": {
            int(row["year"]): int(row["cnt"]) for _, row in school_years.iterrows()
        },
        "rank_total": quality["rank_total"],
        "control_total": quality["control_total"],
    }


def get_year_comparison(years: list[int] | None = None) -> pd.DataFrame:
    """按年份对比 school 投档统计。"""
    target_years = years or [2023, 2024]
    placeholders = ", ".join(f":y{i}" for i in range(len(target_years)))
    params = {f"y{i}": y for i, y in enumerate(target_years)}
    return query_df(
        f"""
        SELECT
            year,
            COUNT(*) AS total_records,
            SUM(CASE WHEN subject_type = '历史类' THEN 1 ELSE 0 END) AS history_count,
            SUM(CASE WHEN subject_type = '物理类' THEN 1 ELSE 0 END) AS physics_count,
            ROUND(AVG(min_score), 2) AS avg_min_score,
            MAX(min_score) AS max_min_score
        FROM school_admission_line
        WHERE year IN ({placeholders})
        GROUP BY year
        ORDER BY year
        """,
        params,
    )


def get_home_stats() -> dict[str, int]:
    row = query_df(
        """
        SELECT
            (SELECT COUNT(*) FROM school_admission_line) AS school_total,
            (SELECT COUNT(DISTINCT year) FROM school_admission_line) AS year_count,
            (SELECT COUNT(DISTINCT province) FROM school_admission_line) AS province_count
        """
    ).iloc[0]
    return {
        "school_total": int(row["school_total"]),
        "year_count": int(row["year_count"]),
        "province_count": int(row["province_count"]),
    }


def get_distinct_values(column: str, table: str = "school_admission_line") -> list:
    allowed = {"year", "province", "subject_type", "admission_category", "batch"}
    if column not in allowed:
        raise ValueError(f"unsupported column: {column}")
    df = query_df(
        f"SELECT DISTINCT {column} AS v FROM {table} "
        f"WHERE {column} IS NOT NULL AND TRIM({column}) != '' "
        f"ORDER BY {column}"
    )
    return df["v"].tolist()


def get_province_coverage() -> pd.DataFrame:
    """各省份插件注册与覆盖计划（静态，来自 province_registry）。"""
    from province_registry import get_province_coverage_rows

    return pd.DataFrame(get_province_coverage_rows())


def get_school_null_rates(
    year: int | None,
    province: str | None,
) -> dict[str, float | int | str]:
    """计算筛选范围内 school 的 min_score/min_rank 空值率与推荐查询模式。"""
    from services.school_query_mode import (
        get_default_query_mode,
        recommend_query_mode,
    )

    conditions = ["1=1"]
    params: dict = {}
    if year is not None:
        conditions.append("year = :year")
        params["year"] = year
    if province:
        conditions.append("province = :province")
        params["province"] = province

    where = " AND ".join(conditions)
    row = query_df(
        f"""
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN min_score IS NULL THEN 1 ELSE 0 END) AS null_score,
            SUM(CASE WHEN min_rank IS NULL THEN 1 ELSE 0 END) AS null_rank
        FROM school_admission_line
        WHERE {where}
        """,
        params,
    ).iloc[0]
    total = int(row["total"] or 0)
    if total == 0:
        mode = get_default_query_mode(province) if province else "mixed"
        return {
            "total": 0,
            "min_score_null_rate": 1.0,
            "min_rank_null_rate": 1.0,
            "recommended_query_mode": mode,
        }

    ms_rate = float(row["null_score"] or 0) / total
    mr_rate = float(row["null_rank"] or 0) / total
    return {
        "total": total,
        "min_score_null_rate": ms_rate,
        "min_rank_null_rate": mr_rate,
        "recommended_query_mode": recommend_query_mode(ms_rate, mr_rate),
    }


def resolve_dashboard_query_mode(
    year: int | None,
    province: str | None,
) -> str:
    """Dashboard 查询/图表模式：山东固定 rank，其余按空值率自动切换。"""
    from services.school_query_mode import get_default_query_mode

    if province == "山东":
        return "rank"
    stats = get_school_null_rates(year, province)
    if stats["total"] == 0 and province:
        return get_default_query_mode(province)
    return str(stats["recommended_query_mode"])


_METADATA_JOIN = """
LEFT JOIN school_metadata m ON (
    s.school_name = m.standard_name
    OR s.school_name = m.school_name
    OR s.school_name LIKE m.standard_name || '%'
)
"""


def get_metadata_distinct_values(column: str) -> list:
    allowed = {"city", "school_type", "ownership", "province"}
    if column not in allowed:
        raise ValueError(f"unsupported metadata column: {column}")
    df = query_df(
        f"SELECT DISTINCT {column} AS v FROM school_metadata "
        f"WHERE {column} IS NOT NULL AND TRIM({column}) != '' "
        f"ORDER BY {column}"
    )
    return df["v"].tolist()


def get_metadata_tier_counts() -> dict[str, int]:
    row = query_df(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN is_985 THEN 1 ELSE 0 END) AS count_985,
            SUM(CASE WHEN is_211 THEN 1 ELSE 0 END) AS count_211,
            SUM(CASE WHEN is_double_first_class THEN 1 ELSE 0 END) AS count_dfc
        FROM school_metadata
        """
    ).iloc[0]
    return {k: int(v) for k, v in row.items()}


def get_metadata_by_city() -> pd.DataFrame:
    return query_df(
        """
        SELECT city AS 城市, COUNT(*) AS 学校数
        FROM school_metadata
        WHERE city IS NOT NULL AND TRIM(city) != ''
        GROUP BY city
        ORDER BY 学校数 DESC, 城市
        """
    )


def get_metadata_by_school_type() -> pd.DataFrame:
    return query_df(
        """
        SELECT school_type AS 学校类型, COUNT(*) AS 学校数
        FROM school_metadata
        WHERE school_type IS NOT NULL AND TRIM(school_type) != ''
        GROUP BY school_type
        ORDER BY 学校数 DESC, 学校类型
        """
    )


def search_schools_enriched(
    year: int | None,
    province: str | None,
    subject_type: str | None,
    keyword: str | None,
    admission_category: str | None = None,
    batch: str | None = None,
    min_score_min: float | None = None,
    min_score_max: float | None = None,
    rank_min: int | None = None,
    rank_max: int | None = None,
    is_985: bool | None = None,
    is_211: bool | None = None,
    is_double_first_class: bool | None = None,
    city: str | None = None,
    school_type: str | None = None,
    limit: int = 500,
) -> pd.DataFrame:
    conditions = ["1=1"]
    params: dict = {"limit": limit}
    if year is not None:
        conditions.append("s.year = :year")
        params["year"] = year
    if province:
        conditions.append("s.province = :province")
        params["province"] = province
    if subject_type:
        conditions.append("s.subject_type = :subject_type")
        params["subject_type"] = subject_type
    if admission_category:
        conditions.append("s.admission_category = :admission_category")
        params["admission_category"] = admission_category
    if batch:
        conditions.append("s.batch = :batch")
        params["batch"] = batch
    if keyword and keyword.strip():
        conditions.append("s.school_name LIKE :keyword")
        params["keyword"] = f"%{keyword.strip()}%"
    if min_score_min is not None:
        conditions.append("s.min_score IS NOT NULL AND s.min_score >= :min_score_min")
        params["min_score_min"] = min_score_min
    if min_score_max is not None:
        conditions.append("s.min_score IS NOT NULL AND s.min_score <= :min_score_max")
        params["min_score_max"] = min_score_max
    if rank_min is not None:
        conditions.append("s.min_rank IS NOT NULL AND s.min_rank >= :rank_min")
        params["rank_min"] = rank_min
    if rank_max is not None:
        conditions.append("s.min_rank IS NOT NULL AND s.min_rank <= :rank_max")
        params["rank_max"] = rank_max
    if is_985 is not None:
        conditions.append("m.is_985 = :is_985")
        params["is_985"] = 1 if is_985 else 0
    if is_211 is not None:
        conditions.append("m.is_211 = :is_211")
        params["is_211"] = 1 if is_211 else 0
    if is_double_first_class is not None:
        conditions.append("m.is_double_first_class = :is_dfc")
        params["is_dfc"] = 1 if is_double_first_class else 0
    if city:
        conditions.append("m.city = :city")
        params["city"] = city
    if school_type:
        conditions.append("m.school_type = :school_type")
        params["school_type"] = school_type

    use_rank_order = (rank_min is not None or rank_max is not None) and min_score_min is None and min_score_max is None
    order_sql = (
        "ORDER BY (s.min_rank IS NULL), s.min_rank ASC, s.school_name"
        if use_rank_order
        else "ORDER BY (s.min_score IS NULL), s.min_score DESC, s.school_name"
    )
    where = " AND ".join(conditions)
    return query_df(
        f"""
        SELECT
            s.year, s.province, s.subject_type, s.admission_category, s.batch,
            s.school_name, s.school_code, s.major_group, s.min_score, s.min_rank,
            s.plan_count,
            m.standard_name, m.city, m.is_985, m.is_211, m.is_double_first_class,
            m.school_type, m.ownership
        FROM school_admission_line s
        {_METADATA_JOIN}
        WHERE {where}
        {order_sql}
        LIMIT :limit
        """,
        params,
    )


def get_tier_reachable_schools(
    year: int | None,
    province: str | None,
    subject_type: str | None,
    max_score: float,
    tier: str,
    limit: int = 100,
) -> pd.DataFrame:
    """某分数段内可达的指定层次院校（去重 standard_name）。"""
    tier_filters = {
        "985": "m.is_985 = 1",
        "211": "m.is_211 = 1",
        "双一流": "m.is_double_first_class = 1",
    }
    tier_sql = tier_filters.get(tier)
    if not tier_sql:
        raise ValueError(f"unsupported tier: {tier}")

    conditions = ["s.min_score IS NOT NULL", "s.min_score <= :max_score", tier_sql]
    params: dict = {"max_score": max_score, "limit": limit}
    if year is not None:
        conditions.append("s.year = :year")
        params["year"] = year
    if province:
        conditions.append("s.province = :province")
        params["province"] = province
    if subject_type:
        conditions.append("s.subject_type = :subject_type")
        params["subject_type"] = subject_type

    where = " AND ".join(conditions)
    return query_df(
        f"""
        SELECT
            m.standard_name AS 院校,
            m.city AS 城市,
            MIN(s.min_score) AS 最低投档分,
            s.subject_type AS 科类,
            s.year AS 年份,
            m.is_985 AS 985,
            m.is_211 AS 211,
            m.is_double_first_class AS 双一流
        FROM school_admission_line s
        INNER JOIN school_metadata m ON (
            s.school_name = m.standard_name
            OR s.school_name = m.school_name
            OR s.school_name LIKE m.standard_name || '%'
        )
        WHERE {where}
        GROUP BY m.standard_name, m.city, s.subject_type, s.year,
                 m.is_985, m.is_211, m.is_double_first_class
        ORDER BY 最低投档分 DESC
        LIMIT :limit
        """,
        params,
    )


def search_schools(
    year: int | None,
    province: str | None,
    subject_type: str | None,
    keyword: str | None,
    admission_category: str | None = None,
    batch: str | None = None,
    min_score_min: float | None = None,
    min_score_max: float | None = None,
    limit: int = 500,
) -> pd.DataFrame:
    conditions = ["1=1"]
    params: dict = {"limit": limit}
    if year is not None:
        conditions.append("year = :year")
        params["year"] = year
    if province:
        conditions.append("province = :province")
        params["province"] = province
    if subject_type:
        conditions.append("subject_type = :subject_type")
        params["subject_type"] = subject_type
    if admission_category:
        conditions.append("admission_category = :admission_category")
        params["admission_category"] = admission_category
    if batch:
        conditions.append("batch = :batch")
        params["batch"] = batch
    if keyword and keyword.strip():
        conditions.append("school_name LIKE :keyword")
        params["keyword"] = f"%{keyword.strip()}%"
    if min_score_min is not None:
        conditions.append("min_score IS NOT NULL AND min_score >= :min_score_min")
        params["min_score_min"] = min_score_min
    if min_score_max is not None:
        conditions.append("min_score IS NOT NULL AND min_score <= :min_score_max")
        params["min_score_max"] = min_score_max

    where = " AND ".join(conditions)
    return query_df(
        f"""
        SELECT year, province, subject_type, admission_category, batch,
               school_name, school_code, major_group, min_score, min_rank, plan_count
        FROM school_admission_line
        WHERE {where}
        ORDER BY (min_score IS NULL), min_score DESC, school_name
        LIMIT :limit
        """,
        params,
    )


def get_school_chart_data(
    year: int | None,
    province: str | None,
    subject_type: str | None,
    admission_category: str | None = None,
    batch: str | None = None,
    *,
    mode: str = "score",
) -> pd.DataFrame:
    value_col = "min_rank" if mode == "rank" else "min_score"
    conditions = [f"{value_col} IS NOT NULL"]
    params: dict = {}
    if year is not None:
        conditions.append("year = :year")
        params["year"] = year
    if province:
        conditions.append("province = :province")
        params["province"] = province
    if subject_type:
        conditions.append("subject_type = :subject_type")
        params["subject_type"] = subject_type
    if admission_category:
        conditions.append("admission_category = :admission_category")
        params["admission_category"] = admission_category
    if batch:
        conditions.append("batch = :batch")
        params["batch"] = batch

    where = " AND ".join(conditions)
    return query_df(
        f"""
        SELECT year, province, subject_type, school_name, min_score, min_rank
        FROM school_admission_line
        WHERE {where}
        """,
        params,
    )


def get_school_export_data() -> pd.DataFrame:
    """导出用全量 school 数据。"""
    return query_df(
        """
        SELECT year, province, subject_type, admission_category, batch,
               school_name, school_code, major_group, min_score, min_rank, plan_count
        FROM school_admission_line
        ORDER BY year DESC, min_score DESC, school_name
        """
    )


def get_category_breakdown() -> pd.DataFrame:
    """按招生类别 × 批次统计。"""
    return query_df(
        """
        SELECT admission_category AS 招生类别,
               batch AS 批次,
               COUNT(*) AS 记录数
        FROM school_admission_line
        GROUP BY admission_category, batch
        ORDER BY admission_category, batch
        """
    )


def get_top_schools(limit: int = 20) -> pd.DataFrame:
    return query_df(
        """
        SELECT school_name, min_score, subject_type, year,
               admission_category, batch
        FROM school_admission_line
        WHERE min_score IS NOT NULL
        ORDER BY min_score DESC
        LIMIT :limit
        """,
        {"limit": int(limit)},
    )


def get_quality_stats() -> dict:
    counts = query_df(
        """
        SELECT
            (SELECT COUNT(*) FROM school_admission_line) AS school_total,
            (SELECT COUNT(*) FROM score_rank_table) AS rank_total,
            (SELECT COUNT(*) FROM province_control_line) AS control_total,
            (SELECT COUNT(*) FROM school_admission_line
             WHERE subject_type IS NULL OR TRIM(subject_type) = '') AS school_empty_subject,
            (SELECT COUNT(*) FROM school_admission_line
             WHERE school_name IS NULL OR TRIM(school_name) = '') AS school_empty_name,
            (SELECT COUNT(*) FROM score_rank_table
             WHERE subject_type IS NULL OR TRIM(subject_type) = '') AS rank_empty_subject,
            (SELECT COUNT(*) FROM province_control_line
             WHERE subject_type IS NULL OR TRIM(subject_type) = '') AS control_empty_subject
        """
    ).iloc[0]
    return {k: int(v) for k, v in counts.items()}
