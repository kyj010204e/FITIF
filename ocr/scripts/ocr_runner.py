import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def write_manifest(output_dir, data):
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "manifest.json"
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def worker(input_path, output_dir, device):
    from paddleocr import PaddleOCRVL

    start = time.perf_counter()

    print("[1/3] PaddleOCR-VL 모델 로딩", flush=True)

    pipeline = PaddleOCRVL(
        pipeline_version="v1.6",
        device=device,
    )

    load_time = time.perf_counter() - start

    print(
        f"모델 로딩 완료: {load_time:.2f}초",
        flush=True,
    )

    print("[2/3] OCR 실행", flush=True)

    predict_start = time.perf_counter()

    results = pipeline.predict(input=str(input_path))

    # 반복 가능한 결과 객체도 여기서 실제 처리
    results = list(results)

    predict_time = time.perf_counter() - predict_start

    print(
        f"OCR 추론 완료: {predict_time:.2f}초",
        flush=True,
    )

    if not results:
        raise RuntimeError("OCR 결과가 없습니다.")

    print("[3/3] 결과 저장", flush=True)

    save_start = time.perf_counter()

    for result in results:
        result.save_to_json(save_path=str(output_dir))
        result.save_to_markdown(save_path=str(output_dir))

    save_time = time.perf_counter() - save_start

    manifest = {
        "status": "success",
        "input_file": input_path.name,
        "ocr_engine": "PaddleOCR-VL",
        "pipeline_version": "v1.6",
        "device": device,
        "result_count": len(results),
        "load_seconds": round(load_time, 2),
        "predict_seconds": round(predict_time, 2),
        "save_seconds": round(save_time, 2),
        "elapsed_seconds": round(
            time.perf_counter() - start, 2
        ),
    }

    write_manifest(output_dir, manifest)

    print("결과 저장 완료", flush=True)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(
        description="FITIF 범용 OCR 실행기"
    )

    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--device", default="gpu:0")

    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="전체 OCR 실행 제한 시간(초)",
    )

    parser.add_argument(
        "--worker",
        action="store_true",
        help=argparse.SUPPRESS,
    )

    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    output_dir = Path(args.output).expanduser().resolve()

    if not input_path.is_file():
        parser.error(f"입력 파일이 없습니다: {input_path}")

    if args.timeout <= 0:
        parser.error("--timeout은 1 이상의 정수여야 합니다.")

    if args.worker:
        worker(input_path, output_dir, args.device)
        return

    # 기존 결과와 섞이지 않도록 이번 실행 전용 폴더 사용
    output_dir.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        "--input", str(input_path),
        "--output", str(output_dir),
        "--device", args.device,
        "--timeout", str(args.timeout),
    ]

    started = time.perf_counter()

    print(
        f"OCR 시작 / 제한 시간: {args.timeout}초",
        flush=True,
    )

    process = subprocess.Popen(
        command,
        start_new_session=True,
    )

    try:
        exit_code = process.wait(timeout=args.timeout)

    except subprocess.TimeoutExpired:
        print("\nOCR 실행 시간 초과", flush=True)

        # Linux에서 자식 프로세스 그룹 종료
        os.killpg(process.pid, signal.SIGTERM)

        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()

        write_manifest(output_dir, {
            "status": "timeout",
            "input_file": input_path.name,
            "device": args.device,
            "timeout_seconds": args.timeout,
            "elapsed_seconds": round(
                time.perf_counter() - started, 2
            ),
        })

        raise SystemExit(124)

    if exit_code != 0:
        write_manifest(output_dir, {
            "status": "failed",
            "input_file": input_path.name,
            "device": args.device,
            "exit_code": exit_code,
        })
        raise SystemExit(exit_code)

    print("OCR 정상 종료", flush=True)


if __name__ == "__main__":
    main()
