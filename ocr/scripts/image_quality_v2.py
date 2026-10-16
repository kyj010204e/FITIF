from io import BytesIO

import cv2
import numpy as np
from PIL import Image, ImageOps

from scripts.image_quality import analyze_bytes as analyze_v1


POLICY_VERSION = "IQA-MVP-2"


def load_gray(data):
    with Image.open(BytesIO(data)) as img:
        img = ImageOps.exif_transpose(img).convert("RGB")
        width, height = img.size

    # 측정 속도를 일정하게 유지
    scale = min(1.0, 1400 / max(width, height))

    if scale < 1:
        img = img.resize(
            (
                max(1, round(width * scale)),
                max(1, round(height * scale)),
            ),
            Image.Resampling.LANCZOS,
        )

    rgb = np.asarray(img)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)

    return gray, width, height


def analyze_regions(gray, rows=4, cols=4):
    height, width = gray.shape
    regions = []

    for r in range(rows):
        for c in range(cols):
            y1 = r * height // rows
            y2 = (r + 1) * height // rows
            x1 = c * width // cols
            x2 = (c + 1) * width // cols

            patch = gray[y1:y2, x1:x2]

            if patch.shape[0] < 8 or patch.shape[1] < 8:
                continue

            lap_var = float(
                cv2.Laplacian(
                    patch,
                    cv2.CV_64F,
                ).var()
            )

            # 빈 종이 영역을 흐림으로 오판하지 않도록
            # 정보량이 낮은 영역은 흐림 판정에서 제외
            local_std = float(patch.std())

            edges = cv2.Canny(patch, 50, 150)
            edge_ratio = float(
                np.count_nonzero(edges) / edges.size
            )

            informative = (
                local_std >= 12
                and edge_ratio >= 0.008
            )

            regions.append({
                "row": r,
                "col": c,
                "brightness": round(float(patch.mean()), 2),
                "contrast_std": round(local_std, 2),
                "sharpness": round(lap_var, 2),
                "edge_ratio": round(edge_ratio, 4),
                "informative": bool(informative),
            })

    return regions


def analyze_bytes(data: bytes):
    # v1 결과를 그대로 보존해 비교 가능하게 함
    base = analyze_v1(data)

    gray, width, height = load_gray(data)
    regions = analyze_regions(gray)

    informative = [
        region
        for region in regions
        if region["informative"]
    ]

    # 1. 부분 흐림
    # 경계선과 명암 변화가 있는 영역만 비교
    partial_blur = False
    blur_ratio = None

    if len(informative) >= 4:
        sharpness = np.array(
            [r["sharpness"] for r in informative],
            dtype=np.float64,
        )

        reference = float(np.median(sharpness))

        if reference > 30:
            weak = np.count_nonzero(
                sharpness < max(15.0, reference * 0.12)
            )

            blur_ratio = round(
                float(weak / len(sharpness)),
                3,
            )

            partial_blur = weak >= 2 and blur_ratio >= 0.25

    # 2. 조명 불균형
    # 글자 획보다는 넓은 밝기 변화를 관찰
    height, width = gray.shape

    smooth = cv2.GaussianBlur(
        gray,
        (0, 0),
        sigmaX=max(8, width / 20),
        sigmaY=max(8, height / 20),
    )

    illumination_p10 = float(np.percentile(smooth, 10))
    illumination_p90 = float(np.percentile(smooth, 90))
    illumination_gap = illumination_p90 - illumination_p10

    # 문서의 글자가 아주 많은 경우에도 변동할 수 있으므로
    # 확정 판정이 아닌 그림자 '가능성'만 반환
    uneven_light = illumination_gap >= 75

    # 3. 과다 노출
    bright_ratio = float(np.mean(gray >= 250))
    dark_ratio = float(np.mean(gray <= 120))

    # 흰 종이가 많다는 이유만으로 과다 노출로 보지 않음.
    # 밝은 픽셀 대다수 + 어두운 획이 거의 없음
    possible_overexposure = (
        bright_ratio >= 0.90
        and base["metrics"]["contrast_range"] < 35
    )

    v2_reasons = []

    if partial_blur:
        v2_reasons.append("POSSIBLE_LOCAL_BLUR")

    if uneven_light:
        v2_reasons.append("UNEVEN_ILLUMINATION")

    if possible_overexposure:
        v2_reasons.append("POSSIBLE_OVEREXPOSURE")

    # v1과 v2는 독립적으로 볼 수 있도록 보존.
    # v1의 TOO_BRIGHT는 이 단계에서 확정 경고로 사용하지 않음.
    v1_reasons = [
        reason
        for reason in base["reasons"]
        if reason != "TOO_BRIGHT"
    ]

    reasons = list(dict.fromkeys(v1_reasons + v2_reasons))

    # 실험용 정책: 강제 차단하지 않음
    status = "WARNING" if reasons else "PASS"

    return {
        "status": status,
        "reasons": reasons,
        "policy_version": POLICY_VERSION,
        "blocking": False,
        "metrics": {
            "width": width,
            "height": height,
            "short_side": min(width, height),
            "global_sharpness": base["metrics"]["sharpness"],
            "brightness": base["metrics"]["brightness"],
            "contrast_range": base["metrics"]["contrast_range"],
            "informative_regions": len(informative),
            "total_regions": len(regions),
            "local_blur_ratio": blur_ratio,
            "illumination_gap": round(illumination_gap, 2),
            "bright_pixel_ratio": round(bright_ratio, 4),
            "dark_pixel_ratio": round(dark_ratio, 4),
        },
        "regions": regions,
        "v1": {
            "status": base["status"],
            "reasons": base["reasons"],
        },
    }
