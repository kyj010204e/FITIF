import csv
import sys

from psycopg2.extras import execute_values

from ocr_loader import connect

# CSV 열 순서: 상병기호, 한글명, 영문명, 완전코드구분, 주상병사용구분,
#              법정감염병구분, 성별구분, 상한연령, 하한연령, 양한방구분
COL_CODE, COL_KO, COL_EN = 0, 1, 2


def read_master(path):
    with open(path, encoding="cp949", newline="") as f:
        rows = list(csv.reader(f))[1:]  # 첫 줄은 열 이름이라 제외

    records = {}
    for r in rows:
        code = r[COL_CODE].strip().replace(".", "").upper()
        if not code or code in records:
            continue  # 빈 코드, 또는 이미 나온 코드(동의어 줄)는 건너뜀
        name_ko = r[COL_KO].strip()
        name_en = r[COL_EN].strip()
        records[code] = (code, name_en[:200], name_ko[:200])
    return list(records.values())


def load_disease_master(conn, records, dry_run=True):
    try:
        with conn.cursor() as cur:
            cur.execute(
                "ALTER TABLE disease "
                "ADD COLUMN IF NOT EXISTS disease_name_ko VARCHAR(200)"
            )

            cur.execute("SELECT count(*) FROM disease")
            before = cur.fetchone()[0]

            execute_values(
                cur,
                """
                INSERT INTO disease (icd_code, disease_name, disease_name_ko)
                VALUES %s
                ON CONFLICT (icd_code) DO UPDATE
                    SET disease_name_ko = EXCLUDED.disease_name_ko
                """,
                records,
                page_size=1000,
            )

            cur.execute("SELECT count(*) FROM disease")
            after = cur.fetchone()[0]

        if dry_run:
            conn.rollback()
        else:
            conn.commit()
    except Exception:
        conn.rollback()
        raise

    inserted = after - before
    return {
        "before": before,
        "after": after,
        "inserted": inserted,
        "already_existed": len(records) - inserted,
        "dry_run": dry_run,
    }


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    path = args[0] if args else "disease_master.csv"
    dry_run = "--commit" not in sys.argv

    records = read_master(path)
    print("고유 코드 수:", len(records))
    print("첫 행:", records[0])

    conn = connect()
    try:
        print(load_disease_master(conn, records, dry_run=dry_run))
    finally:
        conn.close()