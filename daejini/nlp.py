"""형태소 분석 모듈. 2019년 버전의 Mecab을 설치가 쉬운 Kiwi로 교체."""
from kiwipiepy import Kiwi

_kiwi = Kiwi()
_kiwi.add_user_word("대지니", "NNP")


def tokenize(text: str) -> list[str]:
    """문장을 형태소 단위로 나눈다."""
    return [t.form for t in _kiwi.tokenize(text)]


def normalize(text: str) -> str:
    """개체 검색용: 공백 제거 + 대문자 통일."""
    return text.replace(" ", "").upper()
