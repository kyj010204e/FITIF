-- =====================================================================
-- FITIF 팀프로젝트: 멀티모달 헬스케어 PDSS/CDSS 중앙 DB 스키마 (Phase 1)
-- DB: PostgreSQL 16 / 데이터베이스명: team_project
-- 작성: 중앙 DB 담당
--
-- 사용법: team_project DB의 Query Tool에서 이 파일 전체를 실행(F5)
-- 주의: 맨 위 DROP이 기존 테이블과 그 안의 데이터를 모두 지웁니다.
--       데이터 적재 후에는 이 파일을 통째로 실행하지 마세요.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1) 기존 테이블 정리 (자식 → 부모 순서)
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS prescription;
DROP TABLE IF EXISTS diagnosis;
DROP TABLE IF EXISTS vital_sign;
DROP TABLE IF EXISTS cgm_reading;
DROP TABLE IF EXISTS encounter;
DROP TABLE IF EXISTS ingestion_log;
DROP TABLE IF EXISTS drug;
DROP TABLE IF EXISTS member;

-- ---------------------------------------------------------------------
-- 2) 테이블 생성 (부모 → 자식 순서)
-- ---------------------------------------------------------------------

-- 회원: 이름/주민번호 등 식별정보 없이 가명 코드만 보관
CREATE TABLE member (
    member_id    INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pseudo_code  VARCHAR(20) NOT NULL UNIQUE,   -- 가명 코드 예: 'P001'
    sex          CHAR(1),                       -- 'M' / 'F'
    birth_year   SMALLINT,                      -- 생년월일 대신 연도만
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 진료(방문): 1회 방문 = 1행. 그날의 진료 한 건을 묶는 상자
CREATE TABLE encounter (
    encounter_id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    member_id    INT NOT NULL REFERENCES member(member_id),
    visit_date   DATE NOT NULL,
    source_type  VARCHAR(20)                    -- 데이터 출처 예: 'OCR', 'SYNTHETIC'
);

-- 진단
CREATE TABLE diagnosis (
    diagnosis_id   INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    encounter_id   INT NOT NULL REFERENCES encounter(encounter_id),
    icd10_code     VARCHAR(10) NOT NULL,        -- 예: 'E11' (제2형 당뇨병)
    diagnosis_name VARCHAR(200)
);

-- 약물 마스터 (Phase 2 병용금기 DUR용). 코드 체계는 멘토링 후 확정
CREATE TABLE drug (
    drug_id         INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    drug_code       VARCHAR(20) UNIQUE,   -- 기타 제품 코드(KD 13자리 등, 필요 시)
    edi_code        VARCHAR(9),           -- 보험(EDI) 제품코드 9자리. 약물 매핑 기준 키
    ingredient_code VARCHAR(9),           -- 주성분코드 9자리
    atc_code        VARCHAR(10),          -- WHO ATC 코드
    drug_name       VARCHAR(200) NOT NULL,
    ingredient      VARCHAR(200),         -- 성분명
    valid_from      DATE,                 -- 이 코드 정보의 적용 시작일
    valid_to        DATE,                 -- 적용 종료일 (NULL = 현재 유효)
    CONSTRAINT drug_valid_period_chk
        CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from)
);
CREATE UNIQUE INDEX ux_drug_edi_period
    ON drug (edi_code, valid_from) WHERE edi_code IS NOT NULL;
CREATE INDEX ix_drug_ingredient_code ON drug (ingredient_code);

-- 처방: 방문 1건에 약 여러 개
CREATE TABLE prescription (
    prescription_id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    encounter_id    INT NOT NULL REFERENCES encounter(encounter_id),
    drug_id         INT NOT NULL REFERENCES drug(drug_id),
    dose            VARCHAR(50),                -- 예: '500mg'
    frequency       VARCHAR(50),                -- 예: '하루 2회'
    duration_days   SMALLINT                    -- 복용 일수
);

-- 생체신호: 체온, 혈압 (산소포화도 등은 제외)
CREATE TABLE vital_sign (
    vital_id      INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    member_id     INT NOT NULL REFERENCES member(member_id),
    encounter_id  INT REFERENCES encounter(encounter_id),  -- 방문 중 측정이면 연결(선택)
    measured_at   TIMESTAMPTZ NOT NULL,
    body_temp     NUMERIC(4,1),                 -- 체온 (℃)
    bp_systolic   SMALLINT,                     -- 수축기 혈압
    bp_diastolic  SMALLINT,                     -- 이완기 혈압
    source        VARCHAR(20)
);

-- 연속혈당(CGM): 양이 많아 별도 테이블
CREATE TABLE cgm_reading (
    reading_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    member_id        INT NOT NULL REFERENCES member(member_id),
    measured_at      TIMESTAMPTZ NOT NULL,      -- ISO 8601 표준화된 시각
    glucose_mg_dl    SMALLINT,                  -- 결측이면 NULL
    device           VARCHAR(50),               -- 측정 기기 예) 'Galaxy Watch'
    is_interpolated  BOOLEAN DEFAULT FALSE,     -- 보간으로 채운 값인지 (빠진칸을 평균으로 채울경우 등),측정값만 쓸지, 보간값도 포함할지"를 고르기 위함)
    UNIQUE (member_id, measured_at)             -- 같은 시각 중복 적재 방지
);

-- 적재 로그: 적재 성공률 등 정합성 지표(KPI) 계산용
CREATE TABLE ingestion_log (
    log_id        INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_type   VARCHAR(20) NOT NULL,         -- 'OCR', 'CGM' 등
    file_name     VARCHAR(255),
    status        VARCHAR(10) NOT NULL,         -- 'SUCCESS' / 'FAIL'
    total_rows    INT,
    success_rows  INT,
    error_message TEXT,
    ingested_at   TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
