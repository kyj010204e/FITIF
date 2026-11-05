
"""
FITIF PostgreSQL 데이터베이스 연결 모듈

역할:
    FastAPI에서 PostgreSQL 데이터베이스에 접속할 때
    필요한 연결 객체를 생성한다.

현재 개발 단계:
    과거 CGM 데이터(cgm_reading_old) 조회 전용.

보안:
    DB 비밀번호는 Python 코드에 직접 작성하지 않고
    backend/.env 파일에서 읽어온다.
"""

import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv


# 현재 database.py 파일이 들어 있는 폴더의 경로
# 실행하는 터미널 위치와 관계없이 backend/.env를 찾는다.
BASE_DIR = Path(__file__).resolve().parent

# 환경설정 파일 경로
ENV_PATH = BASE_DIR / ".env"

# .env 파일을 환경변수로 로드한다.
load_dotenv(ENV_PATH)


def get_connection():
    """
    PostgreSQL 데이터베이스 연결 객체를 생성한다.

    반환값:
        psycopg2.connection
        PostgreSQL에 SQL을 실행할 수 있는 연결 객체.

    오류:
        필수 환경변수가 없으면 RuntimeError 발생.
        연결에 실패하면 psycopg2.OperationalError 발생.

    주의:
        현재 연결은 읽기 전용 트랜잭션을 사용한다.
        사용자 정보 저장 API를 구현할 때에는
        별도의 쓰기 권한 및 연결 방식을 설계해야 한다.
    """

    # DB 연결에 필요한 환경변수 목록
    required_keys = [
        "DB_HOST",
        "DB_PORT",
        "DB_NAME",
        "DB_USER",
        "DB_PASSWORD",
    ]

    # 설정되지 않은 환경변수를 확인한다.
    missing = [
        key for key in required_keys
        if not os.getenv(key)
    ]

    if missing:
        raise RuntimeError(
            "필수 DB 환경변수 누락: " + ", ".join(missing)
        )

    # PostgreSQL에 연결한다.
    # 비밀번호는 로그에 출력하지 않는다.
    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ["DB_PORT"]),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],

        # DB 서버 응답을 최대 5초까지 기다린다.
        connect_timeout=5,

        # SELECT만 허용하는 읽기 전용 트랜잭션
        options="-c default_transaction_read_only=on"
    )
