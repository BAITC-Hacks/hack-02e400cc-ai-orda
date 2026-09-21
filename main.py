"""Offline FAQ matcher for the AI ORDA rehearsal task (Python 3.9+)."""

import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


FAQ_PATH = Path(__file__).resolve().with_name("faq.txt")
UNKNOWN = "не знаю"


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold().replace("ё", "е")
    return " ".join(re.findall(r"[^\W_]+", text))


@dataclass(frozen=True)
class FAQ:
    topic: str
    question: str
    answer: str
    keywords: tuple


def load_faq(path: Path = FAQ_PATH) -> tuple:
    """Read exactly five Q/A records and validate the editable data file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or len(data) != 5:
        raise ValueError("faq.txt файлында дәл 5 сұрақ–жауап болуы керек.")
    entries = []
    topics = set()
    questions = set()
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("Әр FAQ жазбасы JSON объектісі болуы керек.")
        for field in ("topic", "question", "answer"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                raise ValueError(f"FAQ өрісі бос немесе қате: {field}")
        keywords = item.get("keywords")
        if not isinstance(keywords, list) or not keywords or any(
            not isinstance(word, str) or not normalize(word) for word in keywords
        ):
            raise ValueError("keywords бос емес сөздер/тіркестер тізімі болуы керек.")
        question = normalize(item["question"])
        if not question or question in questions or item["topic"] in topics:
            raise ValueError("FAQ сұрақтары мен тақырыптары қайталанбауы керек.")
        topics.add(item["topic"])
        questions.add(question)
        entries.append(FAQ(
            item["topic"], question, item["answer"].strip(),
            tuple(sorted({normalize(word) for word in keywords})),
        ))
    return tuple(entries)


def find_answer(question: str, entries: Sequence[FAQ]) -> str:
    """Prefer exact questions, then longest whole keyword phrase; reject ties."""
    query = normalize(question)
    if not query:
        return UNKNOWN
    for entry in entries:
        if query == entry.question:
            return entry.answer

    # Spaces enforce word boundaries: «трекер» must not match «трек».
    padded_query = f" {query} "
    scored = []
    for entry in entries:
        score = max(
            (len(keyword.split()) for keyword in entry.keywords
             if f" {keyword} " in padded_query),
            default=0,
        )
        scored.append((score, entry.answer))
    best = max((score for score, _ in scored), default=0)
    winners = [answer for score, answer in scored if score == best]
    return winners[0] if best > 0 and len(winners) == 1 else UNKNOWN


def main() -> int:
    try:
        entries = load_faq()
    except (OSError, ValueError) as error:
        print(f"FAQ файлын оқу қатесі: {error}", file=sys.stderr)
        return 1

    print("AI ORDA FAQ: сұрақ қойыңыз / задайте вопрос.")
    print("Шығу / выход: exit, шығу, выход.")
    while True:
        try:
            question = input("> ")
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if normalize(question) in {"exit", "quit", "шығу", "выход"}:
            return 0
        print(find_answer(question, entries))


if __name__ == "__main__":
    raise SystemExit(main())
