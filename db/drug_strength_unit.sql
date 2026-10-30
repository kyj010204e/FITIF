-- drug 테이블에 함량/투여단위 컬럼 추가 및 HIRA 마스터 값 채우기
--
-- 대상: source = 'HIRA_20260731' 행만 (기존 source IS NULL 행은 변경하지 않음)
-- 실행 순서: [1] 컬럼 추가 -> [2] 1차 채우기 -> [3] 2차 보완
-- 재실행: HIRA 마스터를 다시 적재해 새 컬럼이 비었을 때 [2], [3]을 순서대로 다시 실행
--         ([1]은 IF NOT EXISTS라서 다시 실행해도 됨)
--
-- 파싱 규칙
--   1. 상품명 마지막 괄호 `_(함량단위/1투여단위)` 값을 우선 사용
--      예) 셀타플루캡슐75mg(...)_(98.5mg/1캡슐) -> 98.5 mg, 캡슐
--   2. 마지막 괄호에 함량이 없으면 상품명 앞쪽 숫자 사용 (복합제 10/100밀리그램은 NULL)
--   3. g은 mg으로 환산 (0.15g -> 150 mg), ㎍/μg/µg/mcg는 μg으로 표기 통일
--   4. 국제단위(I.U, KI.U, MI.U, unit, U, KU)는 환산 없이 원문 유지
--   5. 분모가 mL, L, g, mg인 농도형(6g/500mL)은 투여단위로 보지 않고 NULL
--   6. 파싱되지 않는 값은 NULL (값을 추측해서 채우지 않음)


-- [1] 컬럼 추가 ------------------------------------------------------------
ALTER TABLE drug
  ADD COLUMN IF NOT EXISTS strength_value numeric(12,3),
  ADD COLUMN IF NOT EXISTS strength_unit  varchar(20),
  ADD COLUMN IF NOT EXISTS intake_unit    varchar(20);


-- [2] 1차 채우기 ------------------------------------------------------------
WITH base AS (
  SELECT
    drug_id,
    rtrim(split_part(drug_name, '(', 1), '_') AS head,
    regexp_match(drug_name,
      '_\(([0-9]+(?:\.[0-9]+)?)\s*([^/)0-9][^/)]*)/1(?![0-9.])\s*([^)]*)\)$') AS ratio,
    regexp_match(drug_name, '_\(1\s*([^0-9)][^)]*)\)$') AS one_unit
  FROM drug
  WHERE source = 'HIRA_20260731'
),
picked AS (
  SELECT
    drug_id,
    regexp_match(head,
      '(?<![0-9./])([0-9]+(?:\.[0-9]+)?)\s*(mg|밀리그램|mcg|㎍|μg|µg|마이크로그램|g|그램)$') AS f,
    ratio,
    one_unit,
    (ratio IS NOT NULL AND ratio[3] !~* '^(ml|l|g|mg|㎍|μg)') AS ratio_ok
  FROM base
),
parts AS (
  SELECT
    drug_id,
    CASE WHEN ratio_ok THEN ratio[1] ELSE f[1] END       AS v_raw,
    CASE WHEN ratio_ok THEN trim(ratio[2]) ELSE f[2] END AS u_raw,
    COALESCE(
      CASE WHEN ratio_ok THEN NULLIF(trim(ratio[3]), '') END,
      CASE WHEN one_unit IS NOT NULL AND one_unit[1] !~* '^(ml|l|g|mg|㎍|μg)'
           THEN trim(one_unit[1]) END
    ) AS intake_unit
  FROM picked
),
norm AS (
  SELECT
    drug_id,
    v_raw::numeric AS v,
    CASE
      WHEN u_raw IN ('mg','밀리그램')                       THEN 'mg'
      WHEN u_raw IN ('g','그램')                            THEN 'g'
      WHEN u_raw IN ('㎍','μg','µg','mcg','마이크로그램')     THEN 'μg'
      WHEN u_raw IN ('I.U','KI.U','MI.U','unit','U','KU')  THEN u_raw
    END AS u,
    intake_unit
  FROM parts
)
UPDATE drug d
SET strength_value = CASE WHEN n.u IS NULL THEN NULL
                          WHEN n.u = 'g'   THEN n.v * 1000
                          ELSE n.v END,
    strength_unit  = CASE WHEN n.u = 'g' THEN 'mg' ELSE n.u END,
    intake_unit    = n.intake_unit
FROM norm n
WHERE d.drug_id = n.drug_id;


-- [3] 2차 보완 --------------------------------------------------------------
-- 괄호 안에 성분명이 앞에 붙은 형식과 `/정`처럼 1이 생략된 형식
-- 예) _(발프로산나트륨, 0.3g/1정), _(25mg/정)
-- 투여단위가 비어 있는 행만 대상. 함량도 같은 괄호 값으로 맞춰 덮어씀
WITH t AS (
  SELECT drug_id,
    regexp_match(drug_name,
      '_\((?:[^,()]*,\s*)?([0-9]+(?:\.[0-9]+)?)\s*(mg|g|mcg|㎍|μg)\s*/\s*1?\s*([^0-9)/.][^)/]*)\)$') AS m
  FROM drug
  WHERE source = 'HIRA_20260731' AND intake_unit IS NULL
),
norm AS (
  SELECT drug_id,
    m[1]::numeric AS v,
    CASE WHEN m[2] = 'mg'               THEN 'mg'
         WHEN m[2] = 'g'                THEN 'g'
         WHEN m[2] IN ('mcg','㎍','μg')  THEN 'μg' END AS u,
    trim(m[3]) AS intake
  FROM t
  WHERE m IS NOT NULL AND m[3] !~* '^(ml|l|g|mg)'
)
UPDATE drug d
SET strength_value = CASE WHEN n.u = 'g' THEN n.v * 1000 ELSE n.v END,
    strength_unit  = CASE WHEN n.u = 'g' THEN 'mg' ELSE n.u END,
    intake_unit    = n.intake
FROM norm n
WHERE d.drug_id = n.drug_id;


-- 확인 쿼리 (필요할 때 하나씩 실행) ------------------------------------------
-- 샘플: 셀타플루는 98.500 mg 캡슐로 나와야 함
-- SELECT edi_code, drug_name, strength_value, strength_unit, intake_unit
-- FROM drug
-- WHERE edi_code IN ('658203610','640900300','060500090','656001170','658107300','649102190','060500740');
--
-- HIRA 전체 건수 (2026-10-30 기준: total 21998, with_intake 17611)
-- SELECT count(*) FILTER (WHERE strength_value IS NOT NULL) AS with_strength,
--        count(*) FILTER (WHERE intake_unit IS NOT NULL)    AS with_intake,
--        count(*) AS total
-- FROM drug WHERE source = 'HIRA_20260731';
--
-- 기존 행은 변경되지 않아야 함: 0
-- SELECT count(*) FROM drug
-- WHERE source IS NULL AND (strength_value IS NOT NULL OR intake_unit IS NOT NULL);


-- 되돌리기 (값만 비움) ---------------------------------------------------------
-- UPDATE drug SET strength_value = NULL, strength_unit = NULL, intake_unit = NULL;
