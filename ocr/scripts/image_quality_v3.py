from scripts.image_quality_v2 import analyze_bytes as analyze_v2

POLICY_VERSION = "IQA-MVP-3"


def neighbors(region, regions):
    result = []

    for other in regions:
        distance = (
            abs(region["row"] - other["row"])
            + abs(region["col"] - other["col"])
        )

        if distance == 1:
            result.append(other)

    return result


def detect_local_blur(regions):
    candidates = []

    for region in regions:
        surrounding = neighbors(region, regions)

        # 흐릿해져 에지가 사라진 영역도 검사한다.
        # 원래 빈 영역을 일부 제외하기 위해
        # 약간의 명암 변화가 남아 있는지 확인한다.
        very_low_detail = (
            region["sharpness"] < 10
            and region["edge_ratio"] < 0.002
            and region["contrast_std"] >= 5
        )

        # 주변에 선명한 글자/표 구조가 존재하는지 확인
        detailed_neighbors = sum(
            1 for n in surrounding
            if (
                n["sharpness"] > 100
                and n["edge_ratio"] > 0.02
            )
        )

        if very_low_detail and detailed_neighbors >= 1:
            candidates.append(
                (region["row"], region["col"])
            )

    candidate_set = set(candidates)
    groups = []
    visited = set()

    # 인접한 의심 영역끼리 연결
    for start in candidates:
        if start in visited:
            continue

        group = []
        stack = [start]
        visited.add(start)

        while stack:
            row, col = stack.pop()
            group.append((row, col))

            adjacent = [
                (row - 1, col),
                (row + 1, col),
                (row, col - 1),
                (row, col + 1),
            ]

            for point in adjacent:
                if point in candidate_set and point not in visited:
                    visited.add(point)
                    stack.append(point)

        groups.append(group)

    # 인접한 두 영역 이상일 때 경고 후보
    detected_groups = [
        group for group in groups
        if len(group) >= 2
    ]

    return {
        "detected": bool(detected_groups),
        "candidate_regions": [
            {"row": row, "col": col}
            for row, col in candidates
        ],
        "groups": [
            [
                {"row": row, "col": col}
                for row, col in group
            ]
            for group in detected_groups
        ],
    }


def analyze_bytes(data: bytes):
    result = analyze_v2(data)

    blur = detect_local_blur(result["regions"])

    # 기존 v2 결과에 추가 검사만 반영
    reasons = list(result["reasons"])

    if blur["detected"]:
        if "POSSIBLE_LOCAL_BLUR" not in reasons:
            reasons.append("POSSIBLE_LOCAL_BLUR")

    result["policy_version"] = POLICY_VERSION
    result["reasons"] = reasons
    result["status"] = "WARNING" if reasons else "PASS"

    # 이번 버전도 OCR 실행을 차단하지 않는다.
    result["blocking"] = False
    result["local_blur_v3"] = blur

    return result
