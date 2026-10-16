import argparse
import json
import hashlib
import re
from pathlib import Path
from bs4 import BeautifulSoup


def natural_key(path):
    return [
        int(x) if x.isdigit() else x.lower()
        for x in re.split(r"(\d+)", path.name)
    ]


def convert_block(block):
    content = block.get("block_content", "") or ""
    block_type = block.get("block_label", "unknown")

    # HTML 표 구조는 content_raw에 그대로 보존
    plain_text = BeautifulSoup(
        content, "html.parser"
    ).get_text(" ", strip=True)

    return {
        "block_id": block.get("block_id"),
        "type": block_type,
        "order": block.get("block_order"),
        "bbox": block.get("block_bbox"),
        "content_format": (
            "html" if "<table" in content.lower()
            else "text"
        ),
        "content_raw": content,
        "text": plain_text,
    }


def convert_ocr(raw_dir, input_file=None):
    files = sorted(
        raw_dir.glob("*_res.json"),
        key=natural_key
    )

    if not files:
        raise FileNotFoundError(
            f"OCR 결과 JSON이 없습니다: {raw_dir}"
        )

    pages = []

    for index, path in enumerate(files, start=1):
        data = json.loads(
            path.read_text(encoding="utf-8")
        )

        blocks = [
            convert_block(block)
            for block in data.get("parsing_res_list", [])
        ]

        page_index = data.get("page_index")

        pages.append({
            "page_number": (
                page_index + 1
                if isinstance(page_index, int)
                else index
            ),
            "width": data.get("width"),
            "height": data.get("height"),
            "blocks": blocks,
        })

    result = {
        "schema_version": "1.0",
        "document_type": None,
        "ocr_engine": "PaddleOCR-VL",
        "review_status": "unverified",
        "source": {
            "file_name": None,
            "sha256": None,
        },
        "pages": pages,
    }

    if input_file is not None:
        if not input_file.is_file():
            raise FileNotFoundError(input_file)

        result["source"]["file_name"] = input_file.name
        result["source"]["sha256"] = hashlib.sha256(
            input_file.read_bytes()
        ).hexdigest()

    return result


def main():
    parser = argparse.ArgumentParser(
        description="PaddleOCR 결과를 FITIF 범용 JSON으로 변환"
    )

    parser.add_argument(
        "--raw-dir",
        required=True,
        type=Path
    )

    parser.add_argument(
        "--output",
        required=True,
        type=Path
    )

    parser.add_argument(
        "--input",
        type=Path,
        help="원본 파일 경로 (선택)"
    )

    args = parser.parse_args()

    result = convert_ocr(
        args.raw_dir,
        args.input
    )

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    args.output.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    print("JSON 변환 완료")
    print("페이지 수:", len(result["pages"]))
    print(
        "블록 수:",
        sum(len(p["blocks"]) for p in result["pages"])
    )
    print("저장 위치:", args.output)


if __name__ == "__main__":
    main()
