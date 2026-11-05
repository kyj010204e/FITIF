from getpass import getpass
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

# ---------- 설정 ----------
HOSP = Path(r"C:\medicalAI\DataSets\mimic-iv-clinical-database-demo-2.2\hosp")

# ---------- 1) 전처리 (06_mimic_member_preview.py 와 같은 내용) ----------
pt = pd.read_csv(HOSP / "patients.csv.gz")

member = pd.DataFrame({
    "pseudo_code": "M" + pt["subject_id"].astype(str),
    "sex": pt["gender"],
    "birth_year": (pt["anchor_year"] - pt["anchor_age"]).astype(int),
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

# ---------- 3) 적재 ----------
with engine.begin() as conn:      # 끝까지 성공하면 저장, 중간에 오류가 나면 전부 취소
    before = conn.execute(text("SELECT COUNT(*) FROM member")).scalar()
    conn.execute(text("""
        INSERT INTO member (pseudo_code, sex, birth_year)
        VALUES (:pseudo_code, :sex, :birth_year)
        ON CONFLICT (pseudo_code) DO NOTHING
    """), rows)
    after = conn.execute(text("SELECT COUNT(*) FROM member")).scalar()

print(f"member: {before} -> {after} (추가 {after - before}행)")