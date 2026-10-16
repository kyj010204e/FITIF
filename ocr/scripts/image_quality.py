from io import BytesIO

import cv2
import numpy as np
from PIL import Image, ImageOps


def analyze_bytes(data: bytes):
    with Image.open(BytesIO(data)) as img:
        image = ImageOps.exif_transpose(img).convert("RGB")

    width, height = image.size
    short_side = min(width, height)

    gray = cv2.cvtColor(
        np.asarray(image),
        cv2.COLOR_RGB2GRAY,
    )

    scale = min(1.0, 1200 / max(width, height))

    if scale < 1.0:
        gray = cv2.resize(
            gray,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_AREA,
        )

    sharpness = float(
        cv2.Laplacian(gray, cv2.CV_64F).var()
    )

    brightness = float(gray.mean())
    contrast_std = float(gray.std())

    p5, p95 = np.percentile(gray, [5, 95])
    contrast_range = float(p95 - p5)

    warnings = []

    if short_side < 700:
        warnings.append("LOW_RESOLUTION")

    if sharpness < 25:
        warnings.append("POSSIBLE_BLUR")

    if brightness < 75:
        warnings.append("TOO_DARK")

    if brightness > 245:
        warnings.append("TOO_BRIGHT")

    if contrast_range < 35:
        warnings.append("LOW_CONTRAST")

    if short_side < 250:
        status = "RECAPTURE"
        reasons = ["EXTREMELY_LOW_RESOLUTION"]

    elif contrast_std < 4:
        status = "RECAPTURE"
        reasons = ["NEAR_UNIFORM_IMAGE"]

    elif warnings:
        status = "WARNING"
        reasons = warnings

    else:
        status = "PASS"
        reasons = []

    return {
        "status": status,
        "reasons": reasons,
        "policy_version": "IQA-MVP-1",
        "metrics": {
            "width": width,
            "height": height,
            "short_side": short_side,
            "sharpness": round(sharpness, 2),
            "brightness": round(brightness, 2),
            "contrast_std": round(contrast_std, 2),
            "contrast_range": round(contrast_range, 2),
        },
    }
