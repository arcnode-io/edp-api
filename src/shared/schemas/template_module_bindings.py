"""Module-level bindings — act on other channels or a module's children,
never a south-side device directly. Split out of template_protocols for size.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator


class SyntheticBinding(BaseModel):
    """Gateway-side pure-function derivation from cached MQTT inputs.

    Synthetic channels do NOT poll a south-side device. Exactly one of two
    input-source modes applies:

    - `inputs`: a fixed list of topics. The gateway subscribes to each,
      caches latest values, ticks at the measurement's `poll_rate_hz`, and
      publishes the result of applying `operation`. Holds (no publish) until
      every input has at least one cached sample. Topic strings may contain
      `{site_id}` (gateway runtime), and `{device_id}` / `{poi_meter_device_id}`
      (ems-device-api AsyncAPI-gen substitution: the instantiating device, and
      the deployment's single poi_meter-templated device).
    - `source_measurement`: names a measurement projected across every child
      of the device this binding lives on. Resolving children into concrete
      topics is ems-device-api's job, not modeled here.

    `weighted_mean` (capacity_kwh-weighted, per DeviceTemplate.capacity_kwh
    on each child) is only meaningful across children, so it requires
    `source_measurement` mode. `subtract` is only ever between two fixed
    topics (e.g. envelope import limit minus POI power), so it requires `inputs`
    mode. `sum`/`mean`/`max`/`min` work in either mode. `unbalance` is
    100 * max|x - mean| / mean (NEMA MG-1 style, e.g. three phase voltages).

    `child_template` narrows `source_measurement` mode to children of that
    template — a module's children are mixed (pdu, gpu_node, cdu, ...), so the
    rollup declares which ones carry the measurement.
    """

    model_config = ConfigDict(extra="forbid")

    protocol: Literal["synthetic"]
    operation: Literal[
        "subtract", "sum", "mean", "max", "min", "weighted_mean", "unbalance"
    ]
    inputs: list[str] | None = None
    source_measurement: str | None = None
    child_template: str | None = None

    @model_validator(mode="after")
    def _inputs_xor_source_measurement(self) -> "SyntheticBinding":
        """Exactly one input-source mode; operation must match its mode."""
        has_inputs = self.inputs is not None
        has_source = self.source_measurement is not None
        if has_inputs == has_source:
            raise ValueError(
                "synthetic binding requires exactly one of `inputs:` (fixed "
                "topic list) or `source_measurement:` (projected across children)"
            )
        if self.operation == "weighted_mean" and not has_source:
            raise ValueError("operation=weighted_mean requires source_measurement mode")
        if self.operation == "subtract" and not has_inputs:
            raise ValueError("operation=subtract requires inputs mode")
        return self


class DistributeBinding(BaseModel):
    """Command-distribution binding — fans a module-level setpoint out to
    children per `allocation_policy`.

    No target-measurement field: verb + target are inherited from whichever
    Command this binding lives on, resolved per-child by ems-device-api
    matching verb+target against each child's own commands (not modeled here).

    The three envelope-guard fields are optional and all-or-nothing: a plain
    distribute binding (module setpoint fanout, no envelope guard) omits all
    three. When present, they carry the tunable control-law numbers for
    envelope-constrained actuation (ramp rate, hysteresis) — the concrete
    values live in ems-industrial-gateway's cfg.yml, not hardcoded; this
    schema just accepts the shape.
    """

    model_config = ConfigDict(extra="forbid")

    protocol: Literal["distribute"]
    allocation_policy: Literal["equal_split", "soc_weighted"]
    ramp_rate_per_sec: float | None = None
    hysteresis_margin: float | None = None
    hysteresis_dwell_secs: float | None = None

    @model_validator(mode="after")
    def _envelope_guard_all_or_nothing(self) -> "DistributeBinding":
        """The 3 envelope-guard fields must be all present or all absent."""
        fields = (
            self.ramp_rate_per_sec,
            self.hysteresis_margin,
            self.hysteresis_dwell_secs,
        )
        present = sum(f is not None for f in fields)
        if present not in (0, 3):
            raise ValueError(
                "distribute binding's envelope-guard fields (ramp_rate_per_sec, "
                "hysteresis_margin, hysteresis_dwell_secs) require all three or none"
            )
        return self


class PowerCapBinding(BaseModel):
    """Module-level percent cap fanned out to cap commands on its children.

    Every child of `child_template` gets each of `child_commands` set to
    pct/100 of that command's target-measurement bounds.max (clamped to
    bounds.min). Resolved into per-child entries by ems-device-api.

    The control-law tunables are required, unlike distribute's: whether the
    gateway sheds on its own is sizing_params.compute_shed_enabled, so a site
    that turns it on must never find them missing.
    """

    model_config = ConfigDict(extra="forbid")

    protocol: Literal["power_cap"]
    child_template: str
    child_commands: list[str]
    ramp_rate_per_sec: float
    hysteresis_margin: float
    hysteresis_dwell_secs: float
