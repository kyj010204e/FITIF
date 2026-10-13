from getpass import getpass
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

# ---------- 설정 ----------
HOSP = Path(r"C:\medicalAI\DataSets\mimic-iv-clinical-database-demo-2.2\hosp")
SOURCE = "MIMIC_DATASET"

# ---------- 1) 전처리 ----------
adm = pd.read_csv(HOSP / "admissions.csv.gz", dtype=str)
dx = pd.read_csv(HOSP / "diagnoses_icd.csv.gz", dtype=str)
names = pd.read_csv(HOSP / "d_icd_diagnoses.csv.gz", dtype=str)

enc = pd.DataFrame({
    "hadm_id": adm["hadm_id"],
    "pseudo_code": "M" + adm["subject_id"],
    "visit_date": adm["admittime"].str[:10],      # 'YYYY-MM-DD'
})

# ICD-10만 사용하고 진단 이름 붙이기
names10 = names[names["icd_version"] == "10"][["icd_code", "long_title"]]
dx10 = dx[dx["icd_version"] == "10"].merge(names10, on="icd_code", how="left")
print("입원:", len(enc), "/ ICD-10 진단:", len(dx10))

# ---------- 2) PostgreSQL 접속 ----------
password = getpass("PostgreSQL postgres 비밀번호 (입력해도 화면에 안 보여요): ")
url = URL.create(
    "postgresql+psycopg2",
    username="postgres",
    password=password,
    host="localhost",
    port=5432,
    database="team_project",
)
engine = create_engine(url)

# ---------- 3) 적재 ----------
with engine.begin() as conn:      # 끝까지 성공하면 저장, 오류가 나면 전부 취소
    already = conn.execute(
        text("SELECT COUNT(*) FROM encounter WHERE source_type = :s"), {"s": SOURCE}
    ).scalar()
    if already:
        raise SystemExit(f"이미 {already}건이 들어 있어요. 중복 방지를 위해 중단합니다.")

    member_ids = dict(conn.execute(
        text("SELECT pseudo_code, member_id FROM member WHERE pseudo_code LIKE 'M%'")
    ).all())

    enc_before = conn.execute(text("SELECT COUNT(*) FROM encounter")).scalar()
    dx_before = conn.execute(text("SELECT COUNT(*) FROM diagnosis")).scalar()

    # 입원번호(hadm_id) -> 새로 생긴 encounter_id
    hadm_to_enc = {}
    for r in enc.itertuples():
        eid = conn.execute(
            text("""INSERT INTO encounter (member_id, visit_date, source_type)
                    VALUES (:m, :d, :s) RETURNING encounter_id"""),
            {"m": member_ids[r.pseudo_code], "d": r.visit_date, "s": SOURCE},
        ).scalar()
        hadm_to_enc[r.hadm_id] = eid

    dx_rows = [
        {"e": hadm_to_enc[h], "c": c, "n": n[:200]}
        for h, c, n in zip(dx10["hadm_id"], dx10["icd_code"], dx10["long_title"])
    ]
    conn.execute(
        text("""INSERT INTO diagnosis (encounter_id, icd10_code, diagnosis_name)
                VALUES (:e, :c, :n)"""),
        dx_rows,
    )

    enc_after = conn.execute(text("SELECT COUNT(*) FROM encounter")).scalar()
    dx_after = conn.execute(text("SELECT COUNT(*) FROM diagnosis")).scalar()

print(f"encounter: {enc_before} -> {enc_after}")
print(f"diagnosis: {dx_before} -> {dx_after}")