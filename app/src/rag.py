import json
import re
from pathlib import Path


DOCUMENTS = json.loads((Path(__file__).parent.parent / "data" / "documents.json").read_text())


def retrieve(question: str, limit: int = 3) -> list[dict]:
    terms = set(re.findall(r"[a-z0-9]+", question.lower()))
    scored = []
    for doc in DOCUMENTS:
        words = set(re.findall(r"[a-z0-9]+", doc["text"].lower()))
        score = len(terms & words) / max(len(terms), 1)
        scored.append((score, doc))
    ranked = [item for item in sorted(scored, key=lambda item: item[0], reverse=True) if item[0] > 0][:limit]
    return [{**doc, "score": score} for score, doc in ranked]
