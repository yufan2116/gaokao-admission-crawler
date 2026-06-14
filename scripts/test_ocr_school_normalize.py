"""
Phase 20.5 OCR normalize 对齐与校名合法性测试。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from normalizers.school_name import is_invalid_school_name, looks_like_valid_school_name
from normalizers.school_normalizer import normalize_school
from parsers.parse_image_table import _parse_hubei_row_text, _split_major_group_name
from validators.ocr_quality_gate import compute_suspicious_flags, compute_warnings


def test_hubei_ocr_row_mapping() -> None:
    row1 = _parse_hubei_row_text("A00104 北京大学第04组 化 692 国家专项计划")
    assert row1 is not None
    assert row1["school_code"] == "A00104"
    assert row1["school_name"] == "北京大学"
    assert row1["major_group"] == "第04组"
    assert row1["min_score"] == 692.0

    row2 = _parse_hubei_row_text("A00205 清华大学第05组 不限 690")
    assert row2 is not None
    assert row2["school_name"] == "清华大学"
    assert row2["major_group"] == "第05组"
    assert row2["min_score"] == 690.0


def test_split_major_group_name() -> None:
    name, group = _split_major_group_name("北京大学第01组")
    assert name == "北京大学"
    assert group == "第01组"


def test_normalize_hubei_code_not_split_to_digit_name() -> None:
    """A00104 + 北京大学 不应被 _COMBINED_SCHOOL_RE 拆成 school_name=4。"""
    df = pd.DataFrame(
        {
            "school_code": ["A00104", "A00205"],
            "school_name": ["北京大学", "清华大学"],
            "major_group": ["第04组", "第05组"],
            "min_score": [692.0, 690.0],
            "year": [2024, 2024],
            "province": ["湖北", "湖北"],
            "subject_type": ["物理类", "物理类"],
            "batch": ["本科批", "本科批"],
            "admission_category": ["普通类", "普通类"],
        }
    )
    out = normalize_school(df, year=2024, province="湖北", subject_type="物理类", batch="本科批")
    assert out["school_code"].tolist() == ["A00104", "A00205"]
    assert out["school_name"].tolist() == ["北京大学", "清华大学"]
    assert out["major_group"].tolist() == ["第04组", "第05组"]


def test_invalid_school_name_pattern_flag() -> None:
    df = pd.DataFrame(
        {
            "school_name": ["4", "5", "6", "7", "8"],
            "major_group": ["第01组"] * 5,
            "min_score": [600.0] * 5,
        }
    )
    flags = compute_suspicious_flags(
        ocr_status="parsed",
        parsed_rows=5,
        valid_rows=5,
        normalized_df=df,
        valid_df=df,
        data_type="school",
        province="湖北",
    )
    assert "invalid_school_name_pattern" in flags


def test_valid_school_names_no_invalid_flag() -> None:
    df = pd.DataFrame(
        {
            "school_name": ["北京大学", "清华大学", "武汉大学", "华中科技大学", "复旦大学"],
            "major_group": [f"第{i:02d}组" for i in range(1, 6)],
            "min_score": [690.0, 688.0, 670.0, 665.0, 660.0],
        }
    )
    flags = compute_suspicious_flags(
        ocr_status="parsed",
        parsed_rows=5,
        valid_rows=5,
        normalized_df=df,
        valid_df=df,
        data_type="school",
        province="湖北",
    )
    assert "invalid_school_name_pattern" not in flags
    assert flags == []


def test_raw_irregular_warning_only() -> None:
    df = pd.DataFrame(
        {
            "school_name": ["北京大学", "清华大学", "武汉大学", "华中科技大学", "复旦大学"],
            "major_group": [f"第{i:02d}组" for i in range(1, 6)],
            "min_score": [690.0, 688.0, 670.0, 665.0, 660.0],
        }
    )
    warnings = compute_warnings(ocr_items=[{"text": "x", "x_center": 0, "y_center": 0}], province="湖北")
    flags = compute_suspicious_flags(
        ocr_status="parsed",
        parsed_rows=5,
        valid_rows=5,
        normalized_df=df,
        valid_df=df,
        data_type="school",
    )
    assert "raw_column_count_irregular" in warnings
    assert flags == []


def test_school_name_validity_helpers() -> None:
    assert looks_like_valid_school_name("北京大学")
    assert not looks_like_valid_school_name("4")
    assert not looks_like_valid_school_name("692")
    assert not looks_like_valid_school_name("普通类")
    assert is_invalid_school_name("4")
    assert not is_invalid_school_name("北京大学")


def main() -> int:
    tests = [
        test_hubei_ocr_row_mapping,
        test_split_major_group_name,
        test_normalize_hubei_code_not_split_to_digit_name,
        test_invalid_school_name_pattern_flag,
        test_valid_school_names_no_invalid_flag,
        test_raw_irregular_warning_only,
        test_school_name_validity_helpers,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"OK  {fn.__name__}")
        except Exception as exc:
            print(f"FAIL {fn.__name__}: {exc}")
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
