import math


DAMAGE_WEIGHTS = {
    0: 0.35,  # Longitudinal Crack
    1: 0.40,  # Transverse Crack
    2: 0.70,  # Alligator Crack
    3: 0.85   # Pothole
}


def calculate_severity(class_id, confidence, box_area, image_area):

    # Safety checks
    if image_area <= 0 or box_area <= 0:
        return 0.0, "LOW"

    type_weight = DAMAGE_WEIGHTS.get(class_id, 0.35)

    # Fraction of the image occupied by the detected damage
    normalized_area = box_area / image_area

    # Logarithmic size score between 0 and 1
    size_score = min(
        math.log10(normalized_area * 100 + 1) / math.log10(31),
        1.0
    )

    # Reduce the influence of very low-confidence detections
    conf_factor = confidence if confidence >= 0.20 else confidence * 0.5

    # Final severity score
    severity_score = (
        0.50 * type_weight
        + 0.35 * size_score
        + 0.15 * conf_factor
    )

    # Severity category
    if severity_score < 0.42:
        severity_level = "LOW"
    elif severity_score < 0.72:
        severity_level = "MEDIUM"
    else:
        severity_level = "HIGH"

    return round(severity_score, 3), severity_level