from pathlib import Path
import pandas as pd

# MIMIC hosp 폴더 경로
HOSP = Path(r"C:\medicalAI\DataSets\mimic-iv-clinical-database-demo-2.2\hosp")

pt = pd.read_csv(HOSP / "patients.csv.gz")

member = pd.DataFrame({
    "pseudo_code": "M" + pt["subject_id"].astype(str),
    "sex": pt["gender"],
    "birth_year": (pt["anchor_year"] - pt["anchor_age"]).astype(int),
})

print(member.shape)
print(member.head())
print("코드 최대 길이:", member["pseudo_code"].str.len().max())
print(member["sex"].value_counts())