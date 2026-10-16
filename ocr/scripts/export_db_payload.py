import argparse
import hashlib
import json
import mimetypes
from pathlib import Path


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def cell_text(cell):
    if isinstance(cell, dict):
        return str(
            cell.get("text", cell.get("content", ""))
        )
    return str(cell if cell is not None else "")


def document_to_text(document):
    """사용자 확정 문서를 읽기 쉬운 TEXT로 변환."""
    lines = []

    for page in document.get("pages", []):
        page_no = page.get(
            "page", page.get("page_number", 1)
        )
        lines.append(f"=== PAGE {page_no} ===")

        for item in page.get("contents", []):
            if item.get("type") == "table":
                for row in item.get("rows", []):
                    values = [cell_text(c) for c in row]
                    lines.append(" | ".join(values))

            else:
                value = item.get(
                    "content", item.get("text", "")
                )
                if value:
                    lines.append(str(value))

    return "\n".join(lines)


def raw_to_text(raw):
    """수정 전 OCR 블록을 TEXT로 변환.

    HTML 표인 경우 BeautifulSoup로 텍스트만 추출.
    """
    from bs4 import BeautifulSoup

    lines = []

    for page in raw.get("pages", []):
        page_no = page.get("page_number", 1)
        lines.append(f"=== PAGE {page_no} ===")

        for block in page.get("blocks", []):
            if block.get("type") == "table":
                html = block.get("content_raw") or ""

                soup = BeautifulSoup(
                    html, "html.parser"
                )

                table_rows = soup.find_all("tr")

                if table_rows:
                    for tr in table_rows:
                        cells = tr.find_all(
                            ["td", "th"],
                            recursive=False,
                        )
                        values = [
                            cell.get_text(
                                " ", strip=True
                            )
                            for cell in cells
                        ]
                        lines.append(" | ".join(values))
                else:
                    lines.append(
                        block.get("text", "")
                    )

            else:
                value = block.get("text", "")
                if value:
                    lines.append(str(value))

    return "\n".join(lines)


def build_payload(
    image_path,
    confirmed_path,
    storage_path,
    encounter_id=None,
    raw_path=None,
):
    image_bytes = image_path.read_bytes()
    confirmed = read_json(confirmed_path)

    if confirmed.get("review_status") != "user_confirmed":
        raise ValueError(
            "사용자 확정 문서만 DB 저장 대상으로 처리합니다."
        )

    if not isinstance(confirmed.get("pages"), list):
        raise ValueError("확정 JSON에 pages 배열이 없습니다.")

    if not confirmed["pages"]:
        raise ValueError("확정 JSON의 pages가 비어 있습니다.")

    corrected_text = document_to_text(confirmed)

    if not corrected_text.strip():
        raise ValueError("확정 문서에 텍스트가 없습니다.")

    if raw_path is not None:
        raw = read_json(raw_path)
        original_text = raw_to_text(raw)
    else:
        original_text = None

    # ERD file_type varchar(10)
    file_type = image_path.suffix.lower().lstrip(".")

    if file_type == "jpeg":
        file_type = "jpg"

    if len(file_type) > 10:
        raise ValueError("file_type이 DB 길이를 초과합니다.")

    if not storage_path:
        raise ValueError("storage_path는 필수입니다.")

    if encounter_id is not None and encounter_id <= 0:
        raise ValueError("encounter_id는 양의 정수여야 합니다.")

    row = {
        "encounter_id": encounter_id,
        "file_name": image_path.name,
        "file_type": file_type,
        "storage_path": storage_path,
        "sha256": hashlib.sha256(
            image_bytes
        ).hexdigest(),
        "ocr_text_raw": original_text,
        "ocr_text_corrected": corrected_text,
    }

    return {
        "schema_version": "1.0",
        "target_table": "public.source_document",
        "ready_for_insert": encounter_id is not None,
        "data": row,
        "review": {
            "status": "user_confirmed",
            "diagnosis_mapping": "not_performed",
            "prescription_mapping": "not_performed",
        },
    }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--image", required=True, type=Path
    )
    parser.add_argument(
        "--confirmed", required=True, type=Path
    )
    parser.add_argument(
        "--storage-path", required=True
    )
    parser.add_argument(
        "--encounter-id", type=int
    )
    parser.add_argument(
        "--raw", type=Path
    )
    parser.add_argument(
        "--output", required=True, type=Path
    )

    args = parser.parse_args()

    payload = build_payload(
        image_path=args.image,
        confirmed_path=args.confirmed,
        storage_path=args.storage_path,
        encounter_id=args.encounter_id,
        raw_path=args.raw,
    )

    args.output.parent.mkdir(
        parents=True, exist_ok=True
    )

    args.output.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("DB 변환 완료")
    print("대상:", payload["target_table"])
    print(
        "INSERT 준비:",
        payload["ready_for_insert"]
    )
    print("파일:", args.output)


if __name__ == "__main__":
    main()
