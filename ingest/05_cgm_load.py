from getpass import getpass
from pathlib import Path

import pandas as pd
from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, MetaData, SmallInteger, String, Table
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import URL

# ---------- 설정 ----------
BASE = Path(r"C:\medicalAI\DataSets\Diabetes Datasets-ShanghaiT1DM and ShanghaiT2DM")
FOLDERS = ["Shanghai_T1DM", "Shanghai_T2DM"]
TIMEZONE = "Asia/Shanghai"   # 원본에 시간대 표시가 없어서 '중국 시간'이라고 가정 (연습용)
CHUNK = 5000                 # 한 번에 DB로 보낼 행 수

# cgm_reading 테이블 (insert 문을 만들기 위한 설명서일 뿐, 테이블을 새로 만들지 않아요)
cgm_table = Table(
    "cgm_reading", MetaData(),
    Column("reading_id", BigInteger, primary_key=True),
    Column("member_id", Integer),
    Column("measured_at", DateTime(timezone=True)),
    Column("glucose_mg_dl", SmallInteger),
    Column("device", String),
    Column("is_interpolated", Boolean),
)

# ---------- 1) PostgreSQL 접속 + member_id 목록 ----------
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

with engine.connect() as conn:
    member_ids = dict(conn.execute(text("SELECT pseudo_code, member_id FROM member")).all())
print("member 수:", len(member_ids))

# ---------- 2) 파일 목록 (엑셀이 열려 있을 때 생기는 ~$ 임시 파일은 제외) ----------
files = []
for folder in FOLDERS:
    for f in sorted((BASE / folder).iterdir()):
        if f.suffix.lower() in (".xls", ".xlsx") and not f.name.startswith("~$"):
            files.append(f)
print("읽을 CGM 파일 수:", len(files))

# ---------- 3) 파일마다 전처리 ----------
rows = []
skipped_files = []
for f in files:
    pseudo = "P" + f.name.split("_")[0]
    member_id = member_ids.get(pseudo)
    if member_id is None:
        skipped_files.append(f.name)      # member에 없는 환자는 건너뜀
        continue

    df = pd.read_excel(f)
    # 일부 파일은 열 이름이 달라서('CGM ' vs 'CGM (mg / dl)') 이름 대신 순서로 읽어요.
    df = df.iloc[:, :2]
    df.columns = ["Date", "CGM"]
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df["CGM"] = pd.to_numeric(df["CGM"], errors="coerce")
    df = df.dropna(subset=["Date", "CGM"])                       # 시각/혈당이 빈 줄 버림
    df = df.drop_duplicates(subset="Date")                       # 같은 시각 중복 방지
    df["Date"] = df["Date"].dt.tz_localize(TIMEZONE, ambiguous="NaT", nonexistent="NaT")
    df = df.dropna(subset=["Date"])

    for ts, g in zip(df["Date"], df["CGM"]):
        rows.append({
            "member_id": member_id,
            "measured_at": ts.to_pydatetime(),
            "glucose_mg_dl": int(round(g)),
            "device": None,              # 기기 정보가 확인되지 않아 비워 둠
            "is_interpolated": False,
        })

print("넣을 혈당 행 수:", len(rows))
if skipped_files:
    print("member에 없어서 건너뛴 파일:", skipped_files)

# ---------- 4) 넣기 (UNIQUE(member_id, measured_at) 덕분에 다시 실행해도 중복 안 생김) ----------
stmt = insert(cgm_table).on_conflict_do_nothing(index_elements=["member_id", "measured_at"])
with engine.begin() as conn:
    for i in range(0, len(rows), CHUNK):
        conn.execute(stmt, rows[i:i + CHUNK])
    total = conn.execute(text("SELECT COUNT(*) FROM cgm_reading")).scalar()
    n_member = conn.execute(text("SELECT COUNT(DISTINCT member_id) FROM cgm_reading")).scalar()

print("cgm_reading 테이블의 현재 행 수:", total)
print("혈당 기록이 있는 member 수:", n_member)