import csv

from psycopg2.extras import execute_values

from ocr_loader import connect

SOURCE = "HIRA_20260731"


def read_master(path):
    with open(path, encoding="cp949", newline="") as f:
        rows = list(csv.reader(f))[1:]  # 첫 줄은 제목이라 제외

    records = []
    for r in rows:
        records.append(
            (
                r[2].strip(),           # edi_code        <- 제품코드
                r[1].strip(),           # ingredient_code <- 주성분코드
                r[3].strip(),           # drug_name       <- 제품명
                r[5].strip() or None,   # atc_code        <- ATC코드 (빈 값은 NULL)
                r[6].strip() or None,   # ingredient      <- ATC코드 명칭
                SOURCE,                 # source
            )
        )
    return records


def load_drug_master(conn, records, dry_run=True):
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM drug")
            before = cur.fetchone()[0]

            execute_values(
                cur,
                """
                INSERT INTO drug
                    (edi_code, ingredient_code, drug_name, atc_code, ingredient, source)
                VALUES %s
                ON CONFLICT (edi_code) DO NOTHING
                """,
                records,
                page_size=1000,
            )

            cur.execute("SELECT count(*) FROM drug")
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
        "inserted": inserted,
        "skipped": len(records) - inserted,
        "dry_run": dry_run,
    }


if __name__ == "__main__":
    records = read_master("ATC_CODE.csv")
    print("파일에서 읽은 행:", len(records))
    print("첫 행:", records[0])

    conn = connect()
    try:
        print(load_drug_master(conn, records, dry_run=False))
    finally:
        conn.close()