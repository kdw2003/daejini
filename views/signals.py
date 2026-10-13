"""매매 참고 구간: 지표 상태, 지지·저항 구간, 전략 백테스트."""
import altair as alt
import pandas as pd
import streamlit as st

from daejini import ui
from daejini.company.data import company_index
from daejini.company.metrics import currency_of, fmt_price
from daejini.news.analyze import AnalysisError
from daejini.news.service import api_error_message
from daejini.signals.analyze import explain
from daejini.signals.backtest import DEFAULT_FEE_PCT, DEFAULT_TAX_PCT, STRATEGIES, run
from daejini.signals.indicators import current_signals, zones

UP, DOWN, MUTED = "#d1242f", "#1d5fd0", "#9aa3ad"  # 상승 빨강, 하락 파랑
BUY_ZONE, SELL_ZONE = "#2a9d8f", "#e9a23b"  # 구간 색은 상승·하락 색과 겹치지 않게
TONE = {"up": "red", "down": "blue", "neutral": "gray"}

index = company_index()
st.title("매매 참고 구간")
st.caption("기술적 지표로 계산한 참고용 구간과 과거 검증 결과예요. 매수·매도 권유가 아니고, 과거 성과가 미래를 보장하지 않아요.")

name = st.selectbox("종목", list(index), format_func=lambda n: f"{n} · {index[n][1]}", key="signals-company")
ticker = index[name][0]
cur = currency_of(ticker)
PRICE_FMT = ",.0f" if cur == "KRW" else "$,.2f"
with st.spinner("5년 치 시세와 지표를 계산하는 중"):
    try:
        df = ui.ohlc_with_indicators(ticker)
    except Exception as e:
        st.error(f"시세를 불러오지 못했어요: {e}")
        st.stop()
if len(df) < 200:
    st.warning("데이터가 200거래일보다 적어 분석할 수 없어요.")
    st.stop()

signals = current_signals(df)
z = zones(df)
last_date = df["date"].iloc[-1]

# 현재 지표 상태
st.subheader("지금 차트 상태")
st.caption(f"{last_date:%Y-%m-%d} 종가 기준")
cols = st.columns(len(signals))
for col, s in zip(cols, signals):
    with col.container(border=True):
        st.caption(s.name)
        st.markdown(f"**:{TONE[s.tone]}[{s.state}]**")
        st.caption(s.detail)

# 참고 구간
st.subheader("참고 구간")
if z is None:
    st.caption("구간을 계산할 데이터가 부족해요.")
else:
    def pct(x):
        return f"현재가 대비 {(x / z.price - 1) * 100:+.1f}%"

    def won(x):
        if cur == "USD":
            return f"${x:,.2f}"
        return f"{round(x, -2 if z.price >= 10_000 else -1):,.0f}원"

    def show(col, label, value, note, help=None):
        with col:
            st.caption(label, help=help)
            st.markdown(f"#### {ui.dollars(value)}")
            st.caption(ui.dollars(note))

    c = st.columns([1, 1.4, 1.4, 1])
    show(c[0], "현재가", fmt_price(z.price, cur), f"하루 평균 변동폭 {fmt_price(z.atr, cur)}")
    if z.buy_zone:
        show(c[1], "관심 구간 (지지선 근처)", f"{won(z.buy_zone[0])} ~ {won(z.buy_zone[1])}", "지지선 " + pct(z.support),
             help="최근 120일 저점·고점 중 현재가 바로 아래 가격 ± 하루 평균 변동폭의 절반")
        show(c[3], "손절 참고선", won(z.stop), pct(z.stop),
             help="지지선에서 하루 평균 변동폭의 1.5배 아래. 이 아래로 내려가면 지지선이 무너졌다고 봐요.")
    else:
        show(c[1], "관심 구간", "없음", "최근 120일 저점보다 아래(신저가 구간)라 지지선을 찾지 못했어요.")
    if z.sell_zone:
        show(c[2], "경계 구간 (저항선 근처)", f"{won(z.sell_zone[0])} ~ {won(z.sell_zone[1])}", "저항선 " + pct(z.resistance),
             help="최근 120일 저점·고점 중 현재가 바로 위 가격 ± 하루 평균 변동폭의 절반")
    else:
        show(c[2], "경계 구간", "없음", "최근 120일 고점보다 위(신고가 구간)라 저항선을 찾지 못했어요.")

    # 6개월 캔들 차트 + 이동평균 + 볼린저 밴드 + 구간
    recent = df[df["date"] >= last_date - pd.DateOffset(months=6)].copy()
    recent["dir"] = (recent["close"] >= recent["open"]).map({True: "상승", False: "하락"})
    x = alt.X("date:T", title=None, axis=alt.Axis(format="%m.%d"))
    candle_color = alt.Color("dir:N", scale=alt.Scale(domain=["상승", "하락"], range=[UP, DOWN]), legend=None)
    band = alt.Chart(recent).mark_area(opacity=0.12, color=MUTED).encode(x=x, y="bb_lower:Q", y2="bb_upper:Q")
    wick = alt.Chart(recent).mark_rule().encode(x=x, y=alt.Y("low:Q", scale=alt.Scale(zero=False), title="원" if cur == "KRW" else "달러"), y2="high:Q", color=candle_color)
    body = alt.Chart(recent).mark_bar(width=3).encode(
        x=x, y="open:Q", y2="close:Q", color=candle_color,
        tooltip=[alt.Tooltip("date:T", title="날짜", format="%Y-%m-%d"),
                 alt.Tooltip("open:Q", title="시가", format=PRICE_FMT), alt.Tooltip("high:Q", title="고가", format=PRICE_FMT),
                 alt.Tooltip("low:Q", title="저가", format=PRICE_FMT), alt.Tooltip("close:Q", title="종가", format=PRICE_FMT)])
    ma = alt.Chart(recent).transform_fold(["ma20", "ma60"], as_=["선", "값"]).mark_line(strokeWidth=1.5).encode(
        x=x, y="값:Q",
        color=alt.Color("선:N", scale=alt.Scale(domain=["ma20", "ma60"], range=["#e8833a", "#6b7280"]),
                        legend=alt.Legend(orient="top", title=None, labelExpr="datum.label == 'ma20' ? '20일 이동평균' : '60일 이동평균'")))
    layers = [band, wick, body, ma]
    rects = []
    if z.buy_zone:
        rects.append({"구간": "관심 구간", "lo": z.buy_zone[0], "hi": z.buy_zone[1], "color": BUY_ZONE})
    if z.sell_zone:
        rects.append({"구간": "경계 구간", "lo": z.sell_zone[0], "hi": z.sell_zone[1], "color": SELL_ZONE})
    if rects:
        layers.insert(0, alt.Chart(pd.DataFrame(rects)).mark_rect(opacity=0.18).encode(
            y="lo:Q", y2="hi:Q", color=alt.Color("color:N", scale=None), tooltip=["구간", alt.Tooltip("lo:Q", format=","), alt.Tooltip("hi:Q", format=",")]))
    if z.stop:
        layers.append(alt.Chart(pd.DataFrame({"y": [z.stop]})).mark_rule(strokeDash=[5, 4], color=BUY_ZONE).encode(
            y="y:Q", tooltip=[alt.Tooltip("y:Q", title="손절 참고선", format=",.0f")]))
    st.altair_chart(alt.layer(*layers).resolve_scale(color="independent").properties(height=380),
                    use_container_width=True, theme=None)
    st.caption("초록 띠: 관심 구간 · 주황 띠: 경계 구간 · 초록 점선: 손절 참고선 · 회색 영역: 볼린저 밴드")

# 백테스트
st.subheader("과거 검증 (백테스트)")
p_col, cost_col = st.columns([1, 2])
years = {"1년": 1, "3년": 3, "5년": 5}[p_col.segmented_control("기간", ["1년", "3년", "5년"], default="3년", key="bt-years") or "3년"]
with cost_col.expander("비용 가정"):
    # 미국 주식: 증권거래세 없음, 국내 증권사 해외주식 수수료는 보통 0.07~0.25%
    fee_default, tax_default = (DEFAULT_FEE_PCT, DEFAULT_TAX_PCT) if cur == "KRW" else (0.10, 0.0)
    fee = st.number_input("수수료(%, 매수·매도 각각)", min_value=0.0, max_value=1.0, value=fee_default, step=0.005,
                          format="%.3f", key=f"fee-{cur}")
    tax = st.number_input("매도 시 세금(%)", min_value=0.0, max_value=1.0, value=tax_default, step=0.01,
                          format="%.2f", key=f"tax-{cur}")
    st.caption("기본값은 미국 주식 수수료 0.10%·세금 없음(한국 주식은 수수료 0.015%·증권거래세 0.20%) 가정이에요. "
               "환전 수수료, 양도소득세, 호가 차이(슬리피지)는 반영하지 않아요.")

# 지표 계산에 120거래일이 필요하므로 5년을 고르면 그만큼 늦게 시작
start = max(last_date - pd.DateOffset(years=years), df["date"].iloc[130])
results, hold = {}, None
with st.spinner("전략별로 과거 데이터를 돌리는 중"):
    for key, (label, _desc, _fn) in STRATEGIES.items():
        results[label], hold = run(df, key, start, fee, tax)
all_results = {**results, "단순 보유": hold}

def num(value, fmt):
    return "—" if value is None else format(value, fmt)


table = pd.DataFrame([{
    "전략": label,
    "총수익률(%)": num(r.total_return, "+.1f"),
    "연환산(%)": num(r.cagr, "+.1f"),
    "최대낙폭(%)": num(r.mdd, ".1f"),
    "거래 수": "—" if label == "단순 보유" else str(len(r.trades)),
    "승률(%)": "—" if label == "단순 보유" else num(r.win_rate, ".0f"),
    "보유 비율(%)": num(r.exposure, ".0f"),
} for label, r in all_results.items()])


def highlight(row):
    if row["전략"] == "단순 보유":
        return ["font-weight: 600"] * len(row)
    better = all_results[row["전략"]].total_return > hold.total_return
    return [f"color: {UP}" if better and c == "총수익률(%)" else "" for c in row.index]


st.dataframe(table.style.apply(highlight, axis=1), hide_index=True, use_container_width=True)
beat = [label for label, r in results.items() if r.total_return > hold.total_return]
st.caption(
    f"{start:%Y-%m-%d}부터 {last_date:%Y-%m-%d}까지, 수수료·세금 반영. "
    + (f"단순 보유보다 나았던 전략: {', '.join(beat)}." if beat else "이 기간에는 어떤 전략도 단순 보유보다 낫지 않았어요.")
    + " 최대낙폭은 고점에서 가장 많이 떨어졌던 폭이에요. 거래가 적으면 운에 좌우되기 쉬워요."
)

# 전략 하나 자세히
pick = st.segmented_control("자세히 볼 전략", list(results), default=list(results)[0], key="bt-pick") or list(results)[0]
desc = next(d for label, d, _ in STRATEGIES.values() if label == pick)
st.caption(f"규칙: {desc}. 신호는 그날 종가로 정하고 다음 날 시가에 거래해요.")
r = results[pick]
curve = pd.concat([
    pd.DataFrame({"date": r.equity.index, "자산": (r.equity.values - 1) * 100, "구분": pick}),
    pd.DataFrame({"date": hold.equity.index, "자산": (hold.equity.values - 1) * 100, "구분": "단순 보유"}),
])
chart = alt.Chart(curve).mark_line(strokeWidth=2).encode(
    x=alt.X("date:T", title=None, axis=alt.Axis(format="%y.%m")),
    y=alt.Y("자산:Q", title="누적 수익률(%)"),
    color=alt.Color("구분:N", scale=alt.Scale(domain=[pick, "단순 보유"], range=[BUY_ZONE, MUTED]), legend=alt.Legend(orient="top", title=None)),
    tooltip=[alt.Tooltip("date:T", title="날짜", format="%Y-%m-%d"), "구분", alt.Tooltip("자산:Q", title="누적 수익률(%)", format="+.1f")],
).properties(height=300)
zero = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color=MUTED, strokeDash=[3, 3]).encode(y="y:Q")
st.altair_chart(alt.layer(zero, chart), use_container_width=True, theme=None)
with st.expander(f"거래 내역 ({len(r.trades)}건)"):
    if r.trades:
        trades = pd.DataFrame(r.trades)
        st.dataframe(
            trades.style.format({"매수일": "{:%Y-%m-%d}", "매도일": "{:%Y-%m-%d}", "매수가": "{:,.0f}", "매도가": "{:,.0f}", "수익률(%)": "{:+.2f}"})
            .map(lambda v: f"color: {UP}" if v > 0 else f"color: {DOWN}" if v < 0 else "", subset=["수익률(%)"]),
            hide_index=True, use_container_width=True,
        )
    else:
        st.caption("이 기간에 신호가 한 번도 나오지 않았어요.")

# AI 해설
st.subheader("AI 해설")
client = ui.get_client()
if client is None:
    st.info("AI 해설을 쓰려면 .env에 ANTHROPIC_API_KEY를 넣으세요.")
else:
    state_key = f"signals-ai-{name}-{years}"
    if st.button("지표와 백테스트 결과 해설 듣기", type="primary"):
        with st.spinner("해설을 쓰는 중"):
            try:
                st.session_state[state_key] = explain(client, name, signals, z, all_results, years, cur)
            except AnalysisError as e:
                st.warning(str(e))
            except Exception as e:
                st.warning(api_error_message(e))
    c = st.session_state.get(state_key)
    if c:
        st.markdown(f"**{ui.md(c.summary)}**")
        st.markdown("\n".join(f"- {ui.md(p)}" for p in c.points))
        st.markdown(f"**백테스트:** {ui.md(c.backtest)}")
        st.caption(f"주의: {ui.md(c.caution)}")
