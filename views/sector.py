"""산업 비교: 같은 업종 기업들의 핵심 지표를 나란히."""
import altair as alt
import pandas as pd
import streamlit as st

from daejini import ui
from daejini.company.data import load_companies
from daejini.company.metrics import METRIC_INFO, fmt_metric, fmt_money

companies = load_companies()
st.title("산업 비교")
sector = st.segmented_control("업종", list(companies), default=list(companies)[0], key="sector") or list(companies)[0]

with st.spinner(f"{sector} 기업 데이터를 불러오는 중"):
    snaps = ui.sector_snapshots(sector)
for s in snaps:
    if s.error:
        st.warning(s.error)
snaps = [s for s in snaps if not s.error]
if not snaps:
    st.stop()
avg = ui.sector_average(snaps)
years = sorted({s.annuals[0].year for s in snaps if s.annuals})
st.caption(f"현재 시가총액 ÷ {'·'.join(map(str, years))} 회계연도 연간 실적(지배주주 기준). 기업마다 회계연도 마감 시점이 달라요. 데이터: Yahoo Finance")

# 비교 표
rows = []
for s in snaps:
    row = {"기업": f"{s.name} ({s.ticker})", "시가총액": fmt_money(s.market_cap, s.currency)}
    for key, (label, *_rest) in METRIC_INFO.items():
        row[label] = fmt_metric(key, getattr(s.metrics, key), s.metrics.loss)
    rows.append(row)
avg_row = {"기업": "업종 중간값", "시가총액": ""}
avg_row.update({label: fmt_metric(key, avg[key]) for key, (label, *_r) in METRIC_INFO.items()})
st.dataframe(pd.DataFrame(rows + [avg_row]), hide_index=True, use_container_width=True)

# 지표별 1위
leaders = []
for key, (label, _unit, higher, _desc) in METRIC_INFO.items():
    vals = [(getattr(s.metrics, key), s) for s in snaps if getattr(s.metrics, key) is not None]
    if key == "per":
        vals = [(v, s) for v, s in vals if v > 0]
    if key == "debt_ratio" and sector == "금융":
        continue  # 은행은 예금이 부채라 부채비율로 우열을 가리지 않음
    if len(vals) < 2:
        continue
    v, s = (max if higher else min)(vals, key=lambda x: x[0])
    leaders.append(f"**{label}** {s.name} ({fmt_metric(key, v)})")
if leaders:
    st.markdown("지표별 가장 좋은 기업: " + " · ".join(leaders))

# 지표 하나를 골라 막대 비교
st.subheader("지표 비교")
labels = {label: key for key, (label, *_r) in METRIC_INFO.items()}
pick = st.segmented_control("지표", list(labels), default="ROE", key="metric") or "ROE"
key = labels[pick]
unit, higher, desc = METRIC_INFO[key][1], METRIC_INFO[key][2], METRIC_INFO[key][3]
st.caption(desc + (" 높을수록 좋아요." if higher else " 낮을수록 좋아요."))

data = pd.DataFrame([{"기업": s.name, "값": getattr(s.metrics, key)} for s in snaps])
missing = data[data["값"].isna()]["기업"].tolist()
data = data.dropna()
if data.empty:
    st.caption("이 업종에서는 계산할 수 있는 값이 없어요.")
else:
    order = data.sort_values("값", ascending=not higher)["기업"].tolist()
    base = alt.Chart(data).encode(
        y=alt.Y("기업:N", sort=order, title=None),
        x=alt.X("값:Q", title=f"{pick} ({unit})"),
    )
    bars = base.mark_bar(cornerRadiusEnd=4, height=22, color="#1f5fd1")
    text = base.mark_text(align="left", dx=4).encode(text=alt.Text("값:Q", format=",.1f"))
    layers = [bars, text]
    if avg[key] is not None:
        rule = alt.Chart(pd.DataFrame({"평균": [avg[key]]})).mark_rule(strokeDash=[4, 3], color="#9aa3ad").encode(
            x="평균:Q", tooltip=[alt.Tooltip("평균:Q", title="업종 중간값", format=",.1f")])
        layers.append(rule)
    st.altair_chart(alt.layer(*layers).properties(height=60 + 40 * len(data)), use_container_width=True)
    note = "점선은 업종 중간값이에요."
    if missing:
        note += f" 값이 없어 빠진 기업: {', '.join(missing)}"
        if key == "per":
            note += " (적자)"
    st.caption(note)

# 기업 분석으로 이동
st.divider()
pick_col, go_col = st.columns([3, 1], vertical_alignment="bottom")
target = pick_col.selectbox("자세히 볼 기업", [s.name for s in snaps], key="sector-target")
if go_col.button("기업 분석 열기", use_container_width=True):
    st.session_state["company"] = target
    st.switch_page("views/company.py")

with st.expander("지표 읽는 법"):
    for key, (label, unit, higher, desc) in METRIC_INFO.items():
        st.markdown(f"- **{label}**: {desc}")
    st.markdown("- 업종마다 적정 수준이 달라서, 다른 업종끼리보다 같은 업종 안에서 비교하는 게 의미 있어요.")
