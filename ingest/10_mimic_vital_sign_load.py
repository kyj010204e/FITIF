from getpass import getpass
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

# ---------- 설정 ----------
BASE = Path(r"C:\medicalAI\DataSets\mimic-iv-clinical-database-demo-2.2")
HOSP = BASE / "hosp"
ICU = BASE / "icu"
SOURCE = "MIMIC_DATASET"          # encounter.source_type 과 같은 값
TIMEZONE = "America/New_York"     # MIMIC 은 미국 보스턴 병원 데이터

# ---------- 1) 전처리 ----------
# (1) 외래 혈압 (omr): 날짜만 있어서 그날 00:00 으로 넣어요
omr = pd.read_csv(HOSP / "omr.csv.gz", dtype=str)
omr = omr[omr["result_name"].isin(["Blood Pressure", "Blood Pressure Sitting"])]
bp = omr["result_value"].str.extract(r"^(\d+)/(\d+)$").astype(float)
omr = omr.assign(sys=bp[0], dia=bp[1]).dropna(subset=["sys", "dia"])
omr = omr[omr["sys"].between(50, 260) & omr["dia"].between(20, 160) & (omr["sys"] > omr["dia"])]
vit_omr = pd.DataFrame({
    "subject_id": omr["subject_id"],
    "hadm_id": None,                                  # 외래라 입원과 연결 안 함
    "measured_at": omr["chartdate"] + " 00:00:00",
    "body_temp": None,
    "bp_systolic": omr["sys"],
    "bp_diastolic": omr["dia"],
    "source": "MIMIC_OMR",
})

# (2) ICU 혈압/체온 (chartevents)
ce = pd.read_csv(ICU / "chartevents.csv.gz",
                 usecols=["subject_id", "hadm_id", "charttime", "itemid", "valuenum"],
                 dtype={"subject_id": str, "hadm_id": str})
KEY = ["subject_id", "hadm_id", "charttime"]

sys_ = ce[ce["itemid"] == 220179][KEY + ["valuenum"]].drop_duplicates(KEY).rename(columns={"valuenum": "sys"})
dia_ = ce[ce["itemid"] == 220180][KEY + ["valuenum"]].drop_duplicates(KEY).rename(columns={"valuenum": "dia"})
icu_bp = sys_.merge(dia_, on=KEY)                      # 수축기+이완기가 같은 시각인 것만
icu_bp = icu_bp[icu_bp["sys"].between(50, 260) & icu_bp["dia"].between(20, 160) & (icu_bp["sys"] > icu_bp["dia"])]
vit_bp = pd.DataFrame({
    "subject_id": icu_bp["subject_id"],
    "hadm_id": icu_bp["hadm_id"],
    "measured_at": icu_bp["charttime"],
    "body_temp": None,
    "bp_systolic": icu_bp["sys"],
    "bp_diastolic": icu_bp["dia"],
    "source": "MIMIC_ICU",
})

# 체온: 223761 = ℉, 223762 = ℃  (℉ 는 ℃ 로 변환)
tmp = ce[ce["itemid"].isin([223761, 223762])].copy()
tmp["temp_c"] = tmp["valuenum"].where(tmp["itemid"] == 223762, (tmp["valuenum"] - 32) * 5 / 9).round(1)
tmp = tmp[tmp["temp_c"].between(32, 43)].drop_duplicates(KEY)
vit_temp = pd.DataFrame({
    "subject_id": tmp["subject_id"],
    "hadm_id": tmp["hadm_id"],
    "measured_at": tmp["charttime"],
    "body_temp": tmp["temp_c"],
    "bp_systolic": None,
    "bp_diastolic": None,
    "source": "MIMIC_ICU",
})

vit = pd.concat([vit_omr, vit_bp, vit_temp], ignore_index=True)
print("혈압(외래):", len(vit_omr), "/ 혈압(ICU):", len(vit_bp), "/ 체온(ICU):", len(vit_temp),
      "/ 합계:", len(vit))

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
# 시각(measured_at)을 미국 동부 시간으로 해석해서 저장하도록 접속 시간대를 지정
engine = create_engine(url, connect_args={"options": f"-c timezone={TIMEZONE}"})


def nn(x):
    return None if pd.isna(x) else x


# ---------- 3) vital_sign 넣기 ----------
insert_vital = text("""
    INSERT INTO vital_sign
        (member_id, encounter_id, measured_at, body_temp, bp_systolic, bp_diastolic, source)
    VALUES (:m, :e, :t, :temp, :sys, :dia, :src)
""")

with engine.begin() as conn:      # 끝까지 성공하면 저장, 오류가 나면 전부 취소
    adm = pd.read_csv(HOSP / "admissions.csv.gz", dtype=str)
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
        "SELECT COUNT(*) FROM vital_sign WHERE source LIKE 'MIMIC%'")).scalar()
    if done:
        raise SystemExit(f"이미 MIMIC 생체신호 {done}건이 들어 있어요. 중복 방지를 위해 중단합니다.")

    before = conn.execute(text("SELECT COUNT(*) FROM vital_sign")).scalar()

    rows = []
    for r in vit.itertuples():
        rows.append({
            "m": member_ids["M" + r.subject_id],
            "e": hadm_to_enc[r.hadm_id] if isinstance(r.hadm_id, str) else None,
            "t": r.measured_at,
            "temp": nn(r.body_temp),
            "sys": None if pd.isna(r.bp_systolic) else int(r.bp_systolic),
            "dia": None if pd.isna(r.bp_diastolic) else int(r.bp_diastolic),
            "src": r.source,
        })
    conn.execute(insert_vital, rows)

    after = conn.execute(text("SELECT COUNT(*) FROM vital_sign")).scalar()

print(f"vital_sign: {before} -> {after} (추가 {after - before}행)")