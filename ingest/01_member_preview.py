from pathlib import Path
import pandas as pd

# 데이터 위치 (r 은 경로의 \ 를 그대로 쓰겠다는 표시)
BASE = Path(r"C:\medicalAI\DataSets\Diabetes Datasets-ShanghaiT1DM and ShanghaiT2DM")

# 1) 요약표 두 개 읽어서 합치기
t1 = pd.read_excel(BASE / "Shanghai_T1DM_Summary.xlsx")
t2 = pd.read_excel(BASE / "Shanghai_T2DM_Summary.xlsx")
summary = pd.concat([t1, t2], ignore_index=True)

# 2) 'Patient Number'(예: 1001_0_20210730)를 환자번호와 날짜로 쪼개기
parts = summary["Patient Number"].astype(str).str.split("_", expand=True)
summary["patient_no"] = parts[0]                                   # 1001
summary["visit_date"] = pd.to_datetime(parts[2], format="%Y%m%d")  # 2021-07-30

# 3) 같은 환자가 여러 번 입원한 기록은 첫 번째 것만 남기기
summary = summary.sort_values(["patient_no", "visit_date"])
first = summary.drop_duplicates("patient_no", keep="first")

# 4) member 테이블 모양으로 만들기
member = pd.DataFrame({
    "pseudo_code": "P" + first["patient_no"],                              # P1001
    "sex": first["Gender (Female=1, Male=2)"].map({1: "F", 2: "M"}),
    "birth_year": first["visit_date"].dt.year - first["Age (years)"],     # 입원 연도 - 나이
})

# 5) 결과 눈으로 확인
print(member.shape)
print(member.head())
print(member.isna().sum())
print(member["sex"].value_counts())