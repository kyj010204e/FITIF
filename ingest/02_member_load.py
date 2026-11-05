from getpass import getpass
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

# ---------- 설정 ----------
BASE = Path(r"C:\medicalAI\DataSets\Diabetes Datasets-ShanghaiT1DM and ShanghaiT2DM")

# ---------- 1) 전처리 (01_member_preview.py 와 같은 내용) ----------
t1 = pd.read_excel(BASE / "Shanghai_T1DM_Summary.xlsx")
t2 = pd.read_excel(BASE / "Shanghai_T2DM_Summary.xlsx")
summary = pd.concat([t1, t2], ignore_index=True)

parts = summary["Patient Number"].astype(str).str.split("_", expand=True)
summary["patient_no"] = parts[0]
summary["visit_date"] = pd.to_datetime(parts[2], format="%Y%m%d")

summary = summary.sort_values(["patient_no", "visit_date"])
first = summary.drop_duplicates("patient_no", keep="first")

member = pd.DataFrame({
    "pseudo_code": "P" + first["patient_no"],
    "sex": first["Gender (Female=1, Male=2)"].map({1: "F", 2: "M"}),
    "birth_year": (first["visit_date"].dt.year - first["Age (years)"]).astype(int),
})
rows = member.to_dict("records")
print("넣을 행 수:", len(rows))

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

# ---------- 3) member 테이블에 넣기 ----------
insert_sql = text("""
    INSERT INTO member (pseudo_code, sex, birth_year)
    VALUES (:pseudo_code, :sex, :birth_year)
    ON CONFLICT (pseudo_code) DO NOTHING
""")

with engine.begin() as conn:
    conn.execute(insert_sql, rows)
    count = conn.execute(text("SELECT COUNT(*) FROM member")).scalar()

print("member 테이블의 현재 행 수:", count)