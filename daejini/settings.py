"""설정 값 읽기와 앱 비밀번호.

로컬에서는 .env, Streamlit Community Cloud에서는 앱 설정의 Secrets에 값을 넣는다.
Secrets 값은 환경 변수로 옮겨 두어 나머지 코드는 os.environ만 보면 되게 한다.
"""
import hmac
import os

KEYS = ("ANTHROPIC_API_KEY", "DART_API_KEY", "SEC_USER_AGENT", "APP_PASSWORD")


def load_secrets(secrets) -> None:
    """Streamlit secrets(dict 비슷한 객체)의 값을 환경 변수로. 이미 있는 환경 변수는 덮어쓰지 않는다."""
    for key in KEYS:
        if os.environ.get(key):
            continue
        try:
            value = secrets.get(key)
        except Exception:  # 로컬에 secrets.toml이 없으면 읽을 때 예외가 난다
            return
        if value:
            os.environ[key] = str(value)


def app_password() -> str:
    """비어 있으면 비밀번호 없이 열린다 (로컬 사용)."""
    return os.environ.get("APP_PASSWORD", "")


def password_ok(given: str, expected: str) -> bool:
    """입력 길이와 상관없이 같은 시간에 비교한다."""
    return bool(expected) and hmac.compare_digest(given.encode(), expected.encode())
