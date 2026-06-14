# gaokao-admission-crawler

国内高校各系招生分数线采集与整理工具。

## Current Stable Version

**MVP+ Stable**（`mvp-plus-stable`，Phase 16 冻结）

- **已结构化可查询**：江苏（2021–2024 school）、浙江 / 山东 / 广东（2024 school；广东为普通类 PDF）
- **Source-aware 已注册未结构化**：河南（`verification_required`）、福建（`waf_blocked`）、河北（`connection_reset`）
- 这是 **MVP+ 稳定版本**，不是全国完整库；详见 [`docs/release_notes.md`](docs/release_notes.md)

回归测试：

```bash
python scripts/run_regression.py
# → data/cleaned/regression_report.json
```

**Phase 8** 起采用多省插件架构（`provinces/` + `province_registry.py`），核心 parse / normalize / validate 流水线全国共用，各省仅实现发现与解析入口。

## 项目目标

爬取并结构化存储 **2025 年以前** 的高考录取线数据：

- **已入库可查询**：江苏省（2021–2024）、浙江省（2024 school）、山东省（2024 school）
- **已发现/下载未入库**：河南省（2024 school；RAR/图片 Word）
- **部分已入库**：广东省（2024 school 普通类历史/物理；机器可读 PDF；艺体类暂不建模）
- **已注册待采集**：福建省（2024 school 普通类；Excel/PDF；艺体类 skipped_unsupported_category）、河北省（2024 school 普通类本科/专科；Excel/PDF；艺体/对口 skipped_unsupported_category）
- **能力**：数据采集 → 解析清洗 → SQLite 存储 → Dashboard 可视化

## Roadmap

| 省份 | 状态 |
|------|------|
| 江苏 | 已入库（2021–2024 school / rank / control） |
| 浙江 | 已入库（2024 school） |
| 山东 | 已入库（2024 school） |
| 河南 | 已下载未入库（2024 school；RAR/图片 Word；官方验证码页不绕过） |
| 广东 | 部分已入库（2024 school 普通类；艺体类 skipped_unsupported_category） |
| 福建 | 已注册（2024 school 普通类本科/专科；艺体类 skipped_unsupported_category） |
| 河北 | 已注册（2024 school 普通类本科/专科；专业粒度；艺体/对口 skipped_unsupported_category） |

### 当前省份数据状态（Phase 12.1）

以下与 `configs/province_data_availability.py`、Dashboard「Province Availability」及 `GET /province-availability` 一致。

| 省份 | 年份 | 可结构化 | 数据格式 | 入库状态 | 查询模式 | Access Status | 说明 |
|------|------|----------|----------|----------|----------|---------------|------|
| 江苏 | 2021–2024 | 是 | Excel | 已入库 | 按分数 | available | school / rank / control 均已入库 |
| 浙江 | 2024 | 是 | Excel | 已入库 | 按分数 | available | 普通类一、二段平行投档 Excel 已入库 |
| 山东 | 2024 | 是 | Excel | 已入库 | 按位次 | available | 常规批投档表以 min_rank 为主 |
| 河南 | 2024 | 否 | RAR + image Word + verification page | 已下载未入库 | 不支持（PDF/图片源） | verification_required | 公开 RAR 内为图片型 Word；官方数据中心需验证码 |
| 广东 | 2024 | 部分 | ZIP + machine-readable PDF | 部分已入库 | 按分数 | partial | 普通类历史/物理已入库；艺体类已下载但暂不建模 |
| 福建 | 2024 | 是 | Excel / PDF | 未开始 | 按分数 | waf_blocked | 普通类本科/专科投档；艺体类 skipped_unsupported_category |
| 河北 | 2024 | 是 | Excel / PDF | 未开始 | 按分数 | connection_reset | 普通类本科/专科专业粒度；艺体/对口 skipped_unsupported_category |

新增省份：在 `provinces/<name>/` 实现 `ProvincePlugin` 并注册到 `province_registry.py`，无需修改核心解析层。

## 项目结构

```
gaokao-admission-crawler/
├── README.md
├── requirements.txt
├── config.py              # 全局配置（请求、列名映射等）
├── main.py                # CLI 入口（经 province_registry 调度）
├── province_registry.py   # 省份插件注册表
├── sources/               # Phase 15 数据源适配层
│   ├── base.py            # SourceType / AccessStatus / SourceAdapter
│   ├── html_site.py       # HTML_LIST（江苏、山东）
│   ├── seed_site.py       # SEED_ONLY（浙江、福建、河北）
│   ├── attachment_site.py # 附件直链 seed
│   ├── archive_site.py    # ARCHIVE（广东 ZIP、河南 RAR）
│   ├── protected_site.py  # PROTECTED（河南 datacenter 等）
│   └── registry.py        # 省份 → SourceAdapter 工厂
├── provinces/             # Phase 8 多省插件
│   ├── base.py            # ProvincePlugin / SubjectMode
│   ├── jiangsu/           # 江苏（已完成）
│   ├── zhejiang/          # 浙江（2024 school 已完成）
│   ├── shandong/          # 山东（2024 school 已完成）
│   ├── henan/             # 河南（2024 school，Phase 11）
│   ├── guangdong/         # 广东（2024 school，Phase 12）
│   ├── fujian/            # 福建（2024 school，Phase 14）
│   └── hebei/             # 河北（2024 school，Phase 14.1）
├── crawlers/              # 爬虫、数据源注册、自动发现
│   └── discovery.py
├── parsers/               # HTML / Excel / PDF 解析
├── normalizers/           # 标准化层
├── validators/            # 业务校验
├── db/                    # SQLAlchemy 模型、repository
├── dashboard/             # Streamlit 可视化
├── app/                   # FastAPI 查询与换算接口
├── services/
│   ├── national_scan.py       # Phase 17 全国扫描
│   └── province_csv_export.py # Phase 21 分省 CSV 导出
├── configs/
├── docs/
├── data/
│   ├── raw/                   # 原始下载
│   ├── cleaned/               # 清洗/报告 JSON
│   └── export/csv/            # 分省 CSV 导出（gitignore，本地生成）
└── scripts/
```

## 旧版说明（MVP）

早期版本仅聚焦江苏省 2021–2024；现架构已支持扩展全国，见上方 Roadmap。

## 数据库表

| 表名 | 说明 |
|------|------|
| `province_control_line` | 省控线（批次控制分） |
| `school_admission_line` | 院校投档 / 录取线 |
| `major_admission_line` | 专业录取线 |
| `score_rank_table` | 一分一段表 |
| `school_metadata` | 院校元数据（985/211/城市/类型等，人工 seed） |

## 安装依赖

要求 **Python 3.10+**。

```bash
cd gaokao-admission-crawler
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
# source .venv/bin/activate

pip install -r requirements.txt
```

可选 PDF 支持：

```bash
pip install pdfplumber
```

可选图片表格 OCR（实验，见 Phase 20）：

```bash
pip install paddleocr paddlepaddle
```

## 初始化数据库

```bash
python main.py init-db
```

将在项目根目录创建 `gaokao.db` 及数据表（含 `school_metadata`）。

### 导入学校元数据（Phase 9）

`school_metadata` 为**人工维护 seed**，用于演示投档线与院校元数据的 join 分析，**不声称全国学校库完整**。

```bash
python main.py import-school-metadata data/manual/school_metadata_seed.csv
```

按 `standard_name` 或 `school_name` upsert，输出 `inserted / updated / skipped`。

关联查询：`GET /schools/enriched`（支持 `is_985`、`city`、`score_min` 等筛选）。

## 运行爬虫（江苏省）

```bash
# 默认最多下载 1 个文件（避免过量请求）
python main.py crawl-jiangsu

# 指定年份、最多下载 2 个文件
python main.py crawl-jiangsu --year 2024 --max-files 2
```

原始文件保存至 `data/raw/jiangsu/{year}/`。

爬虫行为：

- 所有请求携带 `User-Agent`
- 每次请求间隔 2 秒（可在 `config.py` 调整 `REQUEST_DELAY`）
- 访问前检查 `robots.txt`
- 失败时记录日志并跳过，不中断整体流程

## 解析 Excel

将下载或手动放置的 Excel 解析为标准化 CSV：

```bash
python main.py parse-excel path/to/file.xlsx

# 指定默认年份（表内无年份列时）
python main.py parse-excel data/raw/jiangsu/2024/xxx.xlsx --year 2024
```

输出保存至 `data/cleaned/`。

测试脚本：

```bash
python scripts/test_parse_excel.py path/to/file.xlsx 2024
```

## 导入 Excel 到数据库（Phase 1.5）

将 Excel 解析、字段标准化后写入 SQLite，支持去重与校验：

```bash
# 院校投档线
python main.py import-excel data/raw/jiangsu/2024/example.xlsx --type school --year 2024 --province 江苏

# 专业录取线
python main.py import-excel path/to/majors.xlsx --type major --year 2024 --province 江苏

# 省控线
python main.py import-excel path/to/control.xlsx --type control --year 2024 --province 江苏

# 一分一段表
python main.py import-excel path/to/rank.xlsx --type rank --year 2024 --province 江苏
```

**流程**：读取 Excel → `parse_excel` 标准化 → 必填字段校验 → 按 `--type` 写入对应表。

**输出统计**：`inserted`（新写入）/ `skipped`（库中已存在，按业务键去重）/ `failed`（校验失败或写入异常）。

**去重规则**：

| 表 | 唯一键 |
|----|--------|
| 省控线 | year + province + subject_type + batch |
| 院校线 | year + province + school_name + subject_type + batch + major_group |
| 专业线 | year + province + school_name + major_name + subject_type + major_group |
| 一分一段 | year + province + subject_type + score |

**必填字段**：

- `school`：year, province, school_name, subject_type, min_score
- `major`：year, province, school_name, major_name, subject_type, min_score
- `control`：year, province, subject_type, batch, score
- `rank`：year, province, subject_type, score, cumulative_count

重复导入同一文件时，已存在记录会被跳过，不会报错。

## Phase 4：标准化层（Normalization Layer）

统一数据流：

```
HTML / PDF / Excel
        ↓
     parse
        ↓
    normalize
        ↓
    validate
        ↓
    database
```

### 标准 Schema

| 类型 | 标准字段 |
|------|----------|
| school | year, province, subject_type, school_code, school_name, major_group, min_score, min_rank, tie_breaker_text, plan_count |
| rank | year, province, subject_type, score, same_score_count, cumulative_count |
| control | year, province, subject_type, batch, score |
| major | year, province, subject_type, school_name, major_name, min_score, min_rank |

### 标准化输出

```bash
python main.py normalize-excel data/raw/jiangsu/2024/school/attachments/xxx.xlsx \
    --type school --year 2024 --province 江苏
```

输出至 `data/cleaned/normalized_xxx.csv`。

### 校验规则（validators/validate.py）

- **school**：`min_score` 须在 100–750；`subject_type` 须为文科/理科/历史类/物理类/综合改革
- **rank**：累计人数随分数降低应递增（表级检查）
- **control**：`score` 必填
- **major**：`major_name` 非空

### 比较两个标准化 CSV

```bash
python scripts/compare_normalized.py data/cleaned/a.csv data/cleaned/b.csv
```

输出列结构差异、空值率、重复率、数据量对比。

### 导入（已接入 normalize + validate）

```bash
python main.py import-excel path/to/file.xlsx --type school --year 2024 --province 江苏
```

内部流程：parse → normalize → validate → 入库。

## Phase 5：FastAPI 查询 API

基于 SQLite 提供 JSON 查询接口，无前端、无推荐算法。

### 安装 API 依赖

```bash
pip install fastapi uvicorn[standard]
# 或
pip install -r requirements.txt
```

### 启动服务

```bash
# 确保已有数据
python main.py init-db
python main.py import-excel data/raw/jiangsu/2024/school/attachments/sample_历史类投档线.xlsx --type school --year 2024 --province 江苏

# 启动 API
uvicorn app.api:app --reload
```

### 接口列表

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 `{"status":"ok"}` |
| GET | `/schools` | 院校投档线查询 |
| GET | `/ranks` | 一分一段表查询 |
| GET | `/controls` | 省控线查询 |
| GET | `/stats/summary` | 数据库汇总统计 |
| GET | `/province-availability` | 各省数据源可机器读取性、入库状态与 `access_status`（Phase 15） |
| GET | `/convert/score-to-rank` | 分数查位次 |
| GET | `/convert/rank-to-score` | 位次查分数 |
| GET | `/convert/equivalent-score` | 跨年等效分换算 |
| GET | `/schools/by-score` | 按分数区间筛选院校（山东等 min_score 缺失省份会返回 400） |
| GET | `/schools/by-rank` | 按位次区间筛选院校（山东等推荐） |
| GET | `/schools/by-equivalent-score` | 按等效分筛选往年院校 |

### 示例请求

```text
http://127.0.0.1:8000/health
http://127.0.0.1:8000/schools?year=2024&province=江苏&subject_type=历史类
http://127.0.0.1:8000/schools?school_name=南京&limit=20
http://127.0.0.1:8000/ranks?year=2024&province=江苏&subject_type=物理类
http://127.0.0.1:8000/ranks?year=2024&province=江苏&subject_type=物理类&score=650
http://127.0.0.1:8000/controls?year=2024&province=江苏
http://127.0.0.1:8000/stats/summary
http://127.0.0.1:8000/province-availability
```

## Phase 6：位次换算（Rank Conversion）

基于一分一段表实现分数↔位次、跨年等效分、按等效分筛院校。

### 换算接口

```text
# 分数查位次
http://127.0.0.1:8000/convert/score-to-rank?year=2024&province=江苏&subject_type=物理类&score=650

# 位次查分数
http://127.0.0.1:8000/convert/rank-to-score?year=2024&province=江苏&subject_type=物理类&rank=80

# 跨年等效分（需两年均有一分一段数据）
http://127.0.0.1:8000/convert/equivalent-score?province=江苏&subject_type=物理类&from_year=2024&to_year=2023&score=650
```

### 院校筛选

```text
# 按分数 ±tolerance 筛选（江苏 / 浙江）
http://127.0.0.1:8000/schools/by-score?year=2024&province=江苏&subject_type=物理类&score=650&tolerance=10

# 按位次 ±tolerance 筛选（山东官方表以最低位次为主）
http://127.0.0.1:8000/schools/by-rank?year=2024&province=山东&subject_type=综合改革&rank=50000&tolerance=5000

# 当前分换算为往年等效分后筛选
http://127.0.0.1:8000/schools/by-equivalent-score?current_year=2024&target_year=2023&province=江苏&subject_type=物理类&score=650&tolerance=10
```

### 校验规则

- `score`：0–750
- `rank`：> 0
- `from_year` ≠ `to_year`
- `tolerance`：0–50
- 缺一分一段表时返回 **404**

### 换算逻辑

1. **分数→位次**：取该分 `cumulative_count`；无精确分时取 `<= score` 最近分段
2. **位次→分数**：取 `cumulative_count >= rank` 的最高分
3. **等效分**：from_year 分数→位次→to_year 位次→分数

### `/schools` 参数

- `year`、`province`、`subject_type`：可选过滤
- `school_name`：模糊查询
- `min_score` / `max_score`：分数区间（江苏 / 浙江）
- `rank_min` / `rank_max`：位次区间（山东）
- `limit`：默认 50，最大 200

`/schools/enriched` 同样支持 `rank_min` / `rank_max`（与 `score_min` / `score_max` 并列）。

### `/ranks` 参数

- `year`、`province`、`subject_type`：**必填**
- `score`：可选；传入时返回该分对应累计人数
- `limit`：默认 100（不传 score 时生效）

交互式文档：`http://127.0.0.1:8000/docs`

> **数据库 schema 变更**：若新增字段（如 `tie_breaker_text`），开发阶段可删除 `gaokao.db` 后重新执行 `python main.py init-db`；或运行 `init-db` 自动执行轻量迁移。

## Phase 3：江苏真实 Excel 解析增强

适配江苏省考试院真实表格格式（投档线、一分一段表等），支持自动识别表头、清洗非数据行。

### 探查 Excel 结构

导入前先查看 sheet、预览数据、推测表头行：

```bash
python main.py inspect-excel data/raw/jiangsu/2024/school/attachments/xxx.xlsx

# 或使用脚本
python scripts/inspect_excel.py data/raw/jiangsu/2024/school/attachments/xxx.xlsx
```

输出内容：
- 所有 sheet 名称
- 每个 sheet 前 20 行 × 15 列预览
- 各列非空数量
- 推测的表头行索引（`detect_header_row`）

### 真实 Excel 调试流程

```bash
# 1. 探查列名与表头
python main.py inspect-excel data/raw/jiangsu/2024/school/attachments/xxx.xlsx

# 2. 确认列名后导入（文件名含「历史」「物理」可自动推断科类）
python main.py import-excel data/raw/jiangsu/2024/school/attachments/xxx.xlsx --type school --year 2024 --province 江苏

# 一分一段表
python main.py import-excel data/raw/jiangsu/2024/rank/attachments/xxx.xlsx --type rank --year 2024 --province 江苏
```

### 解析增强说明

| 能力 | 说明 |
|------|------|
| 自动表头 | 前 30 行内匹配关键词最多的行作为表头 |
| 清洗 | 去全空行/列、过滤「说明/备注/注：」行 |
| 列名映射 | 按 `--type` 映射江苏常见列名 |
| 科类推断 | 从文件名识别「历史类」「物理类」 |
| 同分排序 | `tie_breaker_text` 写入 `school_admission_line` |

**school 类型映射示例**：

- 院校代号 → `school_code`
- 院校名称 → `school_name`
- 专业组代码 → `major_group`
- 投档最低分 → `min_score`
- 投档最低分同分考生排序项 → `tie_breaker_text`
- 位次 → `min_rank`（**非必填**）

**rank 类型映射**：

- 分数 → `score`
- 人数 / 本段人数 → `same_score_count`
- 累计人数 → `cumulative_count`

## Phase 2：江苏省官方数据源（2024）

数据源配置位于 `crawlers/sources_registry.py` 中的 `JIANGSU_SOURCES`，按 **年份 → 类型 → 列表** 组织：

```python
JIANGSU_SOURCES = {
    2024: {
        "control": [{"title": "...", "url": "...", "type": "html_or_excel_or_pdf"}],
        "rank": [...],
        "school": [...],
        "major": [...],
    }
}
```

- `url` 可为空（TODO），需手动从江苏省教育考试院官网补全
- `type`：`html`（公告页，自动提取附件）| `xlsx` | `xls` | `pdf` | `jpg` | `excel`

### Phase 2.1：HTML 公告页附件提取

江苏省教育考试院多数数据发布在 **HTML 公告页** 内，附件为 `.xlsx/.xls/.pdf/.jpg` 等。

**单独测试附件提取：**

```bash
python main.py extract-attachments https://www.jseea.cn/webfile/index/index_zkxx/2024-07-18/7219509116052443136.html
```

输出每个附件的 `title`、`file_type`、`url`。

**下载配置源（含 HTML 页面 + 附件）：**

```bash
python main.py download-source --province 江苏 --year 2024 --type school
```

预期行为：

1. 保存 HTML 页面到 `data/raw/jiangsu/2024/school/{标题}.html`
2. 提取页面内附件并下载到 `data/raw/jiangsu/2024/school/attachments/`
3. 例如本科批次投档线页面会下载历史类、物理类 Excel 附件

**逐分段统计表：**

```bash
python main.py download-source --province 江苏 --year 2024 --type rank
```

### Phase 2.2：403 时的手动流程（合规降级）

江苏省教育考试院可能对自动化请求返回 **403**。不做绕 WAF / Selenium / 代理，改为 **浏览器手动保存 + 本地解析**：

1. 浏览器打开官网公告页（如本科批次投档线）
2. 右键 **「另存为」** 保存完整网页为 HTML（建议「网页，全部」）
3. 本地提取附件链接：

```bash
python main.py extract-attachments-local saved_page.html --base-url https://www.jseea.cn/webfile/index/index_zkxx/2024-07-18/7219509116052443136.html
```

4. 将输出的附件 `url` 填入 `crawlers/sources_registry.py` 对应源的 `attachments` 字段
5. 批量下载配置的附件直链：

```bash
python main.py download-source --province 江苏 --year 2024 --type school
```

6. 入库：

```bash
python main.py import-excel data/raw/jiangsu/2024/school/attachments/xxx.xlsx --type school --year 2024 --province 江苏
```

**单独下载一个附件直链：**

```bash
python main.py download-attachment "https://example.com/file.xlsx" --output-dir data/raw/jiangsu/2024/school/attachments

# 自定义文件名 / 强制覆盖
python main.py download-attachment "https://example.com/file.xlsx" --output-dir data/raw/jiangsu/2024/school/attachments --filename 物理类投档线.xlsx --force
```

**`attachments` 配置示例**（`school` 已预置结构，补全 `url` 即可）：

```python
"attachments": [
    {"title": "...(历史类)", "url": "https://...", "file_type": "xlsx"},
    {"title": "...(物理类)", "url": "https://...", "file_type": "xlsx"},
]
```

当 `attachments` 字段存在时，`download-source` **跳过在线 HTML 提取**，直接下载列表中的直链。

### 查看已配置数据源

```bash
python main.py list-sources --province 江苏 --year 2024
```

输出字段：`year`、`data_type`、`file_type`、`url`、`title`。

### 下载官方文件

```bash
# 下载省控线
python main.py download-source --province 江苏 --year 2024 --type control

# 下载全部类型（control / rank / school / major）
python main.py download-source --province 江苏 --year 2024 --type all

# 强制覆盖已存在文件
python main.py download-source --province 江苏 --year 2024 --type school --force
```

保存路径：

- HTML 页面：`data/raw/jiangsu/{year}/{data_type}/{安全文件名}.html`
- 页面附件：`data/raw/jiangsu/{year}/{data_type}/attachments/{安全文件名}.xlsx`
- 直链文件：`data/raw/jiangsu/{year}/{data_type}/{安全文件名}.扩展名`
- 文件已存在时默认跳过（`--force` 覆盖）

### 检查 URL 配置完整性

```bash
python scripts/check_sources.py
```

示例输出：

```
[2024][control] 0 configured, 1 missing
[2024][rank] 1 configured, 0 missing
...
```

补全 URL 后，典型工作流：

```bash
python main.py extract-attachments https://www.jseea.cn/webfile/index/index_zkxx/2024-07-18/7219509116052443136.html
python main.py download-source --province 江苏 --year 2024 --type school
python main.py import-excel data/raw/jiangsu/2024/school/attachments/xxx.xlsx --type school --year 2024 --province 江苏
```

## 当前限制

- **Phase 3** 增强江苏真实 Excel 解析；`inspect-excel` 用于导入前调试
- 旧版 `crawl-jiangsu` 仍从索引页发现链接，受 robots.txt 限制可能无法访问
- 默认 **最多下载 1 个文件**，避免对目标站点造成压力
- Excel 列名映射覆盖常见表头，特殊格式需扩展 `config.EXCEL_COLUMN_ALIASES`
- PDF 机器可读表格解析见 Phase 13（`parse_pdf_tables`，无 OCR）
- API 仅提供查询，不含写入与推荐

## Phase 7：真实数据补全与导入流程固化

目标：将江苏省 2024 官方 Excel 完整入库，并做质量检查。

### Phase 7.4：真实跑数与问题修复

Phase 7.4 是**真实跑数阶段**，目标是根据真实文件修解析规则，而不是继续堆功能。

```bash
# 全量流水线（init-db → rank/control/school 导入 → 各年 data-quality）
python scripts/run_jiangsu_2021_2024_pipeline.py

# 仅发现，不下载不导入
python scripts/run_jiangsu_2021_2024_pipeline.py --dry-run

# 清空数据库后重跑
python scripts/run_jiangsu_2021_2024_pipeline.py --reset-db --max-pages 100
```

**仅验证 Phase 7.4 修复（不全量重跑）：**

```bash
python main.py discover-download-import --province 江苏 --years 2023 2024 --type rank --max-pages 100
python main.py discover-download-import --province 江苏 --years 2023 2024 --type control --max-pages 100
python main.py data-quality --province 江苏 --year 2024

# 用已下载 HTML 回归测试 parse_html_tables
python scripts/test_real_jiangsu_pages.py
python scripts/test_real_jiangsu_pages.py --type control --year 2024
```

Phase 7.4 修复要点：
- control 发现仅匹配「录取控制分数线」类标题，排除投档线/平行志愿误匹配
- rank 无附件时下载公告 HTML 并尝试 `import-file html --type rank`
- control 导入前跳过表头含「院校代号/投档最低分」的 school 误分类文件（`skipped_wrong_type`）

输出：
- `data/cleaned/pipeline_report_jiangsu_2021_2024.json` — 每步状态与统计
- `data/cleaned/import_errors_jiangsu_2021_2024.json` — 导入失败明细
- `data/cleaned/debug/{文件名}_preview.csv` — 失败文件的 parser 调试预览

### Phase 7.1 / 7.2：自动发现与多年份批量导入（主流程）

从江苏省教育考试院 **招考信息** 列表页自动发现公告、提取附件、下载并可选入库。  
支持江苏 **2021–2024** 多年份：`--years` 优先于 `--year`，列表页只扫描一次。  
实现见 `crawlers/discovery.py`（无 Selenium、无代理、不绕 WAF）。

**A. 自动路线（推荐，Phase 7.3 完整流程）**

```bash
# 1. 一分一段表（rank）— 多 sheet 自动合并，科类：sheet名 > 文件名 > CLI
python main.py discover-download-import --province 江苏 --years 2021 2022 2023 2024 --type rank --max-pages 100

# 2. 省控线（control）— 支持 Excel + 公告 HTML 表格；PDF/图片仅下载不导入
python main.py discover-download-import --province 江苏 --years 2021 2022 2023 2024 --type control --max-pages 100

# 3. 院校投档线（school）
python main.py discover-download-import --province 江苏 --years 2021 2022 2023 2024 --type school --max-pages 100

# 4. 数据质量检查（rank/control/school 入库后再做跨年换算）
python main.py data-quality --province 江苏 --year 2024
python main.py data-quality --province 江苏 --year 2023
```

入库完成后方可使用 `/convert/equivalent-score` 等跨年换算 API。

**分步执行：**

```bash
python main.py discover-sources --province 江苏 --years 2021 2022 2023 2024 --type rank --max-pages 100
python main.py discover-and-download --province 江苏 --years 2021 2022 2023 2024 --type rank --max-pages 100
```

**单文件导入（Excel / HTML）：**

```bash
python main.py import-file data/raw/jiangsu/2024/control/xxx.html --type control --year 2024 --province 江苏
python main.py import-file data/raw/jiangsu/2024/rank/attachments/xxx.xlsx --type rank --year 2024 --province 江苏
```

`import-excel` 仍可用（仅 Excel）。单年仍可用 `--year 2024`。可选：`--keyword`、`--force`。

年份匹配支持阿拉伯数字（2024）与中文（二〇二四）。

**B. 兜底路线（仅官网拒绝 requests / 403 时）**

兜底不是主流程，仅在自动发现返回 403 时使用：

```bash
# 浏览器另存为 HTML 后本地提取附件链接
python main.py extract-attachments-local saved_page.html --base-url https://www.jseea.cn/webfile/index/index_zkxx/2024-07-18/7219509116052443136.html
python main.py download-attachment "https://..." --output-dir data/raw/jiangsu/2024/school/attachments
python main.py import-excel 文件路径 --type school --year 2024 --province 江苏 --subject-type 物理类
```

### 数据源台账与批量配置

- 台账：[`docs/data_sources_jiangsu_2024.md`](docs/data_sources_jiangsu_2024.md)
- 批量路径配置：`configs/jiangsu_2024_files.py`
- 备用批量导入：`python scripts/import_jiangsu_2024.py`

### data-quality 输出项

- 各表记录数
- school / rank 按 `subject_type` 分布
- **rank 科类覆盖**（历史类 + 物理类是否齐全）
- **rank 分数范围**（按科类）
- **control 批次覆盖**（普通类本科 / 特殊类型 / 专科等）
- school `min_score` 范围
- 空值检查（`subject_type`、`school_name`）
- rank `cumulative_count` 单调性（score 降低时应递增）

### Phase 10：浙江 / 山东 school（2024）

两省均为 **comprehensive** 模式，`subject_type = 综合改革`。发现流程复用 `ProvincePlugin` 配置（`index_urls`、`discovery_keywords`、`seed_announcements`），经 `crawlers/generic_discovery.py` 调度。

**浙江**（`provinces/zhejiang/`，策略 `zj_col` + seed 兜底）：

```bash
python main.py discover-sources --province 浙江 --years 2024 --type school --max-pages 20
python main.py discover-download-import --province 浙江 --years 2024 --type school --max-pages 20
python main.py data-quality --province 浙江 --year 2024
```

**山东**（`provinces/shandong/`，策略 `html_list`）：

```bash
python main.py discover-sources --province 山东 --years 2024 --type school --max-pages 20
python main.py discover-download-import --province 山东 --years 2024 --type school --max-pages 20
python main.py data-quality --province 山东 --year 2024
```

浙鲁表格为「院校 + 专业」粒度；若无 `major_group`，normalizer 用 `专业代码-专业名称` 填充以避免去重冲突。

### Phase 10.1：跨省查询模式一致性

三省 `school` 字段完整度不同：**山东官方投档表以最低位次为主，`min_score` 多为空**。系统不会用位次反推分数。

| 省份 | 默认查询模式 | API 推荐 |
|------|-------------|----------|
| 江苏 | score | `/schools/by-score` |
| 浙江 | score | `/schools/by-score` |
| 山东 | rank | `/schools/by-rank` |
| 河南 | score | `/schools/by-score` |
| 广东 | mixed | 视 Excel 入库后空值率自动推荐 |
| 福建 | score | `/schools/by-score` |
| 河北 | score | `/schools/by-score` |

- `data-quality` 输出 `min_score_null_rate`、`min_rank_null_rate`、`recommended_query_mode`
- `/schools/by-score` 当该省该年 `min_score` 空值率 > 80% 时返回 400，提示改用 rank 查询
- Dashboard 学校查询 / 图表页按省份自动切换分数或位次模式

```text
http://127.0.0.1:8000/schools/by-rank?year=2024&province=山东&subject_type=综合改革&rank=50000&tolerance=5000
```

### Phase 11：河南 school（2024）

河南为 **legacy** 模式，`subject_type = 文科 / 理科`（不写综合改革）。发现关键词覆盖本科一批/二批、高职高专批平行投档分数线。

**数据源策略**：

- `datacenter.haeea.cn` 等官方数据中心返回 WAF/验证码查询页时，标记 `unsupported_verification_required`，**不绕过验证码、不用 Selenium**
- 支持教考资源信息网（`henanjk.com`）等可公开访问的 HTML 附件页；可配置 `seed_announcements` 人工填入公告 URL
- 公开 RAR 内常见 **图片型 Word .doc** 投档表：可下载解压，但不做 OCR，标记为 `downloaded_not_imported`

```bash
python main.py discover-sources --province 河南 --years 2024 --type school --max-pages 50
python main.py discover-download-import --province 河南 --years 2024 --type school --max-pages 50
python main.py data-quality --province 河南 --year 2024
```

### Phase 12：广东 school（2024）

广东为 **new_gaokao** 模式，`subject_type = 历史类 / 物理类`。发现扫描省考试院 `ptgk` / 政务公开列表，并支持 `seed_announcements` 人工配置公告 URL。

**数据源策略**：

- 2024 年官方本科/专科投档公告附件多为 **ZIP 包（内含 PDF）** 或独立 PDF
- Excel / 机器可读 PDF 经 `parse_pdf_tables` 解析；**当前仅 `admission_category=普通类` 入库**（不做 OCR）
- 艺术/体育类 PDF 可下载，标记 `skipped_unsupported_category`，不算 `failed`
- ZIP 下载后自动解压，子文件按扩展名分别处理

```bash
python main.py discover-sources --province 广东 --years 2024 --type school --max-pages 50
python main.py discover-download-import --province 广东 --years 2024 --type school --max-pages 50
python main.py data-quality --province 广东 --year 2024
```

### Phase 12.1：省份数据可用性 / 可机器读取性评估

在插件注册（Province Coverage）与 DB 行数统计之外，增加**静态可用性矩阵**，避免用户误以为河南/广东已可查询。

- 配置：`configs/province_data_availability.py`
- Dashboard 首页：**Province Availability** 表
- API：`GET /province-availability`

河南标记为 `downloaded_not_imported`；广东普通类为 `imported_partial`，艺体类为 `skipped_unsupported_category`，**不视为流水线失败**。

```bash
curl http://127.0.0.1:8000/province-availability
```

### Phase 13：PDF 表格解析（机器可读，无 OCR）

支持 `school` / `control` / `rank`，解析链：

```text
PDF → 检测可提取文本
  → pdfplumber → camelot → tabula
  → 成功: parsed → normalize → validate → 入库
  → 失败: unsupported_pdf_table
```

- 实现：`parsers/parse_pdf_tables.py`（`parse_pdf_tables()`）
- 流水线：`importers/pipeline.run_pdf_pipeline()`
- 广东插件：`parse_school` 对 `.pdf` 优先走 PDF 解析
- 依赖：`pdfplumber`（必选）；`camelot-py` / `tabula-py` 为可选回退

```bash
pip install pdfplumber
# 可选回退
# pip install "camelot-py[cv]" tabula-py
```

### Phase 13.1：广东 PDF 普通类收敛与艺体类隔离

广东 PDF 表格解析（Phase 13）已成功，但艺体类投档表字段体系与 `历史类/物理类` 普通类不同，**当前阶段不强行入库**。

- `provinces/guangdong/metadata.py`：从文件名识别 `admission_category`（普通类 / 体育类 / 艺术类）
- `discover-download-import --province 广东 --type school`：**仅导入普通类**
- 艺体类：下载 → 可选解析 → **不入库** → `skipped_unsupported_category`（非 `failed`）
- Summary 新增列 `skip_cat`（`skipped_unsupported_category`）

```bash
python main.py discover-download-import --province 广东 --years 2024 --type school --max-pages 50
python main.py data-quality --province 广东 --year 2024
```

预期：普通类 PDF `imported=4`、`failed=0`、艺体类计入 `skip_cat`、广东 school 约 215 条。

### Phase 14：福建 school（2024）

福建为 **new_gaokao** 模式，`subject_type = 历史类 / 物理类`。仅 **普通类** 本科批 / 专科批投档线入库。

**发现与解析**：

- 插件：`provinces/fujian/`（`html_list` + `seed_announcements`）
- 关键词：普通类本科批 / 高职专科批、院校专业组投档最低分、历史/物理科目组
- Excel → `parse_excel`；机器可读 PDF → `parse_pdf_tables`
- 艺体类 → `skipped_unsupported_category`（非 `failed`）

**字段映射**（福建常见表头）：院校代号、院校名称、院校专业组、投档最低分、投档最低位次、计划数等。

```bash
python main.py discover-sources --province 福建 --years 2024 --type school --max-pages 50
python main.py discover-download-import --province 福建 --years 2024 --type school --max-pages 50
python main.py data-quality --province 福建 --year 2024
```

可在 `provinces/fujian/config.py` 的 `SEED_ANNOUNCEMENTS` 中手工增补福建省教育考试院公告 URL。若官网返回 403（WAF），需在本机网络可访问时再执行下载，或直接在 seed 中配置附件直链。

### Phase 14.1：河北 school（2024）

河北为 **new_gaokao** 模式，`subject_type = 历史类 / 物理类`。仅 **普通类** 本科批 / 专科批投档线入库（专业粒度：`major_group = major_code + '-' + major_name`）。

**发现与解析**：

- 插件：`provinces/hebei/`（`html_list` + `seed_announcements`，支持 `attachment_url` 附件直链）
- 关键词：本科/专科批平行志愿投档情况统计、历史/物理科目组合
- Excel → `parse_excel`；机器可读 PDF → `parse_pdf_tables`
- 艺体类 / 对口类 → `skipped_unsupported_category`（非 `failed`）

**字段映射**（河北常见表头）：院校代号、院校名称、专业代号、专业名称、投档最低分、投档最低位次、计划数等。

```bash
python main.py discover-sources --province 河北 --years 2024 --type school --max-pages 50
python main.py discover-download-import --province 河北 --years 2024 --type school --max-pages 50
python main.py data-quality --province 河北 --year 2024
```

可在 `provinces/hebei/config.py` 的 `SEED_ANNOUNCEMENTS` 中手工增补河北省教育考试院公告 URL 或 `attachment_url` 直链。若 `www.hebeea.edu.cn` 连接被重置，可在本机网络可访问时再执行下载，或直接在 seed 中配置 `file.hebeea.edu.cn` 附件直链。

### Phase 15：Source Adapter（数据源适配层）

统一处理各省考试院不同的访问模式；**WAF / 验证码 / 连接重置是预期环境限制，不是 bug**。

**SourceType 与省份**：

| SourceType | 省份 | 说明 |
|------------|------|------|
| `HTML_LIST` | 江苏、山东 | 扫描列表页发现公告 |
| `SEED_ONLY` | 浙江、福建、河北 | seed 公告 + 可选列表页 |
| `ARCHIVE` | 广东（ZIP）、河南（RAR） | 归档包下载后解压 |
| `PROTECTED` | 河南 datacenter | 验证码查询页，不绕过 |

**Access Status**（Dashboard / `GET /province-availability` 字段 `access_status`）：

| 状态 | 含义 |
|------|------|
| `available` | 官网可正常访问下载 |
| `partial` | 部分附件可机器读取（如广东普通类 PDF） |
| `waf_blocked` | WAF 拦截（如福建 eeafj.cn） |
| `verification_required` | 需验证码（如河南 datacenter） |
| `connection_reset` | TCP 连接被重置（如河北 hebeea.edu.cn） |
| `unsupported_archive` | 归档内为图片/不可解析格式 |
| `unsupported_pdf` | PDF 不可表格化 |

**插件接入**：`ProvincePlugin.source_adapter` 返回对应 `SourceAdapter`，提供 `discover()` / `download()` / `check_availability()` / `get_status()`。

```python
from province_registry import get_province_plugin
adapter = get_province_plugin("福建").source_adapter
print(adapter.get_status())  # waf_blocked
```

### Phase 16：Stabilization / 回归测试 / 作品集版本冻结

冻结 **MVP+ Stable**（`mvp-plus-stable`），不新增省份 / parser。

- 回归脚本：`scripts/run_regression.py`
- 报告：`data/cleaned/regression_report.json`
- 发布说明：[`docs/release_notes.md`](docs/release_notes.md)

```bash
python scripts/run_regression.py
```

覆盖：`data-quality`（苏浙鲁粤 2024）、FastAPI TestClient、Dashboard smoke test、`national-scan --dry-run`。

### Phase 17：National Expansion Controller

全国批量扫描，按 Source Adapter `access_status` 决定是否 discover / download / import；blocked 省份不强行请求。

```bash
python main.py national-scan --year 2024 --type school --dry-run
python main.py national-scan --year 2024 --type school
python main.py national-scan --year 2024 --type school --provinces 江苏 浙江 --import-enabled false
```

报告：`data/cleaned/national_scan_{year}_{type}.json`

### Phase 18：Batch Easy-win Province Plugins

批量新增湖北、湖南、辽宁、重庆 2024 school 新高考插件骨架（`SubjectMode.NEW_GAOKAO`，历史类/物理类）。

- 状态：`plugin_ready` / `pending` / `unknown`，待补真实 seed URL 或列表页验证
- 目录：`provinces/hubei/`、`provinces/hunan/`、`provinces/liaoning/`、`provinces/chongqing/`
- `national-scan --dry-run` 自动覆盖 11 省

### Phase 19：湖北 2024 school 真实数据源验证

湖北 2024 普通类投档线发布于 [湖北教育考试网](http://www.hbccks.cn/)（湖北省教育考试院官网页脚链接的官方站点），非 hbea.edu.cn 正文栏目。

**已验证 seed（2024 普通类）**：

```bash
python main.py discover-sources --province 湖北 --years 2024 --type school --max-pages 50
python main.py discover-download-import --province 湖北 --years 2024 --type school --max-pages 50
python main.py data-quality --province 湖北 --year 2024
```

**现状（2026-06 验证）**：

| 批次 | 首选历史 | 首选物理 |
|------|----------|----------|
| 本科普通批 | apccglq/2024-07/142208 | apccglq/2024-07/142207 |
| 高职高专普通批 | gzgzbl/2024-08/142216 | gzgzbl/2024-08/142215 |

公告页内表格为 **PNG 图片**（无 Excel/PDF 附件）。默认可发现但不入库；可选 `--enable-ocr` 实验解析（见 Phase 20）。

### Phase 20：Image Table OCR Parser（实验）

**默认关闭**。图片表格 OCR 为实验功能，不替代 Excel/PDF parser；结果仍走 validate + data-quality，**不保证 100% 准确**。

可选依赖（不写入 `requirements.txt` 强制项）：

```bash
pip install paddleocr paddlepaddle
```

Windows 若安装困难，可跳过 OCR，仅使用 Excel/PDF 流水线。

Windows CPU 上 PaddlePaddle 3.3+ 可能因 oneDNN/PIR 冲突崩溃；解析器已自动设置 `enable_mkldnn=False` 与环境变量规避。若仍失败，可尝试版本组合 `paddlepaddle==3.2.0` + `paddleocr==3.3.3`。

单张图片导入：

```bash
python main.py import-file data/raw/hubei/2024/school/attachments/xxx.png \
  --type school --year 2024 --province 湖北 \
  --subject-type 物理类 --batch 本科批 --enable-ocr
```

不加 `--enable-ocr` 时提示：`image import requires --enable-ocr`

### Phase 20.1：OCR Quality Gate（安全流程）

**不要批量导入全部图片**。批量 OCR 入库前须抽样审计并通过质量门禁。

单张测试（不入库）：

```bash
python main.py ocr-audit-image data/raw/hubei/2024/school/attachments/1.png \
  --type school --year 2024 --province 湖北 \
  --subject-type 物理类 --batch 本科批
```

抽样审计（不入库，`--limit 5` 建议）：

```bash
python main.py ocr-batch-audit data/raw/hubei/2024/school/attachments \
  --province 湖北 --year 2024 --type school \
  --subject-type 物理类 --batch 本科批 --limit 5
```

输出 `data/cleaned/ocr_batch_audit_hubei_2024_school.json`；若 **≥80%** 图片 `suspicious_flags` 为空，写入 `data/cleaned/ocr_audit_pass_hubei_2024_school.flag`。

`suspicious_flags` 触发条件：`valid_rows==0`、分数不在 100–750、空校名/专业组比例 >20%、`parsed_rows<5`、OCR 列数异常等。

通过后批量导入（须同时带两个参数）：

```bash
python main.py discover-download-import --province 湖北 --years 2024 --type school \
  --max-pages 50 --enable-ocr --ocr-require-audit-pass
```

仅 `--enable-ocr` 而不带 `--ocr-require-audit-pass` 时，**discover-download-import 会拒绝批量 OCR 入库**（单张 `import-file --enable-ocr` 仍可用）。

### Phase 20.2：OCR Small-batch Import

审计通过后，建议**小批量**验证入库稳定性，不要一次全量 OCR。

```bash
python main.py discover-download-import --province 湖北 --years 2024 --type school \
  --max-pages 50 --keyword 物理 \
  --enable-ocr --ocr-require-audit-pass --ocr-limit 5
```

- `--ocr-limit N`：按 `(source_title, attachment_title)` 排序后，只 OCR 入库前 **N 张唯一图片**（未传则不限，但不建议首次全量）
- Summary 额外显示 `ocr_processed` / `ocr_skipped_by_limit`
- 入库后 `data-quality --year 2024 --province 湖北` 应出现 `source_quality=ocr_experimental`

审计输出：

- `data/cleaned/ocr_raw/{filename}.json` — PaddleOCR 原始框
- `data/cleaned/ocr_preview/{filename}.csv` — 重建表格预览（人工复核）

`data-quality` 对 OCR 入库数据会标注 `source_quality=ocr_experimental`、`requires_manual_review=true`（OCR 数据可信度低于 Excel/PDF）。

### Phase 20.6：OCR Dirty Data Cleanup

Phase 20.5 修复前已入库的 OCR 脏数据（如 `school_name="2"/"3"/"4"`）需单独清理，避免污染 `data-quality`。仅删除 `source_url` 以 `ocr_experimental:` 开头且校名明显无效的记录；**不删 Excel/PDF、非 OCR 或正常 OCR 数据**。

```bash
# 默认 dry-run，只统计不删除
python main.py clean-ocr-dirty-data --province 湖北 --year 2024

# 确认后真正删除，并写报告 data/cleaned/ocr_dirty_cleanup_hubei_2024.json
python main.py clean-ocr-dirty-data --province 湖北 --year 2024 --confirm-delete

# 清理后验证
python main.py data-quality --province 湖北 --year 2024
```

参数：`--province`、`--year`、`--source-prefix`（默认 `ocr_experimental:`）、`--confirm-delete`。

脏数据判定（`school_admission_line`，须同时满足 province/year/source_prefix，且满足任一校名异常规则）：纯数字、`len<=1`、`is_invalid_school_name`、`school_code LIKE A0010%` 且校名纯数字等。

`data-quality` 在 `source_quality=ocr_experimental` 时额外输出 `invalid_school_name_count`、`invalid_school_name_rate`。

### Phase 20.7：OCR Performance Profile

只统计各阶段耗时，**不修改解析/入库逻辑**。database 阶段默认 rollback（仅测耗时）。

```bash
python main.py ocr-profile \
  data/raw/hubei/2024/school/attachments/1.png \
  data/raw/hubei/2024/school/attachments/2.png \
  data/raw/hubei/2024/school/attachments/3.png \
  --province 湖北 --year 2024
```

输出 `data/cleaned/ocr_profile.json`，字段：`image_seconds`、`ocr_seconds`、`clustering_seconds`、`dataframe_seconds`、`normalize_seconds`、`validate_seconds`、`database_seconds`、`total_seconds`。

### Phase 20.8：OCR Engine Optimization

消除重复计算：**引擎单例** + **磁盘 OCR 缓存**（不改解析/normalize/validate/数据库逻辑）。

- `parsers/ocr_engine.py`：`get_ocr_engine()` 全局复用 PaddleOCR（`ocr_engine_recreated=false` 表示复用）
- `data/cache/ocr/{sha256}.json`：原始图片 sha256 → OCR JSON；`--use-ocr-cache` 默认开启
- `ocr-profile` 额外输出：`cache_hit`、`cache_miss`、`parser_used`、`ocr_engine_recreated`

```bash
# 第一次：cache_miss（写入缓存）
python main.py ocr-profile 1.png 2.png 3.png --province 湖北 --year 2024 --run-label first_run

# 第二次：cache_hit（OCR 阶段应 <1s/张）
python main.py ocr-profile 1.png 2.png 3.png --province 湖北 --year 2024 --run-label second_run
```

### Phase 20.9：OCR Precompute

将 **OCR 推理** 与 **入库** 拆开：先批量预计算 OCR 缓存，再审计、再小批量入库。

```bash
# 1. 预计算 OCR（默认 --limit 20，已有 cache 跳过推理，可中断后重跑）
python main.py ocr-precompute data/raw/hubei/2024/school/attachments \
  --province 湖北 --year 2024 --type school --limit 20

# 2. 审计（不入库）
python main.py ocr-batch-audit data/raw/hubei/2024/school/attachments \
  --province 湖北 --year 2024 --type school --limit 20

# 3. 小批量入库（须 audit pass + ocr-limit）
python main.py discover-download-import --province 湖北 --years 2024 --type school \
  --max-pages 50 --keyword 物理 \
  --enable-ocr --ocr-require-audit-pass --ocr-limit 20
```

- 输出报告：`data/cleaned/ocr_precompute_hubei_2024_school.json`
- 图片按**自然序**排序（1→2→3→…→10），`--limit 20` 取前 20 张
- cache_miss 时会打印进度（CPU OCR 较慢属正常，非卡死）
- 不 normalize / 不 validate / 不入库；不跳过 audit；不默认全量

### Phase 20.10：OCR Runtime Diagnostics

查清 PaddleOCR 慢速原因（**不改主流程**）：

```bash
python main.py ocr-diagnose
# 可选：--image path/to/1.png  --benchmark-sample（对样本图全量 OCR，较慢）
```

输出 `data/cleaned/ocr_diagnose.json`：Python/Paddle 版本、CUDA、CPU/内存、当前 PaddleOCR 参数、mkldnn、样本图尺寸、小图 benchmark、轻量参数对照与 `likely_slow_reasons`。

### Phase 20.11：OCR Engine 选择（Paddle / RapidOCR）

保留现有 OCR pipeline、audit gate、cache、import 逻辑；默认仍为 **Paddle**，可选更快的 **RapidOCR** 做实验。

**安装（可选）：**

```bash
pip install rapidocr-onnxruntime
```

**CLI 参数（默认 `paddle`）：**

```bash
--ocr-engine paddle|rapidocr
```

适用于：`ocr-profile`、`ocr-precompute`、`ocr-audit-image`、`ocr-batch-audit`、`import-file --enable-ocr`、`discover-download-import --enable-ocr`、`ocr-diagnose`。

**缓存按 engine 区分：**

- 路径：`data/cache/ocr/{engine}/{sha256}.json`
- 含 `engine`、`engine_version`；Paddle 仍可读旧 flat 路径 `data/cache/ocr/{sha256}.json`
- Paddle 与 RapidOCR **不共用**缓存

**快速实验（禁用 cache，测真实推理速度）：**

```bash
python main.py ocr-profile data/raw/hubei/2024/school/attachments/1.png \
  --province 湖北 --year 2024 --ocr-engine rapidocr --no-use-ocr-cache
```

**诊断 RapidOCR：**

```bash
python main.py ocr-diagnose
# 报告含 rapidocr installed、onnxruntime installed、rapidocr tiny benchmark
```

未安装 `rapidocr-onnxruntime` 时返回 `rapidocr_not_installed`，不崩溃。

### Phase 20.12：OCR Engine Quality Comparison

比较 PaddleOCR 与 RapidOCR 的**速度**与**结构化质量**，决定是否可用于湖北 PNG 入库。**不入库、不改库、不跳过 audit 逻辑。**

```bash
# 单张对比（有 cache 优先用 cache；Paddle 无 cache 默认跳过 live 推理）
python main.py ocr-compare-engines data/raw/hubei/2024/school/attachments/1.png \
  --province 湖北 --year 2024 --type school \
  --subject-type 物理类 --batch 本科批

# 批量对比（默认前 5 张）
python main.py ocr-compare-batch data/raw/hubei/2024/school/attachments \
  --province 湖北 --year 2024 --type school \
  --subject-type 物理类 --batch 本科批 --limit 5
```

**输出：**

- 单张：`data/cleaned/ocr_compare_{filename}.json`
- 批量：`data/cleaned/ocr_engine_comparison_hubei_2024_school.json`

**`rapidocr_acceptable` 条件（相对 Paddle baseline）：**

- `valid_rows >= 80%` Paddle valid_rows
- `suspicious_flags` 为空
- `min_score` 范围合理（100–750）
- `school_name_invalid_rate < 5%`

**注意：** RapidOCR 通常比 Paddle 快很多，但若 `row_count_ratio` 过低（如 1.png 已知 Paddle 45 行 vs RapidOCR 13 行），**不能**用于入库；默认仍使用 Paddle。Paddle 无磁盘缓存时加 `--skip-slow-paddle`（默认开启），仅使用已有 Paddle cache 作 baseline。

### Phase 20.13：Hybrid OCR Strategy

**rapidocr-first + quality gate + paddle fallback**：利用 RapidOCR 速度，低质量时回退 Paddle cache。**不是生产默认**，仍须 audit pass 才能入库。

```bash
# 批量 hybrid 审计（不入库，默认 limit 5）
python main.py ocr-batch-audit data/raw/hubei/2024/school/attachments \
  --province 湖北 --year 2024 --type school \
  --subject-type 物理类 --batch 本科批 \
  --limit 5 --ocr-engine hybrid
```

**`--ocr-engine` 选项：**

| 模式 | 说明 |
|------|------|
| `paddle` | 慢但较准（默认） |
| `rapidocr` | 快但可能漏行 |
| `hybrid` | 推荐实验：先 RapidOCR，质量门槛不通过则回退 Paddle cache |

**Hybrid RapidOCR 质量门槛（school）：**

- `valid_rows >= 40`，或有 Paddle baseline cache 时 `>= 80%` Paddle valid_rows
- `suspicious_flags` 为空
- 关键字段非空率 `>= 95%`（school_name / major_group / min_score）
- `school_name_invalid_rate < 5%`
- `min_score` 范围 100–750

**Fallback 规则：**

- 复用 `data/cache/ocr/rapidocr/` 与 `data/cache/ocr/paddle/`（无单独 hybrid cache）
- Paddle fallback **优先读 cache**；无 cache 时默认返回 `fallback_required_but_no_cache`（不跑 700s live Paddle）
- 加 `--allow-slow-paddle-fallback` 才允许 live Paddle

**metadata：** `engine_selected`、`fallback_reason`、`rapidocr_seconds`、`paddle_cache_hit` 等写入 audit / profile 报告。

### Phase 20.15：Corrupted Image Handling

损坏/截断图片不参与 audit 通过率分母，也不计为 OCR 失败。

```bash
# 按自然序校验图片（PIL verify + load）
python main.py verify-images data/raw/hubei/2024/school/attachments \
  --province 湖北 --year 2024 --type school --limit 40
```

输出 `data/cleaned/image_verify_{province}_{year}_{data_type}.json`；损坏图附带 `source_url` / `page_url`（来自 discovery 报告）便于重新下载。

- `ocr-batch-audit`：`corrupted_image` 状态，**无** `suspicious_flags`；`clean_ratio` 分母排除损坏图
- `ocr-precompute`：跳过损坏图，报告 `skipped_corrupted_image`
- `discover-download-import`：`skipped_corrupted_image += 1`，不入库，不算 `ocr_failed`

### Phase 21：Province CSV Export（分省导出）

从 SQLite 按省份分目录导出 UTF-8 BOM CSV，便于 Excel / 外部分析。导出文件**不入 Git**（`data/export/*` 已 gitignore）。

**目录结构：**

```
data/export/csv/
├── 江苏/
│   ├── school_2023.csv
│   └── school_2024.csv
├── 湖北/
│   └── school_2024.csv
└── export_manifest.json    # 导出清单
```

**CLI：**

```bash
# 导出全部省份 school 数据（默认按年份拆分）
python main.py export-csv --type school

# 指定省份与年份
python main.py export-csv --type school --provinces 江苏 湖北 --years 2024

# 多种数据类型
python main.py export-csv --type school --type control --type rank

# 每省合并为一个文件（不按年份拆分）
python main.py export-csv --type school --merge-years

# 脚本入口（等价）
python scripts/export_cleaned_csv.py --years 2024
```

**支持类型：** `school` / `major` / `control` / `rank`（列名为中文，与 Dashboard Excel 导出字段一致）。

**配置：** `config.EXPORT_CSV_DIR`，默认 `data/export/csv`。

## 后续计划

1. 浙鲁 `major_admission_line` 专业粒度入库
2. 增加 `/majors` 专业录取线查询接口
3. 广东扫描件 PDF 仍不支持（无 OCR）；可继续扩充 PDF 表头识别规则

## 合规说明

请遵守目标网站的使用条款与 robots 协议，合理控制访问频率，仅用于个人学习与研究，勿用于商业爬取或高频压测。

## License

MIT（可按需修改）
