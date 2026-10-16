# FITIF OCR

의료 문서 이미지에서 텍스트와 표를 추출하고,
사용자 검수 후 DB 전달용 JSON을 생성하는 시스템입니다.

## 주요 기능

- PaddleOCR-VL 1.6 기반 OCR
- IQA v3 이미지 품질 검사
- HTML 기반 OCR 결과 확인 및 수정
- 진료일 자동 탐색 및 사용자 확인
- 최종 DB JSON 생성 및 다운로드
- 수정 전/후 OCR 결과 분리 보관

## 기술 스택

- Python 3.12
- PaddleOCR 3.7.0
- PaddlePaddle GPU 3.2.1
- Streamlit 1.66.0
- OpenCV / NumPy / Pillow
- BeautifulSoup

## 프로젝트 구조

- app.py : Streamlit 메인 앱
- scripts/ocr_runner.py : OCR 추론
- scripts/process_image.py : OCR 처리
- scripts/export_json.py : OCR JSON 변환
- scripts/document_renderer.py : 문서 구조화
- scripts/image_quality_v3.py : 품질 검사
- scripts/extract_visit_date.py : 진료일 추출
- scripts/export_final_db_json.py : DB JSON 생성
- frontend/document_editor/ : HTML 문서 편집기

## 실행 방법

1. Python 3.12 가상환경을 생성합니다.
2. requirements.txt에 명시된 패키지를 설치합니다.
3. GPU 사용 시 CUDA 환경에 맞는 PaddlePaddle GPU를 별도 설치합니다.
4. ocr 디렉터리에서 다음 명령어를 실행합니다.

    streamlit run app.py --server.address 127.0.0.1 --server.port 8501

최초 실행에는 모델 가중치를 다운로드할 수 있는 환경이 필요합니다.

## 데이터 처리 과정

이미지 업로드
→ IQA v3
→ PaddleOCR-VL
→ HTML 전자문서
→ 사용자 검수
→ 진료일 확인
→ DB 전달용 JSON

## DB 연동

현재 encounter 및 source_document 저장에 필요한
JSON 데이터 생성 기능이 구현되어 있습니다.

실제 PostgreSQL INSERT는 별도 백엔드에서 처리합니다.

diagnoses와 prescriptions의 개별 데이터 구조화는 개발 예정입니다.

## 주의사항

- OCR 인식 결과는 정확성을 보장하지 않습니다.
- 의료정보는 사용자 검수 후 활용해야 합니다.
- 원본 의료 문서와 OCR 결과 JSON은 GitHub에 업로드하지 않습니다.
- 실제 DB 저장 기능은 포함하지 않습니다.
