from bs4 import BeautifulSoup


def parse_ocr_document(raw):
    """PaddleOCR 원본 JSON -> 편집 가능한 문서 구조"""
    pages = []

    for page_index, page in enumerate(raw.get("pages", [])):
        contents = []

        for block in page.get("blocks", []):
            kind = block.get("type", "text")
            html = block.get("content_raw", "") or ""

            if kind == "table":
                soup = BeautifulSoup(html, "html.parser")
                tables = soup.find_all("table")

                for table in tables:
                    rows = []

                    for tr in table.find_all("tr"):
                        cells = []

                        for cell in tr.find_all(
                            ["td", "th"], recursive=False
                        ):
                            cells.append({
                                "text": cell.get_text(
                                    " ", strip=True
                                ),
                                "colspan": max(
                                    1, int(cell.get("colspan", 1))
                                ),
                                "rowspan": max(
                                    1, int(cell.get("rowspan", 1))
                                ),
                            })

                        if cells:
                            rows.append(cells)

                    contents.append({
                        "type": "table",
                        "rows": rows,
                    })

                if not tables:
                    contents.append({
                        "type": "text",
                        "text": block.get("text", ""),
                    })

            else:
                text = block.get("text", "")

                if text and text.strip():
                    contents.append({
                        "type": "text",
                        "text": text,
                    })

        pages.append({
            "page": page.get("page_number", page_index + 1),
            "contents": contents,
        })

    return {"pages": pages}


def export_confirmed(document):
    """편집 결과 -> 간결한 범용 JSON"""
    pages = []

    for page in document["pages"]:
        contents = []

        for item in page["contents"]:
            if item["type"] == "table":
                contents.append({
                    "type": "table",
                    "rows": [
                        [cell["text"] for cell in row]
                        for row in item["rows"]
                    ],
                })
            else:
                contents.append({
                    "type": item["type"],
                    "content": item.get("text", ""),
                })

        pages.append({
            "page": page["page"],
            "contents": contents,
        })

    return {
        "review_status": "user_confirmed",
        "pages": pages,
    }
