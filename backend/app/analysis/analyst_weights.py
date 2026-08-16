from __future__ import annotations

ANALYST_WEIGHT_DIFFERENTIATION_EXPONENT = 2.0
ANALYST_SCORE_MIN = 0.20
ANALYST_SCORE_MAX = 1.00


def analyst_raw_weight(*, data_confidence: float, profile_fit_score: float) -> float:
    confidence = _clamp(data_confidence, ANALYST_SCORE_MIN, ANALYST_SCORE_MAX)
    fit = _clamp(profile_fit_score, ANALYST_SCORE_MIN, ANALYST_SCORE_MAX)
    return (0.50 * confidence) + (0.50 * fit)


def differentiate_and_normalize_analyst_weights(
    raw_weights: list[float],
) -> list[dict[str, float]]:
    if not raw_weights:
        return []

    normalized_raw_weights = [max(float(weight), 0.0) for weight in raw_weights]
    raw_total = sum(normalized_raw_weights)
    base_weights = (
        [weight / raw_total for weight in normalized_raw_weights]
        if raw_total > 0
        else [1.0 / len(normalized_raw_weights)] * len(normalized_raw_weights)
    )
    differentiated_raw_weights = [
        weight**ANALYST_WEIGHT_DIFFERENTIATION_EXPONENT
        for weight in normalized_raw_weights
    ]
    differentiated_total = sum(differentiated_raw_weights)
    analyst_weights = (
        [weight / differentiated_total for weight in differentiated_raw_weights]
        if differentiated_total > 0
        else [1.0 / len(normalized_raw_weights)] * len(normalized_raw_weights)
    )
    return [
        {
            "base_weight": base_weight,
            "differentiated_raw_weight": differentiated_raw_weight,
            "weight": analyst_weight,
        }
        for base_weight, differentiated_raw_weight, analyst_weight in zip(
            base_weights,
            differentiated_raw_weights,
            analyst_weights,
            strict=True,
        )
    ]


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, float(value)))
