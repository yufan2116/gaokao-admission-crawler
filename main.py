"""
命令行入口。

用法:
    python main.py init-db
    python main.py crawl-jiangsu [--year 2024] [--max-files 1]
    python main.py parse-excel path/to/file.xlsx [--year 2024] [--type school]
    python main.py import-excel path/to/file.xlsx --type school --year 2024 --province 江苏 --subject-type 物理类
    python main.py import-school-metadata data/manual/school_metadata_seed.csv
    python main.py data-quality --year 2024 --province 江苏
    python scripts/import_jiangsu_2024.py
    python main.py list-sources --province 江苏 --year 2024
    python main.py download-source --province 江苏 --year 2024 --type control
    python main.py discover-sources --province 江苏 --years 2021 2022 2023 2024 --type school --max-pages 80
    python main.py discover-and-download --province 江苏 --years 2021 2022 2023 2024 --type school --max-pages 80
    python main.py discover-download-import --province 江苏 --years 2021 2022 2023 2024 --type school --max-pages 80
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from config import CLEANED_DIR, DEFAULT_PROVINCE, DEFAULT_YEARS
from crawlers.jiangsu import (
    extract_attachment_links,
    extract_attachment_links_from_html_file,
    resolve_province_crawler,
)
from province_registry import get_province_plugin, list_registered_provinces
from provinces.base import ProvincePlugin
from crawlers.discovery import (
    resolve_discovery_years,
    run_discover,
    run_discover_and_download,
    run_discover_download_import,
)
from crawlers.sources_registry import DATA_TYPES, get_jiangsu_year_config
from db.database import SessionLocal
from db.init_db import init_database
from importers.excel_import import import_excel_to_db
from importers.file_import import UnsupportedImportFormatError, import_file_to_db
from importers.school_metadata_import import import_school_metadata_csv
from importers.pipeline import run_excel_pipeline
from validators.data_quality import run_data_quality_check
from normalizers.province import normalize_province
from parsers.inspect_excel import format_inspect_report, inspect_excel_file
from parsers.parse_excel import parse_excel, parse_excel_file, save_cleaned_csv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")


def cmd_init_db(_args: argparse.Namespace) -> int:
    """初始化 SQLite 数据库表结构。"""
    init_database()
    logger.info("执行成功: init-db")
    return 0


def cmd_crawl_jiangsu(args: argparse.Namespace) -> int:
    """运行江苏省爬虫（MVP：默认只下载 1 个文件）。"""
    crawler = resolve_province_crawler(DEFAULT_PROVINCE)
    files = crawler.crawl(
        max_files=args.max_files,
        target_year=args.year,
    )

    if files:
        for f in files:
            logger.info("  -> %s", f)
    else:
        logger.warning("未下载任何文件，请检查网络或 config.py 中的索引页 URL")
    return 0


def cmd_parse_excel(args: argparse.Namespace) -> int:
    """解析本地 Excel 并输出清洗后的 CSV。"""
    path = Path(args.file)
    if not path.exists():
        logger.error("文件不存在: %s", path)
        return 1

    try:
        df = parse_excel(
            path,
            data_type=getattr(args, "type", None),
            sheet_name=args.sheet,
            default_year=args.year,
        )
    except Exception as exc:
        logger.error("解析失败: %s", exc)
        return 1

    if df.empty:
        logger.warning("解析结果为空")
        return 0

    output_name = args.output or f"{path.stem}_cleaned.csv"
    out_path = save_cleaned_csv(df, output_name, cleaned_dir=CLEANED_DIR)
    logger.info("共 %d 行，已保存至 %s", len(df), out_path)
    return 0


def cmd_normalize_excel(args: argparse.Namespace) -> int:
    """parse → normalize → 输出标准化 CSV。"""
    path = Path(args.file)
    if not path.exists():
        logger.error("文件不存在: %s", path)
        return 1

    province = normalize_province(args.province or DEFAULT_PROVINCE)
    try:
        result = run_excel_pipeline(
            path,
            data_type=args.type,
            year=args.year,
            province=province,
            sheet_name=args.sheet,
        )
    except Exception as exc:
        logger.error("标准化失败: %s", exc)
        return 1

    df = result.normalized_df
    if df.empty:
        logger.warning("标准化结果为空")
        return 0

    output_name = args.output or f"normalized_{path.stem}.csv"
    out_path = save_cleaned_csv(df, output_name, cleaned_dir=CLEANED_DIR)
    logger.info(
        "标准化完成: %d 行 → %s（校验通过 %d 行）",
        len(df),
        out_path,
        len(result.valid_df),
    )
    if result.validation.errors:
        logger.info("校验提示 %d 条（见日志）", len(result.validation.errors))
    return 0


def cmd_import_file(args: argparse.Namespace) -> int:
    """按扩展名解析文件（Excel/HTML）并写入 SQLite。"""
    path = Path(args.file)
    if not path.exists():
        logger.error("文件不存在: %s", path)
        return 1

    province = normalize_province(args.province or DEFAULT_PROVINCE)
    session = SessionLocal()
    try:
        stats = import_file_to_db(
            session,
            path,
            record_type=args.type,
            default_year=args.year,
            default_province=province,
            subject_type=getattr(args, "subject_type", None),
        )
    except UnsupportedImportFormatError as exc:
        logger.error("%s", exc)
        return 1
    except Exception as exc:
        logger.error("导入失败: %s", exc)
        return 1
    finally:
        session.close()

    logger.info(
        "导入完成 [%s] inserted=%d skipped=%d failed=%d",
        args.type,
        stats.inserted,
        stats.skipped,
        stats.failed,
    )
    if stats.errors:
        for err in stats.errors[:10]:
            logger.info("  - %s", err)
    return 0


def cmd_import_excel(args: argparse.Namespace) -> int:
    """解析 Excel 并写入 SQLite。"""
    path = Path(args.file)
    if not path.exists():
        logger.error("文件不存在: %s", path)
        return 1

    province = normalize_province(args.province or DEFAULT_PROVINCE)
    session = SessionLocal()
    try:
        stats = import_excel_to_db(
            session,
            path,
            record_type=args.type,
            default_year=args.year,
            default_province=province,
            sheet_name=args.sheet,
            subject_type=getattr(args, "subject_type", None),
        )
    except Exception as exc:
        logger.error("导入失败: %s", exc)
        return 1
    finally:
        session.close()

    logger.info(
        "导入完成 [%s] inserted=%d skipped=%d failed=%d",
        args.type,
        stats.inserted,
        stats.skipped,
        stats.failed,
    )
    if stats.errors:
        for err in stats.errors[:10]:
            logger.info("  - %s", err)
        if len(stats.errors) > 10:
            logger.info("  ... 另有 %d 条错误未显示", len(stats.errors) - 10)
    return 0


def _resolve_province(province: str) -> ProvincePlugin:
    """校验并返回省份插件。"""
    return get_province_plugin(province)


def cmd_list_sources(args: argparse.Namespace) -> int:
    """列出已配置的数据源。"""
    try:
        plugin = _resolve_province(args.province)
    except ValueError as exc:
        logger.error("%s", exc)
        return 1

    if not plugin.is_available:
        logger.error("%s 插件尚未实现", plugin.province_name)
        return 1

    if not get_jiangsu_year_config(args.year):
        logger.error("未配置 [%s] 年数据源，请编辑 crawlers/sources_registry.py", args.year)
        return 1

    crawler = plugin.get_crawler()
    entries = crawler.list_sources(args.year)

    if not entries:
        logger.warning("无数据源条目")
        return 0

    header = f"{'year':<6} {'data_type':<10} {'file_type':<22} {'url':<40} title"
    print(header)
    print("-" * 100)
    for e in entries:
        url = e["url"] or "(未配置)"
        print(
            f"{e['year']:<6} {e['data_type']:<10} {e['file_type']:<22} "
            f"{url:<40} {e['title']}"
        )
    print(f"\n共 {len(entries)} 条")
    return 0


def cmd_download_source(args: argparse.Namespace) -> int:
    """从配置下载官方数据源到 data/raw/。"""
    try:
        plugin = _resolve_province(args.province)
    except ValueError as exc:
        logger.error("%s", exc)
        return 1

    if not plugin.is_available:
        logger.error("%s 插件尚未实现", plugin.province_name)
        return 1

    if not get_jiangsu_year_config(args.year):
        logger.error("未配置 [%s] 年数据源，请编辑 crawlers/sources_registry.py", args.year)
        return 1

    crawler = plugin.get_crawler()
    try:
        paths = crawler.download_configured_sources(
            year=args.year,
            data_type=args.type,
            force=args.force,
        )
    except ValueError as exc:
        logger.error("%s", exc)
        return 1

    if paths:
        logger.info("已保存 %d 个文件:", len(paths))
        for p in paths:
            logger.info("  -> %s", p.resolve())
    else:
        logger.warning(
            "未下载任何文件。请先用 list-sources 查看配置，并在 crawlers/sources_registry.py 补全 URL"
        )
    return 0


def _print_attachment_links(links: list[dict]) -> None:
    """打印附件列表。"""
    if not links:
        print("未发现附件")
        return
    print(f"{'file_type':<8} {'title':<50} url")
    print("-" * 110)
    for item in links:
        print(f"{item['file_type']:<8} {item['title']:<50} {item['url']}")
    print(f"\n共 {len(links)} 个附件")


def cmd_extract_attachments(args: argparse.Namespace) -> int:
    """测试从 HTML 页面提取附件链接。"""
    url = args.url.strip()
    if not url.startswith("http"):
        logger.error("请提供有效的 HTTP(S) URL")
        return 1

    crawler = resolve_province_crawler(DEFAULT_PROVINCE)
    links = crawler.extract_attachment_links(url)

    if not links:
        print(f"未发现附件: {url}")
        return 0

    _print_attachment_links(links)
    return 0


def cmd_extract_attachments_local(args: argparse.Namespace) -> int:
    """从本地 HTML 文件提取附件链接。"""
    html_path = Path(args.file)
    if not html_path.exists():
        logger.error("文件不存在: %s", html_path)
        return 1

    base_url = args.base_url.strip()
    if not base_url.startswith("http"):
        logger.error("请提供有效的 --base-url（原公告页 URL）")
        return 1

    links = extract_attachment_links_from_html_file(html_path, base_url)
    _print_attachment_links(links)
    return 0


def cmd_download_attachment(args: argparse.Namespace) -> int:
    """下载单个附件直链。"""
    url = args.url.strip()
    if not url.startswith("http"):
        logger.error("请提供有效的 HTTP(S) URL")
        return 1

    output_dir = Path(args.output_dir)
    crawler = resolve_province_crawler(DEFAULT_PROVINCE)
    path = crawler.download_attachment_to_dir(
        url=url,
        output_dir=output_dir,
        filename=args.filename,
        force=args.force,
    )

    if path is None:
        logger.warning("下载未完成: %s", url)
        return 0

    logger.info("已保存: %s", path.resolve())
    return 0


def _add_discovery_common_args(parser: argparse.ArgumentParser) -> None:
    """发现类命令的公共参数（不含 --type）。"""
    registered = "、".join(list_registered_provinces())
    parser.add_argument("--province", default=DEFAULT_PROVINCE, help=f"省份（已注册: {registered}）")
    parser.add_argument("--year", type=int, default=None, help="单一年份，如 2024")
    parser.add_argument(
        "--years",
        type=int,
        nargs="+",
        default=None,
        help="多个年份（优先于 --year），如 --years 2021 2022 2023 2024",
    )
    parser.add_argument("--keyword", default=None, help="额外标题关键词过滤")
    parser.add_argument("--max-pages", type=int, default=5, help="扫描列表页页数上限")
    parser.add_argument("--force", action="store_true", help="覆盖已存在附件")


def _discovery_years_from_args(args: argparse.Namespace) -> list[int]:
    """从 CLI 参数解析年份列表。"""
    return resolve_discovery_years(year=args.year, years=args.years)


def cmd_discover_sources(args: argparse.Namespace) -> int:
    """自动发现各省考试院公告数据源。"""
    try:
        plugin = _resolve_province(args.province)
        years = _discovery_years_from_args(args)
    except ValueError as exc:
        logger.error("%s", exc)
        return 1

    if not plugin.is_available:
        logger.error("%s 插件尚未实现", plugin.province_name)
        return 1

    try:
        by_year = run_discover(
            years=years,
            province=args.province,
            data_type=args.type,
            keyword=args.keyword,
            max_pages=args.max_pages,
        )
    except (ValueError, NotImplementedError) as exc:
        logger.error("%s", exc)
        return 1

    total = sum(len(v) for v in by_year.values())
    if total == 0:
        print("未发现匹配公告。可增大 --max-pages（较早年份需扫描更多列表页）。")
        return 0

    for year in years:
        sources = by_year.get(year, [])
        print(f"\n=== {year}（{len(sources)} 条）===")
        if not sources:
            continue
        print(f"{'title':<55} {'type':<8} {'att':<4} page_url")
        print("-" * 120)
        for s in sources:
            att_count = len(s.get("attachments") or [])
            title = (s.get("title") or "")[:54]
            print(
                f"{title:<55} {s.get('suggested_type', ''):<8} {att_count:<4} {s.get('page_url', '')}"
            )
            for att in s.get("attachments") or []:
                print(f"  └─ {att.get('title', '')}")

    print(f"\n共 {total} 条公告（{len(years)} 个年份）")
    return 0


def cmd_discover_and_download(args: argparse.Namespace) -> int:
    """发现数据源并下载附件。"""
    try:
        plugin = _resolve_province(args.province)
        years = _discovery_years_from_args(args)
    except ValueError as exc:
        logger.error("%s", exc)
        return 1

    if not plugin.is_available:
        logger.error("%s 插件尚未实现", plugin.province_name)
        return 1

    if not args.type:
        logger.error("discover-and-download 需要 --type 参数")
        return 1

    try:
        report_paths, combined_path = run_discover_and_download(
            years=years,
            province=args.province,
            data_type=args.type,
            keyword=args.keyword,
            max_pages=args.max_pages,
            force=args.force,
        )
    except (ValueError, NotImplementedError) as exc:
        logger.error("%s", exc)
        return 1

    for year, path in report_paths.items():
        logger.info("[%s] discovery 报告: %s", year, path.resolve())
    if combined_path:
        logger.info("多年份总报告: %s", combined_path.resolve())
    return 0


def cmd_discover_download_import(args: argparse.Namespace) -> int:
    """发现 → 下载 → 入库。"""
    try:
        plugin = _resolve_province(args.province)
        years = _discovery_years_from_args(args)
    except ValueError as exc:
        logger.error("%s", exc)
        return 1

    if not plugin.is_available:
        logger.error("%s 插件尚未实现", plugin.province_name)
        return 1

    if not args.type:
        logger.error("discover-download-import 需要 --type 参数")
        return 1

    try:
        result = run_discover_download_import(
            years=years,
            province=args.province,
            data_type=args.type,
            keyword=args.keyword,
            max_pages=args.max_pages,
            force=args.force,
        )
    except (ValueError, NotImplementedError) as exc:
        logger.error("%s", exc)
        return 1

    print("\n========== Discover Download Import Summary ==========")
    if result.get("combined_report_path"):
        print(f"combined report: {result['combined_report_path']}")
    print(
        f"{'year':<6} {'pages':<6} {'dl':<4} {'imported':<9} {'skipped':<8} "
        f"{'no_imp':<6} {'failed':<6} error"
    )
    print("-" * 80)
    has_failure = False
    for row in result.get("summary", []):
        err = row.get("error") or ""
        if row.get("failed", 0) > 0 or err:
            has_failure = True
        print(
            f"{row.get('year', ''):<6} "
            f"{row.get('discovered_pages', 0):<6} "
            f"{row.get('downloaded_files', 0):<4} "
            f"{row.get('imported', 0):<9} "
            f"{row.get('skipped', 0):<8} "
            f"{row.get('downloaded_not_imported', 0):<6} "
            f"{row.get('failed', 0):<6} "
            f"{err}"
        )
    if result.get("hint"):
        print(f"\nhint: {result['hint']}")
    print("======================================================")
    return 1 if has_failure else 0


def cmd_import_school_metadata(args: argparse.Namespace) -> int:
    """从 CSV upsert 导入 school_metadata。"""
    path = Path(args.file)
    if not path.exists():
        logger.error("文件不存在: %s", path)
        return 1

    session = SessionLocal()
    try:
        result = import_school_metadata_csv(session, path)
    except ValueError as exc:
        logger.error("%s", exc)
        return 1
    except Exception as exc:
        logger.error("导入失败: %s", exc)
        return 1
    finally:
        session.close()

    logger.info(
        "school_metadata 导入完成: inserted=%d updated=%d skipped=%d",
        result.inserted,
        result.updated,
        result.skipped,
    )
    for err in result.errors[:10]:
        logger.warning("  - %s", err)
    return 0 if not result.errors else 1


def cmd_data_quality(args: argparse.Namespace) -> int:
    """检查指定年份/省份的数据质量。"""
    province = normalize_province(args.province or DEFAULT_PROVINCE)
    session = SessionLocal()
    try:
        report = run_data_quality_check(session, year=args.year, province=province)
    finally:
        session.close()

    for line in report.to_lines():
        print(line)
    return 0


def cmd_inspect_excel(args: argparse.Namespace) -> int:
    """探查 Excel 结构（sheet、预览、表头行）。"""
    path = Path(args.file)
    if not path.exists():
        logger.error("文件不存在: %s", path)
        return 1

    try:
        report = inspect_excel_file(path)
        print(format_inspect_report(report))
    except Exception as exc:
        logger.error("探查失败: %s", exc)
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    """构建 CLI 解析器。"""
    registered = "、".join(list_registered_provinces())
    parser = argparse.ArgumentParser(
        description=f"高考录取线数据采集工具（已注册省份: {registered}）",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="初始化 SQLite 数据库")

    crawl_p = sub.add_parser("crawl-jiangsu", help="爬取江苏省原始数据文件")
    crawl_p.add_argument("--year", type=int, default=None, help="优先下载指定年份")
    crawl_p.add_argument(
        "--max-files",
        type=int,
        default=1,
        help="最多下载文件数（默认 1，避免过量请求）",
    )

    excel_p = sub.add_parser("parse-excel", help="解析 Excel 并导出清洗 CSV")
    excel_p.add_argument("file", help="Excel 文件路径")
    excel_p.add_argument("--year", type=int, default=None, help="默认年份（表内无年份列时使用）")
    excel_p.add_argument("--sheet", default=0, help="工作表名或索引，默认 0")
    excel_p.add_argument("--output", default=None, help="输出 CSV 文件名")
    excel_p.add_argument(
        "--type",
        default="school",
        choices=["school", "major", "control", "rank"],
        help="数据类型，影响列名映射",
    )

    inspect_p = sub.add_parser("inspect-excel", help="探查 Excel 结构（不修改数据库）")
    inspect_p.add_argument("file", help="Excel 文件路径")

    norm_p = sub.add_parser("normalize-excel", help="parse + normalize 输出标准 CSV")
    norm_p.add_argument("file", help="Excel 文件路径")
    norm_p.add_argument(
        "--type",
        required=True,
        choices=["control", "school", "major", "rank"],
        help="数据类型",
    )
    norm_p.add_argument("--year", type=int, required=True, help="默认年份")
    norm_p.add_argument("--province", default=DEFAULT_PROVINCE, help="默认省份")
    norm_p.add_argument("--sheet", default=0, help="工作表名或索引")
    norm_p.add_argument("--output", default=None, help="输出 CSV 文件名")

    import_p = sub.add_parser("import-excel", help="解析 Excel 并写入 SQLite")
    import_p.add_argument("file", help="Excel 文件路径")
    import_p.add_argument(
        "--type",
        required=True,
        choices=["control", "school", "major", "rank"],
        help="写入目标表：control/school/major/rank",
    )
    import_p.add_argument("--year", type=int, required=True, help="默认年份")
    import_p.add_argument(
        "--province",
        default=DEFAULT_PROVINCE,
        help="默认省份（默认：江苏）",
    )
    import_p.add_argument("--sheet", default=0, help="工作表名或索引，默认 0")
    import_p.add_argument(
        "--subject-type",
        default=None,
        help="科类（历史类/物理类）；优先级高于文件名与 Excel 内容推断",
    )

    file_p = sub.add_parser("import-file", help="按扩展名导入 Excel/HTML 文件")
    file_p.add_argument("file", help="文件路径（.xlsx/.xls/.html）")
    file_p.add_argument(
        "--type",
        required=True,
        choices=["control", "school", "major", "rank"],
        help="写入目标表",
    )
    file_p.add_argument("--year", type=int, required=True, help="默认年份")
    file_p.add_argument("--province", default=DEFAULT_PROVINCE, help="默认省份")
    file_p.add_argument("--subject-type", default=None, help="科类（历史类/物理类）")

    meta_p = sub.add_parser("import-school-metadata", help="导入学校元数据 CSV（upsert）")
    meta_p.add_argument("file", help="CSV 路径，如 data/manual/school_metadata_seed.csv")

    dq_p = sub.add_parser("data-quality", help="数据质量检查")
    dq_p.add_argument("--year", type=int, required=True, help="年份，如 2024")
    dq_p.add_argument("--province", default=DEFAULT_PROVINCE, help="省份（默认：江苏）")

    list_p = sub.add_parser("list-sources", help="列出已配置的数据源")
    list_p.add_argument(
        "--province",
        default=DEFAULT_PROVINCE,
        help=f"省份（已注册: {registered}）",
    )
    list_p.add_argument("--year", type=int, required=True, help="年份，如 2024")

    dl_p = sub.add_parser("download-source", help="下载配置的数据源到 data/raw/")
    dl_p.add_argument(
        "--province",
        default=DEFAULT_PROVINCE,
        help=f"省份（已注册: {registered}）",
    )
    dl_p.add_argument("--year", type=int, required=True, help="年份，如 2024")
    dl_p.add_argument(
        "--type",
        required=True,
        choices=[*DATA_TYPES, "all"],
        help="数据类型：control/rank/school/major/all",
    )
    dl_p.add_argument(
        "--force",
        action="store_true",
        help="本地文件已存在时强制重新下载",
    )

    ext_p = sub.add_parser("extract-attachments", help="从 HTML 页面提取附件链接（测试）")
    ext_p.add_argument("url", help="公告页 URL")

    ext_local_p = sub.add_parser(
        "extract-attachments-local",
        help="从本地保存的 HTML 文件提取附件链接",
    )
    ext_local_p.add_argument("file", help="本地 HTML 文件路径")
    ext_local_p.add_argument(
        "--base-url",
        required=True,
        help="原公告页 URL（用于将相对链接转为绝对链接）",
    )

    att_p = sub.add_parser("download-attachment", help="下载单个附件直链")
    att_p.add_argument("url", help="附件 URL")
    att_p.add_argument(
        "--output-dir",
        required=True,
        help="输出目录，如 data/raw/jiangsu/2024/school/attachments",
    )
    att_p.add_argument("--filename", default=None, help="自定义文件名（可选）")
    att_p.add_argument("--force", action="store_true", help="覆盖已存在文件")

    disc_p = sub.add_parser("discover-sources", help="自动发现官网公告数据源")
    _add_discovery_common_args(disc_p)
    disc_p.add_argument(
        "--type",
        default=None,
        choices=[*DATA_TYPES],
        help="数据类型过滤：control/rank/school/major",
    )

    disc_dl_p = sub.add_parser("discover-and-download", help="发现并下载附件")
    _add_discovery_common_args(disc_dl_p)
    disc_dl_p.add_argument(
        "--type",
        required=True,
        choices=[*DATA_TYPES],
        help="数据类型：control/rank/school/major",
    )

    disc_imp_p = sub.add_parser("discover-download-import", help="发现、下载并入库")
    _add_discovery_common_args(disc_imp_p)
    disc_imp_p.add_argument(
        "--type",
        required=True,
        choices=[*DATA_TYPES],
        help="数据类型：control/rank/school/major",
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    commands = {
        "init-db": cmd_init_db,
        "crawl-jiangsu": cmd_crawl_jiangsu,
        "parse-excel": cmd_parse_excel,
        "inspect-excel": cmd_inspect_excel,
        "normalize-excel": cmd_normalize_excel,
        "import-excel": cmd_import_excel,
        "import-file": cmd_import_file,
        "import-school-metadata": cmd_import_school_metadata,
        "list-sources": cmd_list_sources,
        "download-source": cmd_download_source,
        "extract-attachments": cmd_extract_attachments,
        "extract-attachments-local": cmd_extract_attachments_local,
        "download-attachment": cmd_download_attachment,
        "data-quality": cmd_data_quality,
        "discover-sources": cmd_discover_sources,
        "discover-and-download": cmd_discover_and_download,
        "discover-download-import": cmd_discover_download_import,
    }
    handler = commands.get(args.command)
    if handler is None:
        parser.print_help()
        return 1
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
