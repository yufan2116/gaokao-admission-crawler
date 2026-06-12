# 江苏省 2024 高考数据源台账

> 维护说明：下载或导入后请同步更新 `status` 与 `local_path`。  
> 批量导入命令见 `configs/jiangsu_2024_files.py` 与 `scripts/import_jiangsu_2024.py`。

官方站点：[江苏省教育考试院](https://www.jseea.cn)

---

## 1. 省控线

| 字段 | 值 |
|------|-----|
| **title** | 江苏省2024年普通高校招生第一阶段录取控制分数线 |
| **official page url** | *(TODO：补全官网公告页)* |
| **attachment url** | *(TODO)* |
| **file_type** | html / xlsx |
| **local_path** | `data/raw/jiangsu/2024/control/attachments/江苏省2024年普通高校招生第一阶段录取控制分数线.xlsx` |
| **import_type** | `control` |
| **import_command** | `python main.py import-excel data/raw/jiangsu/2024/control/attachments/江苏省2024年普通高校招生第一阶段录取控制分数线.xlsx --type control --year 2024 --province 江苏` |
| **status** | TODO |
| **notes** | 官网可能仅发布 HTML 表格；需另存为 Excel 或手工整理后入库。 |

---

## 2. 一分一段表（历史类）

| 字段 | 值 |
|------|-----|
| **title** | 江苏省2024年普通高考逐分段统计表（历史类等科目类） |
| **official page url** | https://www.jseea.cn/webfile/index/index_zkxx/2024-06-24/7210960924591525888.html |
| **attachment url** | *(从公告页附件提取后填入)* |
| **file_type** | xlsx |
| **local_path** | `data/raw/jiangsu/2024/rank/attachments/江苏省2024年普通高考逐分段统计表（历史类等科目类）.xlsx` |
| **import_type** | `rank` |
| **import_command** | `python main.py import-excel data/raw/jiangsu/2024/rank/attachments/江苏省2024年普通高考逐分段统计表（历史类等科目类）.xlsx --type rank --year 2024 --province 江苏 --subject-type 历史类` |
| **status** | TODO |
| **notes** | `download-source --type rank` 可下载 HTML 并尝试提取附件；403 时用手动保存 HTML + `extract-attachments-local`。 |

---

## 3. 一分一段表（物理类）

| 字段 | 值 |
|------|-----|
| **title** | 江苏省2024年普通高考逐分段统计表（物理类等科目类） |
| **official page url** | https://www.jseea.cn/webfile/index/index_zkxx/2024-06-24/7210960924591525888.html |
| **attachment url** | *(从公告页附件提取后填入)* |
| **file_type** | xlsx |
| **local_path** | `data/raw/jiangsu/2024/rank/attachments/江苏省2024年普通高考逐分段统计表（物理类等科目类）.xlsx` |
| **import_type** | `rank` |
| **import_command** | `python main.py import-excel data/raw/jiangsu/2024/rank/attachments/江苏省2024年普通高考逐分段统计表（物理类等科目类）.xlsx --type rank --year 2024 --province 江苏 --subject-type 物理类` |
| **status** | TODO |
| **notes** | 与历史类同页，通常为两个独立 Excel 附件。 |

---

## 4. 普通类本科批次投档线（历史类）

| 字段 | 值 |
|------|-----|
| **title** | 江苏省2024年普通类本科批次平行志愿投档线（历史等科目类） |
| **official page url** | https://www.jseea.cn/webfile/index/index_zkxx/2024-07-18/7219509116052443136.html |
| **attachment url** | `https://www.jseea.cn/upload/file/2024/lishi_toudang.xlsx` *(示例，以官网实际链接为准)* |
| **file_type** | xlsx |
| **local_path** | `data/raw/jiangsu/2024/school/attachments/江苏省2024年普通类本科批次平行志愿投档线（历史等科目类）.xlsx` |
| **import_type** | `school` |
| **import_command** | `python main.py import-excel data/raw/jiangsu/2024/school/attachments/江苏省2024年普通类本科批次平行志愿投档线（历史等科目类）.xlsx --type school --year 2024 --province 江苏 --subject-type 历史类` |
| **status** | TODO |
| **notes** | 本地样例页 `data/raw/jiangsu/2024/school/sample_page.html` 含附件链接结构参考。 |

---

## 5. 普通类本科批次投档线（物理类）

| 字段 | 值 |
|------|-----|
| **title** | 江苏省2024年普通类本科批次平行志愿投档线（物理等科目类） |
| **official page url** | https://www.jseea.cn/webfile/index/index_zkxx/2024-07-18/7219509116052443136.html |
| **attachment url** | `https://www.jseea.cn/upload/file/2024/wuli_toudang.xlsx` *(示例，以官网实际链接为准)* |
| **file_type** | xlsx |
| **local_path** | `data/raw/jiangsu/2024/school/attachments/江苏省2024年普通类本科批次平行志愿投档线（物理等科目类）.xlsx` |
| **import_type** | `school` |
| **import_command** | `python main.py import-excel data/raw/jiangsu/2024/school/attachments/江苏省2024年普通类本科批次平行志愿投档线（物理等科目类）.xlsx --type school --year 2024 --province 江苏 --subject-type 物理类` |
| **status** | TODO |
| **notes** | 与历史类同公告页，两个 Excel 附件。 |

---

## 6. 专业录取线（TODO）

| 字段 | 值 |
|------|-----|
| **title** | 2024年江苏省普通高考本科批次专业录取线 |
| **official page url** | *(TODO)* |
| **attachment url** | *(TODO)* |
| **file_type** | html / xlsx |
| **local_path** | `data/raw/jiangsu/2024/major/attachments/` |
| **import_type** | `major` |
| **import_command** | `python main.py import-excel <path> --type major --year 2024 --province 江苏` |
| **status** | TODO |
| **notes** | Phase 7 暂不导入；待 URL 与文件格式确认后补充。 |

---

## status 说明

| 状态 | 含义 |
|------|------|
| TODO | 尚未下载或未导入 |
| downloaded | 文件已保存至 local_path |
| imported | 已成功写入 SQLite |
| failed | 下载或导入失败，见 notes |

## 推荐工作流

```bash
python scripts/check_sources.py
python main.py download-source --province 江苏 --year 2024 --type rank
python main.py download-source --province 江苏 --year 2024 --type school
python main.py inspect-excel <文件路径>
python scripts/import_jiangsu_2024.py
python main.py data-quality --year 2024 --province 江苏
```
