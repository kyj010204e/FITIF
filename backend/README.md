# FITIF Health Data Backend

FITIF 프로젝트의 A파트에서 개발하는 **건강정보 조회 및 분석용 FastAPI 백엔드**입니다.

현재는 PostgreSQL에 저장된 과거 연속혈당측정(CGM) 데이터를 사용자별·기간별로 조회하는 기능을 제공합니다.

## 1. 개발 환경

| 항목 | 기술 |
|---|---|
| 언어 | Python 3.12 |
| API 프레임워크 | FastAPI |
| 웹 서버 | Uvicorn |
| 데이터베이스 | PostgreSQL |
| DB 연결 | psycopg2 |
| 환경변수 관리 | python-dotenv |

## 2. 프로젝트 구조

```text
backend/
├── __init__.py
├── main.py            # FastAPI 실행 및 API 엔드포인트
├── database.py        # PostgreSQL 연결
├── requirements.txt   # Python 패키지 목록
├── .env.example       # 환경설정 예시
└── README.md          # 백엔드 개발 문서
```

## 3. 실행 방법

### 3-1. Python 환경 준비

Python 3.12가 설치된 환경에서 진행합니다.

3060 개발 서버에서 사용하는 Conda 환경은 `fitif-api`입니다.

```bash
conda activate fitif-api
cd ~/FITIF
```

### 3-2. 라이브러리 설치

```bash
python -m pip install -r backend/requirements.txt
```

### 3-3. PostgreSQL 연결 설정

`backend/.env.example`을 참고하여 `backend/.env`를 작성합니다.

필요한 환경변수는 다음과 같습니다.

- `DB_HOST`: PostgreSQL 접속 주소
- `DB_PORT`: PostgreSQL 접속 포트
- `DB_NAME`: 데이터베이스 이름
- `DB_USER`: 데이터베이스 사용자
- `DB_PASSWORD`: 데이터베이스 비밀번호

**`.env`는 GitHub에 업로드하지 않습니다.**

### 3-4. FastAPI 실행

프로젝트 최상위 경로에서 실행합니다.

```bash
uvicorn backend.main:app --host 127.0.0.1 --port 8002
```

`127.0.0.1`은 서버 내부에서만 접근할 수 있도록 제한하는 설정입니다. 현재 API에는 사용자 인증이 구현되지 않았으므로 외부에 공개하지 않습니다.

## 4. API 명세

### GET /

서버의 기본 정보를 반환합니다.

### GET /health

FastAPI 서버의 실행 상태를 확인합니다.

```json
{
  "status": "ok"
}
```

### GET /api/cgm/readings

특정 사용자의 과거 CGM 혈당 기록을 조회합니다.

| 파라미터 | 자료형 | 필수 여부 | 설명 |
|---|---|---|---|
| `member_id` | integer | 필수 | 사용자 ID |
| `start_at` | datetime | 선택 | 조회 시작 시각(포함) |
| `end_at` | datetime | 선택 | 조회 종료 시각(미포함) |
| `limit` | integer | 선택 | 최대 조회 건수, 기본 100건 |

날짜·시간은 UTC 오프셋 또는 `Z`가 포함된 ISO 8601 형식을 사용합니다.

요청 예시:

```bash
curl -sG "http://127.0.0.1:8002/api/cgm/readings" \
  --data-urlencode "member_id=28" \
  --data-urlencode "limit=3"
```

응답에는 기록 ID, 측정 시각, 혈당값, 기기 정보, 보간 여부 등이 포함됩니다.

`count`는 전체 데이터 수가 아니라 **현재 요청에서 반환된 기록 수**입니다.

## 5. 테스트 및 검증

현재 완료한 검증:

- PostgreSQL 연결 확인
- 사용자별 CGM 조회
- 기간별 CGM 조회
- 잘못된 날짜 입력 검증
- 과거 CGM 데이터 127,982건에 대한 기본 무결성 검사
- DB 조회값과 API 응답의 샘플 비교
- 3060 서버와 5090 서버 간 SSH 터널을 통한 API 통신 확인

기존 CGM 테이블의 PK, FK 및 UNIQUE 제약조건을 확인했습니다.

다만 전체 API 자동화 테스트, 인증·인가, 실제 의료 데이터의 임상적 정확성 검증은 아직 완료되지 않았습니다.

## 6. 주의사항

현재 API는 개발 및 통합 검증용입니다.

- `cgm_reading_old`는 과거 테스트 데이터입니다.
- 해당 기록을 현재 사용자의 실시간 혈당으로 설명해서는 안 됩니다.
- API에 사용자 인증 기능이 아직 없습니다.
- 운영 환경에서는 로그인 사용자와 조회 대상의 일치 여부를 검증해야 합니다.
- DB 비밀번호나 개인 의료정보를 GitHub에 업로드해서는 안 됩니다.

## 7. 향후 개발 계획

- CGM 혈당 통계 API
- 사용자 인증 및 접근 제어
- 음성·수동 혈당 입력 데이터 저장 API
- C파트 Gemma Tool Calling과 실제 API 통합
- 자동화 테스트 및 API 문서 고도화
