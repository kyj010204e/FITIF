import re
from getpass import getpass
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

# ---------- 설정 ----------
BASE = Path(r"C:\medicalAI\DataSets\Diabetes Datasets-ShanghaiT1DM and ShanghaiT2DM")
SOURCE_TYPE = "SHANGHAI_DATASET"   # 03번 파일과 같은 값이어야 같은 진료(encounter)를 찾아요
DRUG_COLUMNS = ["Hypoglycemic Agents", "Other Agents"]   # 약 목록이 들어있는 두 칸
EMPTY_WORDS = {"none", "nan", "/", ""}                   # '약 없음' 표시들


def split_top(value):
    """쉼표로 약 이름을 나누되, 괄호 안의 쉼표는 나누지 않는다."""
    out, depth, cur = [], 0, ""
    for ch in str(value):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return out


def clean_name(name):
    """앞뒤 공백 제거 + 연속된 공백을 한 칸으로."""
    return re.sub(r"\s+", " ", name).strip()


# ---------- 1) 전처리 ----------
t1 = pd.read_excel(BASE / "Shanghai_T1DM_Summary.xlsx")
t2 = pd.read_excel(BASE / "Shanghai_T2DM_Summary.xlsx")
summary = pd.concat([t1, t2], ignore_index=True)

parts = summary["Patient Number"].astype(str).str.split("_", expand=True)
summary["patient_no"] = parts[0]
summary["visit_date"] = pd.to_datetime(parts[2], format="%Y%m%d")

rx_rows = []        # 한 줄 = 처방 한 건 (환자, 방문일, 약)
drug_names = {}     # 소문자 이름 -> 대표 이름
for _, r in summary.iterrows():
    seen = set()
    for col in DRUG_COLUMNS:
        if pd.isna(r[col]):
            continue
        for raw in split_top(r[col]):
            name = clean_name(raw)
            key = name.lower()
            if key in EMPTY_WORDS or key in seen:
                continue
            seen.add(key)
            drug_names.setdefault(key, name)
            rx_rows.append({
                "pseudo_code": "P" + r["patient_no"],
                "visit_date": r["visit_date"].date(),
                "source_type": SOURCE_TYPE,
                "drug_key": key,
            })

drug_rows = [{"drug_name": n, "drug_key": k} for k, n in drug_names.items()]
print("약 종류 수(중복 제거):", len(drug_rows))
print("넣을 처방 기록 수:", len(rx_rows))

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

# ---------- 3) drug, prescription 넣기 ----------
# NOT EXISTS 덕분에 여러 번 실행해도 중복으로 들어가지 않아요.
insert_drug = text("""
    INSERT INTO drug (drug_name)
    SELECT :drug_name
    WHERE NOT EXISTS (
        SELECT 1 FROM drug d WHERE lower(d.drug_name) = :drug_key
    )
""")

insert_rx = text("""
    INSERT INTO prescription (encounter_id, drug_id)
    SELECT e.encounter_id, d.drug_id
    FROM encounter e
    JOIN member m ON m.member_id = e.member_id
    JOIN drug d ON lower(d.drug_name) = :drug_key
    WHERE m.pseudo_code = :pseudo_code
      AND e.visit_date = :visit_date
      AND e.source_type = :source_type
      AND NOT EXISTS (
          SELECT 1 FROM prescription p
          WHERE p.encounter_id = e.encounter_id
            AND p.drug_id = d.drug_id
      )
""")

with engine.begin() as conn:
    conn.execute(insert_drug, drug_rows)
    conn.execute(insert_rx, rx_rows)
    n_drug = conn.execute(text("SELECT COUNT(*) FROM drug")).scalar()
    n_rx = conn.execute(text("SELECT COUNT(*) FROM prescription")).scalar()

print("drug 테이블의 현재 행 수:", n_drug)
print("prescription 테이블의 현재 행 수:", n_rx)