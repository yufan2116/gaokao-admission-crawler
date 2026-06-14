"""

Phase 20.1 / 20.4 OCR 质量门禁单元测试（不依赖 PaddleOCR）。

"""



from __future__ import annotations



import sys

from pathlib import Path



import pandas as pd



ROOT = Path(__file__).resolve().parent.parent

if str(ROOT) not in sys.path:

    sys.path.insert(0, str(ROOT))



from validators.ocr_quality_gate import (  # noqa: E402

    OCR_AUDIT_PASS_RATIO,

    compute_field_quality,

    compute_suspicious_flags,

    compute_warnings,

    detect_raw_column_count_irregular,

    ocr_audit_pass_flag_path,

    ocr_batch_audit_report_path,

    school_key_fields_complete,

)





def _good_school_df(rows: int = 10) -> pd.DataFrame:

    return pd.DataFrame(

        {

            "school_name": [f"大学{i}" for i in range(rows)],

            "major_group": [f"第{i:02d}组" for i in range(rows)],

            "min_score": [600.0 + i for i in range(rows)],

        }

    )





def test_no_valid_rows_flag() -> None:

    flags = compute_suspicious_flags(

        ocr_status="parsed",

        parsed_rows=3,

        valid_rows=0,

        normalized_df=pd.DataFrame(),

        valid_df=pd.DataFrame(),

        data_type="school",

        province="湖北",

    )

    assert "no_valid_rows" in flags

    assert "too_few_parsed_rows" in flags





def test_min_score_out_of_range() -> None:

    df = pd.DataFrame({"min_score": [50.0, 800.0], "school_name": ["A", "B"], "major_group": ["1", "2"]})

    flags = compute_suspicious_flags(

        ocr_status="parsed",

        parsed_rows=2,

        valid_rows=2,

        normalized_df=df,

        valid_df=df,

        data_type="school",

        province="湖北",

    )

    assert "min_score_out_of_range" in flags





def test_high_null_rates() -> None:

    df = pd.DataFrame(

        {

            "school_name": ["", "", "北大", ""],

            "major_group": ["", "", "", ""],

            "min_score": [600, 610, 620, 630],

        }

    )

    flags = compute_suspicious_flags(

        ocr_status="parsed",

        parsed_rows=4,

        valid_rows=4,

        normalized_df=df,

        valid_df=df,

        data_type="school",

        province="湖北",

    )

    assert "high_school_name_null_rate" in flags

    assert "high_major_group_null_rate" in flags





def test_raw_column_count_irregular() -> None:

    sparse = [

        {"text": "A001", "x_center": 10, "y_center": 100},

        {"text": "北大", "x_center": 50, "y_center": 100},

        {"text": "690", "x_center": 90, "y_center": 100},

    ]

    assert detect_raw_column_count_irregular(sparse, province="湖北") is True



    regular: list[dict] = []

    for row_idx in range(10):

        y = 200 + row_idx * 30

        for col_idx in range(5):

            regular.append(

                {"text": f"c{col_idx}", "x_center": col_idx * 20, "y_center": y}

            )

    assert detect_raw_column_count_irregular(regular, province="湖北") is False





def test_raw_irregular_but_key_fields_ok() -> None:

    """原始 OCR 列数异常，但 normalize 后关键字段完整 → 无 suspicious，有 warning。"""

    df = _good_school_df(10)

    sparse_ocr = [{"text": "x", "x_center": 0, "y_center": 0}]



    flags = compute_suspicious_flags(

        ocr_status="parsed",

        parsed_rows=10,

        valid_rows=10,

        normalized_df=df,

        valid_df=df,

        data_type="school",

        province="湖北",

    )

    warnings = compute_warnings(ocr_items=sparse_ocr, province="湖北")



    assert flags == []

    assert "raw_column_count_irregular" in warnings

    assert school_key_fields_complete(df)

    fq = compute_field_quality(df, data_type="school")

    assert fq["school_name_non_null_rate"] == 1.0

    assert fq["major_group_non_null_rate"] == 1.0

    assert fq["min_score_non_null_rate"] == 1.0





def test_column_count_anomaly_when_key_fields_incomplete() -> None:

    df = pd.DataFrame(

        {

            "school_name": ["A", "", "", ""],

            "major_group": ["g1", "", "", ""],

            "min_score": [600, None, None, None],

        }

    )

    flags = compute_suspicious_flags(

        ocr_status="parsed",

        parsed_rows=4,

        valid_rows=4,

        normalized_df=df,

        valid_df=df,

        data_type="school",

        province="湖北",

    )

    assert "column_count_anomaly" in flags





def test_audit_paths() -> None:

    assert ocr_batch_audit_report_path("hubei", 2024, "school").name == "ocr_batch_audit_hubei_2024_school.json"

    assert ocr_audit_pass_flag_path("hubei", 2024, "school").name == "ocr_audit_pass_hubei_2024_school.flag"





def main() -> int:

    tests = [

        test_no_valid_rows_flag,

        test_min_score_out_of_range,

        test_high_null_rates,

        test_raw_column_count_irregular,

        test_raw_irregular_but_key_fields_ok,

        test_column_count_anomaly_when_key_fields_incomplete,

        test_audit_paths,

    ]

    failed = 0

    for fn in tests:

        try:

            fn()

            print(f"OK  {fn.__name__}")

        except Exception as exc:

            print(f"FAIL {fn.__name__}: {exc}")

            failed += 1

    print(f"INFO pass_threshold={OCR_AUDIT_PASS_RATIO}")

    return 1 if failed else 0





if __name__ == "__main__":

    raise SystemExit(main())


