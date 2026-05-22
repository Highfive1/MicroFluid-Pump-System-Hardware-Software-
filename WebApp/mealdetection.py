from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional

from meal_detection_algo import SStarConfig, SStarStreamDetector, DEFAULT_CONFIG


DEFAULT_GLUCOSE_KEYS = (
    "cgm",
    "glucose",
    "bg",
    "blood_glucose",
    "cgm_mgdl",
    "glucose_mgdl",
    "cgm_value",
)


@dataclass
class MealEvent:
    device_id: str
    detected_at: datetime
    sstar: Optional[float]
    threshold: float


class MealDetectionService:
    """Manages meal detection per device.

    `app.py` supplies per-device live telemetry payloads; this service extracts
    glucose values, updates the online S** detector, and returns an event when a
    meal is detected.
    """

    def __init__(
        self,
        config: Optional[SStarConfig] = None,
        sampling_interval_min: float = 1.0,
        history_minutes: int = 240,
        cooldown_minutes: int = 60,
        glucose_keys: Iterable[str] = DEFAULT_GLUCOSE_KEYS,
    ) -> None:
        self._base_config = config or DEFAULT_CONFIG
        self._sampling_interval_min = float(sampling_interval_min)
        self._history_minutes = int(history_minutes)
        self._cooldown_minutes = int(cooldown_minutes)
        self._glucose_keys = tuple(glucose_keys)

        self._detectors: Dict[str, SStarStreamDetector] = {}

    def _get_detector(self, device_id: str) -> SStarStreamDetector:
        det = self._detectors.get(device_id)
        if det is None:
            det = SStarStreamDetector(
                config=self._base_config,
                sampling_interval_min=self._sampling_interval_min,
                history_minutes=self._history_minutes,
                cooldown_minutes=self._cooldown_minutes,
            )
            self._detectors[device_id] = det
        return det

    def extract_glucose(self, payload: Dict[str, Any]) -> Optional[float]:
        if not isinstance(payload, dict):
            return None

        # Prefer explicit keys; fall back to any key containing 'glucose' or 'cgm'.
        candidates = []
        for k in self._glucose_keys:
            if k in payload:
                candidates.append(k)

        if not candidates:
            for k in payload.keys():
                lk = str(k).lower()
                if "glucose" in lk or lk == "cgm" or "cgm" in lk:
                    candidates.append(k)

        for k in candidates:
            try:
                v = payload.get(k)
                if isinstance(v, bool):
                    continue
                f = float(v)
                if f != f:  # NaN
                    continue
                return f
            except Exception:
                continue
        return None

    def update(self, device_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Update detector for `device_id` with the latest telemetry payload."""
        g = self.extract_glucose(payload)
        if g is None:
            return {"detected": False, "reason": "no_glucose"}

        now = datetime.now(timezone.utc)
        det = self._get_detector(device_id)
        out = det.update(now, g)

        if out.get("detected"):
            ev = MealEvent(
                device_id=device_id,
                detected_at=now,
                sstar=out.get("sstar"),
                threshold=float(out.get("threshold", self._base_config.sstar_threshold)),
            )
            return {"detected": True, "event": ev, **out}

        return out
