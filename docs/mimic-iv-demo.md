# MIMIC-IV Demo 연습 데이터 적재 기록

> **한 줄 요약**: 미국 병원의 실제 입원 환자 기록(이름 등을 지운 공개 샘플 100명)을 우리 DB 구조에 맞춰 넣어 본
> **파이프라인 연습용 데이터**입니다. 한국인·당뇨 전용 데이터가 아니므로 **분석이나 모델 학습에는 쓰지 않습니다.**

- 작성: 중앙 DB 담당
- 적재 스크립트: `ingest/06 ~ 10_mimic_*.py`
- 적재 대상: PostgreSQL `team_project` (스키마는 `db/schema.sql`)

---

## 1. MIMIC-IV Demo가 뭔가요?

| 항목 | 내용 |
|---|---|
| 이름 | MIMIC-IV Clinical Database Demo v2.2 |
| 출처 | PhysioNet (MIT 연구실이 운영하는 의료 데이터 공개 사이트) |
| 원본 병원 | 미국 보스턴의 Beth Israel Deaconess Medical Center |
| 내용 | 병원 전자의무기록(EMR)에서 이름·주민번호 같은 식별 정보를 지운(비식별화) 데이터 |
| 규모 | **환자 100명**, 입원 275건, 중환자실(ICU) 입실 140건 |
| 나이 | 21 ~ 91세 (중앙값 63세) |
| 성별 | 남 57명, 여 43명 |
| 포함 안 된 것 | 의사 기록 같은 자유 서술 텍스트(notes) |
| 라이선스 | ODbL (공개 데이터베이스 라이선스, 출처 표기 필요) |
| 링크 | https://doi.org/10.13026/07hj-2a80 |

원본인 전체 MIMIC-IV는 교육과 서약을 거쳐 승인받은 사람만 쓸 수 있고,
그 샘플인 이 **Demo(100명)만 누구나 내려받을 수 있습니다.**

### 데이터 구성

| 폴더 | 내용 | 우리가 쓴 것 |
|---|---|---|
| `hosp` (병원 전체) | 환자, 입원, 진단, 처방, 검사, 외래 혈압·체중 등 | `patients`, `admissions`, `diagnoses_icd`, `d_icd_diagnoses`, `prescriptions`, `omr` |
| `icu` (중환자실) | 중환자실 입실, 활력징후 기록 등 | `chartevents` (체온, 혈압) |

쓰지 않은 파일(검사 결과 `labevents`, 투약 기록 `emar`, 시술 `procedures_icd` 등)은 나중에 필요하면 같은 방식으로 추가할 수 있습니다.

### 이 데이터의 성격 (중요)

- **입원·중환자 중심**입니다. 외래 진료나 당뇨 환자만 모은 데이터가 아닙니다.
  100명 중 당뇨 진단이 있는 환자는 35명입니다(대부분 2형).
- **아시아계 환자가 없습니다.** 인종 정보가 입원 기록에 있는데 백인, 흑인, 히스패닉, 기타, 미상뿐입니다.
  동아시아인은 서양인보다 낮은 BMI에서 2형 당뇨가 생기고 인슐린 분비 능력이 낮은 경향이 있어, 이 데이터의 결과를 한국형 서비스에 그대로 적용할 수 없습니다.
- **날짜가 가짜입니다.** 환자 정보를 보호하려고 환자마다 날짜를 임의의 값만큼 옮겨 놓았습니다.
  그래서 입원일이 2110~2201년, 출생연도가 2030~2149년처럼 미래 연도로 나옵니다.
  한 환자 안에서의 순서·간격·**입원 당시 나이는 정확**하지만, 실제 연도나 계절은 알 수 없습니다.

---

## 2. 우리 DB에 어떻게 넣었나

### 적재 결과 (MIMIC만)

| 테이블 | 추가된 행 | 비고 |
|---|---|---|
| `member` | 100 | `pseudo_code`가 `M`으로 시작 (상하이는 `P`) |
| `encounter` | 275 | `source_type = 'MIMIC_DATASET'` |
| `diagnosis` | 2,313 | ICD-10만 적재 |
| `drug` | (신규 약 이름만) | 약 이름 기준 중복 제거 |
| `prescription` | 6,941 | (방문, 약) 하나당 한 행 |
| `vital_sign` | 12,965 | 외래 혈압 868 + ICU 혈압 8,335 + ICU 체온 3,762 |

### 컬럼 매핑

| 우리 컬럼 | MIMIC 원본 | 처리 |
|---|---|---|
| `member.pseudo_code` | `patients.subject_id` | 앞에 `M`을 붙임 |
| `member.sex` | `patients.gender` | 그대로 (`M`/`F`) |
| `member.birth_year` | `anchor_year - anchor_age` | 계산. **날짜 이동된 가짜 연도** |
| `encounter.visit_date` | `admissions.admittime` | 날짜 부분만 |
| `diagnosis.icd10_code` | `diagnoses_icd.icd_code` | ICD-10만. 점(.) 없는 원본 표기(`E1165`) |
| `diagnosis.diagnosis_name` | `d_icd_diagnoses.long_title` | 영어 이름 그대로 |
| `drug.drug_name` | `prescriptions.drug` | 공백 정리, 대소문자 무시 중복 제거 |
| `drug.drug_code`, `atc_code` | 없음 | `NULL` (영어 약 이름이라 EDI 매핑 불가) |
| `prescription.dose` | `dose_val_rx` + `dose_unit_rx` | `500 mg` 형태, 단위 통일(`gm`→`g`, `UNIT`→`unit`) |
| `prescription.frequency` | `doses_per_24_hrs` | `하루 N회`. 정보가 없으면 `NULL` |
| `prescription.duration_days` | 처방 시작~종료 시각 | 올림한 일수(최소 1) |
| `vital_sign.measured_at` | `charttime` / `chartdate` | 시간대 `America/New_York`으로 해석 |
| `vital_sign.body_temp` | `chartevents` 체온 | ℉는 ℃로 변환 |
| `vital_sign.bp_*` | `omr`, `chartevents` | 수축기·이완기가 같은 시각인 것만 한 행으로 |

---

## 3. 결정 사항과 이유

| 결정 | 이유 |
|---|---|
| 전체 100명을 넣고 출처를 표시 | 아시아계가 없어 걸러낼 수 없고, 연습 목적이라 양이 필요. 출처 표시로 분석 시 제외 가능 |
| 진단은 **ICD-10만** 적재 (ICD-9 2,193행 제외) | 팀 결정: 기준을 ICD-10으로 두고 필요할 때 KCD로 변환. `icd10_code` 컬럼에 ICD-9이 섞이면 안 됨 |
| 처방은 BASE(수액 바탕액)·Flush(라인 세척) 제외 | 약물 치료가 아님 |
| 용량 `0`은 `NULL` | 인슐린 슬라이딩 스케일 등 "정해진 용량 없음"이라는 뜻이라 0단위 투여로 오해하면 안 됨 |
| 같은 입원의 같은 약은 한 행으로 합침 | 어제 상하이 방식과 같은 구조, 용량은 첫 처방 기준 |
| 시간대 `America/New_York` | 원본이 미국 보스턴 병원. 상하이는 `Asia/Shanghai`로 가정 |
| 출처 값 `MIMIC_DATASET`, `MIMIC_OMR`, `MIMIC_ICU` | 상하이(`SHANGHAI_DATASET`)와 같은 형식, 외래/ICU 구분 |
| 인종·보험·언어 등은 넣지 않음 | 우리 스키마에 없는 정보 |

---

## 4. 알아둘 한계

1. **진단 없는 방문이 많습니다.** 입원 275건 중 152건은 ICD-9 진단만 있어서 `diagnosis`에 행이 없습니다.
2. **외래 혈압(`MIMIC_OMR`)은 시각이 없습니다.** 그날 00:00으로 넣었고 `encounter_id`는 `NULL`입니다.
3. **혈압·체온은 대부분 ICU 측정값**입니다. 일반 환자의 평상시 값과 분포가 다릅니다.
4. **처방 정보가 상하이와 다릅니다.** 상하이 처방은 용량·횟수·기간이 비어 있고, MIMIC만 채워져 있습니다.
5. **영어 약 이름과 영어 진단명**입니다. 한국 코드(EDI, KCD)와 매핑되지 않았습니다.
6. **ODbL 라이선스**: 내부 연습용 사용에는 문제가 없지만, 이 데이터로 만든 DB를 외부에 공개·배포할 때는 출처 표기와 같은 조건 공유 의무가 있습니다. 공개 전에 라이선스를 확인하세요.
7. 원본 데이터 파일은 용량과 라이선스 때문에 **GitHub에 올리지 않습니다.** (`C:\medicalAI\DataSets\` 등 저장소 밖에 보관)
