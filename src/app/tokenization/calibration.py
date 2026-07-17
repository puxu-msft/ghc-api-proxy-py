import math
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from itertools import pairwise
from typing import Any, cast

from app.transform.model_resolver import normalize_for_matching

BUCKET_BOUNDS = (0, 15_000, 30_000, 60_000, 120_000, 240_000, float("inf"))
WEIGHT_CAP = 2_000
FACTOR_CLAMP_MIN = 0.5
FACTOR_CLAMP_MAX = 3.0


@dataclass(slots=True)
class CalibrationBucket:
    sum_real: float = 0.0
    sum_estimated: float = 0.0
    sample_count: int = 0
    mean_estimated: float = 0.0

    @property
    def factor(self) -> float | None:
        if self.sample_count == 0 or self.sum_estimated <= 0:
            return None
        return min(
            FACTOR_CLAMP_MAX,
            max(FACTOR_CLAMP_MIN, self.sum_real / self.sum_estimated),
        )


@dataclass(slots=True)
class CalibrationModel:
    buckets: list[CalibrationBucket] = field(
        default_factory=lambda: [
            CalibrationBucket() for _ in range(len(BUCKET_BOUNDS) - 1)
        ]
    )


class CalibrationEngine:
    def __init__(self, *, on_change: Callable[[], None] | None = None) -> None:
        self._models: dict[tuple[str, str], CalibrationModel] = {}
        self._on_change = on_change

    @staticmethod
    def _key(protocol: str, model: str) -> tuple[str, str]:
        return protocol.lower(), normalize_for_matching(model)

    @staticmethod
    def bucket_index(estimate: int) -> int:
        for index, (lower, upper) in enumerate(pairwise(BUCKET_BOUNDS)):
            if lower <= estimate < upper:
                return index
        return len(BUCKET_BOUNDS) - 2

    def learn(self, protocol: str, model: str, estimate: int, real: int) -> bool:
        if estimate <= 0 or real <= 0:
            return False
        calibration = self._models.setdefault(self._key(protocol, model), CalibrationModel())
        bucket = calibration.buckets[self.bucket_index(estimate)]
        effective_weight = bucket.sample_count
        if effective_weight >= WEIGHT_CAP:
            decay = WEIGHT_CAP / (WEIGHT_CAP + 1)
            bucket.sum_real *= decay
            bucket.sum_estimated *= decay
        bucket.sum_real += real
        bucket.sum_estimated += estimate
        bounded_weight = min(effective_weight, WEIGHT_CAP)
        bucket.mean_estimated = (
            bucket.mean_estimated * bounded_weight + estimate
        ) / (bounded_weight + 1)
        bucket.sample_count = min(bucket.sample_count + 1, WEIGHT_CAP)
        if self._on_change is not None:
            self._on_change()
        return True

    def factor_at(self, protocol: str, model: str, estimate: int) -> float:
        calibration = self._models.get(self._key(protocol, model))
        if calibration is None:
            return 1.0
        anchors = [
            (bucket.mean_estimated, factor)
            for bucket in calibration.buckets
            if bucket.mean_estimated > 0 and (factor := bucket.factor) is not None
        ]
        if not anchors:
            return 1.0
        anchors.sort(key=lambda anchor: anchor[0])
        first = anchors[0]
        last = anchors[-1]
        if estimate <= first[0]:
            return first[1]
        if estimate >= last[0]:
            return last[1]
        for left, right in pairwise(anchors):
            if left[0] <= estimate <= right[0]:
                if left[0] == right[0]:
                    return right[1]
                ratio = (math.log(estimate) - math.log(left[0])) / (
                    math.log(right[0]) - math.log(left[0])
                )
                return left[1] + ratio * (right[1] - left[1])
        return last[1]

    def calibrate(self, protocol: str, model: str, estimate: int) -> int:
        return math.ceil(estimate * self.factor_at(protocol, model, estimate))

    def snapshot(self) -> dict[str, dict[str, Any]]:
        return {
            f"{protocol}:{model}": {
                "protocol": protocol,
                "model": model,
                "buckets": [asdict(bucket) for bucket in calibration.buckets],
            }
            for (protocol, model), calibration in sorted(self._models.items())
        }

    @classmethod
    def from_snapshot(
        cls,
        snapshot: dict[str, Any],
        *,
        on_change: Callable[[], None] | None = None,
    ) -> CalibrationEngine:
        engine = cls(on_change=on_change)
        for raw_value in snapshot.values():
            if not isinstance(raw_value, dict):
                continue
            value = cast(dict[str, Any], raw_value)
            protocol = value.get("protocol")
            model = value.get("model")
            raw_buckets: object = value.get("buckets")
            if not isinstance(protocol, str) or not isinstance(model, str):
                continue
            if not isinstance(raw_buckets, list):
                continue
            typed_buckets = cast(list[object], raw_buckets)
            if len(typed_buckets) != len(BUCKET_BOUNDS) - 1:
                continue
            buckets: list[CalibrationBucket] = []
            try:
                for raw_bucket in typed_buckets:
                    if not isinstance(raw_bucket, dict):
                        raise ValueError("calibration bucket must be an object")
                    bucket = cast(dict[str, Any], raw_bucket)
                    buckets.append(
                        CalibrationBucket(
                            sum_real=float(bucket["sum_real"]),
                            sum_estimated=float(bucket["sum_estimated"]),
                            sample_count=int(bucket["sample_count"]),
                            mean_estimated=float(bucket["mean_estimated"]),
                        )
                    )
            except (KeyError, TypeError, ValueError):
                continue
            engine._models[engine._key(protocol, model)] = CalibrationModel(buckets)
        return engine
