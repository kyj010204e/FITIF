import os
import json
from datetime import date

import psycopg2
from dotenv import load_dotenv


def check_ocr_json(data):
    if data.get("review_status") != "user_confirmed":
        raise ValueError("사용자 검수가 끝나지 않았습니다.")

    visit_date = date.fromisoformat(data["encounter"]["visit_date"])

    if not data["diagnoses"] and not data["prescriptions"]:
        raise ValueError("저장할 진단/처방이 없습니다.")

    for d in data["diagnoses"]:
        if not d.get("icd10_code"):
            raise ValueError(f"진단 코드가 비어 있습니다: {d.get('raw_code')}")

    return visit_date

def find_drug_id(cur, product_code):
    if not product_code:
        return None
    cur.execute("SELECT drug_id FROM drug WHERE edi_code = %s", (product_code,))
    row = cur.fetchone()
    return row[0] if row else None

def load_ocr_result(
    conn, member_id, data, document_type="prescription",
    dry_run=True, on_unmatched="fail",
):
    visit_date = check_ocr_json(data)
    source_type = data["encounter"]["source_type"]

    try:
        with conn.cursor() as cur:
            # 1) 약 -> drug_id 찾기 (읽기만)
            rx_rows = []
            unmatched = []
            for p in data["prescriptions"]:
                drug_id = find_drug_id(cur, p.get("reviewed_product_code"))
                if drug_id is None:
                    unmatched.append(p.get("drug_name_raw"))
                    continue
                rx_rows.append(
                    (drug_id, p.get("dose"), p.get("frequency"), p.get("duration_days"))
                )

            if unmatched and on_unmatched == "fail":
                raise ValueError(f"drug_id를 찾지 못한 약: {unmatched}")

            # 2) encounter
            cur.execute(
                """
                INSERT INTO encounter (member_id, visit_date, source_type)
                VALUES (%s, %s, %s)
                RETURNING encounter_id
                """,
                (member_id, visit_date, source_type),
            )
            encounter_id = cur.fetchone()[0]

            # 3) source_document_v2
            cur.execute(
                """
                INSERT INTO source_document_v2 (encounter_id, document_type)
                VALUES (%s, %s)
                RETURNING document_id
                """,
                (encounter_id, document_type),
            )
            document_id = cur.fetchone()[0]

            # 4) diagnosis
            for d in data["diagnoses"]:
                cur.execute(
                    """
                    INSERT INTO diagnosis (encounter_id, icd10_code, diagnosis_name)
                    VALUES (%s, %s, %s)
                    """,
                    (encounter_id, d["icd10_code"], d["icd10_title"]),
                )

            # 5) prescription
            for drug_id, dose, frequency, duration_days in rx_rows:
                cur.execute(
                    """
                    INSERT INTO prescription
                        (encounter_id, drug_id, dose, frequency, duration_days)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (encounter_id, drug_id, dose, frequency, duration_days),
                )

        if dry_run:
            conn.rollback()
        else:
            conn.commit()
    except Exception:
        conn.rollback()
        raise

    return {
        "encounter_id": encounter_id,
        "document_id": document_id,
        "diagnosis_saved": len(data["diagnoses"]),
        "prescription_saved": len(rx_rows),
        "unmatched_drugs": unmatched,
        "dry_run": dry_run,
    }

def connect():
    load_dotenv()
    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=os.environ["DB_PORT"],
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )


if __name__ == "__main__":
    with open("ocr_test_v2.json", encoding="utf-8") as f:
        data = json.load(f)

    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT member_id FROM member ORDER BY member_id LIMIT 1")
            test_member_id = cur.fetchone()[0]

        result = load_ocr_result(conn, test_member_id, data, dry_run=True)
        print(result)
    finally:
        conn.close()