"""解析器模块。"""

from parsers.inspect_excel import format_inspect_report, inspect_excel_file
from parsers.parse_excel import (
    detect_header_row,
    parse_excel,
    parse_excel_file,
    parse_excel_to_records,
    save_cleaned_csv,
)
from parsers.parse_html import extract_download_links, extract_links
from parsers.parse_pdf import parse_pdf_file
from parsers.parse_pdf_tables import PdfTableParseResult, parse_pdf_tables

__all__ = [
    "extract_links",
    "extract_download_links",
    "detect_header_row",
    "parse_excel",
    "parse_excel_file",
    "parse_excel_to_records",
    "save_cleaned_csv",
    "inspect_excel_file",
    "format_inspect_report",
    "parse_pdf_file",
    "parse_pdf_tables",
    "PdfTableParseResult",
]
