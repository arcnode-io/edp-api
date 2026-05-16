"""Measurement range models: hard equipment bounds + alarm/warn thresholds.

Bounds = physical/equipment limits a device can possibly report.
Thresholds = warn + alarm trigger points used by EMS for alerting.

Both optional on Measurement; forbidden when measurement type=enum.
Cross-field rule (enforced on Measurement): thresholds must lie inside bounds —
an alarm outside the hardware reportable range is a dead alarm.
"""

from pydantic import BaseModel, ConfigDict, model_validator


class Bounds(BaseModel):
    """Operational range — hard physical/equipment limits + nominal operating value."""

    model_config = ConfigDict(extra="forbid")

    min: float
    max: float
    nominal: float

    @model_validator(mode="after")
    def _ordering(self) -> "Bounds":
        """min < max, and nominal ∈ [min, max]."""
        if self.min >= self.max:
            raise ValueError(f"bounds: min ({self.min}) must be < max ({self.max})")
        if not (self.min <= self.nominal <= self.max):
            raise ValueError(
                f"bounds: nominal ({self.nominal}) must lie within "
                f"[min={self.min}, max={self.max}]"
            )
        return self


class Thresholds(BaseModel):
    """Alarm + warning thresholds — warn band nested inside alarm band."""

    model_config = ConfigDict(extra="forbid")

    warn_min: float
    warn_max: float
    alarm_min: float
    alarm_max: float

    @model_validator(mode="after")
    def _ordering(self) -> "Thresholds":
        """alarm_min ≤ warn_min ≤ warn_max ≤ alarm_max."""
        if not (self.alarm_min <= self.warn_min <= self.warn_max <= self.alarm_max):
            raise ValueError(
                "thresholds must satisfy "
                f"alarm_min ({self.alarm_min}) ≤ warn_min ({self.warn_min}) ≤ "
                f"warn_max ({self.warn_max}) ≤ alarm_max ({self.alarm_max})"
            )
        return self


def check_thresholds_inside_bounds(
    bounds: Bounds | None, thresholds: Thresholds | None
) -> None:
    """Raise if alarm thresholds reach outside the physical bounds (dead alarm)."""
    if bounds is None or thresholds is None:
        return
    if thresholds.alarm_min < bounds.min:
        raise ValueError(
            f"alarm_min ({thresholds.alarm_min}) < bounds.min ({bounds.min}) — "
            "alarm unreachable"
        )
    if thresholds.alarm_max > bounds.max:
        raise ValueError(
            f"alarm_max ({thresholds.alarm_max}) > bounds.max ({bounds.max}) — "
            "alarm unreachable"
        )
