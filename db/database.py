"""
数据库连接与会话管理。
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from config import DATABASE_URL

# echo=False 避免调试时刷屏；需要 SQL 日志时可改为 True
engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},  # SQLite 多线程读
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖注入用的会话生成器（预留）。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
