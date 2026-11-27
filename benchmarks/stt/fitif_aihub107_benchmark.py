"""AI Hub 107 경량 ZIP으로 Whisper와 Gemma의 한국어 전사를 비교한다."""
import argparse
import csv
import hashlib
import json
import random
import re
import subprocess
import tempfile
import unicodedata
from collections import defaultdict
from pathlib import Path, PurePosixPath
from statistics import median
from time import perf_counter
from zipfile import ZipFile


# 첫 파일럿에서는 이 태그가 포함된 발화를 샘플링 대상에서 제외한다.
ANNOTATION_TAG = re.compile(r"\((?:FP|SP|SN|NO):", re.IGNORECASE)
SEED = 107
PER_SPEAKER = 5
FIELDS = ("clip", "audio_sha256", "speaker", "reference", "prediction", "status",
          "seconds", "edit_count", "reference_chars")
MODELS = ("whisper", "gemma")
WHISPER_MODELS = ("small", "medium", "large-v3-turbo", "large-v3")


def normalize(text):
    # 전사 표기의 공백과 문장부호 차이는 CER에서 제외한다.
    return "".join(
        char for char in unicodedata.normalize("NFKC", text).casefold()
        if not char.isspace() and not unicodedata.category(char).startswith("P")
    )


def edit_distance(reference, prediction):
    previous = list(range(len(prediction) + 1))
    for i, ref_char in enumerate(reference, 1):
        current = [i]
        for j, pred_char in enumerate(prediction, 1):
            current.append(min(
                current[-1] + 1,
                previous[j] + 1,
                previous[j - 1] + (ref_char != pred_char),
            ))
        previous = current
    return previous[-1]



def transcribe(endpoint, model, audio, timeout):
    # 직접 WAV를 전송한다. 정답 전사와 Whisper 전사는 모델 입력에 넣지 않는다.
    try:
        result = subprocess.run(
            [
                "curl", "--silent", "--show-error", "--fail-with-body", "--max-time", str(timeout),
                "--form", f"file=@{audio};type=audio/wav", "--form-string", f"model={model}",
                "--form-string", "language=ko", "--form-string", "temperature=0",
                "--form-string", "response_format=json", endpoint,
            ],
            text=True, encoding="utf-8", capture_output=True, check=True,
        )
    except subprocess.CalledProcessError as error:
        detail = (error.stderr + "\n" + error.stdout).strip()
        if error.returncode == 28:
            raise TimeoutError(f"{audio.name} | {timeout}초 타임아웃") from None
        raise RuntimeError(f"Ollama 전사 실패 ({audio.name})\n{detail}") from None
    try:
        prediction = json.loads(result.stdout).get("text")
    except (ValueError, AttributeError):
        raise RuntimeError(f"Ollama가 전사 JSON을 반환하지 않았어요 ({audio.name}).") from None
    if not isinstance(prediction, str):
        raise RuntimeError(f"Ollama 응답에 text가 없어요 ({audio.name}).")
    # 빈 전사는 제품 오류와 분리해 그대로 채점한다.
    return prediction.strip()


def sample_clips(archive):
    """공식 fileNm과 WAV 이름을 대조하고 화자별로 재현 가능한 5건을 뽑는다."""
    files = defaultdict(list)
    for entry in archive.infolist():
        path = PurePosixPath(entry.filename)
        if path.suffix.lower() == ".wav":
            files[path.name].append(entry)

    groups = defaultdict(list)
    matched = set()
    for entry in sorted(archive.infolist(), key=lambda item: item.filename):
        if PurePosixPath(entry.filename).suffix.lower() != ".json":
            continue
        label = json.loads(archive.read(entry).decode("utf-8-sig"))
        utterance = label["발화정보"]
        name = PurePosixPath(utterance["fileNm"]).name
        candidates = files[name]
        if len(candidates) != 1 or name in matched:
            raise ValueError(f"WAV와 JSON을 1:1로 매칭할 수 없어요: {name}")
        matched.add(name)
        reference = utterance["stt"]
        if ANNOTATION_TAG.search(reference) or not normalize(reference):
            continue
        speaker = str(label["녹음자정보"]["recorderId"]).strip()
        if not speaker:
            raise ValueError(f"화자 ID가 비어 있어요: {name}")
        groups[speaker].append((candidates[0], reference))

    if not groups:
        raise ValueError("평가할 WAV/JSON 쌍이 없어요.")
    rng = random.Random(SEED)
    clips = []
    for index, speaker in enumerate(sorted(groups), start=1):
        if len(groups[speaker]) < PER_SPEAKER:
            raise ValueError(f"화자 {index}의 평가용 발화가 5개 미만이에요.")
        selected = rng.sample(groups[speaker], PER_SPEAKER)
        clips.extend((f"speaker_{index:02}", entry, reference) for entry, reference in selected)

    print(f"매칭 {len(matched)}쌍 | 파일럿 {len(clips)}건 | 화자 {len(groups)}명", flush=True)
    return clips


def whisper_transcriber(model_name):
    from faster_whisper import WhisperModel

    model = WhisperModel(model_name, device="cuda", compute_type="float16")

    def transcribe_whisper(audio):
        segments, _ = model.transcribe(
            str(audio), language="ko", beam_size=5,
            vad_filter=False, condition_on_previous_text=False,
        )
        return " ".join(segment.text.strip() for segment in segments).strip()

    return transcribe_whisper


def evaluate(archive, clips, output_dir, backend, timeout, whisper_model="small"):
    if backend == "whisper":
        predict = whisper_transcriber(whisper_model)
    else:
        def predict(audio):
            endpoint = "http://127.0.0.1:11434/v1/audio/transcriptions"
            return transcribe(endpoint, "gemma4:12b", audio, timeout)

    output_dir.mkdir(parents=True, exist_ok=True)
    result_name = whisper_result_name(whisper_model) if backend == "whisper" else "gemma"
    target = output_dir / f"{result_name}.csv"
    # 임시 파일에 저장하고 1회 실행이 끝나면 최종 CSV로 교체한다.
    with tempfile.TemporaryDirectory(prefix="fitif-stt-", dir=output_dir) as temporary:
        staging = Path(temporary) / target.name
        with staging.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            for index, (speaker, entry, reference) in enumerate(clips, start=1):
                clip = f"{index:03}.wav"
                audio = Path(temporary) / clip
                wav = archive.read(entry)
                audio.write_bytes(wav)
                start = perf_counter()
                status = "ok"
                prediction = ""
                try:
                    prediction = predict(audio)
                except TimeoutError:
                    status = "timeout"
                except RuntimeError as error:
                    print(f"{clip} | {error}", flush=True)
                    status = "error"
                seconds = perf_counter() - start
                normalized_reference = normalize(reference)
                edits = edit_distance(normalized_reference, normalize(prediction)) if status == "ok" else ""
                writer.writerow(dict(
                    clip=clip, audio_sha256=hashlib.sha256(wav).hexdigest(),
                    speaker=speaker, reference=reference, prediction=prediction,
                    status=status, seconds=f"{seconds:.6f}", edit_count=edits,
                    reference_chars=len(normalized_reference),
                ))
                print(f"[{index}/{len(clips)}] {clip} | {status} | {seconds:.2f}초", flush=True)
        staging.replace(target)


def whisper_result_name(model_name):
    # 기존 small 평가 CSV 이름도 계속 사용할 수 있게 유지한다.
    return "whisper" if model_name == "small" else f"whisper_{model_name}"


def compare(output_dir, whisper_models=("small",)):
    result_names = {
        f"Whisper {name}": whisper_result_name(name) for name in whisper_models
    }
    result_names["Gemma gemma4:12b"] = "gemma"
    missing = [
        f"{name}.csv" for name in result_names.values()
        if not (output_dir / f"{name}.csv").is_file()
    ]
    if missing:
        raise ValueError(f"아직 평가 결과가 없어요: {', '.join(missing)}")

    runs = {}
    for model_label, result_name in result_names.items():
        with (output_dir / f"{result_name}.csv").open(encoding="utf-8-sig", newline="") as handle:
            runs[model_label] = list(csv.DictReader(handle))

    # 재현된 입력 순서와 정답이 같은지 먼저 확인한다.
    keys = ("clip", "audio_sha256", "speaker", "reference", "reference_chars")
    reference_rows = runs["Gemma gemma4:12b"]
    expected = [tuple(row[key] for key in keys) for row in reference_rows]
    for model_label, rows in runs.items():
        observed = [tuple(row[key] for key in keys) for row in rows]
        if not expected or observed != expected:
            raise ValueError(f"평가 목록 또는 정답이 일치하지 않아요: {model_label}")

    successful_clips = [
        {row["clip"] for row in rows if row["status"] == "ok"}
        for rows in runs.values()
    ]
    common = set.intersection(*successful_clips)
    print(f"{len(runs)}개 모델이 모두 성공한 발화 {len(common)}/{len(expected)}건")
    for model_label, rows in runs.items():
        successes = [row for row in rows if row["status"] == "ok"]
        shared = [row for row in successes if row["clip"] in common]
        edits = sum(int(row["edit_count"]) for row in shared)
        chars = sum(int(row["reference_chars"]) for row in shared)
        timeouts = sum(row["status"] == "timeout" for row in rows)
        errors = len(rows) - len(successes) - timeouts
        cer = f"{100 * edits / chars:.2f}% ({edits}/{chars})" if chars else "집계 불가"
        latency = f"{median(float(row['seconds']) for row in shared):.2f}초" if shared else "집계 불가"
        print(f"{model_label} | CER {cer} | 처리시간 중앙값 {latency} | "
              f"완료 {len(successes)}/{len(rows)} | 타임아웃 {timeouts} | 기타 오류 {errors}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", type=Path, help="AI Hub 107 경량 ZIP 경로")
    parser.add_argument("--mode", choices=("check", *MODELS, "compare"), required=True)
    parser.add_argument(
        "--whisper-model", nargs="+", choices=WHISPER_MODELS, default=["small"],
        help="Whisper 평가 모델 1개 또는 비교할 모델 목록",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("aihub107_results"))
    parser.add_argument("--timeout", type=int, default=300, help="Gemma 발화당 요청 제한 시간(초)")
    args = parser.parse_args()
    if args.mode == "compare":
        try:
            compare(args.output_dir, args.whisper_model)
        except ValueError as error:
            parser.error(str(error))
        return
    if args.mode == "whisper" and len(args.whisper_model) != 1:
        parser.error("Whisper를 실행할 때는 평가 모델을 1개 지정해 주세요.")
    if args.zip is None or args.timeout < 1:
        parser.error("입력 ZIP과 1초 이상의 타임아웃이 필요해요.")
    with ZipFile(args.zip) as archive:
        clips = sample_clips(archive)
        if args.mode != "check":
            evaluate(archive, clips, args.output_dir, args.mode, args.timeout, args.whisper_model[0])


if __name__ == "__main__":
    main()
