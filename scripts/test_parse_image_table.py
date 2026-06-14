"""
Phase 20 图片 OCR 解析单元测试（不依赖 PaddleOCR 运行时）。

用法:
    python scripts/test_parse_image_table.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from parsers.parse_image_table import (  # noqa: E402
    HUBEI_DATA_ROW_RE,
    ImageTableParseResult,
    _cluster_rows,
    _infer_batch_from_context,
    _infer_subject_from_context,
    _parse_hubei_row_text,
    _rows_to_hubei_dataframe,
    _split_major_group_name,
    paddleocr_available,
)


def test_split_major_group_name() -> None:
    assert _split_major_group_name("武汉大学第01组") == ("武汉大学", "第01组")
    assert _split_major_group_name("北京大学") == ("北京大学", "")
    assert _split_major_group_name("清华大学第08组") == ("清华大学", "第08组")


def test_parse_hubei_row() -> None:
    row = _parse_hubei_row_text("A00105 北京大学 第05组 化 691")
    assert row is not None
    assert row["school_code"] == "A00105"
    assert row["school_name"] == "北京大学"
    assert row["major_group"] == "第05组"
    assert row["min_score"] == 691.0
    assert "化" in (row.get("notes") or "")

    assert _parse_hubei_row_text("说明文字") is None
    assert HUBEI_DATA_ROW_RE.match("A00105 北京大学 第05组 化 691")


def test_cluster_rows() -> None:
    boxes = [
        {"text": "代号", "x_center": 50, "y_center": 100},
        {"text": "名称", "x_center": 200, "y_center": 102},
        {"text": "A001", "x_center": 55, "y_center": 130},
        {"text": "北大", "x_center": 205, "y_center": 128},
    ]
    rows = _cluster_rows(boxes, y_tolerance=20)
    assert len(rows) == 2
    assert rows[0][0]["text"] == "代号"
    assert rows[1][0]["text"] == "A001"


def test_infer_subject_and_batch_priority() -> None:
    subject = _infer_subject_from_context(
        subject_type="物理类",
        filename="random",
        page_title="首选历史",
        ocr_text="首选历史",
    )
    assert subject == "物理类"

    batch = _infer_batch_from_context(
        batch="本科批",
        filename="专科",
        page_title="",
        ocr_text="",
    )
    assert batch == "本科批"

    batch2 = _infer_batch_from_context(
        batch=None,
        filename="gzgz",
        page_title="高职高专普通批",
        ocr_text="",
    )
    assert batch2 == "专科批"


def test_reconstruct_from_saved_ocr_json() -> None:
    raw_path = ROOT / "data" / "cleaned" / "ocr_raw" / "hubei_2024_wuli_page1.json"
    if not raw_path.exists():
        print(f"跳过: 无审计 JSON {raw_path}")
        return
    items = json.loads(raw_path.read_text(encoding="utf-8"))
    rows = _cluster_rows(items)
    df = _rows_to_hubei_dataframe(
        rows,
        year=2024,
        province="湖北",
        subject_type="物理类",
        batch="本科批",
    )
    assert not df.empty, "湖北 OCR 重建应产生数据行"
    assert "school_name" in df.columns
    assert df["min_score"].notna().any()
    print(f"  重建行数: {len(df)}")


def test_ocr_not_installed_status() -> None:
    """parse_image_table 在未安装 PaddleOCR 时返回 ocr_not_installed。"""
    import sys
    from unittest.mock import patch

    # __init__.py 导出函数会遮蔽 parsers.parse_image_table 属性名，用 sys.modules 取真实模块
    img_mod = sys.modules["parsers.parse_image_table"]

    fake = ROOT / "data" / "raw" / "hubei" / "2024" / "school" / "attachments" / "1.png"
    if not fake.exists():
        print("跳过: 无测试图片")
        return
    with patch.object(img_mod, "paddleocr_available", return_value=False):
        result: ImageTableParseResult = img_mod.parse_image_table(
            fake,
            data_type="school",
            province="湖北",
            year=2024,
            subject_type="物理类",
            batch="本科批",
        )
    assert result.status == "ocr_not_installed"


def main() -> int:
    tests = [
        test_split_major_group_name,
        test_parse_hubei_row,
        test_cluster_rows,
        test_infer_subject_and_batch_priority,
        test_reconstruct_from_saved_ocr_json,
        test_ocr_not_installed_status,
    ]
    failed = 0
    for fn in tests:
        name = fn.__name__
        try:
            fn()
            print(f"OK  {name}")
        except Exception as exc:
            print(f"FAIL {name}: {exc}")
            failed += 1
    if paddleocr_available():
        print("INFO paddleocr 已安装")
    else:
        print("INFO paddleocr 未安装（parse_image_table 将返回 ocr_not_installed）")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
