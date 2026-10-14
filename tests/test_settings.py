import pytest

from daejini import settings
from daejini.portfolio.store import PortfolioStore


def test_password_ok():
    assert settings.password_ok("abc123", "abc123")
    assert not settings.password_ok("abc12", "abc123")
    assert not settings.password_ok("", "")  # 비밀번호가 없으면 로그인 화면 자체를 안 띄움
    assert settings.password_ok("한글비번", "한글비번")


def test_load_secrets_fills_missing_env_only(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "from-env")
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    settings.load_secrets({"APP_PASSWORD": "pw", "DART_API_KEY": "from-secrets", "OTHER": "x"})
    assert settings.app_password() == "pw"
    assert settings.os.environ["DART_API_KEY"] == "from-env"
    assert "OTHER" not in settings.os.environ


def test_load_secrets_without_secrets_file(monkeypatch):
    class Missing:
        def get(self, key):
            raise FileNotFoundError("no secrets.toml")

    monkeypatch.delenv("APP_PASSWORD", raising=False)
    settings.load_secrets(Missing())  # 예외 없이 지나가야 함
    assert settings.app_password() == ""


def test_portfolio_backup_roundtrip_and_validation():
    s = PortfolioStore(":memory:")
    s.buy("NVDA", "엔비디아", "반도체", 2.5, 180.0)
    s.buy("QQQ", "QQQ (나스닥 100 추종)", "ETF", 3, 700.0)
    backup = s.export()

    other = PortfolioStore(":memory:")
    other.buy("TSLA", "테슬라", "전기차·자동차", 1, 300.0)
    assert other.restore(backup) == 2
    assert [(h.ticker, h.quantity) for h in other.holdings()] == [("NVDA", 2.5), ("QQQ", 3.0)]  # 기존 종목은 대체됨

    for bad in ({"nope": []}, {"holdings": [{"ticker": "AAPL"}]}, {"holdings": [{"ticker": "AAPL", "name": "애플", "quantity": -1, "avg_price": 1}]}):
        with pytest.raises(ValueError):
            other.restore(bad)
    assert len(other.holdings()) == 2  # 잘못된 파일은 아무것도 바꾸지 않음
