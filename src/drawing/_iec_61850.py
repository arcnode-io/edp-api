"""IEC 61850 measurement-ref introspection used by the SLD HMI SVG generator.

Two concerns derived from `Measurement.iec_61850_ref` strings on templates:

1. Source-side identification for bus path direction (HMI animation contract):
       Walk bus.members in order; first member whose template carries a
       measurement with `iec_61850_ref="MMXU.W"` = source. Fallback = first.

2. Breaker / disconnect detection for SVG symbol emission:
       Template is a breaker if any measurement's `iec_61850_ref` starts with
       `XCBR.Pos.stVal` or `XSWI.Pos.stVal`. HMI swaps the inner geometry on
       state change; we emit the closed-state baseline.

Multi-source edge case for bus direction: first-listed source wins; refine to
largest-sizing pick when a real customer DTM forces the issue (PR note,
non-blocking per handoff).
"""

from src.shared.schemas.dtm import Bus, Dtm
from src.shared.schemas.template import DeviceTemplate

_SOURCE_IEC_REF = "MMXU.W"
_BREAKER_IEC_PREFIXES = ("XCBR.Pos.stVal", "XSWI.Pos.stVal")


def source_member_index(bus: Bus, dtm: Dtm) -> int:
    """Return the index in bus.members of the source-side device."""
    for i, member in enumerate(bus.members):
        device = dtm.devices[member.device_id]
        template = dtm.templates_used[device.template]
        for measurement in template.measurements.values():
            if measurement.iec_61850_ref == _SOURCE_IEC_REF:
                return i
    return 0


def is_breaker_template(template: DeviceTemplate) -> bool:
    """True if template's measurements declare a breaker / disconnect state."""
    for measurement in template.measurements.values():
        ref = measurement.iec_61850_ref
        if ref is not None and ref.startswith(_BREAKER_IEC_PREFIXES):
            return True
    return False
