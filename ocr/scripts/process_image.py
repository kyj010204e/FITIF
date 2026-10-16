import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(
        description="FITIF 이미지 → JSON"
    )

    parser.add_argument("--input", required=True)
    parser.add_argument("--device", default="gpu:0")
    parser.add_argument("--timeout", type=int, default=120)

    args = parser.parse_args()

    image = Path(args.input).expanduser().resolve()

    if not image.is_file():
        parser.error(f"이미지가 없습니다: {image}")

    if image.suffix.lower() not in {
        ".png", ".jpg", ".jpeg", ".webp"
    }:
        parser.error("지원하지 않는 이미지 형식입니다.")

    if args.timeout <= 0:
        parser.error("timeout은 1 이상의 정수여야 합니다.")

    name = image.stem
    raw_dir = ROOT / "outputs" / "raw" / name
    json_path = ROOT / "outputs" / "json" / f"{name}.json"

    # 동일 작업의 이전 결과와 혼합 방지
    if raw_dir.exists() or json_path.exists():
        parser.error(
            f"동일한 작업 결과가 이미 있습니다: {name}"
        )

    print("[1/3] OCR 실행", flush=True)

    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "ocr_runner.py"),
            "--input", str(image),
            "--output", str(raw_dir),
            "--device", args.device,
            "--timeout", str(args.timeout),
        ],
        cwd=ROOT,
        check=True,
    )

    print("[2/3] OCR 실행 결과 확인", flush=True)

    manifest_path = raw_dir / "manifest.json"

    if not manifest_path.is_file():
        raise RuntimeError("OCR manifest.json이 없습니다.")

    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8")
    )

    if manifest.get("status") != "success":
        raise RuntimeError(
            f"OCR 상태가 success가 아닙니다: "
            f"{manifest.get('status')}"
        )

    print("[3/3] JSON 변환", flush=True)

    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "export_json.py"),
            "--raw-dir", str(raw_dir),
            "--input", str(image),
            "--output", str(json_path),
        ],
        cwd=ROOT,
        check=True,
    )

    if not json_path.is_file():
        raise RuntimeError("최종 JSON이 생성되지 않았습니다.")

    data = json.loads(
        json_path.read_text(encoding="utf-8")
    )

    pages = data.get("pages", [])
    blocks = [
        block
        for page in pages
        for block in page.get("blocks", [])
    ]

    print("\n=== FITIF OCR 완료 ===")
    print("JSON:", json_path)
    print("페이지 수:", len(pages))
    print("블록 수:", len(blocks))


if __name__ == "__main__":
    main()
