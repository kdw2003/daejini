"""대지니 투자 비서 (Streamlit). 실행: streamlit run app.py"""
import os
import sys

import streamlit as st
from dotenv import load_dotenv


def _daejini_files() -> dict:
    """지금 불러와 있는 daejini 모듈: {이름: 파일 경로}"""
    files = {}
    for name, mod in list(sys.modules.items()):
        if name == "daejini" or name.startswith("daejini."):
            path = getattr(mod, "__file__", None)
            if path and os.path.exists(path):
                files[name] = path
    return files


def _changed_since_compiled(path: str) -> bool:
    """파이썬이 모듈을 읽을 때 만든 .pyc에는 그때의 소스 수정 시각·크기가 적혀 있다.
    지금 소스와 다르면 모듈을 읽은 뒤 파일이 바뀐 것 (기록이 없는 첫 실행에서도 알아챔)."""
    import importlib.util

    try:
        with open(importlib.util.cache_from_source(path), "rb") as f:
            header = f.read(16)
        if len(header) < 16 or int.from_bytes(header[4:8], "little") != 0:
            return False  # 해시 기반 .pyc는 시각을 담지 않으므로 판단하지 않음
        stat = os.stat(path)
        return (int.from_bytes(header[8:12], "little") != int(stat.st_mtime) & 0xFFFFFFFF
                or int.from_bytes(header[12:16], "little") != stat.st_size & 0xFFFFFFFF)
    except OSError:
        return False  # .pyc가 없으면(쓰기 금지 등) 판단하지 않음


def reload_changed_daejini_modules() -> bool:
    """새 코드가 들어왔는데 이미 불러온 daejini 모듈이 예전 것이면 전부 버리고 새로 읽게 한다.

    Streamlit은 화면 파일(views/*.py)과 이 파일은 매번 새로 읽지만, 거기서 import한
    daejini 패키지는 서버를 다시 시작할 때까지 예전 것을 기억한다. 그래서 GitHub에 올린
    뒤 클라우드 앱이 '새 화면 + 예전 도우미'로 반쯤 바뀌어 AttributeError가 났다.
    이 함수는 이 파일 안에 있어야 한다(이 파일은 항상 새로 읽히므로).
    """
    seen = sys.__dict__.setdefault("_daejini_file_mtimes", {})
    files = _daejini_files()
    # 기록이 있으면 기록과 비교하고, 기록이 없을 때(서버가 이 코드 이전 버전으로 떠 있던 경우 등)만
    # .pyc와 비교한다. .pyc를 새로 쓸 수 없는 환경에서 매번 다시 읽는 일을 막기 위해서다.
    changed = any(
        (os.path.getmtime(path) != seen[path]) if path in seen else _changed_since_compiled(path)
        for path in files.values()
    )
    if changed:
        for name in files:
            sys.modules.pop(name, None)
        seen.clear()
    return changed


def remember_daejini_modules() -> None:
    """이번 실행에서 처음 불러온 모듈의 파일 수정 시각을 기억한다 (화면을 다 그린 뒤에 호출)."""
    seen = sys.__dict__.setdefault("_daejini_file_mtimes", {})
    for path in _daejini_files().values():
        seen.setdefault(path, os.path.getmtime(path))


reload_changed_daejini_modules()

from daejini.settings import app_password, load_secrets, password_ok  # noqa: E402

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
    remember_daejini_modules()
    st.stop()

try:
    st.navigation(PAGES, position="top").run()
finally:
    remember_daejini_modules()  # 화면 파일이 불러온 모듈까지 기록 (st.stop()으로 끝나도 실행됨)
