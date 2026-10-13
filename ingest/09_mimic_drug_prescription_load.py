import math
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
rx = pd.read_csv(HOSP / "prescriptions.csv.gz", dtype={"hadm_id": str}, low_memory=False)

rx = rx[rx["drug_type"] != "BASE"]                                   # 수액 바탕액 제외
rx = rx[~rx["drug"].str.contains("flush", case=False, na=False)]     # 라인 세척 제외
rx = rx.dropna(subset=["drug", "hadm_id"]).copy()

rx["drug_name"] = rx["drug"].str.split().str.join(" ")               # 공백 정리
rx["drug_key"] = rx["drug_name"].str.lower()

# 단위 통일 (mg, mL 등 단위 표기를 코드로 먼저 정규화)
UNIT_MAP = {"gm": "g", "UNIT": "unit", "mg": "mg", "g": "g", "mcg": "mcg",
            "mL": "mL", "mEq": "mEq", "mmol": "mmol", "L": "L"}


def make_dose(val, unit):
    if pd.isna(val):
        return None
    val = str(val).strip()
    if val.endswith(".0"):
        val = val[:-2]
    if val == "0":            # 0은 '용량 미정'(sliding scale 등)이라 비워 둠
        return None
    unit = ...


def make_freq(n):
    if pd.isna(n) or n == 0:
        return None
    return f"하루 {int(n)}회" if float(n).is_integer() else f"하루 {n}회"


rx["dose"] = [make_dose(v, u) for v, u in zip(rx["dose_val_rx"], rx["dose_unit_rx"])]
rx["frequency"] = rx["doses_per_24_hrs"].map(make_freq)
rx["start"] = pd.to_datetime(rx["starttime"])
rx["stop"] = pd.to_datetime(rx["stoptime"])
rx = rx.sort_values("start")

# (입원, 약) 하나에 한 행으로 합치기
agg = rx.groupby(["hadm_id", "drug_key"], as_index=False).agg(
    drug_name=("drug_name", "first"),
    dose=("dose", "first"),
    frequency=("frequency", "first"),
    start=("start", "min"),
    stop=("stop", "max"),
)


def make_days(start, stop):
    if pd.isna(stop):
        return None
    return max(1, math.ceil((stop - start).total_seconds() / 86400))


agg["duration_days"] = [make_days(s, e) for s, e in zip(agg["start"], agg["stop"])]
print("처방 원본(필터 후):", len(rx), "-> (입원,약) 단위:", len(agg),
      "/ 고유 약:", agg["drug_key"].nunique())

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


def nn(x):
    return None if pd.isna(x) else x


# ---------- 3) drug, prescription 넣기 ----------
insert_drug = text("""
    INSERT INTO drug (drug_name)
    SELECT :drug_name
    WHERE NOT EXISTS (
        SELECT 1 FROM drug d WHERE lower(d.drug_name) = :drug_key
    )
""")

insert_rx = text("""
    INSERT INTO prescription (encounter_id, drug_id, dose, frequency, duration_days)
    VALUES (:e, :d, :dose, :freq, :days)
""")

with engine.begin() as conn:      # 끝까지 성공하면 저장, 오류가 나면 전부 취소
    # 입원번호(hadm_id) -> encounter_id: 08에서 입원 파일 순서대로 넣었으므로 순서로 짝짓고 검증
    enc_rows = conn.execute(text(
        "SELECT encounter_id, member_id, visit_date FROM encounter "
        "WHERE source_type = :s ORDER BY encounter_id"), {"s": SOURCE}).all()
    member_ids = dict(conn.execute(text(
        "SELECT pseudo_code, member_id FROM member WHERE pseudo_code LIKE 'M%'")).all())
    if len(enc_rows) != len(adm):
        raise SystemExit(f"encounter {len(enc_rows)}건 != 입원 {len(adm)}건. 08을 먼저 확인하세요.")

    hadm_to_enc = {}
    for (eid, mid, vdate), r in zip(enc_rows, adm.itertuples()):
        if member_ids["M" + r.subject_id] != mid or str(vdate) != r.admittime[:10]:
            raise SystemExit(f"hadm_id {r.hadm_id} 짝이 맞지 않아요. 중단합니다.")
        hadm_to_enc[r.hadm_id] = eid

    done = conn.execute(text(
        "SELECT COUNT(*) FROM prescription WHERE encounter_id = ANY(:ids)"),
        {"ids": list(hadm_to_enc.values())}).scalar()
    if done:
        raise SystemExit(f"이미 MIMIC 처방 {done}건이 들어 있어요. 중복 방지를 위해 중단합니다.")

    drug_before = conn.execute(text("SELECT COUNT(*) FROM drug")).scalar()
    rx_before = conn.execute(text("SELECT COUNT(*) FROM prescription")).scalar()

    drugs = agg.drop_duplicates("drug_key")[["drug_name", "drug_key"]]
    conn.execute(insert_drug, drugs.to_dict("records"))

    drug_ids = {k: i for i, k in conn.execute(text("SELECT drug_id, lower(drug_name) FROM drug")).all()}

    rx_rows = [
        {"e": hadm_to_enc[h], "d": drug_ids[k], "dose": nn(dose), "freq": nn(freq),
         "days": None if pd.isna(days) else int(days)}
        for h, k, dose, freq, days in zip(agg["hadm_id"], agg["drug_key"], agg["dose"],
                                          agg["frequency"], agg["duration_days"])
    ]
    conn.execute(insert_rx, rx_rows)

    drug_after = conn.execute(text("SELECT COUNT(*) FROM drug")).scalar()
    rx_after = conn.execute(text("SELECT COUNT(*) FROM prescription")).scalar()

print(f"drug: {drug_before} -> {drug_after} (추가 {drug_after - drug_before}행)")
print(f"prescription: {rx_before} -> {rx_after} (추가 {rx_after - rx_before}행)")