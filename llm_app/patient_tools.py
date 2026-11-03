"""환자 조회 툴 (PostgreSQL 버전).

get_patient_record 의 함수 이름, 입력(member_id), 출력 모양은 mock 버전과 같다.
그래서 main.py 의 시스템 프롬프트와 TOOLS 정의는 그대로 쓴다.

접속 정보는 환경변수로 받는다 (코드나 GitHub 에 비밀번호를 쓰지 않는다).
  DB_HOST, DB_PORT(기본 5432), DB_NAME, DB_USER, DB_PASSWORD
  GLUCOSE_TABLE  혈당 테이블 (기본 cgm_reading_shanghai, 또는 cgm_reading_old)

설치:  pip install psycopg2-binary
"""
import logging
import os
import re
from datetime import timedelta, datetime
from decimal import Decimal
from typing import Optional
from zoneinfo import ZoneInfo

import psycopg2
from psycopg2.extras import RealDictCursor

log = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")

# member_id 로 환자와 연결된 혈당 테이블만 허용한다. (cgm_reading_v2 는 member_id 가 없음)
ALLOWED_GLUCOSE_TABLES = ("cgm_reading_shanghai", "cgm_reading_old")
GLUCOSE_TABLE = os.environ.get("GLUCOSE_TABLE", "cgm_reading_shanghai")

CURRENT_MINUTES = 30   # 이 시간 이내면 current
OLD_MINUTES = 60       # 이 시간 이내면 old, 넘으면 unavailable


def _connect():
    needed = ["DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD"]
    missing = [k for k in needed if not os.environ.get(k)]
    if missing:
        raise ValueError(f"DB 접속 환경변수가 없음: {', '.join(missing)}")
    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", "5432")),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        connect_timeout=5,
        cursor_factory=RealDictCursor,
    )


def _num(x):
    """Decimal 을 JSON 에 넣을 수 있는 숫자로 바꾼다. 142.000 -> 142, 98.5 -> 98.5"""
    if x is None:
        return None
    f = float(x)
    return int(f) if f.is_integer() else f


def _times_per_day(freq: Optional[str]) -> Optional[int]:
    """frequency 문자열에서 하루 횟수를 뽑는다. '3', '3회', '1일 3회' 를 처리한다."""
    if not freq:
        return None
    m = re.search(r"(\d+)\s*회", freq) or re.fullmatch(r"\s*(\d+)\s*", freq)
    return int(m.group(1)) if m else None


def _rx_item(r: dict, today) -> dict:
    """처방 한 줄(drug 조인 결과)을 응답 형식으로 만든다."""
    visit = r["visit_date"]
    days = r["duration_days"]
    end = visit + timedelta(days=int(days) - 1) if days else None
    intake = r["intake_unit"]
    dose = r["dose"]
    if dose is None:
        dose_text = None
    else:
        dose_text = f"{dose}{intake}" if intake else f"{dose} (단위 미확인)"
    strength = None
    if r["strength_value"] is not None:
        strength = {"value": _num(r["strength_value"]), "unit": r["strength_unit"]}
    if end is None:
        status = "기간 미확인"
    else:
        status = "복용 중" if end >= today else "종료"
    return {
        "product_name": r["drug_name"],
        "ingredient_name": r["ingredient"],
        "strength": strength,
        "dose_per_intake": dose_text,
        "times_per_day": _times_per_day(r["frequency"]),
        "duration_days": int(days) if days else None,
        "start_date": visit.isoformat(),
        "end_date": end.isoformat() if end else None,
        "status": status,
        "atc_code": r["atc_code"],
    }


def _describe(item: dict) -> str:
    return f"1회 {item['dose_per_intake']}, 하루 {item['times_per_day']}회"


def _compare(prev: list, latest: list, prev_visit, latest_visit) -> dict:
    """성분코드 기준으로 이전/최근 방문의 처방을 비교한다. prev, latest 는 (item, key) 목록."""
    prev_map = {k: i for i, k in prev}
    last_map = {k: i for i, k in latest}
    short = lambda i: {"product_name": i["product_name"], "ingredient_name": i["ingredient_name"]}

    added = [short(last_map[k]) for k in last_map if k not in prev_map]
    stopped = [short(prev_map[k]) for k in prev_map if k not in last_map]
    changed, same = [], 0
    for k in last_map:
        if k not in prev_map:
            continue
        a, b = prev_map[k], last_map[k]
        sig = lambda i: (i["dose_per_intake"], i["times_per_day"], str(i["strength"]))
        if sig(a) == sig(b):
            same += 1
        else:
            changed.append({**short(b), "before": _describe(a), "after": _describe(b)})
    return {
        "compared": {"from_visit": prev_visit.isoformat(), "to_visit": latest_visit.isoformat()},
        "added": added,
        "stopped": stopped,
        "dose_changed": changed,
        "unchanged_count": same,
    }


def _fetch_prescriptions(cur, encounter_id: int, today) -> list:
    cur.execute(
        """
        SELECT p.dose, p.frequency, p.duration_days,
               d.drug_name, d.ingredient, d.ingredient_code, d.atc_code,
               d.strength_value, d.strength_unit, d.intake_unit,
               e.visit_date
        FROM prescription p
        JOIN drug d      ON d.drug_id = p.drug_id
        JOIN encounter e ON e.encounter_id = p.encounter_id
        WHERE p.encounter_id = %s
        ORDER BY p.prescription_id
        """,
        (encounter_id,),
    )
    out = []
    for r in cur.fetchall():
        key = r["ingredient_code"] or r["drug_name"]
        out.append((_rx_item(r, today), key))
    return out


def _fetch_glucose(cur, member_id: int, now: datetime) -> Optional[dict]:
    if GLUCOSE_TABLE not in ALLOWED_GLUCOSE_TABLES:
        raise ValueError(f"허용되지 않은 혈당 테이블: {GLUCOSE_TABLE}")
    # 테이블 이름은 위 허용 목록에서만 오므로 f-string 으로 넣어도 안전하다. 값은 %s 로 넘긴다.
    cur.execute(
        f"""
        SELECT glucose_mg_dl, measured_at
        FROM {GLUCOSE_TABLE}
        WHERE member_id = %s AND glucose_mg_dl IS NOT NULL AND measured_at <= %s
        ORDER BY measured_at DESC
        LIMIT 1
        """,
        (member_id, now),
    )
    last = cur.fetchone()
    if last is None:
        return None  # 혈당 기록 없음

    measured = last["measured_at"].astimezone(KST)
    minutes_ago = int((now - last["measured_at"]).total_seconds() // 60)

    if minutes_ago > OLD_MINUTES:
        return {"freshness": "unavailable", "last_measured_date": measured.date().isoformat()}

    cur.execute(
        f"""
        SELECT MIN(glucose_mg_dl) AS mn, MAX(glucose_mg_dl) AS mx,
               AVG(glucose_mg_dl) AS av, COUNT(*) AS n
        FROM {GLUCOSE_TABLE}
        WHERE member_id = %s AND glucose_mg_dl IS NOT NULL
          AND measured_at >= %s AND measured_at <= %s
        """,
        (member_id, now - timedelta(hours=3), now),
    )
    s = cur.fetchone()
    return {
        "unit": "mg/dL",
        "freshness": "current" if minutes_ago <= CURRENT_MINUTES else "old",
        "latest": {
            "value": int(last["glucose_mg_dl"]),
            "measured_at": measured.isoformat(),
            "minutes_ago": minutes_ago,
        },
        "last_3h": {
            "min": s["mn"],
            "max": s["mx"],
            "avg": int(round(float(s["av"]))) if s["av"] is not None else None,
            "sample_count": s["n"],
        },
    }


def get_patient_record(member_id: int, scenario: Optional[str] = None) -> dict:
    """환자의 진단, 처방, 약 변화, 혈당을 한 번에 돌려준다.

    scenario 는 mock 시절의 인자라 받기만 하고 쓰지 않는다 (main.py 를 고치지 않으려는 것).
    """
    now = datetime.now(KST)
    today = now.date()

    try:
        conn = _connect()
        try:
            with conn.cursor() as cur:
                # 가장 최근 방문 2건 (최근, 이전)
                cur.execute(
                    """
                    SELECT encounter_id, visit_date
                    FROM encounter
                    WHERE member_id = %s
                    ORDER BY visit_date DESC, encounter_id DESC
                    LIMIT 2
                    """,
                    (member_id,),
                )
                visits = cur.fetchall()

                diagnoses, prescriptions, med_changes = [], [], None
                latest_visit_date = None

                if visits:
                    latest = visits[0]
                    latest_visit_date = latest["visit_date"]

                    cur.execute(
                        """
                        SELECT ds.icd_code AS icd10_code,
                               COALESCE(ds.disease_name_ko, ds.disease_name) AS title
                        FROM diagnosis dg
                        JOIN disease ds ON ds.disease_id = dg.disease_id
                        WHERE dg.encounter_id = %s
                        ORDER BY dg.diagnosis_id
                        """,
                        (latest["encounter_id"],),
                    )
                    diagnoses = [dict(r) for r in cur.fetchall()]

                    latest_rx = _fetch_prescriptions(cur, latest["encounter_id"], today)
                    prescriptions = [item for item, _ in latest_rx]

                    if len(visits) == 2:
                        prev = visits[1]
                        prev_rx = _fetch_prescriptions(cur, prev["encounter_id"], today)
                        med_changes = _compare(prev_rx, latest_rx, prev["visit_date"], latest["visit_date"])

                glucose = _fetch_glucose(cur, member_id, now)
        finally:
            conn.close()
    except psycopg2.Error:
        # DB 주소나 계정 정보가 모델 응답에 새지 않도록 자세한 내용은 로그에만 남긴다.
        log.exception("환자 기록 조회 중 DB 오류 (member_id=%s)", member_id)
        raise ValueError("DB 조회 중 오류가 발생함")

    return {
        "status": "ok",
        "member_id": member_id,
        "as_of": now.isoformat(),
        "latest_visit_date": latest_visit_date.isoformat() if latest_visit_date else None,
        "diagnoses": diagnoses,
        "prescriptions": prescriptions,
        "medication_changes": med_changes,
        "glucose": glucose,
    }


if __name__ == "__main__":
    # 사용: DB_* 환경변수를 설정한 뒤  python patient_tools.py 1
    import json
    import sys

    mid = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    print(json.dumps(get_patient_record(mid), ensure_ascii=False, indent=2, default=str))
