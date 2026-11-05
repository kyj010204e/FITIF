# ocr_loader

사용자가 검수한 OCR 결과 JSON을 PostgreSQL에 저장하는 함수 모음입니다.

## 처음 세팅 (Windows PowerShell)

1. 가상환경을 만들고 켭니다.
   python -m venv .venv
   .venv\Scripts\Activate.ps1
2. 패키지를 설치합니다.
   pip install -r requirements.txt
3. .env.example을 복사해 .env로 만들고 DB_USER, DB_PASSWORD를 채웁니다.
   copy .env.example .env
   (.env는 git에 올라가지 않습니다. 비밀번호를 채팅이나 코드에 쓰지 마세요.)
4. DB는 SSH 터널로 접속합니다. 터널 명령은 팀 채팅 공지를 따르고, 창을 닫지 말고 켜 둡니다.
   로컬 포트는 15432입니다.

## 사용법
아래는 백엔드 코드에서 함수를 불러 쓰는 예시입니다. member_id와 ocr_json은 자기 코드의 값으로 바꾸세요.

    from ocr_loader import connect, load_ocr_result

    conn = connect()
    result = load_ocr_result(conn, member_id, ocr_json, dry_run=True)

- member_id는 로그인 정보에서 가져오고, JSON에서 가져오지 않습니다.
- dry_run=True이면 저장하지 않고 롤백합니다. 실제 저장은 dry_run=False입니다.
- review_status가 user_confirmed인 JSON만 저장됩니다.
- 약은 reviewed_product_code(HIRA 제품코드)와 drug.edi_code로 매칭합니다.

## 약 마스터 적재 (load_drug_master.py)

HIRA 약 마스터(ATC_CODE.csv)를 drug 테이블에 한 번 적재하는 스크립트입니다.
이미 21,998건을 적재했으므로 다시 실행할 필요는 없습니다. CSV는 저장소에 없습니다.