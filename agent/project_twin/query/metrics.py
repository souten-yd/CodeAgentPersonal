"""Impact and test-recommendation metrics (PI-9).

Recorded (not gated) quality metrics for the impact and test-selection engine, used by the
shadow/benchmark comparison. Pure set arithmetic.
"""

from __future__ import annotations


def precision_recall(predicted: set[str], actual: set[str]) -> dict[str, float]:
    tp = len(predicted & actual)
    precision = tp / len(predicted) if predicted else (1.0 if not actual else 0.0)
    recall = tp / len(actual) if actual else 1.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {"precision": precision, "recall": recall, "f1": f1, "true_positives": float(tp)}


def test_recommendation_precision(recommended: set[str], relevant: set[str]) -> dict[str, float]:
    return precision_recall(recommended, relevant)
