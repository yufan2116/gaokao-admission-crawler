# Release Notes — MVP+ Stable

**版本标识**：`mvp-plus-stable`（Phase 16 冻结）

这是 **MVP+ 稳定版本**，展示多省插件、Source Adapter 与完整 parse → normalize → validate → 入库流水线。**不是全国完整库**。

---

## 已结构化（可查询）

| 省份 | 范围 | 说明 |
|------|------|------|
| 江苏 | 2021–2024 | school / rank / control（Excel） |
| 浙江 | 2024 | school 普通类平行投档（Excel） |
| 山东 | 2024 | school 常规批投档（Excel，按位次查询为主） |
| 广东 | 2024 | school **普通类**历史/物理（机器可读 PDF）；艺体类已下载但不建模 |

---

## 已识别但未结构化（Source-aware）

| 省份 | Access Status | 说明 |
|------|---------------|------|
| 河南 | `verification_required` | 公开 RAR 内为图片型 Word；`datacenter.haeea.cn` 需验证码，不绕过 |
| 福建 | `waf_blocked` | 福建省教育考试院 WAF（403）；seed 可发现，本环境无法下载 |
| 河北 | `connection_reset` | `hebeea.edu.cn` 连接被重置；可配置 `attachment_url` 直链 |

上述状态为**预期环境限制**，不是流水线 bug。

---

## 核心能力

- **Multi-province plugin**（`provinces/` + `province_registry.py`）
- **Source Adapter**（`sources/`，HTML_LIST / SEED_ONLY / ARCHIVE / PROTECTED）
- **Excel parser**（`parsers/parse_excel.py`）
- **PDF table parser**（pdfplumber → camelot → tabula，无 OCR）
- **Normalization**（`normalizers/`）
- **Validation**（`validators/`）
- **SQLite** 存储（`gaokao.db`）
- **FastAPI** 查询 API（`/schools`、`/schools/by-rank`、`/province-availability` 等）
- **Streamlit Dashboard**（首页、查询、图表、Province Availability）

---

## 回归测试

```bash
python scripts/run_regression.py
```

报告输出：`data/cleaned/regression_report.json`

覆盖：

- `data-quality`（江苏 / 浙江 / 山东 / 广东 2024）
- FastAPI TestClient（`/health`、`/province-availability`、school 查询）
- Dashboard 数据读取 smoke test

---

## 明确不做（本版本）

- 不新增省份
- 不 OCR / Selenium / 代理池
- 不推荐算法 / 志愿预测
- 不绕过验证码
