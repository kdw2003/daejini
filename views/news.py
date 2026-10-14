"""뉴스 브리핑: 메인 화면에서 관심 키워드를 누르면 그 키워드의 요약과 호재·악재 기사가 바로 뜬다."""
import streamlit as st

from daejini import ui
from daejini.news.service import since_iso
from daejini.ui import kst, md

PERIODS = {"오늘·어제": 2, "최근 3일": 3, "최근 7일": 7}
BADGE = {"호재": ":red-badge[호재]", "악재": ":blue-badge[악재]", "중립": ":gray-badge[중립]", None: ":gray-badge[분석 전]"}
SUGGESTIONS = ["엔비디아", "테슬라", "애플", "미국 금리", "반도체", "비트코인"]
PICK, PENDING, UNDO, MANAGE = "news-kw", "news-kw-pending", "news-kw-undo", "news-kw-manage"


def counts(articles):
    c = {"호재": 0, "악재": 0, "중립": 0, None: 0}
    for a in articles:
        c[a["sentiment"]] += 1
    return c


def add_keyword(text: str):
    """추가하고, 다음 화면에서 바로 그 키워드가 선택되게 한다."""
    kw = text.strip()
    if not kw:
        return
    if not store.add_keyword(kw):
        st.toast(f"'{kw}'은(는) 이미 있어요")
    st.session_state[PENDING] = kw
    st.session_state.pop(UNDO, None)
    st.rerun()


def unfollow(kw: str):
    """관심 해제 (버튼 콜백). 실수했을 때 되돌릴 수 있게 기억해 둔다."""
    store.remove_keyword(kw)
    ui.forget_keyword_news(kw)  # 다시 추가하면 바로 새로 모으도록
    st.session_state[UNDO] = kw


def undo_unfollow():
    kw = st.session_state.pop(UNDO, None)
    if kw:
        store.add_keyword(kw)
        st.session_state[PENDING] = kw


def sync_managed_keywords():
    """'키워드 관리' 태그 목록이 바뀌면: ×로 뺀 것은 해제, 새로 입력한 것은 추가."""
    wanted = [k.strip() for k in st.session_state.get(MANAGE, []) if k and k.strip()]
    current = store.keywords()
    removed = [k for k in current if k not in wanted]
    added = [k for k in wanted if k not in current]
    for k in removed:
        unfollow(k)
    for k in added:
        store.add_keyword(k)
    if added:
        st.session_state[PENDING] = added[-1]
        st.session_state.pop(UNDO, None)
    elif len(removed) != 1:
        st.session_state.pop(UNDO, None)  # 여러 개를 한꺼번에 뺀 경우는 되돌리기 대상이 아님


store, client = ui.get_store(), ui.get_client()
keywords = store.keywords()

st.title("뉴스 브리핑")
st.caption("관심 키워드를 누르면 그 키워드의 뉴스 요약과 기사가 바로 나와요. "
           "AI 분석은 기사 제목만 보고 한 판단이라 틀릴 수 있고, 매수·매도 권유가 아니에요.")

# ── 방금 관심 해제한 키워드 되돌리기
if st.session_state.get(UNDO):
    u_text, u_btn = st.columns([4, 1], vertical_alignment="center")
    u_text.info(f"'{st.session_state[UNDO]}'을(를) 관심 키워드에서 뺐어요.", icon=":material/check:")
    u_btn.button("되돌리기", icon=":material/undo:", on_click=undo_unfollow, use_container_width=True)

# ── 키워드가 없을 때: 추천 키워드를 눌러 바로 시작
if not keywords:
    st.markdown("**관심 키워드를 추가해 보세요.** 눌러서 바로 추가할 수 있어요.")
    cols = st.columns(len(SUGGESTIONS))
    for col, kw in zip(cols, SUGGESTIONS):
        if col.button(kw, key=f"suggest-{kw}", icon=":material/add:", use_container_width=True):
            add_keyword(kw)
    with st.form("add-first", clear_on_submit=True, border=False):
        c1, c2 = st.columns([4, 1], vertical_alignment="bottom")
        text = c1.text_input("직접 입력", placeholder="종목, 산업, 경제 주제 (예: 마이크로소프트, 2차전지)")
        if c2.form_submit_button("추가", type="primary", use_container_width=True):
            add_keyword(text)
    st.stop()

# 방금 추가한 키워드를 선택 상태로, 지워진 키워드가 선택돼 있으면 첫 키워드로
if st.session_state.get(PENDING) in keywords:
    st.session_state[PICK] = st.session_state.pop(PENDING)
if st.session_state.get(PICK) not in keywords:
    st.session_state[PICK] = keywords[0]

# ── 관심 키워드 칩: 누르면 아래에 바로 표시
selected = st.pills("관심 키워드", keywords, selection_mode="single", key=PICK) or keywords[0]

# ── 키워드 추가·편집, 기간, 새로고침
c_manage, c_refresh = st.columns(2, vertical_alignment="bottom")
with c_manage.popover("키워드 관리", icon=":material/tune:", use_container_width=True):
    st.session_state[MANAGE] = keywords  # 그릴 때마다 저장된 목록과 맞춤
    st.multiselect(
        "관심 키워드", options=keywords + [s for s in SUGGESTIONS if s not in keywords], key=MANAGE,
        accept_new_options=True, on_change=sync_managed_keywords, placeholder="키워드를 입력하고 Enter",
    )
    st.caption("태그의 × 를 누르면 관심 해제, 이름을 입력하고 Enter를 누르면 추가돼요. "
               "칸을 누르면 추천 키워드도 고를 수 있어요.")
period = st.segmented_control("기간", list(PERIODS), default="오늘·어제", key="news-period") or "오늘·어제"
days = PERIODS[period]
refresh = c_refresh.button("새로고침", icon=":material/refresh:", use_container_width=True,
                           help="선택한 키워드의 최신 뉴스를 지금 다시 모아요")

# ── 선택한 키워드의 뉴스: 처음 열면 자동으로 모으고, 30분 안에는 저장된 결과를 바로 보여줌
with st.spinner(f"'{selected}' 뉴스를 모으는 중"):
    result = ui.refresh_keyword_news(selected, days, force=refresh)
if result and result.error:
    st.warning(f"{result.error} 잠시 뒤 새로고침을 눌러 보세요.")

articles = store.recent_articles(selected, since_iso(days))
summary = store.summary(selected)
c = counts(articles)

with st.container(border=True):
    h_title, h_btn = st.columns([4, 1], vertical_alignment="center")
    h_title.subheader(md(selected), anchor=False)
    h_btn.button("관심 해제", key="unfollow", icon=":material/bookmark_remove:", on_click=unfollow, args=(selected,),
                 use_container_width=True, help="이 키워드를 관심 키워드에서 빼요")
    st.markdown(f"기사 {len(articles)}건 · :red[호재 {c['호재']}] · :blue[악재 {c['악재']}] · 중립 {c['중립']}"
                + (f" · 분석 전 {c[None]}" if c[None] else ""))
    if summary and summary["lines"]:
        st.markdown("\n".join(f"{i}. {md(line)}" for i, line in enumerate(summary["lines"], 1)))
        st.caption(f"{kst(summary['created_at'])} AI 요약 · {summary['model']}")
    elif client is None:
        st.caption("AI 3줄 요약과 호재·악재 분류는 Claude API 키가 있어야 해요. 지금은 기사 목록만 보여드려요.")

if not articles:
    st.write(f"{period} 동안 '{selected}' 기사를 찾지 못했어요. 기간을 늘리거나 다른 키워드를 눌러 보세요.")
    st.stop()

# 휴대폰에서는 분류·정렬을 한 줄씩 (버튼이 잘리지 않게)
st.html("""<style>@media (max-width: 640px) {
  .st-key-news-filters [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] { flex: 1 1 100% !important; min-width: 100% !important; }
}</style>""")
f_col, o_col = st.container(key="news-filters").columns([3, 2])
pick = f_col.segmented_control("분류", ["전체", "호재", "악재", "중립"], default="전체", key="news-filter") or "전체"
order = o_col.segmented_control("정렬", ["최신순", "영향 큰 순"], default="최신순", key="news-order") or "최신순"

shown = [a for a in articles if pick == "전체" or a["sentiment"] == pick]
if order == "영향 큰 순":
    shown.sort(key=lambda a: a["impact"] or 0, reverse=True)
if not shown:
    st.caption(f"'{pick}'로 분류된 기사가 없어요.")

for a in shown:
    title = md(a["title"])
    link = f"[{title}]({a['url']})" if a["url"].startswith("https://") else title
    st.markdown(f"{BADGE[a['sentiment']]} **{link}**")
    meta = [md(a["source"] or ""), kst(a["published"])]
    if a["impact"]:
        meta.append("영향 " + "●" * a["impact"] + "○" * (3 - a["impact"]))
    if a["target"]:
        meta.append(md(a["target"]))
    st.caption(" · ".join(m for m in meta if m))
    if a["reason"]:
        st.caption(f"근거: {md(a['reason'])}")
