# PR 1 — edp-api Templates Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the templates layer in edp-api: Pydantic schema for device templates, a startup loader that walks `device_templates/`, and 18 template YAML files (15 leaf + 3 module) covering every current `equipment_id` plus the three module aggregations.

**Architecture:** Templates live as YAML files under `edp-api/device_templates/{leaf,module}/`. A Pydantic schema validates each file. A loader walks the directory at startup, validates every file, and panics on the first failure. The result is an in-process catalog keyed by template slug. No downstream consumer in this PR — `dtm_generator` is unaware until PR 2.

**Tech Stack:** Python 3.13, Pydantic v2, pytest, uv, ruff, ty. Existing patterns from `src/shared/schemas/dtm.py`.

**Reference:** `ems/docs/superpowers/specs/2026-05-09-redo-device-api-foundation-design.md` (sections "Template schema", "Templates — bundling and runtime", "Validation rules").

---

## Verification Gate (mandatory)

**After every small step, run:**

```bash
uv run poe checks && uv run poe unit
```

If either fails, fix before the next step. Do not chain steps. This applies to:
- Every step that writes/edits code or YAML
- Every step that runs a test
- Every commit step (the gate must pass *before* the commit)

`poe checks` runs depcheck + format + lint + typecheck + security. `poe unit` runs the colocated `src/**/test_*.py` suite. Integration tests (`poe integration`) run at task boundaries only — not per step.

When the spec already includes a per-step pytest invocation (e.g., `pytest -vv src/path/test.py::test_name -v`), that targeted run is in addition to the gate, not a substitute. Run the targeted test to confirm the specific behavior, then the gate to confirm nothing else regressed.

---

## File Structure

**Create:**
- `src/shared/schemas/template.py` — Pydantic models: `Binding`, `Measurement`, `Command`, `DeviceTemplate`, `TemplateKind`, `Publisher`, `Fanout`. ≤180 lines.
- `src/shared/schemas/test_template.py` — schema validation tests. AAA pattern.
- `src/dtm/template_loader.py` — `TemplateLoader` class with `load_catalog() -> dict[str, DeviceTemplate]`. ≤120 lines.
- `src/dtm/test_template_loader.py` — loader tests with tmp_path fixtures.
- `device_templates/leaf/revenue_meter.yaml` — worked example (ION9000 / GRD-MTR-001).
- `device_templates/leaf/switchgear.yaml` — GRD-SWG-001.
- `device_templates/leaf/protective_relay.yaml` — GRD-RLY-001.
- `device_templates/leaf/transformer.yaml` — GRD-XFM-001.
- `device_templates/leaf/pcs.yaml` — GRD-PCS-001.
- `device_templates/leaf/dnp3_master_external.yaml` — utility-master, no equipment_id, sentinel bindings.
- `device_templates/leaf/gpu_node.yaml` — CMP-NODE-001 (Redfish).
- `device_templates/leaf/cdu.yaml` — CMP-CDU-001 (Redfish).
- `device_templates/leaf/network_switch.yaml` — CMP-SWITCH-001 (Redfish).
- `device_templates/leaf/network_switch_spine.yaml` — CMP-SWITCH-002 (Redfish, distinct from ToR).
- `device_templates/leaf/pdu.yaml` — CMP-PDU-001 (SNMP).
- `device_templates/leaf/rack.yaml` — CMP-RACK-001 (passive — declares structural template only with `extra_measurements:` permitted but no own measurements/commands; per spec validation rule, must declare ≥1 of measurements/commands → see Task 5b for rack-specific decision).
- `device_templates/leaf/bess.yaml` — EXT-BESS-001 (Modbus or DNP3 — verify from current commercial-ac topology).
- `device_templates/leaf/bess_alt.yaml` — EXT-BESS-002 (alternative vendor; if same logical role, this conflicts with the "one canonical vendor per role" decision; see Task 5b).
- `device_templates/leaf/dc_external.yaml` — EXT-DC-001.
- `device_templates/leaf/dc_external_alt.yaml` — EXT-DC-002 (same conflict question).
- `device_templates/module/compute_module.yaml` — aggregation; rollups TBD per Task 6.
- `device_templates/module/grid_module.yaml` — aggregation; rollups TBD per Task 6.
- `device_templates/module/bess_module.yaml` — aggregation with `set_active_power` fanout command.

**Modify:**
- `src/main.py` — call `TemplateLoader().load_catalog()` at startup and store in app state. Process exits if load fails.

**Note on the EXT-BESS-001/002 and EXT-DC-001/002 conflict with "one canonical vendor per role":** During brainstorming we agreed multi-vendor is out of scope for MVP. If `EXT-BESS-001` and `EXT-BESS-002` represent two different vendor BESS units filling the same logical role, only one is selected per deployment via `hardware_selector_map.yaml`. **Task 5b resolves this by reading the hardware_selector map to confirm which is canonical for MVP and authoring only the canonical leaf template; the alternate template is deferred.** We may end up with 13 leaf templates instead of 15.

---

## Task 1: Pydantic Template Schema

**Files:**
- Create: `src/shared/schemas/template.py`
- Test: `src/shared/schemas/test_template.py`

- [ ] **Step 1: Write failing test for `TemplateKind` enum and basic imports**

```python
# src/shared/schemas/test_template.py
"""Device template schema unit tests."""

import pytest
from pydantic import ValidationError

from src.shared.schemas.template import (
    Binding,
    Command,
    DeviceTemplate,
    Fanout,
    Measurement,
    Publisher,
    TemplateKind,
)


def test_template_kind_values() -> None:
    # Arrange / Act / Assert
    assert TemplateKind.LEAF == "leaf"
    assert TemplateKind.MODULE == "module"


def test_publisher_values() -> None:
    # Arrange / Act / Assert
    assert Publisher.LINE_CONTROLLER == "line_controller"
    assert Publisher.ANALYST == "analyst"


def test_fanout_values() -> None:
    # Arrange / Act / Assert
    assert Fanout.LINE_CONTROLLER == "line_controller"
```

- [ ] **Step 2: Run test, expect ImportError**

Run: `uv run pytest -vv src/shared/schemas/test_template.py`
Expected: `ImportError: cannot import name 'TemplateKind' from 'src.shared.schemas.template'`

- [ ] **Step 3: Implement enums**

```python
# src/shared/schemas/template.py
"""Device template schema — canonical vocabulary per ADR-002 §7.

Templates own per-measurement protocol bindings (Modbus FC, DNP3 addrs,
SNMP OIDs). DTMs reference templates by slug; per-instance Devices contribute
deployment specifics (host, port, parent, display_name).
"""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator


class TemplateKind(StrEnum):
    """Leaf templates have equipment_id; modules are aggregations with contains."""

    LEAF = "leaf"
    MODULE = "module"


class Publisher(StrEnum):
    """Who publishes a measurement that has no protocol binding (rollups)."""

    LINE_CONTROLLER = "line_controller"
    ANALYST = "analyst"


class Fanout(StrEnum):
    """Who handles a command that has no direct binding (fans out to children)."""

    LINE_CONTROLLER = "line_controller"
```

- [ ] **Step 4: Run, expect pass**

Run: `uv run pytest -vv src/shared/schemas/test_template.py`
Expected: 3 passed.

- [ ] **Step 5: Add tests for Binding model**

```python
def test_binding_modbus_tcp() -> None:
    # Arrange / Act
    b = Binding(
        protocol="modbus_tcp",
        function_code=4,
        address=100,
        data_type="int16",
        scale=0.1,
    )
    # Assert
    assert b.protocol == "modbus_tcp"
    assert b.function_code == 4
    assert b.scale == 0.1


def test_binding_dnp3_tcp() -> None:
    # Arrange / Act
    b = Binding(protocol="dnp3_tcp", point_index=10, point_type="analog_input")
    # Assert
    assert b.protocol == "dnp3_tcp"


def test_binding_snmp() -> None:
    # Arrange / Act
    b = Binding(protocol="snmp", oid="1.3.6.1.4.1.1718.4.1.3.3.1.7")
    # Assert
    assert b.protocol == "snmp"


def test_binding_redfish() -> None:
    # Arrange / Act
    b = Binding(protocol="redfish", uri="/Chassis/1/Power", json_pointer="/PowerControl/0/PowerConsumedWatts")
    # Assert
    assert b.protocol == "redfish"
```

- [ ] **Step 6: Run, expect failures**

Run: `uv run pytest -vv src/shared/schemas/test_template.py -k binding`
Expected: 4 failures — `Binding` not defined.

- [ ] **Step 7: Implement Binding as a discriminated union**

Append to `src/shared/schemas/template.py`:

```python
class ModbusBinding(BaseModel):
    """Modbus TCP per-measurement register slot."""

    protocol: Literal["modbus_tcp"]
    function_code: int                       # 3=holding, 4=input, 6=write_single
    address: int
    data_type: Literal["int16", "uint16", "int32", "uint32", "float32"] = "int16"
    word_order: Literal["high_low", "low_high"] = "high_low"
    scale: float = 1.0
    offset: float = 0.0


class Dnp3Binding(BaseModel):
    """DNP3 per-measurement point reference."""

    protocol: Literal["dnp3_tcp"]
    point_index: int
    point_type: Literal["analog_input", "binary_input", "analog_output", "binary_output", "counter"]


class SnmpBinding(BaseModel):
    """SNMP per-measurement OID."""

    protocol: Literal["snmp"]
    oid: str


class RedfishBinding(BaseModel):
    """Redfish per-measurement resource path + JSON pointer."""

    protocol: Literal["redfish"]
    uri: str
    json_pointer: str | None = None


class CanopenBinding(BaseModel):
    """CANopen-over-Ethernet per-measurement PDO mapping."""

    protocol: Literal["canopen_gw"]
    cob_id: int
    byte_offset: int
    byte_length: int


Binding = Annotated[
    ModbusBinding | Dnp3Binding | SnmpBinding | RedfishBinding | CanopenBinding,
    Field(discriminator="protocol"),
]
```

- [ ] **Step 8: Run, expect pass**

Run: `uv run pytest -vv src/shared/schemas/test_template.py`
Expected: 7 passed.

- [ ] **Step 9: Add tests for Measurement and Command**

```python
def test_measurement_with_binding() -> None:
    # Arrange / Act
    m = Measurement(
        unit="volts",
        type="float",
        poll_rate_hz=1.0,
        binding={"protocol": "modbus_tcp", "function_code": 4, "address": 100},
    )
    # Assert
    assert m.unit == "volts"
    assert m.binding is not None
    assert m.publisher is None


def test_measurement_with_publisher() -> None:
    # Arrange / Act
    m = Measurement(unit="percent", type="float", publisher=Publisher.LINE_CONTROLLER)
    # Assert
    assert m.publisher == Publisher.LINE_CONTROLLER
    assert m.binding is None


def test_measurement_rejects_both_binding_and_publisher() -> None:
    # Arrange / Act / Assert
    with pytest.raises(ValidationError, match="exactly one of"):
        Measurement(
            unit="volts",
            type="float",
            binding={"protocol": "modbus_tcp", "function_code": 4, "address": 100},
            publisher=Publisher.LINE_CONTROLLER,
        )


def test_measurement_rejects_neither_binding_nor_publisher() -> None:
    # Arrange / Act / Assert
    with pytest.raises(ValidationError, match="exactly one of"):
        Measurement(unit="volts", type="float")


def test_measurement_enum_values() -> None:
    # Arrange / Act
    m = Measurement(
        unit="none",
        type="enum",
        values={1: "AUTO", 2: "MANUAL"},
        binding={"protocol": "modbus_tcp", "function_code": 3, "address": 200, "data_type": "uint16"},
    )
    # Assert
    assert m.values == {1: "AUTO", 2: "MANUAL"}


def test_command_with_binding() -> None:
    # Arrange / Act
    c = Command(
        verb="reset",
        target="counters",
        unit="none",
        payload="trigger",
        binding={"protocol": "modbus_tcp", "function_code": 6, "address": 300},
    )
    # Assert
    assert c.verb == "reset"


def test_command_with_fanout() -> None:
    # Arrange / Act
    c = Command(
        verb="set",
        target="active_power",
        unit="watts",
        payload="float",
        fanout=Fanout.LINE_CONTROLLER,
    )
    # Assert
    assert c.fanout == Fanout.LINE_CONTROLLER
    assert c.binding is None


def test_command_rejects_both_binding_and_fanout() -> None:
    # Arrange / Act / Assert
    with pytest.raises(ValidationError, match="exactly one of"):
        Command(
            verb="set",
            target="active_power",
            unit="watts",
            payload="float",
            binding={"protocol": "modbus_tcp", "function_code": 6, "address": 400},
            fanout=Fanout.LINE_CONTROLLER,
        )
```

- [ ] **Step 10: Run, expect failures**

Run: `uv run pytest -vv src/shared/schemas/test_template.py -k "measurement or command"`
Expected: 8 failures — `Measurement` / `Command` not defined.

- [ ] **Step 11: Implement Measurement and Command**

Append:

```python
class Measurement(BaseModel):
    """One channel a device emits. Either bound to a protocol or
    published by line-controller/analyst."""

    unit: str                                # ADR-002 §3 enum-locked vocabulary
    type: Literal["float", "bool", "enum"]
    poll_rate_hz: float | None = None
    display_name_default: str | None = None
    iec_61850_ref: str | None = None
    values: dict[int, str] | None = None     # required for type=enum
    binding: Binding | None = None
    publisher: Publisher | None = None

    @model_validator(mode="after")
    def exactly_one_source(self) -> "Measurement":
        """Each measurement MUST have exactly one of binding or publisher."""
        has_binding = self.binding is not None
        has_publisher = self.publisher is not None
        if has_binding == has_publisher:
            raise ValueError(
                "measurement requires exactly one of `binding:` (gateway-bound) "
                "or `publisher:` (derived/rollup)"
            )
        return self


class Command(BaseModel):
    """One channel a device receives. Either bound to a protocol or
    fanned out by line-controller."""

    verb: Literal["set", "reset", "clear", "start", "stop", "enable", "disable"]
    target: str
    unit: str
    payload: Literal["float", "bool", "enum", "trigger"]
    display_name_default: str | None = None
    binding: Binding | None = None
    fanout: Fanout | None = None

    @model_validator(mode="after")
    def exactly_one_source(self) -> "Command":
        """Each command MUST have exactly one of binding or fanout."""
        has_binding = self.binding is not None
        has_fanout = self.fanout is not None
        if has_binding == has_fanout:
            raise ValueError(
                "command requires exactly one of `binding:` (gateway-bound) "
                "or `fanout:` (line-controller-handled)"
            )
        return self
```

- [ ] **Step 12: Run, expect pass**

Run: `uv run pytest -vv src/shared/schemas/test_template.py`
Expected: 15 passed.

- [ ] **Step 13: Add tests for DeviceTemplate kind=leaf and kind=module**

```python
def _modbus_binding_dict() -> dict:
    return {"protocol": "modbus_tcp", "function_code": 4, "address": 100}


def test_device_template_leaf_minimal() -> None:
    # Arrange / Act
    t = DeviceTemplate(
        template="revenue_meter",
        kind=TemplateKind.LEAF,
        equipment_id="GRD-MTR-001",
        vendor="Schneider Electric",
        model="ION9000",
        description="test",
        contains=[],
        measurements={
            "voltage_a": Measurement(
                unit="volts", type="float", binding=_modbus_binding_dict()
            )
        },
    )
    # Assert
    assert t.kind == TemplateKind.LEAF
    assert t.equipment_id == "GRD-MTR-001"


def test_device_template_module_minimal() -> None:
    # Arrange / Act
    t = DeviceTemplate(
        template="bess_module",
        kind=TemplateKind.MODULE,
        description="BESS module aggregation",
        contains=[{"template": "bess_rack", "qty": "scalable"}],
        measurements={
            "state_of_charge": Measurement(
                unit="percent", type="float", publisher=Publisher.LINE_CONTROLLER
            )
        },
    )
    # Assert
    assert t.kind == TemplateKind.MODULE
    assert t.equipment_id is None
    assert t.contains[0].template == "bess_rack"


def test_device_template_leaf_requires_equipment_id() -> None:
    # Arrange / Act / Assert
    with pytest.raises(ValidationError, match="equipment_id required"):
        DeviceTemplate(
            template="revenue_meter",
            kind=TemplateKind.LEAF,
            equipment_id=None,
            description="test",
            measurements={
                "v": Measurement(
                    unit="volts", type="float", binding=_modbus_binding_dict()
                )
            },
        )


def test_device_template_module_rejects_equipment_id() -> None:
    # Arrange / Act / Assert
    with pytest.raises(ValidationError, match="equipment_id forbidden"):
        DeviceTemplate(
            template="bess_module",
            kind=TemplateKind.MODULE,
            equipment_id="GRD-MTR-001",
            description="test",
            contains=[],
            measurements={
                "soc": Measurement(
                    unit="percent", type="float", publisher=Publisher.LINE_CONTROLLER
                )
            },
        )


def test_device_template_must_declare_measurements_or_commands() -> None:
    # Arrange / Act / Assert
    with pytest.raises(ValidationError, match="must declare at least one"):
        DeviceTemplate(
            template="empty",
            kind=TemplateKind.LEAF,
            equipment_id="GRD-MTR-001",
            description="test",
        )


def test_template_slug_format_rejected() -> None:
    # Arrange / Act / Assert
    with pytest.raises(ValidationError, match="slug"):
        DeviceTemplate(
            template="Revenue-Meter",     # uppercase + dash → invalid
            kind=TemplateKind.LEAF,
            equipment_id="GRD-MTR-001",
            description="test",
            measurements={
                "v": Measurement(
                    unit="volts", type="float", binding=_modbus_binding_dict()
                )
            },
        )
```

- [ ] **Step 14: Run, expect failures**

Run: `uv run pytest -vv src/shared/schemas/test_template.py -k device_template`
Expected: 6 failures — `DeviceTemplate` and `ContainsEntry` not defined.

- [ ] **Step 15: Implement DeviceTemplate and ContainsEntry**

Append:

```python
import re

_SLUG_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}[a-z0-9]$")


class ContainsEntry(BaseModel):
    """Reference to a child template inside a module's contains[]."""

    template: str
    qty: Literal["scalable"] | int = "scalable"


class DeviceTemplate(BaseModel):
    """One device template — leaf (1:1 with equipment_id) or module (aggregation)."""

    template: str                            # ADR-002 §9 slug
    kind: TemplateKind
    equipment_id: str | None = None
    vendor: str | None = None
    model: str | None = None
    description: str
    contains: list[ContainsEntry] = Field(default_factory=list)
    measurements: dict[str, Measurement] = Field(default_factory=dict)
    commands: dict[str, Command] = Field(default_factory=dict)

    @model_validator(mode="after")
    def slug_format(self) -> "DeviceTemplate":
        """Template name must be a snake_case slug per ADR-002 §9."""
        if not _SLUG_RE.match(self.template):
            raise ValueError(f"template slug {self.template!r} must match {_SLUG_RE.pattern}")
        return self

    @model_validator(mode="after")
    def equipment_id_matches_kind(self) -> "DeviceTemplate":
        """Leaves require equipment_id; modules forbid it."""
        if self.kind == TemplateKind.LEAF and self.equipment_id is None:
            raise ValueError(f"template {self.template!r}: equipment_id required for kind=leaf")
        if self.kind == TemplateKind.MODULE and self.equipment_id is not None:
            raise ValueError(f"template {self.template!r}: equipment_id forbidden for kind=module")
        return self

    @model_validator(mode="after")
    def must_have_channels(self) -> "DeviceTemplate":
        """Every template must declare at least one of measurements/commands."""
        if not self.measurements and not self.commands:
            raise ValueError(
                f"template {self.template!r} must declare at least one of "
                "measurements: or commands:"
            )
        return self
```

- [ ] **Step 16: Run, expect pass**

Run: `uv run pytest -vv src/shared/schemas/test_template.py`
Expected: 21 passed.

- [ ] **Step 17: Run full edp-api checks**

Run: `uv run poe checks`
Expected: All checks passed.

- [ ] **Step 18: Commit**

```bash
git add src/shared/schemas/template.py src/shared/schemas/test_template.py
git commit -m "$(cat <<'EOF'
✨ feat: device template Pydantic schema

Adds Binding (discriminated union over modbus_tcp/dnp3_tcp/snmp/redfish/
canopen_gw), Measurement, Command, ContainsEntry, and DeviceTemplate per
ADR-002 §7. Validation rules: slug format per §9, equipment_id presence
matches kind=leaf/module, every template declares at least one channel,
each measurement/command has exactly one of binding/publisher (or
binding/fanout for commands).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Template Loader

**Files:**
- Create: `src/dtm/template_loader.py`
- Test: `src/dtm/test_template_loader.py`

- [ ] **Step 1: Write failing test for empty directory**

```python
# src/dtm/test_template_loader.py
"""TemplateLoader unit tests using tmp_path fixtures."""

from pathlib import Path

import pytest

from src.dtm.template_loader import TemplateLoader, TemplateLoadError


def test_load_catalog_empty_dir(tmp_path: Path) -> None:
    # Arrange
    (tmp_path / "leaf").mkdir()
    (tmp_path / "module").mkdir()
    loader = TemplateLoader(root=tmp_path)
    # Act
    catalog = loader.load_catalog()
    # Assert
    assert catalog == {}
```

- [ ] **Step 2: Run, expect ImportError**

Run: `uv run pytest -vv src/dtm/test_template_loader.py`
Expected: ImportError — `TemplateLoader` not defined.

- [ ] **Step 3: Implement minimal loader**

```python
# src/dtm/template_loader.py
"""TemplateLoader — walks device_templates/, validates, builds catalog.

Per the foundation design spec (2026-05-09): edp-api walks its
device_templates/ at startup, validates every YAML, and panics on the
first failure. Catalog is keyed by template slug.
"""

import logging
from pathlib import Path

import yaml
from pydantic import ValidationError

from src.shared.schemas.template import DeviceTemplate

logger = logging.getLogger(__name__)


class TemplateLoadError(Exception):
    """Raised when a template file fails to parse or validate."""


class TemplateLoader:
    """Walks `<root>/{leaf,module}/*.yaml`, validates each, returns catalog."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def load_catalog(self) -> dict[str, DeviceTemplate]:
        """Return catalog keyed by template slug. Raises on first failure."""
        catalog: dict[str, DeviceTemplate] = {}
        for kind_dir in ("leaf", "module"):
            sub = self._root / kind_dir
            if not sub.is_dir():
                continue
            for path in sorted(sub.glob("*.yaml")):
                tpl = self._load_file(path)
                if tpl.template in catalog:
                    raise TemplateLoadError(
                        f"duplicate template slug {tpl.template!r}: "
                        f"{path} conflicts with prior file"
                    )
                catalog[tpl.template] = tpl
        return catalog

    @staticmethod
    def _load_file(path: Path) -> DeviceTemplate:
        try:
            raw = yaml.safe_load(path.read_text())
        except yaml.YAMLError as e:
            raise TemplateLoadError(f"{path}: invalid YAML: {e}") from e
        try:
            return DeviceTemplate.model_validate(raw)
        except ValidationError as e:
            raise TemplateLoadError(f"{path}: schema validation failed:\n{e}") from e
```

- [ ] **Step 4: Run, expect pass**

Run: `uv run pytest -vv src/dtm/test_template_loader.py::test_load_catalog_empty_dir`
Expected: 1 passed.

- [ ] **Step 5: Add tests for happy path with one leaf, validation failure, duplicate slug**

```python
def _write_revenue_meter(dir_: Path) -> None:
    (dir_ / "revenue_meter.yaml").write_text(
        """
template: revenue_meter
kind: leaf
equipment_id: GRD-MTR-001
vendor: Schneider Electric
model: ION9000
description: test
measurements:
  voltage_a:
    unit: volts
    type: float
    binding:
      protocol: modbus_tcp
      function_code: 4
      address: 100
""".lstrip()
    )


def test_load_catalog_loads_one_leaf(tmp_path: Path) -> None:
    # Arrange
    (tmp_path / "leaf").mkdir()
    (tmp_path / "module").mkdir()
    _write_revenue_meter(tmp_path / "leaf")
    loader = TemplateLoader(root=tmp_path)
    # Act
    catalog = loader.load_catalog()
    # Assert
    assert "revenue_meter" in catalog
    assert catalog["revenue_meter"].equipment_id == "GRD-MTR-001"


def test_load_catalog_raises_on_invalid_yaml(tmp_path: Path) -> None:
    # Arrange
    (tmp_path / "leaf").mkdir()
    (tmp_path / "module").mkdir()
    (tmp_path / "leaf" / "broken.yaml").write_text("template: : :\n")
    loader = TemplateLoader(root=tmp_path)
    # Act / Assert
    with pytest.raises(TemplateLoadError, match="invalid YAML"):
        loader.load_catalog()


def test_load_catalog_raises_on_validation_failure(tmp_path: Path) -> None:
    # Arrange — leaf with no measurements/commands
    (tmp_path / "leaf").mkdir()
    (tmp_path / "module").mkdir()
    (tmp_path / "leaf" / "bad.yaml").write_text(
        """
template: empty
kind: leaf
equipment_id: GRD-MTR-001
description: empty
""".lstrip()
    )
    loader = TemplateLoader(root=tmp_path)
    # Act / Assert
    with pytest.raises(TemplateLoadError, match="schema validation failed"):
        loader.load_catalog()


def test_load_catalog_rejects_duplicate_slug(tmp_path: Path) -> None:
    # Arrange — same slug under leaf/ and module/ would conflict if a real module
    # used the slug; we simulate via two leaf files claiming the same slug
    (tmp_path / "leaf").mkdir()
    (tmp_path / "module").mkdir()
    _write_revenue_meter(tmp_path / "leaf")
    (tmp_path / "leaf" / "revenue_meter_dup.yaml").write_text(
        """
template: revenue_meter
kind: leaf
equipment_id: GRD-MTR-001
description: dup
measurements:
  v:
    unit: volts
    type: float
    binding: { protocol: modbus_tcp, function_code: 4, address: 100 }
""".lstrip()
    )
    loader = TemplateLoader(root=tmp_path)
    # Act / Assert
    with pytest.raises(TemplateLoadError, match="duplicate template slug"):
        loader.load_catalog()
```

- [ ] **Step 6: Run, expect pass**

Run: `uv run pytest -vv src/dtm/test_template_loader.py`
Expected: 5 passed.

- [ ] **Step 7: Run full checks**

Run: `uv run poe checks`
Expected: All checks passed.

- [ ] **Step 8: Commit**

```bash
git add src/dtm/template_loader.py src/dtm/test_template_loader.py
git commit -m "$(cat <<'EOF'
✨ feat: template_loader walks device_templates/ at startup

Walks <root>/{leaf,module}/*.yaml, parses with PyYAML, validates each
file against DeviceTemplate, and builds an in-process catalog keyed by
template slug. Raises TemplateLoadError on invalid YAML, schema
validation failure, or duplicate slug — fail-fast at startup so drift
surfaces before any DTM emit.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Worked-Example Leaf Template — `revenue_meter`

Authoring methodology applies to all subsequent leaf templates.

**Files:**
- Create: `device_templates/leaf/revenue_meter.yaml`
- Test: `src/dtm/test_template_loader.py` (extend with a real-catalog test)

- [ ] **Step 1: Read the equipment spec and existing topology binding**

Read `/home/resister/arcnode/edp-module-assemblies/equipment/GRD-MTR-001/spec.yaml` for vendor metadata. Read the `revenue_meter` entry in `assemblies/grid-container/commercial-ac/topology.yaml` for the current Modbus binding (unit_id=2, register addresses).

The current topology had `unit_id: 2` (per-instance, lives on Device.connection in DTM, not in the template) and `point_maps` with names like `kwh_delivered`, `kwh_received`, `power_factor`, `thd_voltage`. These become measurements in the template.

- [ ] **Step 2: Author the template file**

Create `device_templates/leaf/revenue_meter.yaml`:

```yaml
template: revenue_meter
kind: leaf
equipment_id: GRD-MTR-001
vendor: Schneider Electric
model: PowerLogic ION9000
description: Class 0.1S revenue meter (ANSI C12.20 / IEC 62053-22)

measurements:
  kwh_delivered:
    unit: watt_hours
    type: float
    poll_rate_hz: 0.1
    display_name_default: "Energy Delivered"
    binding:
      protocol: modbus_tcp
      function_code: 3
      address: 4000
      data_type: int32
      word_order: high_low
      scale: 1.0
      offset: 0.0

  kwh_received:
    unit: watt_hours
    type: float
    poll_rate_hz: 0.1
    display_name_default: "Energy Received"
    binding:
      protocol: modbus_tcp
      function_code: 3
      address: 4002
      data_type: int32
      word_order: high_low

  power_factor:
    unit: none
    type: float
    poll_rate_hz: 1
    display_name_default: "Power Factor"
    binding:
      protocol: modbus_tcp
      function_code: 3
      address: 4010
      data_type: int16
      scale: 0.001

  thd_voltage_a:
    unit: percent
    type: float
    poll_rate_hz: 0.5
    display_name_default: "THD Voltage Phase A"
    binding:
      protocol: modbus_tcp
      function_code: 3
      address: 4020
      data_type: int16
      scale: 0.01

  thd_voltage_b:
    unit: percent
    type: float
    poll_rate_hz: 0.5
    display_name_default: "THD Voltage Phase B"
    binding:
      protocol: modbus_tcp
      function_code: 3
      address: 4021
      data_type: int16
      scale: 0.01

  thd_voltage_c:
    unit: percent
    type: float
    poll_rate_hz: 0.5
    display_name_default: "THD Voltage Phase C"
    binding:
      protocol: modbus_tcp
      function_code: 3
      address: 4022
      data_type: int16
      scale: 0.01
```

- [ ] **Step 3: Add a real-catalog test**

In `src/dtm/test_template_loader.py`, append:

```python
def test_load_real_catalog_includes_revenue_meter() -> None:
    # Arrange — real device_templates/ at repo root
    repo_root = Path(__file__).resolve().parents[2]
    loader = TemplateLoader(root=repo_root / "device_templates")
    # Act
    catalog = loader.load_catalog()
    # Assert
    assert "revenue_meter" in catalog
    rm = catalog["revenue_meter"]
    assert rm.equipment_id == "GRD-MTR-001"
    assert "kwh_delivered" in rm.measurements
```

- [ ] **Step 4: Run, expect pass**

Run: `uv run pytest -vv src/dtm/test_template_loader.py::test_load_real_catalog_includes_revenue_meter`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add device_templates/leaf/revenue_meter.yaml src/dtm/test_template_loader.py
git commit -m "$(cat <<'EOF'
✨ feat: revenue_meter leaf template (ION9000)

Worked example for the device_templates/leaf/ catalog. Maps to
GRD-MTR-001. Measurements cover kwh_delivered/received, power_factor,
and per-phase THD voltage from the ION9000 Modbus register map. Sets
the pattern for the remaining 14 leaf templates.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Worked-Example Module Template — `bess_module`

**Files:**
- Create: `device_templates/module/bess_module.yaml`

- [ ] **Step 1: Author the template file**

Create `device_templates/module/bess_module.yaml`:

```yaml
template: bess_module
kind: module
description: BESS module aggregation — published rollups + setpoint fanout

contains:
  - template: bess_rack
    qty: scalable

measurements:
  state_of_charge:
    unit: percent
    type: float
    poll_rate_hz: 1
    display_name_default: "Module State of Charge"
    publisher: line_controller

  active_power:
    unit: watts
    type: float
    poll_rate_hz: 1
    display_name_default: "Module Active Power"
    publisher: line_controller

  reactive_power:
    unit: vars
    type: float
    poll_rate_hz: 1
    display_name_default: "Module Reactive Power"
    publisher: line_controller

commands:
  set_active_power:
    verb: set
    target: active_power
    unit: watts
    payload: float
    display_name_default: "Set Active Power"
    fanout: line_controller

  set_reactive_power:
    verb: set
    target: reactive_power
    unit: vars
    payload: float
    fanout: line_controller
```

- [ ] **Step 2: Add a catalog test**

In `src/dtm/test_template_loader.py`, append:

```python
def test_load_real_catalog_includes_bess_module() -> None:
    # Arrange
    repo_root = Path(__file__).resolve().parents[2]
    loader = TemplateLoader(root=repo_root / "device_templates")
    # Act
    catalog = loader.load_catalog()
    # Assert
    assert "bess_module" in catalog
    m = catalog["bess_module"]
    assert m.kind.value == "module"
    assert m.equipment_id is None
    assert m.contains[0].template == "bess_rack"
    assert m.measurements["state_of_charge"].publisher.value == "line_controller"
    assert m.commands["set_active_power"].fanout.value == "line_controller"
```

- [ ] **Step 3: Run, expect pass**

Run: `uv run pytest -vv src/dtm/test_template_loader.py::test_load_real_catalog_includes_bess_module`
Expected: 1 passed.

- [ ] **Step 4: Commit**

```bash
git add device_templates/module/bess_module.yaml src/dtm/test_template_loader.py
git commit -m "$(cat <<'EOF'
✨ feat: bess_module template with line_controller fanout

Worked module-template example. Declares scalable bess_rack children,
three rollup measurements (state_of_charge, active_power,
reactive_power) published by line-controller, and two setpoint
commands fanned out to children by line-controller. No protocol
binding on either side — module aggregations don't talk directly to
hardware.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Author Remaining Leaf Templates

This task batches the remaining leaf-template authoring. Each follows the methodology from Task 3.

**For each template:**
1. Read `equipment/<id>/spec.yaml` for vendor metadata.
2. Read the matching device entry in current `assemblies/.../commercial-ac/topology.yaml` for the per-instance protocol_config block — use that to populate the template's `binding:` blocks.
3. Author `device_templates/leaf/<slug>.yaml` matching the Task 3 shape.
4. Verify it loads via `uv run pytest -vv src/dtm/test_template_loader.py::test_load_real_catalog_full_count` (added in Task 8).

**Mapping — equipment_id ↔ template slug ↔ source topology binding:**

| equipment_id | template slug | protocol | binding source |
|---|---|---|---|
| GRD-MTR-001 | revenue_meter | modbus_tcp | done in Task 3 |
| GRD-SWG-001 | switchgear | modbus_tcp | grid-container/commercial-ac/topology.yaml device #1 (unit_id=1) |
| GRD-RLY-001 | protective_relay | dnp3_tcp | grid-container/commercial-ac/topology.yaml device #2 (master=1, outstation=100) |
| GRD-XFM-001 | transformer | (passive in topology — no protocol; declare commands-only or skip) | n/a — see Task 5b |
| GRD-PCS-001 | pcs | (TBD — not in current commercial-ac topology since AC profile excludes PCS) | hardware_selector / EPC PD500 datasheet |
| GRD-* (no equipment_id) | dnp3_master_external | dnp3_tcp | grid-container/commercial-ac/topology.yaml device #4 (PROVISIONED_AT_COMMISSIONING placeholders → measurements use sentinel-tolerant binding values; or template declares the channels and per-instance Device.connection holds the addresses) |
| CMP-NODE-001 | gpu_node | redfish | compute-container/commercial-ac/topology.yaml |
| CMP-CDU-001 | cdu | redfish | compute-container/commercial-ac/topology.yaml |
| CMP-SWITCH-001 | network_switch | redfish | compute-container/commercial-ac/topology.yaml |
| CMP-SWITCH-002 | network_switch_spine | redfish | TBD — not in current commercial-ac topology |
| CMP-PDU-001 | pdu | snmp | compute-container/commercial-ac/topology.yaml |
| CMP-RACK-001 | rack | n/a (passive) | see Task 5b |
| EXT-BESS-001 / 002 | bess | TBD | see Task 5b |
| EXT-DC-001 / 002 | dc_external | TBD | see Task 5b |

- [ ] **Step 5a: Author the four directly-mappable grid + compute leaves**

Author these four templates using the topology.yaml binding info already on disk:
- `device_templates/leaf/switchgear.yaml`
- `device_templates/leaf/protective_relay.yaml`
- `device_templates/leaf/gpu_node.yaml`
- `device_templates/leaf/cdu.yaml`
- `device_templates/leaf/network_switch.yaml`
- `device_templates/leaf/pdu.yaml`
- `device_templates/leaf/dnp3_master_external.yaml`

For each, replicate the Task 3 shape. For `dnp3_master_external`, use abstract measurements (e.g. `breaker_status`, `tap_position`) with binding `point_index` placeholders; the per-instance Device.connection carries the real addresses set at commissioning.

For the rack template (`CMP-RACK-001`), declare a single `extra_measurements_only: true` flag — actually wait, that field doesn't exist. Per the schema, every template must declare ≥1 of measurements/commands. Rack is passive in topology (no protocol). Resolution: either (a) skip CMP-RACK-001 entirely from PR 1 templates (rack is not a published device), or (b) author a minimal rack template with one structural measurement like `populated_slots` published by line_controller. Pick (a) — skip rack. Document in the PR description.

- [ ] **Step 5b: Resolve unmapped equipment_ids**

For each of the following, decide and document in the PR description:

- **GRD-XFM-001 (Trihal transformer):** Passive — no protocol per spec. Skip from PR 1; not in current topology.yaml either.
- **GRD-PCS-001 (EPC PD500):** Not in commercial-ac topology (it's commercial-dc-ext only). Skip from PR 1; author when commercial-dc-ext gets its topology.yaml.
- **CMP-SWITCH-002 (spine):** Not in current commercial-ac topology. Skip from PR 1.
- **CMP-RACK-001:** Skip per Step 5a discussion (passive, no protocol).
- **EXT-BESS-001 / EXT-BESS-002:** Read `hardware_selector_map.yaml` to determine the canonical MVP vendor. Author one `bess` template for that vendor. Skip the alternate.
- **EXT-DC-001 / EXT-DC-002:** Same — author one `dc_external` template, skip the alternate.

The actual leaf templates landing in PR 1: 7 templates from Step 5a + revenue_meter from Task 3 + 1 bess + 1 dc_external = **10 leaf templates total**, not 15. The other 5 equipment_ids are deferred.

Update the spec's "What edp-api looks like after migration" section in a follow-up doc-only commit, or accept the discrepancy and note in the PR description.

- [ ] **Step 5c: Add a count assertion test**

In `src/dtm/test_template_loader.py`, append:

```python
def test_load_real_catalog_full_count() -> None:
    # Arrange
    repo_root = Path(__file__).resolve().parents[2]
    loader = TemplateLoader(root=repo_root / "device_templates")
    # Act
    catalog = loader.load_catalog()
    # Assert — 10 leaves + 3 modules expected for PR 1 scope
    leaf_count = sum(1 for t in catalog.values() if t.kind.value == "leaf")
    module_count = sum(1 for t in catalog.values() if t.kind.value == "module")
    assert leaf_count == 10
    assert module_count == 3
```

- [ ] **Step 5d: Run all tests**

Run: `uv run pytest -vv src/dtm/test_template_loader.py`
Expected: all pass.

- [ ] **Step 5e: Commit**

```bash
git add device_templates/leaf/ src/dtm/test_template_loader.py
git commit -m "$(cat <<'EOF'
✨ feat: 9 additional leaf templates (grid + compute + bess + dc)

Authors switchgear, protective_relay, gpu_node, cdu, network_switch,
pdu, dnp3_master_external, bess, dc_external. Bindings transposed
from current commercial-ac topology.yamls. Five equipment_ids deferred
from PR 1 scope (transformer, pcs, switch_spine, rack, alternate
bess/dc vendor) — see PR description.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Author Remaining Module Templates

**Files:**
- Create: `device_templates/module/compute_module.yaml`
- Create: `device_templates/module/grid_module.yaml`

- [ ] **Step 1: Author compute_module**

Create `device_templates/module/compute_module.yaml`:

```yaml
template: compute_module
kind: module
description: Compute container aggregation — utilization rollups

contains:
  - template: gpu_node
    qty: scalable
  - template: cdu
    qty: 1
  - template: network_switch
    qty: scalable
  - template: pdu
    qty: scalable

measurements:
  total_power:
    unit: watts
    type: float
    poll_rate_hz: 1
    display_name_default: "Module Total Power"
    publisher: line_controller

  total_thermal_load:
    unit: watts
    type: float
    poll_rate_hz: 1
    display_name_default: "Module Thermal Load"
    publisher: line_controller

  pue:
    unit: none
    type: float
    poll_rate_hz: 0.1
    display_name_default: "Power Usage Effectiveness"
    publisher: analyst
```

- [ ] **Step 2: Author grid_module**

Create `device_templates/module/grid_module.yaml`:

```yaml
template: grid_module
kind: module
description: Grid container aggregation — interconnect rollups

contains:
  - template: switchgear
    qty: 1
  - template: revenue_meter
    qty: 1
  - template: protective_relay
    qty: 1
  - template: dnp3_master_external
    qty: 1

measurements:
  net_active_power:
    unit: watts
    type: float
    poll_rate_hz: 1
    display_name_default: "Net Active Power"
    publisher: line_controller

  grid_frequency:
    unit: hertz
    type: float
    poll_rate_hz: 10
    display_name_default: "Grid Frequency"
    publisher: line_controller

  interconnect_state:
    unit: none
    type: enum
    values: { 0: OPEN, 1: CLOSED, 2: TRIPPED }
    publisher: line_controller
```

- [ ] **Step 3: Add tests**

In `src/dtm/test_template_loader.py`, append:

```python
def test_load_real_catalog_includes_compute_and_grid_modules() -> None:
    # Arrange
    repo_root = Path(__file__).resolve().parents[2]
    loader = TemplateLoader(root=repo_root / "device_templates")
    # Act
    catalog = loader.load_catalog()
    # Assert
    assert "compute_module" in catalog
    assert "grid_module" in catalog
    cm = catalog["compute_module"]
    gm = catalog["grid_module"]
    assert cm.kind.value == "module"
    assert gm.kind.value == "module"
    assert any(c.template == "gpu_node" for c in cm.contains)
    assert any(c.template == "switchgear" for c in gm.contains)
```

- [ ] **Step 4: Run, expect pass**

Run: `uv run pytest -vv src/dtm/test_template_loader.py`
Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add device_templates/module/compute_module.yaml device_templates/module/grid_module.yaml src/dtm/test_template_loader.py
git commit -m "$(cat <<'EOF'
✨ feat: compute_module + grid_module aggregation templates

compute_module: contains gpu_node (scalable), cdu (1), network_switch
(scalable), pdu (scalable). Rollups for total_power, total_thermal_load
(line_controller); pue (analyst). grid_module: contains switchgear,
revenue_meter, protective_relay, dnp3_master_external (each qty=1).
Rollups net_active_power, grid_frequency, interconnect_state enum.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Wire Startup Validation in main.py

**Files:**
- Modify: `src/main.py`

- [ ] **Step 1: Read current main.py to find startup hook**

Run: `cat src/main.py`

Identify where app startup happens (typically `lifespan` context manager or `@app.on_event("startup")` for FastAPI).

- [ ] **Step 2: Add template loader call**

Modify `src/main.py` to call `TemplateLoader(root=Path("device_templates")).load_catalog()` during startup. Store the catalog on `app.state.template_catalog`. If load raises, let it propagate — process exits, ASGI server fails to start, container restarts in a loop until templates are fixed.

Specifically, locate the startup section and add:

```python
from pathlib import Path

from src.dtm.template_loader import TemplateLoader

# ... existing code ...

# inside startup hook
catalog = TemplateLoader(root=Path("device_templates")).load_catalog()
logger.info(f"loaded {len(catalog)} device templates: {sorted(catalog)}")
app.state.template_catalog = catalog
```

If `src/main.py` exceeds 200 lines after the change, refactor by moving startup config into `src/startup.py` (one-line file budget split is acceptable per CLAUDE.md).

- [ ] **Step 3: Add a smoke test that boots the app**

In `tests/test_app.py` (or wherever the existing app boot test lives), add:

```python
def test_app_startup_loads_template_catalog(client) -> None:
    # Arrange — client fixture starts the app
    # Act / Assert — catalog attribute exists and is non-empty
    assert hasattr(client.app.state, "template_catalog")
    assert len(client.app.state.template_catalog) >= 13  # 10 leaf + 3 module
```

- [ ] **Step 4: Run, expect pass**

Run: `uv run pytest -vv tests/test_app.py`
Expected: passes.

- [ ] **Step 5: Run full unit + integration tests**

Run: `uv run poe unit && uv run poe integration`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/main.py tests/test_app.py
git commit -m "$(cat <<'EOF'
✨ feat: load device template catalog at app startup

main.py now calls TemplateLoader at startup and stashes the catalog on
app.state.template_catalog. Process exits on validation failure —
templates are a hard dependency, not optional.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Final Checks + Push + CI

- [ ] **Step 1: Run full pipeline**

Run: `uv run poe checks && uv run poe unit && uv run poe integration`
Expected: all green.

- [ ] **Step 2: Verify file size budget**

Run: `wc -l src/shared/schemas/template.py src/dtm/template_loader.py src/main.py`
Expected: each ≤ 200 lines. If template.py exceeds, split into `template_schemas.py` (Binding/Measurement/Command) and `template.py` (DeviceTemplate + ContainsEntry) following the dtm.py / dtm_protocols.py precedent.

- [ ] **Step 3: Push**

Run: `git push`

- [ ] **Step 4: Watch CI**

Run: `glab ci status`
Expected: pipeline running. Wait for terminal state.

- [ ] **Step 5: Confirm pipeline success**

Run: `until glab ci status 2>&1 | grep -qE "passed|failed|canceled|skipped"; do sleep 15; done; glab ci status`
Expected: `Pipeline state: success`.

---

## Self-Review

**Spec coverage:**
- ✅ Pydantic template schema → Task 1
- ✅ Template loader → Task 2
- ✅ 18 YAML files target — actually 13 (10 leaf + 3 module) per Task 5b deferrals; document gap in PR description
- ✅ Validate at startup → Task 7
- ✅ Tests for catalog walk, validation rules, lookup → Tasks 1-7

**Placeholder scan:**
- Task 5b includes phrases like "Read `hardware_selector_map.yaml` to determine the canonical MVP vendor" — that's a directive with a concrete file path, not a placeholder. Acceptable.
- Task 5b "deferred" and "skip" are real decisions documented in this plan, not TBDs.
- Task 7 file-size guidance "If src/main.py exceeds 200 lines after the change, refactor by moving startup config into src/startup.py" is a contingent action with criteria, acceptable.

**Type consistency:**
- `Binding` is the type alias; `ModbusBinding`/`Dnp3Binding`/etc. are the variants — consistent across Task 1 and YAML examples.
- `Publisher.LINE_CONTROLLER` and `Fanout.LINE_CONTROLLER` are distinct enums by design (publisher applies to measurements, fanout to commands).
- `TemplateKind.LEAF` / `MODULE` consistent.
- `DeviceTemplate.equipment_id` is `str | None` and the validator enforces presence per kind — consistent.

**Scope:** Single PR; foundation only. PR 2 (DTM rework + topology.yaml lock-step) and PR 3 (device-api) are separate plans. Confirmed.
