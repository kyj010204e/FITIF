# FITIF STT 1차 성능 비교 · AI Hub 107

2026년 11월 27일 · RTX 5090

**1차 STT 후보는 Whisper `large-v3-turbo`다.** 이번 파일럿에서 문자 오류율(CER) 1.83%, 발화당 처리 시간 중앙값 0.11초를 기록했고 25건을 모두 처리했다.

## 평가 방법

AI Hub 107번 「자유대화 음성(노인남여)」 경량 샘플에서 WAV와 전사 JSON 2,930쌍을 매칭했다. `FP`, `SP`, `SN`, `NO` 태그가 있는 발화를 제외하고 고정 시드 107로 화자 5명에게서 5건씩 선택했다. 네 모델에 동일한 WAV 25개를 입력했다.

Whisper는 faster-whisper에서 CUDA FP16, 한국어, 빔 크기 5로 실행했다. Gemma는 Ollama의 로컬 전사 API에 WAV를 직접 보냈고 요청당 제한은 300초였다. 처리 시간은 각 모델 호출부터 결과 반환까지이며, Gemma에는 로컬 HTTP 요청 시간이 포함된다. 휴대폰 녹음이나 앱 전체 응답 시간은 별도 측정 항목이다.

## 실측 결과

| 모델 | CER ↓ | 처리 시간 중앙값 ↓ | 완료 | 타임아웃 |
|---|---:|---:|---:|---:|
| Whisper medium | 4.88% (16/328) | 0.17초 | 25/25 | 0 |
| **Whisper large-v3-turbo** | **1.83% (6/328)** | **0.11초** | **25/25** | **0** |
| Whisper large-v3 | 5.79% (19/328) | 0.21초 | 25/25 | 0 |
| Gemma gemma4:12b 직접 전사 | 22.56% (74/328) | 92.98초 | 18/25 | 7 |

CER과 처리 시간은 네 모델이 모두 성공한 **18개 발화** 기준이다. CER은 유니코드를 정규화하고 공백·문장부호를 제외한 정답 328자에 대한 편집 거리 합계다. 완료와 타임아웃은 전체 25건을 기준으로 집계했다.

## FITIF 적용 판단

이번 구성에서는 Whisper large-v3-turbo가 음성을 전사하고 Gemma가 그 텍스트로 사용자 의도를 판단하는 구조를 1차안으로 잡는다. Gemma 직접 전사는 성공한 요청에서도 중앙값이 92.98초였고 전체 25건 중 7건이 타임아웃됐다.

이번 결과는 화자 5명에 한정되고 전사 태그가 있는 발화와 타임아웃 발화는 CER 비교에서 빠졌다. FITIF 전용 음성으로 혈당 값·소수점·단위 완전 일치율과 느린 발화의 조기 녹음 종료율을 확인한 뒤 앱 적용을 검증한다.

데이터 출처 · [AI Hub 107번 데이터](https://www.aihub.or.kr/aihubdata/data/view.do?dataSetSn=107)

## 재현 방법

AI Hub에서 경량 샘플 ZIP을 내려받아 로컬 경로를 지정한다. Python 환경에 `faster-whisper`를 설치하고 CUDA 12용 cuBLAS 및 cuDNN 9 라이브러리를 Python 프로세스가 찾도록 설정한다. Gemma 평가에는 `gemma4:12b`가 설치된 Ollama와 로컬 `/v1/audio/transcriptions` 엔드포인트, `curl`이 필요하다.

```bash
cd benchmarks/stt
sample_zip='/path/to/New_Sample.zip'
python3 fitif_aihub107_benchmark.py --zip "$sample_zip" --mode check

for model in medium large-v3-turbo large-v3; do
  python3 fitif_aihub107_benchmark.py --zip "$sample_zip" \
    --mode whisper --whisper-model "$model" || exit 1
done

python3 fitif_aihub107_benchmark.py --zip "$sample_zip" --mode gemma --timeout 300 &&
python3 fitif_aihub107_benchmark.py --mode compare \
  --whisper-model medium large-v3-turbo large-v3
```

모델별 CSV는 기본적으로 `aihub107_results/`에 생성된다. 원본 ZIP, WAV, JSON과 발화별 전사가 포함된 결과 CSV는 로컬에 보관한다. 위 표에는 집계값만 공개한다.

참고 · [faster-whisper GPU 요구 사항](https://github.com/SYSTRAN/faster-whisper#gpu)
