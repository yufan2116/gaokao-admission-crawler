"""
项目全局配置。
省份、年份、请求参数等集中管理，避免硬编码散落各处。
"""

from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent

# 数据目录
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
CLEANED_DIR = DATA_DIR / "cleaned"

# SQLite 数据库路径
DATABASE_URL = f"sqlite:///{BASE_DIR / 'gaokao.db'}"

# 默认目标省份与年份范围（MVP 阶段）
DEFAULT_PROVINCE = "江苏"
DEFAULT_YEARS = [2021, 2022, 2023, 2024]

# HTTP 请求配置
REQUEST_TIMEOUT = 30  # 秒
REQUEST_DELAY = 2.0  # 每次请求间隔（秒），遵守访问频率
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# Excel 列名映射（不同年份表头可能不同，在此统一映射）
EXCEL_COLUMN_ALIASES = {
    "year": ["年份", "year", "年度"],
    "province": ["省份", "province", "省市"],
    "school_name": ["院校名称", "学校名称", "school_name", "院校"],
    "school_code": ["院校代号", "院校代码", "学校代码", "school_code", "代号"],
    "major_name": ["专业名称", "major_name", "专业"],
    "major_code": ["专业代号", "major_code", "专业代码"],
    "subject_type": ["科类", "选科", "subject_type", "科目类别"],
    "batch": ["批次", "batch", "录取批次"],
    "major_group": ["专业组", "专业组代码", "major_group", "院校专业组"],
    "min_score": ["最低分", "投档分", "投档最低分", "分数线", "投档分数线", "min_score", "最低投档分"],
    "tie_breaker_text": ["投档最低分同分考生排序项", "同分排序", "辅助排序分", "同分考生排序项"],
    "avg_score": ["平均分", "avg_score"],
    "max_score": ["最高分", "max_score"],
    "min_rank": ["最低位次", "位次", "名次号", "min_rank", "排名"],
    "plan_count": ["计划数", "招生人数", "招生计划", "投档计划数", "plan_count"],
    "score": ["分数", "score", "控制线", "成绩", "分值"],
    "same_score_count": ["同分人数", "same_score_count", "人数", "本段人数"],
    "cumulative_count": ["累计人数", "cumulative_count", "累计"],
}
