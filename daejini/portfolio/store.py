"""보유 종목 저장 (뉴스와 같은 SQLite 파일, 별도 테이블)."""
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..news.store import DEFAULT_DB

SCHEMA = """
CREATE TABLE IF NOT EXISTS holdings (
    ticker TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    sector TEXT NOT NULL,
    quantity REAL NOT NULL CHECK (quantity > 0),
    avg_price REAL NOT NULL CHECK (avg_price > 0),
    added_at TEXT NOT NULL
);
"""


@dataclass
class Holding:
    ticker: str
    name: str
    sector: str
    quantity: float
    avg_price: float

    @property
    def cost(self) -> float:
        return self.quantity * self.avg_price


class PortfolioStore:
    def __init__(self, path=DEFAULT_DB):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def holdings(self) -> list[Holding]:
        rows = self.conn.execute(
            "SELECT ticker, name, sector, quantity, avg_price FROM holdings ORDER BY added_at"
        )
        return [Holding(**dict(r)) for r in rows]

    def buy(self, ticker: str, name: str, sector: str, quantity: float, price: float) -> Holding:
        """보유 중이면 추가 매수로 보고 평균단가를 다시 계산한다."""
        if quantity <= 0 or price <= 0:
            raise ValueError("수량과 단가는 0보다 커야 해요.")
        row = self.conn.execute("SELECT quantity, avg_price FROM holdings WHERE ticker = ?", (ticker,)).fetchone()
        with self.conn:
            if row:
                total_qty = row["quantity"] + quantity
                avg = (row["quantity"] * row["avg_price"] + quantity * price) / total_qty
                self.conn.execute(
                    "UPDATE holdings SET quantity = ?, avg_price = ? WHERE ticker = ?", (total_qty, avg, ticker)
                )
            else:
                self.conn.execute(
                    "INSERT INTO holdings VALUES (?, ?, ?, ?, ?, ?)",
                    (ticker, name, sector, quantity, price, datetime.now(timezone.utc).isoformat()),
                )
        return next(h for h in self.holdings() if h.ticker == ticker)

    def update(self, ticker: str, quantity: float, avg_price: float) -> None:
        if quantity <= 0 or avg_price <= 0:
            raise ValueError("수량과 단가는 0보다 커야 해요.")
        with self.conn:
            self.conn.execute(
                "UPDATE holdings SET quantity = ?, avg_price = ? WHERE ticker = ?", (quantity, avg_price, ticker)
            )

    def remove(self, ticker: str) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM holdings WHERE ticker = ?", (ticker,))
