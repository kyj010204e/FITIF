from getpass import getpass
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

# ---------- 설정 ----------
BASE = Path(r"C:\medicalAI\DataSets\Diabetes Datasets-ShanghaiT1DM and ShanghaiT2DM")
SOURCE_TYPE = "SHANGHAI_DATASET"   # encounter.source_type 에 적을 데이터 출처 이름

# 당뇨 유형 -> ICD-10 코드 (연습용 매핑. 의학적 확정은 팀/멘토 확인 필요)
ICD10 = {
    "T1DM": ("E10", "Type 1 diabetes mellitus"),
    "T2DM": ("E11", "Type 2 diabetes mellitus"),
}

# ---------- 1) 전처리 ----------
t1 = pd.read_excel(BASE / "Shanghai_T1DM_Summary.xlsx")
t2 = pd.read_excel(BASE / "Shanghai_T2DM_Summary.xlsx")
summary = pd.concat([t1, t2], ignore_index=True)

parts = summary["Patient Number"].astype(str).str.split("_", expand=True)
summary["patient_no"] = parts[0]
summary["visit_date"] = pd.to_datetime(parts[2], format="%Y%m%d")

summary["diabetes_type"] = summary["Type of Diabetes"].astype(str).str.strip()
unknown = set(summary["diabetes_type"]) - set(ICD10)
if unknown:
    raise ValueError(f"예상하지 못한 당뇨 유형이 있어요: {unknown}")

rows = []
for _, r in summary.iterrows():
    code, name = ICD10[r["diabetes_type"]]
    rows.append({
        "pseudo_code": "P" + r["patient_no"],
        "visit_date": r["visit_date"].date(),
        "source_type": SOURCE_TYPE,
        "icd10_code": code,
        "diagnosis_name": name,
    })
print("넣을 진료(입원) 기록 수:", len(rows))

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

# ---------- 3) encounter, diagnosis 넣기 ----------
# NOT EXISTS 덕분에 이 파일을 여러 번 실행해도 같은 기록이 중복으로 들어가지 않아요.
insert_encounter = text("""
    INSERT INTO encounter (member_id, visit_date, source_type)
    SELECT m.member_id, :visit_date, :source_type
    FROM member m
    WHERE m.pseudo_code = :pseudo_code
      AND NOT EXISTS (
          SELECT 1 FROM encounter e
          WHERE e.member_id = m.member_id
            AND e.visit_date = :visit_date
            AND e.source_type = :source_type
      )
""")

insert_diagnosis = text("""
    INSERT INTO diagnosis (encounter_id, icd10_code, diagnosis_name)
    SELECT e.encounter_id, :icd10_code, :diagnosis_name
    FROM encounter e
    JOIN member m ON m.member_id = e.member_id
    WHERE m.pseudo_code = :pseudo_code
      AND e.visit_date = :visit_date
      AND e.source_type = :source_type
      AND NOT EXISTS (
          SELECT 1 FROM diagnosis d
          WHERE d.encounter_id = e.encounter_id
            AND d.icd10_code = :icd10_code
      )
""")

with engine.begin() as conn:
    conn.execute(insert_encounter, rows)
    conn.execute(insert_diagnosis, rows)
    n_enc = conn.execute(text("SELECT COUNT(*) FROM encounter")).scalar()
    n_dx = conn.execute(text("SELECT COUNT(*) FROM diagnosis")).scalar()

print("encounter 테이블의 현재 행 수:", n_enc)
print("diagnosis 테이블의 현재 행 수:", n_dx)