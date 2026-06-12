"""
初始化 SQLite 数据库：创建所有表。
"""

import logging

from sqlalchemy import inspect, text

from db.database import engine
from db.models import Base

logger = logging.getLogger(__name__)


def _school_unique_includes_category(ddl: str | None) -> bool:
    if not ddl:
        return False
    upper = ddl.upper()
    if "ADMISSION_CATEGORY" not in upper:
        return False
    unique_idx = upper.find("UNIQUE")
    if unique_idx < 0:
        return False
    return "ADMISSION_CATEGORY" in upper[unique_idx:]


def _rebuild_school_table_with_category_unique(conn) -> None:
    """SQLite 无法 ALTER UNIQUE，需重建表以纳入 admission_category。"""
    logger.info("重建 school_admission_line 表（唯一键含 admission_category）")
    conn.execute(
        text(
            """
            CREATE TABLE school_admission_line_new (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                year INTEGER NOT NULL,
                province VARCHAR(32) NOT NULL,
                school_name VARCHAR(128) NOT NULL,
                school_code VARCHAR(32) NOT NULL,
                subject_type VARCHAR(32) NOT NULL,
                admission_category VARCHAR(32) NOT NULL DEFAULT '普通类',
                batch VARCHAR(64) NOT NULL,
                major_group VARCHAR(64),
                min_score FLOAT,
                min_rank INTEGER,
                plan_count INTEGER,
                tie_breaker_text TEXT,
                source_url TEXT,
                created_at DATETIME NOT NULL,
                CONSTRAINT uq_school_admission_line UNIQUE (
                    year, province, school_code, subject_type,
                    admission_category, batch, major_group
                )
            )
            """
        )
    )
    conn.execute(
        text(
            """
            INSERT INTO school_admission_line_new (
                id, year, province, school_name, school_code, subject_type,
                admission_category, batch, major_group, min_score, min_rank,
                plan_count, tie_breaker_text, source_url, created_at
            )
            SELECT
                id, year, province, school_name, school_code, subject_type,
                COALESCE(NULLIF(TRIM(admission_category), ''), '普通类'),
                batch, major_group, min_score, min_rank,
                plan_count, tie_breaker_text, source_url, created_at
            FROM school_admission_line
            """
        )
    )
    conn.execute(text("DROP TABLE school_admission_line"))
    conn.execute(text("ALTER TABLE school_admission_line_new RENAME TO school_admission_line"))
    conn.execute(
        text("CREATE INDEX IF NOT EXISTS ix_school_admission_line_year ON school_admission_line (year)")
    )
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_school_admission_line_province "
            "ON school_admission_line (province)"
        )
    )
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_school_admission_line_school_code "
            "ON school_admission_line (school_code)"
        )
    )
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_school_admission_line_admission_category "
            "ON school_admission_line (admission_category)"
        )
    )
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_school_admission_line_batch "
            "ON school_admission_line (batch)"
        )
    )


def _migrate_schema() -> None:
    """轻量迁移：为已有数据库补充新列（开发期也可用删库重建）。"""
    insp = inspect(engine)
    if not insp.has_table("school_admission_line"):
        return

    columns = {c["name"] for c in insp.get_columns("school_admission_line")}
    with engine.begin() as conn:
        if "tie_breaker_text" not in columns:
            conn.execute(
                text("ALTER TABLE school_admission_line ADD COLUMN tie_breaker_text TEXT")
            )
            logger.info("已迁移: school_admission_line.tie_breaker_text")
        if "admission_category" not in columns:
            conn.execute(
                text(
                    "ALTER TABLE school_admission_line "
                    "ADD COLUMN admission_category VARCHAR(32) NOT NULL DEFAULT '普通类'"
                )
            )
            conn.execute(
                text(
                    "UPDATE school_admission_line "
                    "SET admission_category = '普通类' "
                    "WHERE admission_category IS NULL OR TRIM(admission_category) = ''"
                )
            )
            conn.execute(
                text(
                    "UPDATE school_admission_line "
                    "SET batch = '本科批' "
                    "WHERE batch IS NULL OR TRIM(batch) = ''"
                )
            )
            logger.info("已迁移: school_admission_line.admission_category")

        ddl_row = conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='school_admission_line'")
        ).fetchone()
        ddl = ddl_row[0] if ddl_row else None
        if not _school_unique_includes_category(ddl):
            _rebuild_school_table_with_category_unique(conn)


def init_database() -> None:
    """根据 ORM 模型创建全部数据表（已存在则跳过），并执行轻量迁移。"""
    Base.metadata.create_all(bind=engine)
    _migrate_schema()
    logger.info("数据库初始化完成，表已就绪。")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_database()
