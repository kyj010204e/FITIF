import argparse
import json
from datetime import date
from pathlib import Path

from scripts.export_db_payload import build_payload


ROOT = Path(__file__).resolve().parents[1]


def build_final_payload(job_id: str, visit_date: str):
    # 진료일 검증
    parsed_date = date.fromisoformat(visit_date)

    if not (1900 <= parsed_date.year <= date.today().year):
        raise ValueError("진료일이 허용 범위를 벗어났습니다.")

    if parsed_date > date.today():
        raise ValueError("진료일은 미래 날짜일 수 없습니다.")

    confirmed_path = ROOT / "outputs/confirmed" / f"{job_id}.json"
    raw_path = ROOT / "outputs/json" / f"{job_id}.json"

    # 기존 Streamlit이 OCR 입력을 PNG로 저장
    image_path = ROOT / "inputs/real" / f"{job_id}.png"

    if not image_path.exists():
        raise FileNotFoundError(f"원본 이미지 없음: {image_path}")

    if not confirmed_path.exists():
        raise FileNotFoundError(f"확정 JSON 없음: {confirmed_path}")

    # 원본 이미지가 현재 서버에 저장된 실제 경로
    # DB 서버와 저장소가 다르면 추후 스토리지 경로로 변경해야 함
    storage_path = str(image_path.resolve())

    document_payload = build_payload(
        image_path=image_path,
        confirmed_path=confirmed_path,
        storage_path=storage_path,
        encounter_id=None,
        raw_path=raw_path if raw_path.exists() else None,
    )

    source_document = document_payload["data"].copy()

    # encounter_id는 DB INSERT 후 생성되는 값이므로 제거
    source_document.pop("encounter_id", None)

    return {
        "schema_version": "1.1",
        "event_type": "medical_document_confirmed",
        "review_status": "user_confirmed",
        "encounter": {
            "visit_date": parsed_date.isoformat(),
            "source_type": "uploaded_document",
        },
        "source_document": source_document,
        "diagnoses": [],
        "prescriptions": [],
        "metadata": {
            "job_id": job_id,
            "visit_date_confirmed": True,
            "diagnosis_extraction_status": "not_performed",
            "prescription_extraction_status": "not_performed",
            "member_id_source": "authenticated_backend",
            "encounter_id_source": "database_generated",
            "storage_path_scope": "ocr_server_local",
            "storage_transfer_required_if_separate_server": True,
            "ocr_raw_available": raw_path.exists(),
        },
    }


def save_final_payload(job_id: str, visit_date: str):
    payload = build_final_payload(job_id, visit_date)

    output = ROOT / "outputs/db_payload" / f"{job_id}_final.json"
    output.parent.mkdir(parents=True, exist_ok=True)

    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output, payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--visit-date", required=True)
    args = parser.parse_args()

    output, payload = save_final_payload(
        args.job_id,
        args.visit_date,
    )

    print("최종 DB JSON 생성 완료")
    print("진료일:", payload["encounter"]["visit_date"])
    print("출력 경로:", output)
    print("DB INSERT 실행 여부: 아니오")


if __name__ == "__main__":
    main()
