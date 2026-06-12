"""
高考录取线数据可视化 Dashboard（Streamlit）。

启动:
    streamlit run dashboard/dashboard.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dashboard.data_access import (  # noqa: E402
    get_coverage_status,
    get_distinct_values,
    get_home_stats,
    get_metadata_by_city,
    get_metadata_by_school_type,
    get_metadata_distinct_values,
    get_metadata_tier_counts,
    get_province_coverage,
    get_quality_stats,
    get_school_chart_data,
    get_tier_reachable_schools,
    get_year_comparison,
    resolve_dashboard_query_mode,
    search_schools_enriched,
)
from dashboard.export_excel import export_excel_bytes  # noqa: E402

st.set_page_config(
    page_title="高考录取线数据看板",
    page_icon="📊",
    layout="wide",
)

PAGES = ["首页", "学校查询", "学校层次分析", "图表", "数据质量", "项目说明"]


def sidebar_filters(
    key_prefix: str,
    *,
    include_category: bool = False,
) -> tuple[int | None, str | None, str | None, str | None, str | None]:
    years = get_distinct_values("year")
    provinces = get_distinct_values("province")
    subjects = get_distinct_values("subject_type")

    year = st.sidebar.selectbox(
        "年份",
        options=["全部"] + years,
        key=f"{key_prefix}_year",
    )
    province = st.sidebar.selectbox(
        "省份",
        options=["全部"] + provinces,
        key=f"{key_prefix}_province",
    )
    subject_type = st.sidebar.selectbox(
        "科类",
        options=["全部"] + subjects,
        key=f"{key_prefix}_subject",
    )

    admission_category = None
    batch = None
    if include_category:
        categories = get_distinct_values("admission_category")
        batches = get_distinct_values("batch")
        cat = st.sidebar.selectbox(
            "招生类别",
            options=["全部"] + categories,
            key=f"{key_prefix}_admission_category",
        )
        bat = st.sidebar.selectbox(
            "批次",
            options=["全部"] + batches,
            key=f"{key_prefix}_batch",
        )
        admission_category = None if cat == "全部" else cat
        batch = None if bat == "全部" else bat

    return (
        None if year == "全部" else int(year),
        None if province == "全部" else province,
        None if subject_type == "全部" else subject_type,
        admission_category,
        batch,
    )


def page_home() -> None:
    st.title("高考录取线数据看板")
    st.caption("数据来源：SQLite（只读）")

    stats = get_home_stats()
    c1, c2, c3 = st.columns(3)
    c1.metric("school 记录总数", f"{stats['school_total']:,}")
    c2.metric("年份数", stats["year_count"])
    c3.metric("省份数", stats["province_count"])

    st.divider()
    st.subheader("数据概览")
    overview = pd.DataFrame(
        [
            {"指标": "school 记录数", "数值": stats["school_total"]},
            {"指标": "覆盖年份数", "数值": stats["year_count"]},
            {"指标": "覆盖省份数", "数值": stats["province_count"]},
        ]
    )
    st.dataframe(overview, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Province Coverage")
    st.caption("多省插件注册状态（Phase 8）；与下方 DB 实际入库情况可对照查看")
    province_cov = get_province_coverage()
    st.dataframe(province_cov, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("数据覆盖状态")
    coverage = get_coverage_status()
    school_ok = all(y in coverage["school_years"] for y in (2023, 2024))
    school_detail = "、".join(
        f"{y}（{coverage['school_by_year'].get(y, 0):,} 条）"
        for y in (2023, 2024)
    )
    rank_ok = coverage["rank_total"] > 0
    control_ok = coverage["control_total"] > 0

    status_rows = [
        {
            "数据类型": "School",
            "覆盖情况": f"2023 / 2024 {'✅' if school_ok else '⚠'}",
            "说明": f"已结构化入库：{school_detail}" if school_ok else "部分年份缺失",
        },
        {
            "数据类型": "Rank",
            "覆盖情况": "已结构化 ✅" if rank_ok else "图片源，未结构化 ⚠",
            "说明": f"一分一段表 {coverage['rank_total']:,} 条"
            if rank_ok
            else "官网发布 JPG/PNG 图片表，暂不做 OCR",
        },
        {
            "数据类型": "Control",
            "覆盖情况": "已结构化 ✅" if control_ok else "图片源，未结构化 ⚠",
            "说明": f"省控线 {coverage['control_total']:,} 条"
            if control_ok
            else "官网发布图片表，暂不做 OCR",
        },
    ]
    st.dataframe(pd.DataFrame(status_rows), use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("导出 Excel 报告")
    st.caption("含年份对比、分数分布、Top20、类别分布等原生 Excel 图表")
    st.download_button(
        label="下载 Excel 报告（含图表）",
        data=export_excel_bytes(),
        file_name="gaokao_dashboard_report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="home_export_excel",
    )


def page_school_search() -> None:
    st.title("学校查询")
    st.caption("投档线 + school_metadata 关联（seed 数据，非全国完整库）")

    year, province, subject_type, admission_category, batch = sidebar_filters(
        "search", include_category=True
    )
    keyword = st.sidebar.text_input("学校名称搜索", placeholder="输入院校名称关键词")

    st.sidebar.subheader("院校元数据")
    filter_985 = st.sidebar.checkbox("仅 985", key="search_is_985")
    filter_211 = st.sidebar.checkbox("仅 211", key="search_is_211")
    filter_dfc = st.sidebar.checkbox("仅 双一流", key="search_is_dfc")

    cities = get_metadata_distinct_values("city")
    city_options = ["全部"] + cities
    city_sel = st.sidebar.selectbox("城市", options=city_options, key="search_city")

    types = get_metadata_distinct_values("school_type")
    type_sel = st.sidebar.selectbox(
        "学校类型",
        options=["全部"] + types,
        key="search_school_type",
    )

    query_mode = resolve_dashboard_query_mode(year, province)
    if query_mode == "rank":
        st.sidebar.caption("当前为**位次查询模式**（该省投档表以最低位次为主）")
    elif query_mode == "mixed":
        st.sidebar.caption("当前为**混合模式**（部分记录仅有分数或位次）")

    score_min_arg: float | None = None
    score_max_arg: float | None = None
    rank_min_arg: int | None = None
    rank_max_arg: int | None = None

    if query_mode != "rank":
        st.sidebar.subheader("分数区间")
        score_col1, score_col2 = st.sidebar.columns(2)
        with score_col1:
            min_score_min = st.number_input(
                "min_score_min",
                min_value=0,
                max_value=750,
                value=0,
                step=1,
                key="search_score_min",
            )
        with score_col2:
            min_score_max = st.number_input(
                "min_score_max",
                min_value=0,
                max_value=750,
                value=750,
                step=1,
                key="search_score_max",
            )
        score_min_arg = float(min_score_min) if min_score_min > 0 else None
        score_max_arg = float(min_score_max) if min_score_max < 750 else None
        if min_score_min > min_score_max:
            st.warning("分数下限不能大于上限，请调整筛选条件。")
            return

    if query_mode in ("rank", "mixed"):
        st.sidebar.subheader("位次区间")
        rank_col1, rank_col2 = st.sidebar.columns(2)
        with rank_col1:
            rank_min_input = st.number_input(
                "rank_min",
                min_value=1,
                max_value=500000,
                value=1,
                step=100,
                key="search_rank_min",
            )
        with rank_col2:
            rank_max_input = st.number_input(
                "rank_max",
                min_value=1,
                max_value=500000,
                value=500000,
                step=100,
                key="search_rank_max",
            )
        rank_min_arg = int(rank_min_input) if rank_min_input > 1 else None
        rank_max_arg = int(rank_max_input) if rank_max_input < 500000 else None
        if rank_min_arg is not None and rank_max_arg is not None and rank_min_arg > rank_max_arg:
            st.warning("位次下限不能大于上限，请调整筛选条件。")
            return

    df = search_schools_enriched(
        year,
        province,
        subject_type,
        keyword,
        admission_category=admission_category,
        batch=batch,
        min_score_min=score_min_arg,
        min_score_max=score_max_arg,
        rank_min=rank_min_arg,
        rank_max=rank_max_arg,
        is_985=True if filter_985 else None,
        is_211=True if filter_211 else None,
        is_double_first_class=True if filter_dfc else None,
        city=None if city_sel == "全部" else city_sel,
        school_type=None if type_sel == "全部" else type_sel,
    )
    st.caption(f"共 {len(df)} 条记录（最多显示 500 条）")
    if df.empty:
        st.info("无匹配记录。若元数据列为空，请先运行 import-school-metadata 导入 seed。")
    else:
        display = df.rename(
            columns={
                "standard_name": "标准校名",
                "city": "城市",
                "is_985": "985",
                "is_211": "211",
                "is_double_first_class": "双一流",
                "school_type": "学校类型",
                "ownership": "办学性质",
            }
        )
        st.dataframe(display, use_container_width=True, hide_index=True)


def page_tier_analysis() -> None:
    st.title("学校层次分析")
    st.caption("基于 school_metadata seed 与投档线 join，仅供演示")

    tier = get_metadata_tier_counts()
    if tier.get("total", 0) == 0:
        st.warning(
            "school_metadata 表为空。请运行："
            "`python main.py import-school-metadata data/manual/school_metadata_seed.csv`"
        )
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("元数据院校数", tier["total"])
    c2.metric("985", tier["count_985"])
    c3.metric("211", tier["count_211"])
    c4.metric("双一流", tier["count_dfc"])

    st.divider()
    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("按城市统计")
        city_df = get_metadata_by_city()
        if city_df.empty:
            st.info("暂无城市数据。")
        else:
            st.dataframe(city_df, use_container_width=True, hide_index=True)
            fig_city = px.bar(
                city_df.head(15),
                x="城市",
                y="学校数",
                color_discrete_sequence=["#4C78A8"],
            )
            fig_city.update_layout(margin=dict(l=20, r=20, t=30, b=20), height=360)
            st.plotly_chart(fig_city, use_container_width=True)

    with col_b:
        st.subheader("按学校类型统计")
        type_df = get_metadata_by_school_type()
        if type_df.empty:
            st.info("暂无类型数据。")
        else:
            st.dataframe(type_df, use_container_width=True, hide_index=True)
            fig_type = px.pie(type_df, names="学校类型", values="学校数")
            fig_type.update_layout(margin=dict(l=20, r=20, t=30, b=20), height=360)
            st.plotly_chart(fig_type, use_container_width=True)

    st.divider()
    st.subheader("分数段可达层次院校")
    st.caption("筛选投档最低分 ≤ 指定分数的院校（按 standard_name 去重）")

    f1, f2, f3, f4 = st.columns(4)
    years = get_distinct_values("year")
    with f1:
        tier_year = st.selectbox("年份", options=years, index=max(0, len(years) - 1), key="tier_year")
    with f2:
        tier_subject = st.selectbox(
            "科类",
            options=get_distinct_values("subject_type"),
            key="tier_subject",
        )
    with f3:
        tier_score = st.number_input(
            "分数上限",
            min_value=0,
            max_value=750,
            value=600,
            step=1,
            key="tier_score",
        )
    with f4:
        tier_label = st.selectbox("层次", options=["985", "211", "双一流"], key="tier_label")

    reachable = get_tier_reachable_schools(
        int(tier_year),
        "江苏",
        tier_subject,
        float(tier_score),
        tier_label,
    )
    st.caption(
        f"{tier_year} 年 · {tier_subject} · 分数 ≤ {tier_score} · {tier_label}："
        f"共 {len(reachable)} 所"
    )
    if reachable.empty:
        st.info("该分数段暂无匹配层次院校（可能 seed 未覆盖或分数偏低）。")
    else:
        st.dataframe(reachable, use_container_width=True, hide_index=True)


def page_charts() -> None:
    st.title("图表分析")

    st.download_button(
        label="导出当前数据为 Excel（含图表）",
        data=export_excel_bytes(),
        file_name="gaokao_dashboard_report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="charts_export_excel",
    )
    st.divider()

    st.subheader("年份对比：2023 vs 2024")
    comparison = get_year_comparison([2023, 2024])
    if comparison.empty:
        st.info("暂无 2023 / 2024 对比数据。")
    else:
        display = comparison.rename(
            columns={
                "year": "年份",
                "total_records": "总记录数",
                "history_count": "历史类数量",
                "physics_count": "物理类数量",
                "avg_min_score": "平均最低分",
                "max_min_score": "最高最低分",
            }
        )
        st.dataframe(display, use_container_width=True, hide_index=True)

        comp_long = comparison.melt(
            id_vars=["year"],
            value_vars=["history_count", "physics_count"],
            var_name="科类",
            value_name="数量",
        )
        comp_long["科类"] = comp_long["科类"].map(
            {"history_count": "历史类", "physics_count": "物理类"}
        )
        fig_year = px.bar(
            comp_long,
            x="year",
            y="数量",
            color="科类",
            barmode="group",
            labels={"year": "年份", "数量": "记录数"},
            color_discrete_map={"历史类": "#E45756", "物理类": "#54A24B"},
        )
        fig_year.update_layout(margin=dict(l=20, r=20, t=30, b=20), height=320)
        st.plotly_chart(fig_year, use_container_width=True)

    st.divider()

    year, province, subject_type, admission_category, batch = sidebar_filters(
        "chart", include_category=True
    )
    chart_mode = resolve_dashboard_query_mode(year, province)
    df = get_school_chart_data(
        year, province, subject_type, admission_category, batch, mode=chart_mode
    )

    if df.empty:
        hint = "位次" if chart_mode == "rank" else "分数"
        st.warning(f"当前筛选条件下无可用 {hint} 数据。")
        return

    mode_label = "位次" if chart_mode == "rank" else "分数"
    st.caption(f"当前数据集：{len(df)} 条有效投档记录 · 展示模式：{mode_label}")

    col1, col2 = st.columns(2)
    value_col = "min_rank" if chart_mode == "rank" else "min_score"
    value_label = "最低位次" if chart_mode == "rank" else "投档最低分"

    with col1:
        st.subheader(f"图1：{mode_label}分布")
        fig_hist = px.histogram(
            df,
            x=value_col,
            nbins=30,
            labels={value_col: value_label, "count": "院校数"},
            color_discrete_sequence=["#4C78A8"],
        )
        fig_hist.update_layout(margin=dict(l=20, r=20, t=30, b=20), height=380)
        st.plotly_chart(fig_hist, use_container_width=True)

    with col2:
        st.subheader("图2：科类对比")
        subject_df = df.dropna(subset=[value_col])
        if subject_df.empty:
            st.info("暂无科类对比数据。")
        else:
            fig_box = px.box(
                subject_df,
                x="subject_type",
                y=value_col,
                color="subject_type",
                labels={"subject_type": "科类", value_col: value_label},
            )
            fig_box.update_layout(
                showlegend=False,
                margin=dict(l=20, r=20, t=30, b=20),
                height=380,
            )
            st.plotly_chart(fig_box, use_container_width=True)

    if chart_mode == "rank":
        st.subheader("图3：Top20 低位次学校（位次越小越好）")
        top20 = (
            df.dropna(subset=["min_rank"])
            .sort_values("min_rank", ascending=True)
            .drop_duplicates(subset=["school_name", "subject_type"], keep="first")
            .head(20)
        )
        sort_col = "min_rank"
        bar_label = "最低位次"
    else:
        st.subheader("图3：Top20 高分学校")
        top20 = (
            df.dropna(subset=["min_score"])
            .sort_values("min_score", ascending=False)
            .drop_duplicates(subset=["school_name", "subject_type"], keep="first")
            .head(20)
        )
        sort_col = "min_score"
        bar_label = "投档最低分"

    if top20.empty:
        st.info("暂无 Top20 数据。")
    else:
        top20 = top20.copy()
        top20["label"] = top20.apply(
            lambda r: f"{r['school_name']} ({r['subject_type']})", axis=1
        )
        fig_bar = px.bar(
            top20.sort_values(sort_col, ascending=chart_mode == "rank"),
            x=sort_col,
            y="label",
            orientation="h",
            labels={sort_col: bar_label, "label": "院校"},
            color=sort_col,
            color_continuous_scale="Blues",
        )
        fig_bar.update_layout(
            margin=dict(l=20, r=20, t=30, b=20),
            height=520,
            showlegend=False,
        )
        st.plotly_chart(fig_bar, use_container_width=True)


def page_quality() -> None:
    st.title("数据质量")

    stats = get_quality_stats()

    c1, c2, c3 = st.columns(3)
    c1.metric("school 总数", f"{stats['school_total']:,}")
    c2.metric("rank 总数", f"{stats['rank_total']:,}")
    c3.metric("control 总数", f"{stats['control_total']:,}")

    st.divider()
    st.subheader("空值检查")

    checks = pd.DataFrame(
        [
            {
                "表": "school_admission_line",
                "检查项": "subject_type 为空",
                "数量": stats["school_empty_subject"],
                "状态": "正常" if stats["school_empty_subject"] == 0 else "异常",
            },
            {
                "表": "school_admission_line",
                "检查项": "school_name 为空",
                "数量": stats["school_empty_name"],
                "状态": "正常" if stats["school_empty_name"] == 0 else "异常",
            },
            {
                "表": "score_rank_table",
                "检查项": "subject_type 为空",
                "数量": stats["rank_empty_subject"],
                "状态": "正常" if stats["rank_empty_subject"] == 0 else "异常",
            },
            {
                "表": "province_control_line",
                "检查项": "subject_type 为空",
                "数量": stats["control_empty_subject"],
                "状态": "正常" if stats["control_empty_subject"] == 0 else "异常",
            },
        ]
    )
    st.dataframe(checks, use_container_width=True, hide_index=True)

    has_issue = (
        stats["school_empty_subject"] > 0
        or stats["school_empty_name"] > 0
        or stats["rank_empty_subject"] > 0
        or stats["control_empty_subject"] > 0
    )
    if has_issue:
        st.error("存在空值异常，请检查导入数据。")
    else:
        st.success("school 的 subject_type / school_name 均无空值。")

    if stats["rank_total"] == 0 or stats["control_total"] == 0:
        st.info(
            "rank / control 表当前为空（官网源多为图片格式，需手动录入或等待 Excel/HTML 表格源）。"
        )


def page_about() -> None:
    st.title("项目说明")
    st.markdown(
        """
### 数据来源
- 数据来自**江苏省教育考试院**公开发布的招考信息
- 系统支持自动发现公告、下载附件并结构化入库

### 当前能力
| 类型 | 状态 | 说明 |
|------|------|------|
| **school** | 已结构化 | 院校投档线 Excel 可自动导入 |
| **rank** | 图片源 | 一分一段表官网多为 JPG/PNG，**暂不做 OCR** |
| **control** | 图片源 | 省控线官网多为图片，**暂不做 OCR** |

### 项目定位
本项目是**数据采集与结构化 MVP**，用于：
- 爬取与清洗官方录取数据
- 提供查询 API 与可视化看板
- 验证多年份、多科类数据质量

**不是**志愿预测系统，不提供录取概率测算或志愿填报建议。

### 技术栈
Python · SQLite · FastAPI · Streamlit · Plotly

### 学校元数据（Phase 9）
- `school_metadata` 为人工维护 seed（约 40 所江苏常见院校）
- 用于投档线与 985/211/城市/类型 join 演示，**非全国完整库**
- 导入：`python main.py import-school-metadata data/manual/school_metadata_seed.csv`
        """
    )


def main() -> None:
    page = st.sidebar.radio("导航", PAGES, label_visibility="collapsed")
    st.sidebar.divider()

    if page == "首页":
        page_home()
    elif page == "学校查询":
        page_school_search()
    elif page == "学校层次分析":
        page_tier_analysis()
    elif page == "图表":
        page_charts()
    elif page == "数据质量":
        page_quality()
    else:
        page_about()


if __name__ == "__main__":
    main()
