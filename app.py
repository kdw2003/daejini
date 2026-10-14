"""대지니 투자 비서 (Streamlit). 실행: streamlit run app.py"""
import streamlit as st
from dotenv import load_dotenv

from daejini.settings import app_password, load_secrets, password_ok

load_dotenv()
load_secrets(st.secrets)

st.set_page_config(page_title="대지니", page_icon="docs/icons/icon-192.png", layout="wide")

# 휴대폰 화면(640px 이하): 한 줄짜리 카드가 화면을 다 차지하지 않게 2개씩 놓고 숫자를 줄인다
st.html("""
<style>
@media (max-width: 640px) {
  [data-testid="stHorizontalBlock"] { flex-wrap: wrap !important; gap: 0.5rem !important; }
  [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
    flex: 1 1 calc(50% - 0.5rem) !important; min-width: calc(50% - 0.5rem) !important;
  }
  [data-testid="stMetricValue"] { font-size: 1.35rem !important; }
  [data-testid="stMetric"] { padding: 0.6rem !important; }
  h1 { font-size: 1.8rem !important; }
}
</style>
""")

PAGES = [
    st.Page("views/home.py", title="홈", icon=":material/home:", default=True),
    st.Page("views/news.py", title="뉴스 브리핑", icon=":material/newspaper:"),
    st.Page("views/company.py", title="기업 분석", icon=":material/domain:"),
    st.Page("views/sector.py", title="산업 비교", icon=":material/compare_arrows:"),
    st.Page("views/portfolio.py", title="포트폴리오", icon=":material/account_balance_wallet:"),
    st.Page("views/signals.py", title="매매 참고 구간", icon=":material/candlestick_chart:"),
]

# 앱 비밀번호: APP_PASSWORD가 설정돼 있으면 로그인 화면부터.
# 로그인 중에도 페이지 목록을 (숨긴 채) 등록해 둬야 로그인 뒤 원래 주소의 페이지가 열린다.
password = app_password()
if password and not st.session_state.get("authed"):
    st.navigation(PAGES, position="hidden")
    _, center, _ = st.columns([1, 1.2, 1])
    with center:
        st.title("대지니")
        st.caption("미국 주식 투자 비서")
        with st.form("login"):
            given = st.text_input("비밀번호", type="password")
            if st.form_submit_button("들어가기", type="primary", use_container_width=True):
                if password_ok(given, password):
                    st.session_state["authed"] = True
                    st.rerun()
                st.error("비밀번호가 맞지 않아요.")
    st.stop()

st.navigation(PAGES, position="top").run()
