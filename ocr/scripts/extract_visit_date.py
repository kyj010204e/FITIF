import argparse
import json
import re
from datetime import date
from pathlib import Path

DATE_PATTERN = re.compile(
    r"(?<!\d)"
    r"((?:19|20)\d{2})"
    r"\s*(?:[-./]|년\s*)\s*"
    r"(\d{1,2})"
    r"\s*(?:[-./]|월\s*)\s*"
    r"(\d{1,2})"
    r"\s*일?"
    r"(?!\d)"
)


def collect_text(document):
    texts = []

    for page in document.get("pages", []):
        for content in page.get("contents", []):
            if content.get("type") == "table":
                for row in content.get("rows", []):
                    cells = []
                    for cell in row:
                        if isinstance(cell, dict):
                            cells.append(str(cell.get("text", "")))
                        else:
                            cells.append(str(cell))
                    texts.append(" | ".join(cells))
            else:
                texts.append(str(
                    content.get("content", content.get("text", ""))
                ))

    return texts


def extract_date_candidates(document):
    grouped = {}

    for text in collect_text(document):
        for match in DATE_PATTERN.finditer(text):
            year, month, day = map(int, match.groups())

            try:
                parsed = date(year, month, day).isoformat()
            except ValueError:
                continue

            if parsed not in grouped:
                grouped[parsed] = {
                    "date": parsed,
                    "count": 0,
                    "source_text": text[:200],
                }

            grouped[parsed]["count"] += 1

    return sorted(
        grouped.values(),
        key=lambda item: (-item["count"], item["date"]),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    args = parser.parse_args()

    document = json.loads(
        Path(args.input).read_text(encoding="utf-8")
    )

    result = extract_date_candidates(document)

    print(json.dumps(result, ensure_ascii=False, indent=2))
