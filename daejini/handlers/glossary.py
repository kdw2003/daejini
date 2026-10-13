from ..router import GLOSSARY


def answer(parsed) -> str:
    terms = parsed.entities["term"]
    if not terms:
        return "어떤 용어가 궁금한지 알려주세요. 예: 'PER 뜻이 뭐야?'"
    return "\n".join(f"[{t}] {GLOSSARY[t]}" for t in terms)
