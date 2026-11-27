-- ============================================================================
-- [FIT-IF 4.1] DKD 90일 외래 공백기 & 신장 9대 대사부하 확장 스키마
-- 연동 대상: 공용 서버(team_project) 기존 public 스키마(member, encounter, drug 등)
-- 작성 목적: 1) 출처/분할 격리, 2) 검사/식단/약물 PK 시계열 적재, 3) 9대 피처 마트 구축 및 jungjeeo 권한 부여
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. 코호트 출처 및 누수 방지 분할 매니페스트 (member 테이블과 1:1 연동)
--    - 목적: 환자(member_id) 단위로 학습/검증/평가/격리군을 고정하여 데이터 누수 차단
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.cohort_split_manifest (
    manifest_id      SERIAL PRIMARY KEY,
    member_id        INT NOT NULL UNIQUE REFERENCES public.member(member_id) ON DELETE CASCADE,
    dataset_source   VARCHAR(40) NOT NULL,  -- 원천 데이터셋 ('NHANES', 'KNHANES', 'SHANGHAI_T2DM', 'CKD_ROUTE', 'CHALLENGE_2019', 'PILOT_REAL')
    split_role       VARCHAR(20) NOT NULL,  -- 분할 역할 ('TRAIN', 'VAL', 'TEST', 'ISOLATED', 'EDA_VAL', 'PILOT_ONLY')
    baseline_egfr    NUMERIC(6,2),          -- 기준 시점(T0) 기저 신사구체여과율 (mL/min/1.73m²)
    baseline_uacr    NUMERIC(8,2),          -- 기준 시점(T0) 기저 요알부민/크레아티닌 비 (mg/g)
    kdigo_stage      VARCHAR(15),           -- KDIGO 신장질환 병기 ('G1', 'G2', 'G3a', 'G3b', 'G4')
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- ----------------------------------------------------------------------------
-- 2. 외래·입원 혈액/소변 진단검사 시계열 테이블
--    - 목적: eGFR, 크레아티닌, 당화혈색소 등 시간별 검사 결과 저장
--    - 누수 방지 핵심: 채혈 시간(collected_at)과 결과지 가용 시간(available_at)을 분리하여
--                     예측 기준 시점(anchor_ts) 이전에 뜬 결과(available_at <= anchor_ts)만 피처로 사용
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.lab_result (
    lab_id           BIGSERIAL PRIMARY KEY,
    member_id        INT NOT NULL REFERENCES public.member(member_id) ON DELETE CASCADE,
    encounter_id     INT REFERENCES public.encounter(encounter_id) ON DELETE SET NULL,
    test_code        VARCHAR(30) NOT NULL,  -- 표준 검사 코드 ('EGFR', 'CREATININE', 'HBA1C', 'UACR', 'POTASSIUM', 'ALBUMIN', 'BUN', 'PHOSPHORUS')
    test_value       NUMERIC(10,3) NOT NULL,-- 실측 검사 수치
    unit             VARCHAR(20),           -- 단위 ('mL/min/1.73m2', 'mg/dL', '%', 'mg/g', 'mEq/L' 등)
    collected_at     TIMESTAMPTZ NOT NULL,  -- 실제 채혈/채뇨 시점
    available_at     TIMESTAMPTZ NOT NULL,  -- 전산에 검사 결과가 등록되어 조회 가능해진 시점
    source           VARCHAR(30),           -- 데이터 출처 구분
    created_at       TIMESTAMPTZ DEFAULT NOW()
);
-- 환자별·검사항목별 결과 가용 시간 조회 속도 향상을 위한 복합 인덱스
CREATE INDEX IF NOT EXISTS idx_lab_member_avail ON public.lab_result(member_id, test_code, available_at);

-- ----------------------------------------------------------------------------
-- 3. 일일 식단·영양소 섭취 로그 테이블
--    - 목적: 국건영 실측 기준선 비교 및 나트륨·칼륨·인·단백질 누적 식이 부하 산출용
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.diet_intake_log (
    diet_log_id      BIGSERIAL PRIMARY KEY,
    member_id        INT NOT NULL REFERENCES public.member(member_id) ON DELETE CASCADE,
    recorded_date    DATE NOT NULL,         -- 섭취 일자
    energy_kcal      NUMERIC(7,2),          -- 총 에너지 섭취량 (kcal)
    protein_g        NUMERIC(6,2),          -- 단백질 섭취량 (g) -> 사구체 과여과 부하 계산용
    sodium_mg        NUMERIC(7,2),          -- 나트륨 섭취량 (mg) -> KDIGO 상한(2,000mg) 초과 여부 판정용
    potassium_mg     NUMERIC(7,2),          -- 칼륨 섭취량 (mg)
    phosphorus_mg    NUMERIC(7,2),          -- 인 섭취량 (mg)
    carbs_g          NUMERIC(6,2),          -- 탄수화물 섭취량 (g)
    source           VARCHAR(30),           -- 데이터 출처 ('KNHANES', 'SHANGHAI_DIET', 'PILOT_LOG' 등)
    created_at       TIMESTAMPTZ DEFAULT NOW()
);
-- 환자별·일자별 식이 로그 조회 인덱스
CREATE INDEX IF NOT EXISTS idx_diet_member_date ON public.diet_intake_log(member_id, recorded_date);

-- ----------------------------------------------------------------------------
-- 4. 약물 신장 배설 반감기 및 DUR 메타 테이블 (기존 drug 테이블과 1:1 확장)
--    - 목적: 4.3 단계의 Rowland-Tozer PK 반감기 보정 연산 및 5.1 DUR 금기/감량 룰 엔진용 참조 마스터
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.drug_pk_reference (
    drug_id          INT PRIMARY KEY REFERENCES public.drug(drug_id) ON DELETE CASCADE,
    fe_renal         NUMERIC(4,3),          -- 신장 미변화체 배설 분율 (0.000 ~ 1.000, Rowland-Tozer 공식 핵심 계수)
    t_half_normal_hr NUMERIC(6,2),          -- 정상 신기능 기준 약물 반감기 (시간)
    oct2_inhibitor   BOOLEAN DEFAULT FALSE, -- 신세뇨관 유기양이온 수송체(OCT2) 억제 여부
    nephrotoxic_flag BOOLEAN DEFAULT FALSE, -- NSAIDs 등 신독성 주의 약물 여부
    dur_egfr_cutoff  NUMERIC(5,1),          -- 투여 금기 또는 용량 감량이 필요한 eGFR 임계치
    updated_at       TIMESTAMPTZ DEFAULT NOW()
);

-- ----------------------------------------------------------------------------
-- 5. 최종 분석용 피처 마트: 신장 9대 대사부하 지표 + 가변 공백기(Δt) + 타깃(Y)
--    - 목적: 4.3 파이프라인 산출물 적재, 4.5 R/Python 통계 검증, 5.2 예측 모델 학습용 통합 테이블
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.renal_9_burden_mart (
    mart_id               BIGSERIAL PRIMARY KEY,
    member_id             INT NOT NULL REFERENCES public.member(member_id) ON DELETE CASCADE,
    anchor_ts             TIMESTAMPTZ NOT NULL, -- 예측 기준 시점 (이 시점 이전의 과거 누적 데이터만 집계)
    delta_t_days          NUMERIC(6,1) NOT NULL,-- 직전 검사일로부터 다음 방문(또는 현재)까지 경과 일수 (가변 공백기 Δt)
    -- [신장 9대 대사부하 피처 (X)]
    f1_glycemic_cv        NUMERIC(6,2),         -- 피처 1: 연속혈당 변동계수 (CV, %)
    f2_glycemic_iauc      NUMERIC(8,2),         -- 피처 2: 식후 고혈당 누적 면적 (iAUC)
    f3_tir_below_range    NUMERIC(5,2),         -- 피처 3: 혈당 목표범위(70~180 mg/dL) 이탈률 (%)
    f4_drug_pk_load       NUMERIC(8,3),         -- 피처 4: Rowland-Tozer 반감기 보정 누적 약물 노출 부하
    f5_oct2_nsaid_score   NUMERIC(6,2),         -- 피처 5: 세뇨관 배설 경쟁(OCT2) 및 신독성 약물 병용 부하 점수
    f6_sodium_excess      NUMERIC(7,2),         -- 피처 6: KDIGO 권장 상한 대비 나트륨 초과 섭취 부하
    f7_potassium_load     NUMERIC(7,2),         -- 피처 7: 칼륨 섭취 및 혈청 칼륨 배설 부하
    f8_protein_phos_load  NUMERIC(7,2),         -- 피처 8: 단백질·인 섭취에 의한 사구체 과여과 부하
    f9_hemodynamic_load   NUMERIC(6,2),         -- 피처 9: 수축기혈압 및 체중 기반 혈류역학 압력 부하
    -- [예측 정답 라벨 (Y)]
    target_next_egfr      NUMERIC(6,2),         -- 회귀 타깃: 다음 외래 방문 시 실측 eGFR 수치
    target_rapid_decline  SMALLINT,             -- 분류 타깃: eGFR 50% 이상 급락 또는 투석(RRT) 발생 여부 (정상=0, 악화=1)
    created_at            TIMESTAMPTZ DEFAULT NOW()
);
-- 환자별·예측 기준 시점별 피처 마트 조회 인덱스
CREATE INDEX IF NOT EXISTS idx_mart_member_anchor ON public.renal_9_burden_mart(member_id, anchor_ts);

-- ----------------------------------------------------------------------------
-- 6. 협업 권한 부여 (정지오님 계정: jungjeeo)
--    - 신규 생성한 5개 테이블의 조회(SELECT)·입력(INSERT)·수정(UPDATE)·삭제(DELETE) 권한 및
--      SERIAL/BIGSERIAL 자동 증가 시퀀스 사용 권한을 함께 부여
-- ----------------------------------------------------------------------------
GRANT SELECT, INSERT, UPDATE, DELETE ON
    public.cohort_split_manifest,
    public.lab_result,
    public.diet_intake_log,
    public.drug_pk_reference,
    public.renal_9_burden_mart
TO jungjeeo;

-- 내가 생성한 신규 테이블 4개의 시퀀스만 지정하여 jungjeeo에게 권한 부여
GRANT USAGE, SELECT ON SEQUENCE
    public.cohort_split_manifest_manifest_id_seq,
    public.lab_result_lab_id_seq,
    public.diet_intake_log_diet_log_id_seq,
    public.renal_9_burden_mart_mart_id_seq
TO jungjeeo;