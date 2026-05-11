# PR 2 — edp-api DTM Rework ⇄ edp-module-assemblies topology.yaml Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace edp-api's DTM emit with the canonical ADR-002 §7 shape (parent-chain devices, dict-keyed by slug, `templates_used` embedded, `buses[]` populated). Rewrite the two existing assembly topology.yamls (compute-container/commercial-ac and grid-container/commercial-ac) to the new authoring shape (`template:` ref, `connection:` block, `buses:` section). Delete the dead per-device protocol_config code.

**Architecture:** edp-api and edp-module-assemblies merge in lock-step (same calendar window). After this PR, edp-api's DTM payload exactly matches the canonical schema device-api will consume in PR 3. dtm_generator walks the new topology.yaml, looks up templates from PR 1's catalog, assigns deterministic slugs (`{template}_{index}`), expands bus member patterns, and embeds `templates_used`.

**Tech Stack:** Python 3.13, Pydantic v2, pytest, uv, ruff, ty (edp-api). YAML authoring (edp-module-assemblies). Existing template catalog from PR 1.

**Reference:**
- `ems/docs/superpowers/specs/2026-05-09-redo-device-api-foundation-design.md` — sections "Canonical DTM", "Slug generation rules", "Bus authoring", "Migration"
- `arcnode/ems/topic_structure_adr.md` ADR-002 §7, §9, §14

**Lock-step:** PR 2 is two coordinated PRs (edp-api + edp-module-assemblies) merged in the same window. Either repo's main branch is broken against the other otherwise.

---

## Verification Gate (mandatory)

After every small step, run:

```bash
uv run poe checks && uv run poe unit
```

If either fails, fix before the next step. After `dtm_generator_service.py` changes, also run `uv run poe integration`. The targeted `pytest -vv ...` invocations specified in step descriptions are in addition to this gate, not a substitute.

---

## File Structure

**edp-api — replace:**
- `src/shared/schemas/dtm.py` (158 lines today) — full rewrite. New canonical schema per spec: `Connection`, `Device` (slug-id + template ref + parent + connection + blocking + extra_measurements), `BusMember`, `Bus`, `Dtm` (deployment_uuid + ems_mode + sizing_params + dict-keyed devices + buses + templates_used + computed pending_devices). Drops `Module`, drops `device_uuid: UUID`.
- `src/dtm/topology_yaml.py` (29 lines today) — full rewrite. New shape: `TopologyDeviceSpec` (template + description + connection + blocking + extra_measurements), `TopologyBusMemberSpec` (device_template + port), `TopologyBusSpec` (bus_id + type + members), `TopologyYaml` (devices + buses).
- `src/dtm/dtm_generator_service.py` (149 lines today) — full rewrite. Slug generation, module dissolution into Devices, parent-chain assignment, templates_used embedding, bus member expansion.
- `src/shared/schemas/test_dtm.py`, `src/shared/schemas/test_dtm_placeholders.py` — rewrite for new shape.
- `src/dtm/test_dtm_generator_service.py` — rewrite for new generator behavior.

**edp-api — delete:**
- `src/shared/schemas/dtm_protocols.py` (118 lines) — dead. Per-device `protocol_config` no longer exists; bindings live in templates.
- `src/shared/schemas/test_dtm_protocols.py` — dead.

**edp-module-assemblies — rewrite:**
- `assemblies/compute-container/commercial-ac/topology.yaml` — new shape (drop `protocol_config`, rename `device_type` → `template`, nest `host`/`port` under `connection`, add `buses:` section).
- `assemblies/grid-container/commercial-ac/topology.yaml` — same.

**Slug rule:** `{template}_{index_within_site}`. Index numbering is contiguous, 1-based, deterministic from the deployment resolution. Always indexed (`revenue_meter_1`, even when count=1).

**Modules dissolve:** Today's edp-api emits `compute_container_1` as a `Module` entity with `module_id`. New shape makes it a `Device` with `template: compute_module, parent: null` and slug `compute_module_1`. Children get `parent: compute_module_1`.

**Out of scope for PR 2:**
- BESS instantiation in commercial-ac DTMs (no `assemblies/bess/` topology.yaml exists today; bess_module + bess_rack templates remain in catalog but aren't referenced by any commercial-ac DTM yet).
- `dnp3_master_external` instantiation (deferred from PR 1; needs `equipment/GRD-UTM-001/spec.yaml`).
- AsyncAPI generation in device-api (sub-project C).

---

## Task 1: Rewrite `topology_yaml.py` Schema

**Files:**
- Modify: `src/dtm/topology_yaml.py` (full rewrite)
- Test: `src/dtm/test_topology_yaml.py` (new — colocated)

This task lands in edp-api alone. The file currently models the old shape; rewriting it makes the dtm_generator stop compiling, but we'll address that in Task 4. The old topology.yamls in edp-module-assemblies will fail to parse against the new schema — that's the expected lock-step coupling.

- [ ] **Step 1: Write failing test for new TopologyYaml shape**

```python
# src/dtm/test_topology_yaml.py
"""TopologyYaml schema unit tests — new authoring shape per PR 2."""

import pytest
from pydantic import ValidationError

from src.dtm.topology_yaml import (
    TopologyBusMemberSpec,
    TopologyBusSpec,
    TopologyConnectionSpec,
    TopologyDeviceSpec,
    TopologyYaml,
)
from src.shared.schemas.dtm import BlockingKind


def test_topology_device_spec_minimal() -> None:
    # Arrange / Act
    spec = TopologyDeviceSpec(
        template="revenue_meter",
        description="ION9000",
        connection=TopologyConnectionSpec(
            host="mock-modbus-server", port=502, unit_id="2"
        ),
    )
    # Assert
    assert spec.template == "revenue_meter"
    assert spec.connection.host == "mock-modbus-server"
    assert spec.blocking == [BlockingKind.LIVE_MODE]   # default


def test_topology_connection_accepts_sentinel_port() -> None:
    # Arrange / Act
    c = TopologyConnectionSpec(
        host="PROVISIONED_AT_COMMISSIONING",
        port="PROVISIONED_AT_COMMISSIONING",
        unit_id="PROVISIONED_AT_COMMISSIONING",
    )
    # Assert
    assert c.port == "PROVISIONED_AT_COMMISSIONING"


def test_topology_bus_spec_with_members() -> None:
    # Arrange / Act
    bus = TopologyBusSpec(
        bus_id="ac_main",
        type="ac",
        members=[
            TopologyBusMemberSpec(device_template="switchgear", port="line"),
            TopologyBusMemberSpec(device_template="revenue_meter", port="voltage_in"),
        ],
    )
    # Assert
    assert bus.type == "ac"
    assert len(bus.members) == 2


def test_topology_yaml_full_shape() -> None:
    # Arrange / Act
    y = TopologyYaml(
        devices=[
            TopologyDeviceSpec(
                template="revenue_meter",
                description="meter",
                connection=TopologyConnectionSpec(
                    host="mock-modbus-server", port=502, unit_id="2"
                ),
            ),
        ],
        buses=[
            TopologyBusSpec(
                bus_id="ac_main",
                type="ac",
                members=[
                    TopologyBusMemberSpec(
                        device_template="revenue_meter", port="voltage_in"
                    )
                ],
            )
        ],
    )
    # Assert
    assert len(y.devices) == 1
    assert len(y.buses) == 1


def test_topology_bus_type_rejected_outside_dc_ac() -> None:
    # Arrange — type="dontknow" should fail enum validation
    with pytest.raises(ValidationError):
        TopologyBusSpec.model_validate(
            {"bus_id": "x", "type": "dontknow", "members": []}
        )
```

Run gate. Expect ImportError (the new types don't exist).

- [ ] **Step 2: Rewrite `src/dtm/topology_yaml.py`**

```python
"""Per-assembly device topology yaml shape.

Authored in `edp-module-assemblies/assemblies/<type>/<variant>/topology.yaml`,
fetched by URL from `manifest.yaml`. Per ADR-002 §7 + §14: device_template
references resolve against edp-api/device_templates/ at DTM emit time.
"""

from typing import Literal

from pydantic import BaseModel, Field

from src.shared.schemas.dtm import BlockingKind
from src.shared.schemas.template_protocols import ProvisionedInt


class TopologyConnectionSpec(BaseModel):
    """Per-instance runtime connection params authored alongside the device."""

    host: str
    port: ProvisionedInt
    unit_id: str | None = None    # modbus unit_id, dnp3 outstation, etc.


class TopologyDeviceSpec(BaseModel):
    """One device entry inside an assembly's topology yaml."""

    template: str                  # references a slug in edp-api/device_templates/
    description: str
    connection: TopologyConnectionSpec
    blocking: list[BlockingKind] = Field(
        default_factory=lambda: [BlockingKind.LIVE_MODE]
    )


class TopologyBusMemberSpec(BaseModel):
    """One member declaration in a bus — pattern over device_template."""

    device_template: str          # generator expands per resolution count
    port: str | None = None       # references a port_id on the device's equipment


class TopologyBusSpec(BaseModel):
    """Electrical bus connecting devices via their ports."""

    bus_id: str
    type: Literal["dc", "ac"]
    members: list[TopologyBusMemberSpec]


class TopologyYaml(BaseModel):
    """Top-level topology yaml: devices + buses authored per assembly variant."""

    devices: list[TopologyDeviceSpec]
    buses: list[TopologyBusSpec] = Field(default_factory=list)
```

Note: `ProvisionedInt` currently lives in `src/shared/schemas/template_protocols.py`? Confirm — I think it's in `src/shared/schemas/dtm_protocols.py`. The path **must** be updated as part of this task: ProvisionedInt + PROVISIONED_AT_COMMISSIONING need to live in a non-deleted module. Move them to `src/shared/schemas/dtm.py` (the canonical schema) when you do Task 2. Until then, this import will be wrong and tests will fail — which is expected for the failing-test phase of TDD. Adjust the import in Step 2 once Task 2 fixes the location.

Actually: do this in tighter sequence — keep ProvisionedInt in `dtm_protocols.py` for now, import from there, and deal with the move in Task 3 when we delete `dtm_protocols.py`. The import will need to flip back to `dtm.py` then.

- [ ] **Step 3: Run gate. All 5 new topology_yaml tests pass.**

Old `dtm_generator_service.py` will now fail to compile because it expects the old TopologyDeviceSpec shape. That's fine — Task 4 fixes the generator; until then `poe unit` will surface those failures. **Important:** if cascade failures from `dtm_generator_service.py` block this task's gate, comment out the broken imports in `dtm_generator_service.py` AS A TEMPORARY MEASURE and document in the commit message. Do not "fix" the generator partially — leave it broken until Task 4.

Actually a cleaner approach: this task is *additive* if we keep the existing types around. Since `dtm.py`/`dtm_generator_service.py` will both be rewritten anyway, just stage them. Concretely:

Alternative gate strategy: do NOT run `poe unit` after Step 2. Run only `poe lint` + `poe typecheck`. The unit suite will go red until Task 4 lands. Note this in the commit message and resume the full gate at Task 4.

- [ ] **Step 4: Commit (partial-state OK because PR 2 is one logical change spanning multiple files):**

```bash
git add src/dtm/topology_yaml.py src/dtm/test_topology_yaml.py
git commit -m "$(cat <<'EOF'
✨ feat: TopologyYaml new authoring shape (template + connection + buses)

Per PR 2 of redo-device-api foundation. New TopologyDeviceSpec carries
`template:` ref instead of free `device_type:`; per-instance host/port/
unit_id move into a TopologyConnectionSpec block; topology.yaml gains
a `buses:` section with template-pattern members. Old per-device
protocol_config is gone — bindings live in edp-api/device_templates/.

Cascade failures in dtm_generator_service expected until Task 4
(rewrite); poe checks (lint/typecheck) green; poe unit deferred.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

DO NOT push.

---

## Task 2: Replace `dtm.py` with Canonical Schema

**Files:**
- Modify: `src/shared/schemas/dtm.py` (full rewrite)
- Modify: `src/shared/schemas/test_dtm.py` (rewrite for new shape)
- Modify: `src/shared/schemas/test_dtm_placeholders.py` (rewrite for new shape)
- Note: `src/shared/schemas/dtm_protocols.py` still exists; deletion is in Task 3.

- [ ] **Step 1: Read the current files for the precedents you're keeping**

Read `src/shared/schemas/dtm.py` (the current file you'll replace), `src/shared/schemas/dtm_protocols.py` (where ProvisionedInt + PROVISIONED_AT_COMMISSIONING currently live — these MOVE here), `src/shared/schemas/template.py` (DeviceTemplate import target).

Sentinel + ProvisionedInt move from `dtm_protocols.py` to `dtm.py` because they're top-level placeholder primitives that survive the dtm_protocols deletion. Update the existing test_dtm_placeholders to import them from the new location.

- [ ] **Step 2: Write failing tests for the canonical Dtm shape**

Replace `src/shared/schemas/test_dtm.py` content. Tests:

```python
"""Canonical DTM schema tests per ADR-002 §7."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from src.shared.schemas.dtm import (
    PROVISIONED_AT_COMMISSIONING,
    BlockingKind,
    Bus,
    BusMember,
    Connection,
    Device,
    Dtm,
    EmsMode,
    ProvisionedInt,
    SizingParams,
)
from src.shared.schemas.template import DeviceTemplate, Measurement, TemplateKind
from src.shared.schemas.template_protocols import ModbusBinding

DEPLOYMENT_ID: UUID = UUID("00000000-0000-0000-0000-000000000010")


def _modbus_binding() -> ModbusBinding:
    return ModbusBinding(protocol="modbus_tcp", function_code=4, address=100)


def _revenue_meter_template() -> DeviceTemplate:
    return DeviceTemplate(
        template="revenue_meter",
        kind=TemplateKind.LEAF,
        equipment_id="GRD-MTR-001",
        vendor="Schneider",
        model="ION9000",
        description="t",
        measurements={
            "voltage_a": Measurement(unit="volts", type="float", binding=_modbus_binding())
        },
    )


def _connection() -> Connection:
    return Connection(host="10.0.0.1", port=502, unit_id="2")


def _device(
    *,
    device_id: str = "revenue_meter_1",
    template: str = "revenue_meter",
    parent: str | None = None,
    connection: Connection | None = None,
) -> Device:
    return Device(
        device_id=device_id,
        template=template,
        parent=parent,
        connection=connection or _connection(),
    )


def _sizing() -> SizingParams:
    return SizingParams(
        P_compute_total_kW=10.0, E_BESS_total_kWh=5000.0, T_coolant_setpoint_C=30.0
    )


def _dtm(
    *,
    devices: dict[str, Device] | None = None,
    buses: list[Bus] | None = None,
    templates_used: dict[str, DeviceTemplate] | None = None,
) -> Dtm:
    return Dtm(
        deployment_uuid=DEPLOYMENT_ID,
        ems_mode=EmsMode.SIM,
        sizing_params=_sizing(),
        devices=devices or {"revenue_meter_1": _device()},
        buses=buses or [],
        templates_used=templates_used or {"revenue_meter": _revenue_meter_template()},
    )


def test_device_id_must_be_snake_case_slug() -> None:
    # Arrange / Act / Assert
    with pytest.raises(ValidationError, match="slug"):
        Device(
            device_id="RevenueMeter-1",     # invalid slug
            template="revenue_meter",
            connection=_connection(),
        )


def test_device_blocking_default_is_live_mode() -> None:
    # Arrange / Act
    d = _device()
    # Assert
    assert d.blocking == [BlockingKind.LIVE_MODE]


def test_dtm_devices_keyed_by_device_id() -> None:
    # Arrange / Act
    dtm = _dtm()
    # Assert
    assert "revenue_meter_1" in dtm.devices


def test_dtm_pending_devices_excludes_fully_provisioned() -> None:
    # Arrange / Act
    dtm = _dtm()
    # Assert
    assert dtm.pending_devices == []


def test_dtm_pending_devices_includes_devices_with_sentinel() -> None:
    # Arrange
    pending = _device(
        device_id="revenue_meter_1",
        connection=Connection(host=PROVISIONED_AT_COMMISSIONING, port=502),
    )
    # Act
    dtm = _dtm(devices={"revenue_meter_1": pending})
    # Assert
    assert [d.device_id for d in dtm.pending_devices] == ["revenue_meter_1"]


def test_dtm_rejects_orphan_parent() -> None:
    # Arrange — child references a parent that's not in devices
    child = _device(device_id="revenue_meter_1", parent="grid_module_1")
    # Act / Assert
    with pytest.raises(ValidationError, match="parent"):
        _dtm(devices={"revenue_meter_1": child})


def test_dtm_rejects_orphan_template_ref() -> None:
    # Arrange — device references a template not in templates_used
    d = _device(device_id="revenue_meter_1", template="not_a_template")
    # Act / Assert
    with pytest.raises(ValidationError, match="templates_used"):
        _dtm(devices={"revenue_meter_1": d})


def test_dtm_rejects_orphan_bus_member() -> None:
    # Arrange — bus member references a device not in devices
    bus = Bus(
        bus_id="ac_main",
        type="ac",
        members=[BusMember(device_id="ghost_device", port="line")],
    )
    # Act / Assert
    with pytest.raises(ValidationError, match="bus member"):
        _dtm(buses=[bus])


def test_bus_type_dc_or_ac_only() -> None:
    # Arrange / Act / Assert
    with pytest.raises(ValidationError):
        Bus.model_validate({"bus_id": "x", "type": "rf", "members": []})


def test_module_kind_device_has_null_connection() -> None:
    # Arrange — module template doesn't bind to a single device's protocol
    module_dev = Device(
        device_id="grid_module_1",
        template="grid_module",
        parent=None,
        connection=None,
    )
    # Assert — connection is optional and may be None
    assert module_dev.connection is None
```

This is the spec for the canonical schema. Run gate (lint+typecheck only — full unit suite still wedged from Task 1).

- [ ] **Step 3: Implement `src/shared/schemas/dtm.py` (full rewrite)**

Replace the file. The new module owns:
- `PROVISIONED_AT_COMMISSIONING: Final[str]` (moved from dtm_protocols.py — the canonical home now)
- `ProvisionedInt = int | Literal["PROVISIONED_AT_COMMISSIONING"]` (moved from dtm_protocols.py)
- `EmsMode`, `BlockingKind` enums (existing)
- `SizingParams` (existing)
- `Connection`: `host: str` (sentinel-tolerant), `port: ProvisionedInt`, `unit_id: str | None = None`
- `Device`: `device_id: str` (slug-validated), `template: str`, `parent: str | None`, `display_name: str | None`, `connection: Connection | None` (None for module-kind devices), `blocking: list[BlockingKind]`, `extra_measurements: dict[str, Measurement] | None`, computed `has_placeholders`, computed `mode`
- `BusMember`: `device_id: str`, `port: str | None`
- `Bus`: `bus_id: str`, `type: Literal["dc","ac"]`, `members: list[BusMember]`
- `Dtm`: `deployment_uuid: UUID`, `ems_mode: EmsMode`, `sizing_ref: str | None`, `sizing_params: SizingParams`, `devices: dict[str, Device]`, `buses: list[Bus]`, `templates_used: dict[str, DeviceTemplate]`, computed `pending_devices`
- Three Dtm-level validators:
  - `parent_chain_resolves`: every `device.parent` is null or a key in `devices`
  - `template_refs_resolve`: every `device.template` is a key in `templates_used`
  - `bus_members_resolve`: every `bus.members[].device_id` is a key in `devices`
- `Device.device_id` validator: snake_case slug per ADR §9 (mirror template slug regex)
- Existing `_contains_sentinel` recursive walker + `Device.has_placeholders` + `Dtm.pending_devices` (carry forward but adjust for new field set)

**Important**: this file may grow > 200 lines. If it does, split into `dtm.py` (top-level Dtm + Device + validators) and `dtm_primitives.py` (Connection + BusMember + Bus + sentinel + ProvisionedInt). The dtm.py / dtm_protocols.py precedent is exactly this.

- [ ] **Step 4: Run targeted tests + lint/typecheck**

```bash
uv run pytest -vv src/shared/schemas/test_dtm.py
uv run poe lint && uv run poe typecheck
```

All `test_dtm.py` tests pass. Lint+typecheck clean. Other test files (`test_dtm_placeholders`, `test_dtm_protocols`, `test_topology_yaml`, `test_dtm_generator_service`) still wedged from Task 1 — that's OK.

- [ ] **Step 5: Rewrite `src/shared/schemas/test_dtm_placeholders.py`**

Update the file's imports to pull `PROVISIONED_AT_COMMISSIONING`, `ProvisionedInt`, `Connection`, `Device`, `Dtm` from the new dtm.py. Drop any reference to old `Module` entity. Update assertions to use slug-keyed dict access (`dtm.devices["revenue_meter_1"]`) instead of list iteration. Tests that probe sentinel behavior at the protocol_config level no longer apply (protocol_config is gone) — drop those tests; replace with sentinel tests on `Connection.host` / `Connection.port` / per-device fields.

The new file's tests should cover:
- Single sentinel in host → device.has_placeholders = True
- Single sentinel in port → device.has_placeholders = True
- Sentinel in unit_id → device.has_placeholders = True
- All real values → device.mode = LIVE
- Dtm.pending_devices includes only devices with sentinels

Aim for ≤ 200 lines. If you keep useful test cases from the old file, that's fine.

- [ ] **Step 6: Run gate**

```bash
uv run pytest -vv src/shared/schemas/test_dtm.py src/shared/schemas/test_dtm_placeholders.py
uv run poe lint && uv run poe typecheck
```

Both test files green. Other tests still wedged — that's expected.

- [ ] **Step 7: Commit**

```bash
git add src/shared/schemas/dtm.py src/shared/schemas/test_dtm.py src/shared/schemas/test_dtm_placeholders.py
git commit -m "$(cat <<'EOF'
✨ feat: canonical Dtm schema per ADR-002 §7

Replaces dtm.py with the canonical shape: parent-chain Devices keyed by
snake_case slug, embedded templates_used map, buses[] with type=dc|ac,
and three Dtm-level referential integrity validators (parent_chain_resolves,
template_refs_resolve, bus_members_resolve). Drops the Module entity
and device_uuid:UUID — modules become Devices with kind=module template
and parent=null. Sentinel + ProvisionedInt move from dtm_protocols.py
(deleted in next commit) to dtm.py as canonical home.

dtm_generator_service.py and topology_yaml.py still wedged from Task 1;
Task 4 unblocks them.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Delete Dead `dtm_protocols.py`

**Files:**
- Delete: `src/shared/schemas/dtm_protocols.py`
- Delete: `src/shared/schemas/test_dtm_protocols.py`

- [ ] **Step 1: Verify nothing live imports from these files**

```bash
grep -rn "from src.shared.schemas.dtm_protocols\|from src.shared.schemas.test_dtm_protocols" src tests
```

Expected: no hits, or only hits inside the files being deleted. If anything else imports from `dtm_protocols`, fix it to import from the new `dtm.py` (Connection, ProvisionedInt, sentinel) or `template_protocols.py` (binding types) before deleting.

- [ ] **Step 2: Delete the files**

```bash
git rm src/shared/schemas/dtm_protocols.py src/shared/schemas/test_dtm_protocols.py
```

- [ ] **Step 3: Run gate**

```bash
uv run poe lint && uv run poe typecheck
```

Clean expected. unit suite still wedged.

- [ ] **Step 4: Commit**

```bash
git commit -m "$(cat <<'EOF'
🔥 chore: delete dead dtm_protocols.py + test

Per-device protocol_config is gone in the canonical schema (bindings
live in templates per ADR-002 §7). The Modbus/Dnp3/Snmp/Canopen/Redfish
*Config classes that lived here are no longer used. Sentinel +
ProvisionedInt moved to dtm.py in the previous commit.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Rewrite `dtm_generator_service.py`

**Files:**
- Modify: `src/dtm/dtm_generator_service.py` (full rewrite)
- Modify: `src/dtm/test_dtm_generator_service.py` (rewrite)

- [ ] **Step 1: Read the current generator and the new schemas**

Read `src/dtm/dtm_generator_service.py` (current behavior: walks resolution, reads topology yamls per assembly type, builds Module + Device list). Read the new `src/dtm/topology_yaml.py` and `src/shared/schemas/dtm.py` (Task 1 + 2 outputs).

The new generator's responsibilities:
1. For each container instance (compute, grid, possibly bess later), emit a single module-kind Device with slug `{module_template}_{i}` and parent=null
2. For each device in the variant's topology.yaml, emit a leaf-kind Device with slug `{device_template}_{counter_per_template_per_site}` and parent set to the enclosing module's slug
3. Walk all referenced template slugs, look up in the catalog (passed in via DI), embed verbatim in `Dtm.templates_used`
4. For each bus declared in any topology.yaml, expand its template-pattern members into `BusMember(device_id=..., port=...)` entries — one BusMember per matching emitted Device
5. Carry through `connection`, `blocking` from topology.yaml verbatim
6. Set top-level `ems_mode = SIM`
7. Set top-level `sizing_params` from resolution (existing logic stays)

**Slug counter**: site-wide, per-template. For commercial-ac with 1 compute container (7 gpu_nodes, 1 cdu, 1 network_switch, 4 pdus), slugs are `gpu_node_1`...`gpu_node_7`, `cdu_1`, `network_switch_1`, `pdu_1`...`pdu_4`. If 2 compute containers, gpu_node continues to `gpu_node_14` etc. (counter is per-template across the whole site).

**Module slug**: `compute_module_1`, `compute_module_2`, ... `grid_module_1`, etc. The container/module relationship: each container_count instance becomes one module Device. Its leaf children get `parent: compute_module_N`.

- [ ] **Step 2: Write failing tests for the new generator**

Replace `src/dtm/test_dtm_generator_service.py`. Tests cover:

```python
"""DtmGeneratorService unit tests for the canonical schema (PR 2)."""

from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from src.bom_generator.manifest_models import (
    AssemblyVariant,
    Manifest,
    PlateUrls,
    ProfileAssemblies,
)
from src.dtm.dtm_generator_service import DtmGeneratorService
from src.dtm.template_loader import TemplateLoader
from src.shared.enums import (
    BessCoupling,
    ClimateZone,
    DeploymentProfile,
    EmsTarget,
    GpuVariant,
    SourcingTier,
)
from src.shared.schemas.dtm import EmsMode
from src.shared.schemas.module_resolution import ModuleResolution


DEPLOYMENT_ID: UUID = UUID("12345678-1234-1234-1234-123456789abc")


def _real_catalog() -> dict:
    """Use the real device_templates/ catalog from PR 1."""
    repo_root = Path(__file__).resolve().parents[2]
    return TemplateLoader(root=repo_root / "device_templates").load_catalog()


def _av(*, type_: str, variant: str) -> AssemblyVariant:
    base = f"s3://arcnode-artifacts/assemblies/{type_.replace('_', '-')}/{variant}"
    return AssemblyVariant(
        bom=f"{base}/bom.yaml",
        step=f"{base}/assembly.step",
        glb=f"{base}/assembly.glb",
        topology_yaml=f"{base}/topology.yaml",
    )


def _manifest() -> Manifest:
    return Manifest(
        version="0.1.0",
        assemblies={
            "compute_container": {"commercial-ac": _av(type_="compute_container", variant="commercial-ac")},
            "grid_container": {"commercial-ac": _av(type_="grid_container", variant="commercial-ac")},
        },
        plates={"CG": PlateUrls(spec="s3://test/CG.yaml", step="s3://test/CG.step")},
        profiles={
            "commercial_ac": ProfileAssemblies(
                compute_container="commercial-ac",
                grid_container="commercial-ac",
                interface_plates=["CG"],
            ),
        },
    )


def _resolution(*, container_count: int = 1) -> ModuleResolution:
    return ModuleResolution(
        deployment_id=DEPLOYMENT_ID,
        deployment_profile=DeploymentProfile.COMMERCIAL_AC,
        compute_container_count=container_count,
        grid_container_present=True,
        bess_coupling=BessCoupling.AC_COUPLED,
        bess_capacity_mwh=5.0,
        sourcing_tier=SourcingTier.COMMERCIAL,
        ems_target=EmsTarget.AWS_STANDARD,
        gpu_variant=GpuVariant.H100_SXM,
        gpu_count=container_count * 56,
        climate_zone=ClimateZone.TEMPERATE,
    )


def _make_client() -> MagicMock:
    """Mocked manifest client returning the new-shape topology.yamls.

    Loads the actual edp-module-assemblies topology.yamls (post-rewrite in
    Tasks 5+6) so end-to-end paths match.
    """
    client = MagicMock()
    client.fetch_manifest.return_value = _manifest()

    assemblies_root = Path("/home/resister/arcnode/edp-module-assemblies/assemblies")

    def fetch_topo(url: str) -> dict:
        # Reason: extract type + variant from the s3 URL and load from local disk
        import yaml
        if "compute-container" in url:
            return yaml.safe_load(
                (assemblies_root / "compute-container/commercial-ac/topology.yaml").read_text()
            )
        if "grid-container" in url:
            return yaml.safe_load(
                (assemblies_root / "grid-container/commercial-ac/topology.yaml").read_text()
            )
        raise ValueError(f"unmocked: {url}")

    client.fetch_topology_yaml.side_effect = fetch_topo
    return client


def test_generate_emits_sim_mode() -> None:
    # Arrange
    service = DtmGeneratorService(_make_client(), template_catalog=_real_catalog())
    # Act
    actual = service.generate(profile="commercial_ac", resolution=_resolution())
    # Assert
    assert actual.ems_mode == EmsMode.SIM


def test_generate_dissolves_modules_into_devices() -> None:
    # Arrange
    service = DtmGeneratorService(_make_client(), template_catalog=_real_catalog())
    # Act
    actual = service.generate(profile="commercial_ac", resolution=_resolution())
    # Assert — module Devices exist with parent=null
    assert "compute_module_1" in actual.devices
    assert "grid_module_1" in actual.devices
    assert actual.devices["compute_module_1"].parent is None
    assert actual.devices["grid_module_1"].parent is None


def test_generate_assigns_per_template_indexed_slugs() -> None:
    # Arrange
    service = DtmGeneratorService(_make_client(), template_catalog=_real_catalog())
    # Act
    actual = service.generate(profile="commercial_ac", resolution=_resolution())
    # Assert — gpu_node_1 through gpu_node_7 (7 nodes per current topology)
    gpu_slugs = [s for s in actual.devices if s.startswith("gpu_node_")]
    assert sorted(gpu_slugs) == [f"gpu_node_{i}" for i in range(1, 8)]
    assert "revenue_meter_1" in actual.devices


def test_generate_parents_leaves_under_modules() -> None:
    # Arrange
    service = DtmGeneratorService(_make_client(), template_catalog=_real_catalog())
    # Act
    actual = service.generate(profile="commercial_ac", resolution=_resolution())
    # Assert — every gpu_node has parent=compute_module_1; revenue_meter has parent=grid_module_1
    assert actual.devices["gpu_node_1"].parent == "compute_module_1"
    assert actual.devices["revenue_meter_1"].parent == "grid_module_1"


def test_generate_embeds_templates_used() -> None:
    # Arrange
    service = DtmGeneratorService(_make_client(), template_catalog=_real_catalog())
    # Act
    actual = service.generate(profile="commercial_ac", resolution=_resolution())
    # Assert — every referenced template appears in templates_used verbatim
    referenced_slugs = {d.template for d in actual.devices.values()}
    assert referenced_slugs <= set(actual.templates_used)
    # Spot check shape
    assert actual.templates_used["revenue_meter"].equipment_id == "GRD-MTR-001"


def test_generate_expands_bus_members() -> None:
    # Arrange
    service = DtmGeneratorService(_make_client(), template_catalog=_real_catalog())
    # Act
    actual = service.generate(profile="commercial_ac", resolution=_resolution())
    # Assert — at least one bus exists with concrete device_id members
    assert len(actual.buses) > 0
    bus = actual.buses[0]
    for m in bus.members:
        # Every BusMember resolves to a real device
        assert m.device_id in actual.devices


def test_generate_slug_counter_continues_across_containers() -> None:
    # Arrange — 2 compute containers means gpu_node count doubles
    service = DtmGeneratorService(_make_client(), template_catalog=_real_catalog())
    # Act
    actual = service.generate(
        profile="commercial_ac", resolution=_resolution(container_count=2)
    )
    # Assert — gpu_node_1 through gpu_node_14
    gpu_slugs = [s for s in actual.devices if s.startswith("gpu_node_")]
    assert len(gpu_slugs) == 14


def test_generate_unknown_profile_raises() -> None:
    # Arrange
    service = DtmGeneratorService(_make_client(), template_catalog=_real_catalog())
    # Act / Assert
    with pytest.raises(ValueError, match="not in manifest"):
        service.generate(profile="dod_dc_int", resolution=_resolution())
```

Run gate. All 8 tests fail (generator not yet rewritten).

- [ ] **Step 3: Rewrite `src/dtm/dtm_generator_service.py`**

Substantially restructure. Key changes:
- Constructor now takes `template_catalog: dict[str, DeviceTemplate]` (DI'd from app startup).
- New private helpers: `_assign_slug(template: str, counter: dict[str, int]) -> str`, `_module_slug_for(asm_type: str, instance: int) -> str`, `_expand_bus(bus_spec, by_template: dict[str, list[str]]) -> Bus`.
- `generate()` walks profile assemblies, fetches topology YAMLs, parses with new TopologyYaml, accumulates Devices into a dict, accumulates Bus expansions, walks devices to populate templates_used.

Sketch:

```python
"""DtmGeneratorService — emits canonical Dtm per ADR-002 §7."""

import logging
from typing import Final

from src.bom_generator.manifest_client import ManifestClient
from src.bom_generator.manifest_models import Manifest
from src.dtm.topology_yaml import (
    TopologyBusSpec,
    TopologyDeviceSpec,
    TopologyYaml,
)
from src.shared.enums import GpuVariant
from src.shared.schemas.dtm import (
    Bus,
    BusMember,
    Connection,
    Device,
    Dtm,
    EmsMode,
    SizingParams,
)
from src.shared.schemas.module_resolution import ModuleResolution
from src.shared.schemas.template import DeviceTemplate

logger = logging.getLogger(__name__)

_P_PER_GPU_KW: Final[dict[GpuVariant, float]] = {
    GpuVariant.H100_SXM: 0.7,
    GpuVariant.B200: 1.0,
}
_PUE: Final[float] = 1.3
_T_COOLANT_SETPOINT_C: Final[float] = 30.0

_MODULE_TEMPLATE_BY_ASSEMBLY_TYPE: Final[dict[str, str]] = {
    "compute_container": "compute_module",
    "grid_container": "grid_module",
}


class DtmGeneratorService:
    """Builds a canonical Dtm. ems-device-api owns later LIVE rewrites."""

    def __init__(
        self,
        manifest_client: ManifestClient,
        template_catalog: dict[str, DeviceTemplate],
    ) -> None:
        self._client = manifest_client
        self._catalog = template_catalog

    def generate(self, *, profile: str, resolution: ModuleResolution) -> Dtm:
        manifest = self._client.fetch_manifest()
        if profile not in manifest.profiles:
            raise ValueError(
                f"profile {profile!r} not in manifest "
                f"(available: {sorted(manifest.profiles)})"
            )
        prof = manifest.profiles[profile]

        devices: dict[str, Device] = {}
        buses: list[Bus] = []
        slug_counter: dict[str, int] = {}
        # device_template -> list of emitted device_ids (for bus member expansion)
        by_template: dict[str, list[str]] = {}

        # compute containers
        for i in range(resolution.compute_container_count):
            self._emit_container(
                manifest=manifest,
                asm_type="compute_container",
                variant=prof.compute_container,
                instance_index=i + 1,
                devices=devices,
                buses=buses,
                slug_counter=slug_counter,
                by_template=by_template,
            )

        # grid container
        if prof.grid_container is not None:
            self._emit_container(
                manifest=manifest,
                asm_type="grid_container",
                variant=prof.grid_container,
                instance_index=1,
                devices=devices,
                buses=buses,
                slug_counter=slug_counter,
                by_template=by_template,
            )

        templates_used = self._collect_templates_used(devices)

        return Dtm(
            deployment_uuid=resolution.deployment_id,
            ems_mode=EmsMode.SIM,
            sizing_params=self._sizing(resolution),
            devices=devices,
            buses=buses,
            templates_used=templates_used,
        )

    def _emit_container(
        self,
        *,
        manifest: Manifest,
        asm_type: str,
        variant: str,
        instance_index: int,
        devices: dict[str, Device],
        buses: list[Bus],
        slug_counter: dict[str, int],
        by_template: dict[str, list[str]],
    ) -> None:
        # Module Device (parent: null)
        module_template = _MODULE_TEMPLATE_BY_ASSEMBLY_TYPE[asm_type]
        module_slug = f"{module_template}_{instance_index}"
        devices[module_slug] = Device(
            device_id=module_slug,
            template=module_template,
            parent=None,
            connection=None,
        )
        by_template.setdefault(module_template, []).append(module_slug)

        # Topology yaml (may be absent → log + skip)
        topology = self._fetch_topology(manifest, asm_type, variant)
        if topology is None:
            return

        # Leaf devices, parented to the module
        for spec in topology.devices:
            slug = self._assign_slug(spec.template, slug_counter)
            devices[slug] = Device(
                device_id=slug,
                template=spec.template,
                parent=module_slug,
                connection=Connection(
                    host=spec.connection.host,
                    port=spec.connection.port,
                    unit_id=spec.connection.unit_id,
                ),
                blocking=list(spec.blocking),
            )
            by_template.setdefault(spec.template, []).append(slug)

        # Bus expansion
        for bus_spec in topology.buses:
            buses.append(self._expand_bus(bus_spec, by_template))

    def _fetch_topology(
        self, manifest: Manifest, asm_type: str, variant: str
    ) -> TopologyYaml | None:
        type_map = manifest.assemblies.get(asm_type, {})
        av = type_map.get(variant)
        if av is None or av.topology_yaml is None:
            logger.warning(
                f"topology_yaml missing for {asm_type}/{variant} — skipping devices"
            )
            return None
        raw = self._client.fetch_topology_yaml(av.topology_yaml)
        return TopologyYaml.model_validate(raw)

    @staticmethod
    def _assign_slug(template: str, counter: dict[str, int]) -> str:
        n = counter.get(template, 0) + 1
        counter[template] = n
        return f"{template}_{n}"

    @staticmethod
    def _expand_bus(bus_spec: TopologyBusSpec, by_template: dict[str, list[str]]) -> Bus:
        members: list[BusMember] = []
        for ms in bus_spec.members:
            for device_id in by_template.get(ms.device_template, []):
                members.append(BusMember(device_id=device_id, port=ms.port))
        return Bus(bus_id=bus_spec.bus_id, type=bus_spec.type, members=members)

    def _collect_templates_used(
        self, devices: dict[str, Device]
    ) -> dict[str, DeviceTemplate]:
        slugs = {d.template for d in devices.values()}
        result: dict[str, DeviceTemplate] = {}
        for slug in slugs:
            if slug not in self._catalog:
                raise ValueError(
                    f"device references template {slug!r} not in catalog"
                )
            result[slug] = self._catalog[slug]
        return result

    @staticmethod
    def _sizing(resolution: ModuleResolution) -> SizingParams:
        per_gpu_kw = _P_PER_GPU_KW[resolution.gpu_variant]
        return SizingParams(
            P_compute_total_kW=resolution.gpu_count * per_gpu_kw * _PUE,
            E_BESS_total_kWh=resolution.bess_capacity_mwh * 1000,
            T_coolant_setpoint_C=_T_COOLANT_SETPOINT_C,
        )
```

This file may exceed 200 lines after black formatting. If so, split into `dtm_generator_service.py` (DtmGeneratorService class) and `dtm_generator_internals.py` (helpers _emit_container, _expand_bus, _collect_templates_used). Stop and report DONE_WITH_CONCERNS so the controller can authorize.

- [ ] **Step 4: Run gate**

```bash
uv run poe checks && uv run poe unit
```

**Important:** at this point the assembly topology.yamls in edp-module-assemblies still have the OLD shape, so `_make_client()` in tests will fail to parse them. The test fixture above expects the NEW shape — those tests will fail until Tasks 5+6 land. Mark this task as DONE_WITH_CONCERNS if the dtm_generator tests fail because the topology.yamls aren't yet rewritten; integration test confirmation lands at Task 7.

Or alternatively: structure the test fixtures to write inline mock yamls in the new shape (using tmp_path), independent of edp-module-assemblies. **Do this** — it makes Task 4 self-contained and doesn't require Tasks 5+6 to be merged first.

If you take the inline-fixture approach, change `_make_client()` to write minimal-but-valid new-shape topology.yamls under tmp_path and return them. Update the slug-counter test to match whatever device counts the inline fixtures use.

- [ ] **Step 5: Commit**

```bash
git add src/dtm/dtm_generator_service.py src/dtm/test_dtm_generator_service.py
git commit -m "$(cat <<'EOF'
✨ feat: dtm_generator emits canonical Dtm per ADR-002 §7

Service constructor now takes template_catalog as DI. generate() walks
profile assemblies, fetches new-shape topology.yamls, dissolves modules
into Devices with parent=null, assigns deterministic slugs
({template}_{site_counter}), parents leaves under their enclosing
module Device, expands template-pattern bus members against emitted
device_ids, and embeds templates_used verbatim from the catalog.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

DO NOT push — assemblies-side rewrites still pending in Tasks 5+6.

---

## Task 5: Rewrite `compute-container/commercial-ac/topology.yaml`

**Repo:** `/home/resister/arcnode/edp-module-assemblies` (different repo from edp-api)

**File:** `assemblies/compute-container/commercial-ac/topology.yaml`

This task lands in the assemblies repo. Lock-step with edp-api Tasks 1-4: assemblies-repo PR must merge in the same window as the edp-api PR, otherwise either repo's main is broken against the other.

- [ ] **Step 1: Read the current topology.yaml**

```bash
cat /home/resister/arcnode/edp-module-assemblies/assemblies/compute-container/commercial-ac/topology.yaml
```

Confirm devices: 7× gpu_node (CMP-NODE-001), 1× cdu (CMP-CDU-001), 1× network_switch (CMP-SWITCH-001), 4× pdu (CMP-PDU-001).

- [ ] **Step 2: Author the new-shape file**

```yaml
# Per-assembly device topology consumed by edp-api dtm_generator (PR 2 shape).
# Per-instance host/port/unit_id live under connection:; protocol bindings live
# in the matching template at edp-api/device_templates/<slug>.yaml.
# SIM-mode hosts use mock-{protocol}-server convention; ems-device-api flips
# to LIVE addresses on commissioning.

devices:
  # 7x HGX B200 nodes — Redfish on BMC. Per-server suffix lives on a future
  # `ports:` discriminator on the template; at MVP they share one Redfish
  # endpoint and the dtm_generator slug-counter disambiguates instances.
  - template: gpu_node
    description: HGX B200 server #1 (CMP-NODE-001)
    connection: { host: mock-redfish-server, port: 8443 }
  - template: gpu_node
    description: HGX B200 server #2 (CMP-NODE-001)
    connection: { host: mock-redfish-server, port: 8443 }
  - template: gpu_node
    description: HGX B200 server #3 (CMP-NODE-001)
    connection: { host: mock-redfish-server, port: 8443 }
  - template: gpu_node
    description: HGX B200 server #4 (CMP-NODE-001)
    connection: { host: mock-redfish-server, port: 8443 }
  - template: gpu_node
    description: HGX B200 server #5 (CMP-NODE-001)
    connection: { host: mock-redfish-server, port: 8443 }
  - template: gpu_node
    description: HGX B200 server #6 (CMP-NODE-001)
    connection: { host: mock-redfish-server, port: 8443 }
  - template: gpu_node
    description: HGX B200 server #7 (CMP-NODE-001)
    connection: { host: mock-redfish-server, port: 8443 }

  # Coolant Distribution Unit — Motivair MCDU-10
  - template: cdu
    description: Motivair MCDU-10 210kW (CMP-CDU-001)
    connection: { host: mock-redfish-server, port: 8443 }

  # ToR Switch — NVIDIA SN5600
  - template: network_switch
    description: NVIDIA Spectrum-X SN5600 800GbE (CMP-SWITCH-001)
    connection: { host: mock-redfish-server, port: 8443 }

  # 4x PDUs — Server Tech PRO3X SNMP
  - template: pdu
    description: Server Tech PRO3X 60A 3ph #1 A-feed (CMP-PDU-001)
    connection: { host: mock-snmp-server, port: 161 }
  - template: pdu
    description: Server Tech PRO3X 60A 3ph #2 A-feed (CMP-PDU-001)
    connection: { host: mock-snmp-server, port: 161 }
  - template: pdu
    description: Server Tech PRO3X 60A 3ph #3 B-feed (CMP-PDU-001)
    connection: { host: mock-snmp-server, port: 161 }
  - template: pdu
    description: Server Tech PRO3X 60A 3ph #4 B-feed (CMP-PDU-001)
    connection: { host: mock-snmp-server, port: 161 }

# Compute container has no buses at MVP — power flows in a single feed and
# the 4 PDUs already encode the A/B feed split via descriptions.
buses: []
```

- [ ] **Step 3: Validate it parses against edp-api's new TopologyYaml**

From the edp-api repo:

```bash
cd /home/resister/arcnode/edp-api && uv run python -c "
import yaml
from src.dtm.topology_yaml import TopologyYaml
raw = yaml.safe_load(open('/home/resister/arcnode/edp-module-assemblies/assemblies/compute-container/commercial-ac/topology.yaml').read())
t = TopologyYaml.model_validate(raw)
print(f'devices: {len(t.devices)}')
for d in t.devices:
    print(f'  {d.template}  {d.connection.host}:{d.connection.port}')
"
```

Expected: 13 devices listed, no errors.

- [ ] **Step 4: Commit in the assemblies repo**

```bash
cd /home/resister/arcnode/edp-module-assemblies
git add assemblies/compute-container/commercial-ac/topology.yaml
git commit -m "$(cat <<'EOF'
✨ feat: compute-container/commercial-ac topology.yaml new shape

Lock-step with edp-api PR 2 (canonical DTM rework). Drops per-device
protocol_config blocks (bindings now in edp-api/device_templates/).
device_type → template ref; host/port nest under connection. buses[]
empty for compute container at MVP.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

DO NOT push — coordinate with Task 6 + edp-api side.

---

## Task 6: Rewrite `grid-container/commercial-ac/topology.yaml`

**Repo:** `/home/resister/arcnode/edp-module-assemblies`

**File:** `assemblies/grid-container/commercial-ac/topology.yaml`

- [ ] **Step 1: Read the current file**

```bash
cat /home/resister/arcnode/edp-module-assemblies/assemblies/grid-container/commercial-ac/topology.yaml
```

Devices: switchgear (GRD-SWG-001), protective_relay (GRD-RLY-001), revenue_meter (GRD-MTR-001), dnp3_master_external (newly added).

**Important:** dnp3_master_external is deferred from PR 1 (no GRD-UTM-001 spec yet). Decision: drop it from this rewrite for now — PR 1's templates catalog doesn't include it, so Task 4's generator would fail templates_used resolution. Add a TODO comment in the file.

- [ ] **Step 2: Author the new-shape file**

```yaml
# Per-assembly grid-container device topology (PR 2 shape).
# SafeGear MV cells, SEL relay, ION9000 meter. Trihal is passive — its
# integrated thermometer is Modbus RTU which DTM v1 schema doesn't model
# (no MODBUS_RTU enum); add when a Modbus RTU/TCP gateway is selected.
#
# TODO: dnp3_master_external (utility DNP3 master) — deferred until
# edp-module-assemblies grows equipment/GRD-UTM-001/spec.yaml. The
# corresponding leaf template (`dnp3_master_external`) will land alongside.

devices:
  - template: switchgear
    description: ABB SafeGear 15kV cell (GRD-SWG-001)
    connection: { host: mock-modbus-server, port: 502, unit_id: "1" }

  - template: protective_relay
    description: SEL-351-7 distribution feeder relay (GRD-RLY-001)
    connection: { host: mock-dnp3-server, port: 20000 }

  - template: revenue_meter
    description: Schneider PowerLogic ION9000 (GRD-MTR-001)
    connection: { host: mock-modbus-server, port: 502, unit_id: "2" }

# AC interconnect bus: switchgear feeds revenue_meter via ION9000's voltage_in
# port; protective_relay shares the same line for trip permissive logic.
buses:
  - bus_id: ac_main
    type: ac
    members:
      - { device_template: switchgear, port: line_out }
      - { device_template: revenue_meter, port: VOLTAGE_IN }
      - { device_template: protective_relay, port: line_in }
```

Port names (`line_out`, `VOLTAGE_IN`, `line_in`) are placeholders — they reference `port_id`s that should appear in equipment/<id>/spec.yaml. Templates don't validate port refs at PR 2 (deferred). Pick names that match equipment spec port_ids when known (e.g. ION9000 spec has `VOLTAGE_IN`); use lowercase descriptive names otherwise.

- [ ] **Step 3: Validate parsing**

```bash
cd /home/resister/arcnode/edp-api && uv run python -c "
import yaml
from src.dtm.topology_yaml import TopologyYaml
raw = yaml.safe_load(open('/home/resister/arcnode/edp-module-assemblies/assemblies/grid-container/commercial-ac/topology.yaml').read())
t = TopologyYaml.model_validate(raw)
print(f'devices: {len(t.devices)}, buses: {len(t.buses)}')
for d in t.devices:
    print(f'  {d.template}')
for b in t.buses:
    print(f'  bus {b.bus_id} ({b.type}): {[m.device_template for m in b.members]}')
"
```

Expected: 3 devices, 1 bus with 3 members.

- [ ] **Step 4: Commit in the assemblies repo**

```bash
cd /home/resister/arcnode/edp-module-assemblies
git add assemblies/grid-container/commercial-ac/topology.yaml
git commit -m "$(cat <<'EOF'
✨ feat: grid-container/commercial-ac topology.yaml new shape

Lock-step with edp-api PR 2. switchgear + protective_relay +
revenue_meter under the new shape with connection blocks and an
ac_main bus declaration. dnp3_master_external dropped pending
GRD-UTM-001 spec.yaml (will return alongside that work).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: End-to-End Smoke + Final Pipeline

This task lives in edp-api and exercises Tasks 1-6 end-to-end.

- [ ] **Step 1: Add an integration test that loads both real assembly topology.yamls**

Create `tests/test_dtm_generator_e2e.py`:

```python
"""End-to-end DTM generation against real device_templates/ and assemblies/ topologies."""

from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID

import yaml

from src.bom_generator.manifest_models import (
    AssemblyVariant,
    Manifest,
    PlateUrls,
    ProfileAssemblies,
)
from src.dtm.dtm_generator_service import DtmGeneratorService
from src.dtm.template_loader import TemplateLoader
from src.shared.enums import (
    BessCoupling,
    ClimateZone,
    DeploymentProfile,
    EmsTarget,
    GpuVariant,
    SourcingTier,
)
from src.shared.schemas.dtm import EmsMode
from src.shared.schemas.module_resolution import ModuleResolution


def _client_against_real_assemblies() -> MagicMock:
    """Mocked manifest client returning the actual edp-module-assemblies topology.yamls."""
    client = MagicMock()
    client.fetch_manifest.return_value = Manifest(
        version="0.1.0",
        assemblies={
            "compute_container": {
                "commercial-ac": AssemblyVariant(
                    bom="s3://test/compute-container/commercial-ac/bom.yaml",
                    step="s3://test/compute-container/commercial-ac/assembly.step",
                    glb="s3://test/compute-container/commercial-ac/assembly.glb",
                    topology_yaml="s3://test/compute-container/commercial-ac/topology.yaml",
                )
            },
            "grid_container": {
                "commercial-ac": AssemblyVariant(
                    bom="s3://test/grid-container/commercial-ac/bom.yaml",
                    step="s3://test/grid-container/commercial-ac/assembly.step",
                    glb="s3://test/grid-container/commercial-ac/assembly.glb",
                    topology_yaml="s3://test/grid-container/commercial-ac/topology.yaml",
                )
            },
        },
        plates={"CG": PlateUrls(spec="s3://test/CG.yaml", step="s3://test/CG.step")},
        profiles={
            "commercial_ac": ProfileAssemblies(
                compute_container="commercial-ac",
                grid_container="commercial-ac",
                interface_plates=["CG"],
            )
        },
    )

    asm = Path("/home/resister/arcnode/edp-module-assemblies/assemblies")

    def fetch(url: str) -> dict:
        if "compute-container" in url:
            return yaml.safe_load(
                (asm / "compute-container/commercial-ac/topology.yaml").read_text()
            )
        if "grid-container" in url:
            return yaml.safe_load(
                (asm / "grid-container/commercial-ac/topology.yaml").read_text()
            )
        raise ValueError(url)

    client.fetch_topology_yaml.side_effect = fetch
    return client


def _resolution() -> ModuleResolution:
    return ModuleResolution(
        deployment_id=UUID("12345678-1234-1234-1234-123456789abc"),
        deployment_profile=DeploymentProfile.COMMERCIAL_AC,
        compute_container_count=1,
        grid_container_present=True,
        bess_coupling=BessCoupling.AC_COUPLED,
        bess_capacity_mwh=5.0,
        sourcing_tier=SourcingTier.COMMERCIAL,
        ems_target=EmsTarget.AWS_STANDARD,
        gpu_variant=GpuVariant.H100_SXM,
        gpu_count=56,
        climate_zone=ClimateZone.TEMPERATE,
    )


def test_e2e_commercial_ac_dtm_validates() -> None:
    # Arrange
    repo_root = Path(__file__).resolve().parents[1]
    catalog = TemplateLoader(root=repo_root / "device_templates").load_catalog()
    service = DtmGeneratorService(
        _client_against_real_assemblies(), template_catalog=catalog
    )
    # Act
    dtm = service.generate(profile="commercial_ac", resolution=_resolution())
    # Assert — top-level shape
    assert dtm.ems_mode == EmsMode.SIM
    # Module Devices exist
    assert "compute_module_1" in dtm.devices
    assert "grid_module_1" in dtm.devices
    # Compute leaves: 7 gpu_nodes + 1 cdu + 1 network_switch + 4 pdus = 13 + 1 module = 14
    compute_descendants = [
        s for s, d in dtm.devices.items() if d.parent == "compute_module_1"
    ]
    assert len(compute_descendants) == 13
    # Grid leaves: 3 + 1 module = 4
    grid_descendants = [
        s for s, d in dtm.devices.items() if d.parent == "grid_module_1"
    ]
    assert len(grid_descendants) == 3
    # Templates used
    assert "gpu_node" in dtm.templates_used
    assert "compute_module" in dtm.templates_used
    assert "grid_module" in dtm.templates_used
    # Buses: 1 ac_main from grid topology
    assert any(b.bus_id == "ac_main" for b in dtm.buses)
    bus = next(b for b in dtm.buses if b.bus_id == "ac_main")
    member_ids = {m.device_id for m in bus.members}
    assert "switchgear_1" in member_ids
    assert "revenue_meter_1" in member_ids
    assert "protective_relay_1" in member_ids


def test_e2e_pending_devices_empty_when_topology_has_no_sentinels() -> None:
    # Arrange
    repo_root = Path(__file__).resolve().parents[1]
    catalog = TemplateLoader(root=repo_root / "device_templates").load_catalog()
    service = DtmGeneratorService(
        _client_against_real_assemblies(), template_catalog=catalog
    )
    # Act
    dtm = service.generate(profile="commercial_ac", resolution=_resolution())
    # Assert
    assert dtm.pending_devices == []
```

- [ ] **Step 2: Run gate**

```bash
uv run poe checks && uv run poe unit && uv run poe integration
```

Both new e2e tests pass (depend on Tasks 5 + 6 being merged in the assemblies repo first; if not, the tests will fail because the real topology.yamls will still have the old shape).

- [ ] **Step 3: Commit (edp-api side)**

```bash
git add tests/test_dtm_generator_e2e.py
git commit -m "$(cat <<'EOF'
✅ test: end-to-end DTM emission against real assembly topologies

Asserts the real edp-module-assemblies topology.yamls (post-rewrite
in PR 2 Tasks 5+6) parse and yield a valid Dtm with the expected
device-id slugs, parent chains, embedded templates_used, and ac_main
bus expansion.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Push + CI on Both Repos

- [ ] **Step 1: Confirm both repos green locally**

```bash
cd /home/resister/arcnode/edp-api && uv run poe checks && uv run poe unit && uv run poe integration
```

(The assemblies repo doesn't have a Python CI; YAML files are validated by edp-api's tests.)

- [ ] **Step 2: Push edp-api**

```bash
cd /home/resister/arcnode/edp-api && git push
```

- [ ] **Step 3: Push edp-module-assemblies**

```bash
cd /home/resister/arcnode/edp-module-assemblies && git push
```

- [ ] **Step 4: Watch edp-api CI**

```bash
glab ci status
until glab ci status 2>&1 | grep -qE "passed|failed|canceled|skipped"; do sleep 15; done
glab ci status | tail -10
```

Expected: success.

- [ ] **Step 5: Confirm assemblies repo CI status (if it has any pipelines)**

```bash
cd /home/resister/arcnode/edp-module-assemblies && glab ci status 2>&1 | tail -10
```

May report no pipeline. Acceptable.

---

## Self-Review

**Spec coverage:**
- Canonical Dtm schema → Task 2
- Templates_used embedding → Task 4 generator + Task 7 e2e assertion
- Slug rule `{template}_{counter}` → Task 4 generator + Task 7 assertion
- Modules-as-Devices → Task 4 generator + Task 7 assertion
- buses[] expansion → Task 4 generator + Task 7 assertion
- Topology.yaml new shape → Tasks 5 + 6
- dtm_protocols.py deletion → Task 3

**Placeholder scan:**
- "TODO: dnp3_master_external" in grid topology.yaml is a real deferred item, not a plan placeholder.
- All step descriptions include concrete code.

**Type consistency:**
- `Connection` class name used consistently (not `ConnectionSpec` or similar).
- `Device.connection: Connection | None` matches Task 4's Optional handling.
- `templates_used: dict[str, DeviceTemplate]` keyed by template slug.
- BusMember has `device_id: str` (the slug, not UUID).

**Scope:** Single PR coordinated across two repos. Sub-projects B and C are separate plans.
