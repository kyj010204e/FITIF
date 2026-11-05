import os
import json
from datetime import date

import psycopg2
from dotenv import load_dotenv

# pgAdmin 스키마 목록에는 source_document_v2가 없고 document_log만 있어서 이쪽으로 바꿨음.
# 테이블 이름이 다르면 이 값만 고치면 됨.
DOCUMENT_TABLE = "document_log"


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


def find_disease_id(cur, icd_code):
    """icd_code로 disease_id를 찾는다. 'J10.1'과 'J101' 표기 차이는 점을 빼고 비교해서 맞춘다.
    못 찾으면 None, 여러 disease와 매칭되면 ValueError."""
    if not icd_code:
        return None
    code = icd_code.strip().upper()
    cur.execute(
        """
        SELECT DISTINCT disease_id
        FROM disease
        WHERE upper(replace(icd_code, '.', '')) = %s
        """,
        (code.replace(".", ""),),
    )
    rows = cur.fetchall()
    if len(rows) > 1:
        raise ValueError(f"진단 코드가 여러 disease와 매칭됩니다: {icd_code}")
    return rows[0][0] if rows else None


def load_ocr_result(
    conn, member_id, data, document_type="prescription",
    dry_run=True, on_unmatched="fail",
):
    visit_date = check_ocr_json(data)
    source_type = data["encounter"]["source_type"]

    try:
        with conn.cursor() as cur:
            # 1) 진단 -> disease_id 찾기 (읽기만)
            dx_ids = []
            unmatched_dx = []
            for d in data["diagnoses"]:
                disease_id = find_disease_id(cur, d.get("icd10_code"))
                if disease_id is None:
                    unmatched_dx.append(d.get("icd10_code"))
                    continue
                if disease_id not in dx_ids:  # 같은 병이 두 줄이면 한 번만 저장
                    dx_ids.append(disease_id)

            if unmatched_dx and on_unmatched == "fail":
                raise ValueError(f"disease_id를 찾지 못한 진단 코드: {unmatched_dx}")

            # 2) 약 -> drug_id 찾기 (읽기만)
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

            # 3) encounter
            cur.execute(
                """
                INSERT INTO encounter (member_id, visit_date, source_type)
                VALUES (%s, %s, %s)
                RETURNING encounter_id
                """,
                (member_id, visit_date, source_type),
            )
            encounter_id = cur.fetchone()[0]

            # 4) 문서 기록 (테이블 이름은 위의 DOCUMENT_TABLE)
            cur.execute(
                f"""
                INSERT INTO {DOCUMENT_TABLE} (encounter_id, document_type)
                VALUES (%s, %s)
                RETURNING document_id
                """,
                (encounter_id, document_type),
            )
            document_id = cur.fetchone()[0]

            # 5) diagnosis (disease_id 기준)
            for disease_id in dx_ids:
                cur.execute(
                    """
                    INSERT INTO diagnosis (encounter_id, disease_id, diagnosed_date)
                    VALUES (%s, %s, %s)
                    """,
                    (encounter_id, disease_id, visit_date),
                )

            # 6) prescription
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
        "diagnosis_saved": len(dx_ids),
        "prescription_saved": len(rx_rows),
        "unmatched_diagnoses": unmatched_dx,
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