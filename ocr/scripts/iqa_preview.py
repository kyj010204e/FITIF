from io import BytesIO

import cv2
import numpy as np
from PIL import Image, ImageOps


def create_iqa_preview(data: bytes, result: dict) -> bytes:
    """부분 흐림 의심 영역만 표시한 PNG 생성."""

    with Image.open(BytesIO(data)) as img:
        image = ImageOps.exif_transpose(img).convert("RGB")
        rgb = np.asarray(image).copy()

    height, width = rgb.shape[:2]

    blur = result.get("local_blur_v3", {})
    groups = blur.get("groups", [])

    if not groups:
        buffer = BytesIO()
        Image.fromarray(rgb).save(buffer, format="PNG")
        return buffer.getvalue()

    # 현재 IQA v3는 4x4 영역 분석
    regions = result.get("regions", [])

    if not regions:
        raise ValueError("영역 분석 정보가 없습니다.")

    rows = max(r["row"] for r in regions) + 1
    cols = max(r["col"] for r in regions) + 1

    output = rgb.copy()
    overlay = rgb.copy()

    suspects = {
        (r["row"], r["col"])
        for group in groups
        for r in group
    }

    for row, col in suspects:
        x1 = col * width // cols
        x2 = (col + 1) * width // cols
        y1 = row * height // rows
        y2 = (row + 1) * height // rows

        cv2.rectangle(
            overlay,
            (x1, y1),
            (x2 - 1, y2 - 1),
            (255, 50, 50),
            thickness=-1,
        )

    output = cv2.addWeighted(
        overlay, 0.18, output, 0.82, 0
    )

    thickness = max(2, width // 500)

    for row, col in suspects:
        x1 = col * width // cols
        x2 = (col + 1) * width // cols
        y1 = row * height // rows
        y2 = (row + 1) * height // rows

        cv2.rectangle(
            output,
            (x1, y1),
            (x2 - 1, y2 - 1),
            (210, 25, 25),
            thickness=thickness,
        )

    buffer = BytesIO()
    Image.fromarray(output).save(buffer, format="PNG")
    return buffer.getvalue()
