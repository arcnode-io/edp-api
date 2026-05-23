# EDP API 📦📐

![](https://img.shields.io/gitlab/pipeline-status/arcnode-io/edp-api?branch=main&logo=gitlab)
![](https://gitlab.com/arcnode-io/edp-api/badges/main/coverage.svg)
![](https://img.shields.io/badge/ty_checked-gray?logo=astral)
![](https://img.shields.io/badge/3.13-gray?logo=python)
![](https://img.shields.io/badge/web_framework-fastapi-27a699)

> Stateless Engineering Delivery Package generator — configurator inputs in, EDP artifacts out

## About

`edp-api` takes a `ConfiguratorPayload`, resolves the number and type of modules, and generates the Engineering Delivery Package. Use FastAPI background tasks.

Pipeline is stateless and deterministic. Same input → same artifacts. 

See [`arcnode`](https://gitlab.com/arcnode-io/arcnode) for system overview.
See [`platform-api`](https://gitlab.com/arcnode-io/platform-api) for platform api.
See [`docs/external-references.md`](docs/external-references.md) for the cross-repo ADRs, standards, and contracts this codebase consumes.

## DTM Data Flow

DTM = stitched from two sources:

1. **`ConfiguratorPayload` -> `ModuleResolution`** — profile, container counts, sizing.
2. **Per-assembly topology yaml** (lives in `edp-module-assemblies` repo, fetched by URL from the manifest resolved by `ManifestService`) — device list per assembly: `device_type`, `protocol_config`, `host`, `port`, `description`. Authoritative for SIM-mode network coords.

`dtm_generator` instantiates the topology N times (one per container instance), assigns `module_id` + `device_uuid = uuid5(deployment_id, ...)` for determinism, emits a `Dtm`. Mode (SIM / LIVE) is a computed property — LIVE iff every device is fully provisioned, SIM if any still holds `PROVISIONED_AT_COMMISSIONING`. No stored field; the data IS the signal. ems-device-api owns commissioning (customer POSTs valid `host`/`port` for each device).

DTM is self-describing in both modes — EMS reads `(host, port)` and polls. No mode-aware lookups in EMS code.

## Artifacts

| #  | Artifact                      | URL Format(s)    | Source and Target                                                                             |
|----|-------------------------------|------------------|-----------------------------------------------------------------------------------------------|
| 1  | Bill of Materials             | json + xlsx      | created by internal BOM generator service and put into artifact_s3                            |
| 2  | Compute Container 3D          | step + glb       | selected from artifact_s3. put by edp-module-assemblies                                       |
| 3  | Grid Container 3D             | step + glb       | selected from artifact_s3 defense, commercial-dc, commercial-ac put by edp-module-assemblies  |
| 4  | Interface Plates              | step + dxf + pdf | fetched from artifact_s3. put by edp-module-assemblies                                        |
| 5  | Single Line Diagram           | dxf + pdf        | created by internal drawing_generator (engineering deliverable)                               |
| 5b | SLD HMI Runtime SVG           | svg              | created by internal drawing_generator (per deployment, with `device_id`-bound element IDs for HMI MQTT binding + animation; served by `ems-device-api` at `GET /topology/sld.svg`) |
| 6  | P&ID — Cooling System         | dxf + pdf        | created by internal drawing_generator and put into artifact_s3                                |
| 7  | Communication Network Diagram | dxf + pdf        | created by internal drawing_generator and put into artifact_s3                                |
| 8  | Cable and Hose Schedule       | json + xlsx      | BomGenerator — derived from BOM lines + spec.yaml port/connection fields → artifact_s3        |
| 9  | Installation Graph            | dxf + pdf        | InstallationGraphGenerator -> artifact_s3                                                     |
| 10 | Device Topology Manifest      | json             | DTMGenerator -> artifact_s3                                                                   |




## Sequence

```plantuml
participant platform_api
participant edp_api
participant module_resolver
participant manifest_service
participant bom_generator
participant dtm_generator
participant drawing_generator
participant installation_graph_generator
database artifact_s3

platform_api -> edp_api: POST /edp-api/jobs { ConfiguratorPayload }
edp_api -> platform_api: 202 { job_id, status_url, edp_artifact_urls[] }

edp_api -> module_resolver: ConfiguratorPayload
module_resolver -> edp_api: ModuleResolution

edp_api -> manifest_service: resolve(profile)
manifest_service -> edp_api: ResolvedProfile { compute, grid, plates[] } urls

edp_api -> bom_generator: ModuleResolution
bom_generator -> artifact_s3: bom.json + bom.xlsx
bom_generator -> artifact_s3: cable_hose_schedule.json + .xlsx

edp_api -> dtm_generator: ModuleResolution
dtm_generator -> artifact_s3: dtm.json

edp_api -> drawing_generator: ModuleResolution
drawing_generator -> artifact_s3: sld.dxf + sld.pdf
drawing_generator -> artifact_s3: sld_hmi.svg
drawing_generator -> artifact_s3: pid.dxf + pid.pdf

edp_api -> drawing_generator: ModuleResolution + dtm
drawing_generator -> artifact_s3: comms.dxf + comms.pdf

edp_api -> installation_graph_generator: ModuleResolution
installation_graph_generator -> artifact_s3: install_graph.dxf + .pdf

platform_api -> edp_api: GET /edp-api/jobs/{job_id}
edp_api -> platform_api: { status: complete, edp_artifact_urls[] }
```

**Current state:** BOM (json + xlsx), DTM, SLD HMI SVG, and SLD
engineering (dxf + pdf) are real generators. P&ID, comms,
installation_graph, and cable_hose_schedule land as `_stub_body` bytes
from `PipelineService` for now — URLs are deterministic and reserved,
content is a placeholder. Real generators drop in one ArtifactKind at a
time without changing the pipeline shape.

The engineering SLD is a paper-grade deliverable: IEC 60617 graphical
symbols, ISO 5457 sheet frame, simplified ISO 7200 title block on A3
landscape. It and the SLD HMI SVG share the same DTM source and the
same IEC 61850 introspection rules (see `src/drawing/_iec_61850.py`) —
device set, bus list, and source-side identification are guaranteed to
agree between the two artifacts by construction.

## SLD HMI SVG re-render endpoint

`POST /edp-api/sld-hmi-svg` takes a `Dtm` JSON body and returns SVG bytes
(`image/svg+xml`). Stateless and idempotent — same DTM in, same SVG out.

Used by `ems-device-api` after applying runtime topology CRUD: device-api
mutates its cached DTM (add/remove/update equipment), POSTs the updated
DTM here, gets a fresh SVG back, and serves it at `GET /topology/sld.svg`
without re-running the full EDP pipeline. Keeps the SVG-authoring logic in
one place — device-api doesn't duplicate or mutate SVG bytes itself.


## Source Layout

NestJS-style: each feature folder owns its `*_service.py` (work) + `*_module.py` (DI).

```
src/
├── module_resolver/
│   ├── module_resolver_service.py   # ConfiguratorPayload → ModuleResolution
│   ├── deployment_profile.py        # (context, bess_coupling) → DeploymentProfile
│   └── module_resolver_module.py
├── bom_generator/
│   ├── bom_generator_service.py     # ModuleResolution → bom.json
│   ├── bom_models.py                # BomLineItem, BomDocument
│   ├── manifest_service.py          # profile → ResolvedProfile lookups
│   ├── manifest_client.py           # S3 fetch + upload wrapper (also handles DTM/SVG bytes)
│   ├── manifest_module.py
│   └── manifest_models.py           # Pydantic mirror of edp-module-assemblies/manifest.yaml
├── dtm/
│   ├── dtm_generator_service.py     # profile + ModuleResolution → Dtm
│   ├── dtm_generator_internals.py   # emit_container, collect_templates_used, sizing
│   ├── template_loader.py           # walks device_templates/, builds catalog at startup
│   └── topology_yaml.py             # per-assembly topology.yaml schema
├── drawing/
│   ├── sld_hmi_svg_service.py       # Dtm → SLD HMI SVG (graphviz dot layout)
│   ├── sld_engineering_service.py   # Dtm → SLD engineering DXF + PDF (ezdxf + matplotlib)
│   ├── drawing_controller.py        # POST /edp-api/sld-hmi-svg re-render endpoint
│   ├── drawing_module.py
│   ├── _layout.py                   # dot-graph layout helpers (HMI)
│   ├── _svg.py                      # SVG element builders (HMI)
│   ├── _iec_61850.py                # IEC 61850 introspection — shared by both SLDs
│   ├── _sld_eng_symbols.py          # IEC 60617 graphical symbol primitives
│   ├── _sld_eng_layout.py           # A3 grid placement, source-first per bus
│   └── _sld_eng_title_block.py      # ISO 5457 frame + ISO 7200-lite title block
├── pipeline/
│   ├── artifact_urls.py             # ResolvedProfile → list[ArtifactRef] (deterministic URLs)
│   └── pipeline_service.py          # BackgroundTask: generate + upload per ArtifactRef
├── jobs/
│   ├── jobs_controller.py
│   ├── jobs_service.py
│   ├── job_store.py                 # in-memory dict, swap-targeted
│   └── jobs_module.py
├── call_api/                        # external API client skeleton (sample)
├── shared/
│   ├── enums.py                     # all StrEnums
│   └── schemas/
│       ├── configurator_payload.py
│       ├── module_resolution.py
│       ├── artifact.py              # ArtifactKind, ArtifactRef, JobCreated, JobResult, JobStatus
│       ├── dtm.py                   # Dtm + Device (parent-chain, computed mode)
│       ├── dtm_primitives.py        # SizingParams, Bus, Connection, PROVISIONED_AT_COMMISSIONING
│       ├── template.py              # DeviceTemplate + Command + Fanout + ContainsEntry
│       ├── template_protocols.py    # Binding discriminated union
│       ├── measurement.py           # Measurement + Publisher
│       └── measurement_ranges.py    # Bounds + Thresholds
├── app_controller.py
├── app_module.py
├── config.py
└── main.py

device_templates/                    # bundled with image, loaded at startup
├── leaf/                            # 11 leaf templates (gpu_node, bess_rack, switchgear, ...)
└── module/                          # 3 module templates (compute_module, bess_module, grid_module)
```


## Core Types
```python

# === Enums ===

class EnergySource(StrEnum):
    NUCLEAR = "nuclear"
    SOLAR = "solar"
    GRID_HYBRID = "grid_hybrid"
    OFF_GRID = "off_grid"


class PrimaryWorkload(StrEnum):
    AI_TRAINING = "ai_training"
    AI_INFERENCE = "ai_inference"
    MIXED = "mixed"


class GpuVariant(StrEnum):
    H100_SXM = "h100_sxm"
    B200 = "b200"


class BessCoupling(StrEnum):
    AC_COUPLED = "ac_coupled"
    DC_INTEGRATED_PCS = "dc_integrated_pcs"
    DC_EXTERNAL_PCS = "dc_external_pcs"
    NONE = "none"


class GridConnection(StrEnum):
    NONE = "none"
    GRID_TIED = "grid_tied"
    GRID_BACKUP = "grid_backup"


class ClimateZone(StrEnum):
    SUBARCTIC = "subarctic"
    TEMPERATE = "temperate"
    ARID_HOT = "arid_hot"
    TROPICAL = "tropical"


class DeploymentContext(StrEnum):
    COMMERCIAL = "commercial"
    SOVEREIGN_GOVERNMENT = "sovereign_government"
    DEFENSE_FORWARD = "defense_forward"


class AwsPartition(StrEnum):
    STANDARD = "standard"
    GOVCLOUD = "govcloud"
    NONE = "none"


class SourcingTier(StrEnum):
    COMMERCIAL = "commercial"
    FEDERAL_CIVILIAN = "federal_civilian"
    DOD_ELIGIBLE = "dod_eligible"


class EmsTarget(StrEnum):
    AWS_STANDARD = "aws_standard"
    AWS_GOVCLOUD = "aws_govcloud"
    AIR_GAPPED = "air_gapped"


class DeploymentProfile(StrEnum):
    # 7 profiles — mirrors edp-module-assemblies/manifest_profiles.yaml.
    # defense_dc_int excluded: CATL-integrated PCS not procurable for any
    # federal/defense customer (sovereign_government + defense_forward
    # both rejected at validator). Hardware variants are commercial vs
    # defense only; SourcingTier tracks the federal_civilian vs
    # dod_eligible procurement-path distinction separately.
    COMMERCIAL_NO_BESS = "commercial_no_bess"
    COMMERCIAL_AC      = "commercial_ac"
    COMMERCIAL_DC_EXT  = "commercial_dc_ext"
    COMMERCIAL_DC_INT  = "commercial_dc_int"   # CATL — commercial only
    DEFENSE_NO_BESS    = "defense_no_bess"
    DEFENSE_AC         = "defense_ac"
    DEFENSE_DC_EXT     = "defense_dc_ext"


# === Schemas ===

class ConfiguratorPayload(BaseModel):
    deployment_id: UUID

    operator_org: str
    deployment_site_name: str
    contact_email: EmailStr

    energy_source: EnergySource
    source_capacity_mw: float = Field(gt=0)

    primary_workload: PrimaryWorkload
    gpu_variant: GpuVariant
    target_gpu_count: int = Field(ge=1)   # round-up to full container handles small values

    bess_coupling: BessCoupling
    bess_capacity_mwh: float = Field(ge=0)

    grid_connection: GridConnection
    climate_zone: ClimateZone
    deployment_context: DeploymentContext
    aws_partition: AwsPartition

    @model_validator(mode="after")
    def bess_consistency(self) -> "ConfiguratorPayload":
        # Reason: NONE coupling ⇔ zero capacity. Catch contradictions at ingress.
        if (self.bess_coupling == BessCoupling.NONE) != (self.bess_capacity_mwh == 0):
            raise ValueError("bess_coupling=NONE iff bess_capacity_mwh=0")
        return self

    @model_validator(mode="after")
    def standard_partition_commercial_only(self) -> "ConfiguratorPayload":
        # Reason: federal/defense workloads cannot run in commercial AWS regions.
        if self.aws_partition == AwsPartition.STANDARD and self.deployment_context != DeploymentContext.COMMERCIAL:
            raise ValueError("aws_partition=standard only valid for deployment_context=commercial")
        return self

    @model_validator(mode="after")
    def dod_excludes_dc_integrated_pcs(self) -> "ConfiguratorPayload":
        # Reason: integrated DC PCS is CATL-only; CATL excluded from DoD procurement.
        if self.deployment_context == DeploymentContext.DEFENSE_FORWARD and self.bess_coupling == BessCoupling.DC_INTEGRATED_PCS:
            raise ValueError("defense_forward + dc_integrated_pcs is not procurable (CATL exclusion)")
        return self


class ModuleResolution(BaseModel):
    deployment_id: UUID

    deployment_profile: DeploymentProfile

    compute_container_count: int = Field(ge=1)
    grid_container_present: bool

    bess_coupling: BessCoupling
    bess_capacity_mwh: float

    sourcing_tier: SourcingTier
    ems_target: EmsTarget

    gpu_variant: GpuVariant
    gpu_count: int
    climate_zone: ClimateZone


# === Profile Resolution ===
#
# (deployment_context, bess_coupling) -> DeploymentProfile
#
# | deployment_context   | bess_coupling      | -> deployment_profile |
# |----------------------|--------------------|-----------------------|
# | commercial           | none               | commercial_no_bess    |
# | commercial           | ac_coupled         | commercial_ac         |
# | commercial           | dc_external_pcs    | commercial_dc_ext     |
# | commercial           | dc_integrated_pcs  | commercial_dc_int     |
# | sovereign_government | none               | defense_no_bess       |
# | sovereign_government | ac_coupled         | defense_ac            |
# | sovereign_government | dc_external_pcs    | defense_dc_ext        |
# | sovereign_government | dc_integrated_pcs  | INVALID — reject 422  |
# | defense_forward      | none               | defense_no_bess       |
# | defense_forward      | ac_coupled         | defense_ac            |
# | defense_forward      | dc_external_pcs    | defense_dc_ext        |
# | defense_forward      | dc_integrated_pcs  | INVALID — reject 422  |
#
# (deployment_context) -> SourcingTier   1:1
# (aws_partition)      -> EmsTarget      1:1
#
# compute_container_count = ceil(target_gpu_count / GPUS_PER_COMPUTE_CONTAINER)
# gpu_count               = compute_container_count * GPUS_PER_COMPUTE_CONTAINER

GPUS_PER_COMPUTE_CONTAINER: Final[int] = 56   # 7 nodes × 8 GPUs, both H100_SXM and B200


# === Job & Response ===

class JobStatus(StrEnum):
    RUNNING  = "running"
    COMPLETE = "complete"
    FAILED   = "failed"


class ArtifactKind(StrEnum):
    BOM                  = "bom"
    COMPUTE_CONTAINER_3D = "compute_container_3d"
    GRID_CONTAINER_3D    = "grid_container_3d"
    INTERFACE_PLATE      = "interface_plate"
    SLD                  = "sld"
    SLD_HMI_SVG          = "sld_hmi_svg"
    PID_COOLING          = "pid_cooling"
    COMMS_DIAGRAM        = "comms_diagram"
    CABLE_HOSE_SCHEDULE  = "cable_hose_schedule"
    INSTALLATION_GRAPH   = "installation_graph"
    DTM                  = "dtm"


class ArtifactRef(BaseModel):
    kind:     ArtifactKind
    format:   str                 # json | xlsx | dxf | pdf | step | glb
    url:      str
    plate_id: str | None = None   # only when kind=INTERFACE_PLATE


class JobCreated(BaseModel):
    job_id:              UUID
    status_url:          str
    edp_artifact_urls:   list[ArtifactRef]   # deterministic, known at POST time


class JobResult(BaseModel):
    status:              JobStatus
    edp_artifact_urls:   list[ArtifactRef]
    error:               str | None = None   # set when status=FAILED


# === DTM (ADR-002 §7 canonical shape) ===
#
# DTM is parent-chain Devices keyed by snake_case slug, with embedded
# templates_used catalog and buses[] for electrical topology. Mode is
# derived from device placeholders — not stored.

class EmsMode(StrEnum):
    SIM  = "sim"
    LIVE = "live"


PROVISIONED_AT_COMMISSIONING: Final[int] = -1   # sentinel for not-yet-provisioned int fields

ProvisionedInt = int                            # int | PROVISIONED_AT_COMMISSIONING sentinel


class BlockingKind(StrEnum):
    # What lifecycle transition a missing device blocks.
    LIVE_MODE                 = "live_mode"
    COMMISSIONING_COMPLETE    = "commissioning_complete"


class SizingParams(BaseModel):
    P_compute_total_kW:   float
    E_BESS_total_kWh:     float
    T_coolant_setpoint_C: float


class Connection(BaseModel):
    # Per-instance runtime params. SIM = from assembly topology yaml;
    # LIVE = ems-device-api rewrites at commissioning.
    host:    str
    port:    ProvisionedInt
    unit_id: str | None = None   # modbus unit_id, dnp3 outstation, etc.


class BusMember(BaseModel):
    device_id: str
    port:      str | None = None   # references a port_id on the device's equipment


class Bus(BaseModel):
    bus_id:  str
    type:    Literal["dc", "ac"]
    members: list[BusMember]


class Device(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id:    str               # snake_case slug (ADR §9)
    template:     str               # ref into Dtm.templates_used
    parent:       str | None = None # FK to another Device.device_id
    display_name: str | None = None
    connection:   Connection | None = None
    blocking:     list[BlockingKind] = Field(default_factory=lambda: [BlockingKind.LIVE_MODE])
    extra_measurements: dict[str, Measurement] | None = None   # ADR §7 escape hatch

    @computed_field
    @property
    def has_placeholders(self) -> bool:
        # True iff any field (incl. nested connection) holds PROVISIONED_AT_COMMISSIONING.
        ...

    @computed_field
    @property
    def mode(self) -> EmsMode:
        return EmsMode.SIM if self.has_placeholders else EmsMode.LIVE


class Dtm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version:         str = "1.0.0"     # edp-api emits 1.0.0; ems-device-api owns later bumps
    deployment_uuid: UUID
    sizing_ref:      str | None = None
    sizing_params:   SizingParams
    devices:         dict[str, Device]              # keyed by device_id
    buses:           list[Bus]
    templates_used:  dict[str, DeviceTemplate]      # catalog snapshot, keyed by template slug

    @computed_field
    @property
    def mode(self) -> EmsMode:
        # LIVE iff every device fully provisioned; SIM if any placeholders remain.
        ...

    @computed_field
    @property
    def pending_devices(self) -> list[Device]:
        # Devices still carrying placeholder values.
        ...

    @model_validator(mode="after")
    def parent_chain_resolves(self) -> "Dtm": ...   # every parent in devices

    @model_validator(mode="after")
    def template_refs_resolve(self) -> "Dtm": ...   # every device.template in templates_used

    @model_validator(mode="after")
    def bus_members_resolve(self) -> "Dtm": ...     # every bus member device_id in devices


# === Protocol bindings live on DeviceTemplate.measurements, not on Device ===
#
# `template_protocols.Binding` is a discriminated union over `protocol:`:
#   ModbusBinding | Dnp3Binding | SnmpBinding | CanopenBinding | RedfishBinding | SyntheticBinding
#
# Templates own per-measurement protocol details (Modbus FC + address,
# DNP3 group/variation/index, SNMP OID, …). Device instances contribute
# deployment specifics (host, port, parent, display_name). The split lets
# the same physical device class be reused across deployments without
# duplicating binding info per instance.
```

## Storage

Pipeline writes deterministic keys under shared `arcnode-artifacts` bucket:

```
s3://arcnode-artifacts/edp/{deployment_id}/{artifact_name}.{ext}
```

URLs are pure functions of `ConfiguratorPayload` — known at POST time, returned in the `202` response. Generators are pure writers; any per-artifact failure flips the whole job to FAILED. See §Failure Model for the retry contract.

`{artifact_name}` mapping (lowercase, snake_case):

| ArtifactKind         | artifact_name              |
|----------------------|----------------------------|
| BOM                  | `bom`                      |
| COMPUTE_CONTAINER_3D | `compute_container`        |
| GRID_CONTAINER_3D    | `grid_container`           |
| INTERFACE_PLATE      | `plate_{plate_id_lower}`   |
| SLD                  | `sld`                      |
| SLD_HMI_SVG          | `sld_hmi`                  |
| PID_COOLING          | `pid_cooling`              |
| COMMS_DIAGRAM        | `comms`                    |
| CABLE_HOSE_SCHEDULE  | `cable_hose_schedule`      |
| INSTALLATION_GRAPH   | `installation_graph`       |
| DTM                  | `dtm`                      |

Example: `s3://arcnode-artifacts/edp/{uuid}/plate_cg.step`


## Failure Model

`JobStore` is an in-memory dict — single replica, no durability. By design.
The pipeline is deterministic (artifact URLs are pure functions of
`ConfiguratorPayload`), so the artifact bytes in S3 are the only state that
matters. The job record is a status projection over the in-flight write.

**Contract with platform-api:**

| Event | platform-api action |
|---|---|
| `POST /edp-api/jobs` returns 202 | Stash `job_id` + `edp_artifact_urls`; begin polling `status_url`. |
| `GET /edp-api/jobs/{id}` → `RUNNING` | Keep polling. |
| `GET /edp-api/jobs/{id}` → `COMPLETE` | Job done. Fetch artifact URLs. |
| `GET /edp-api/jobs/{id}` → `FAILED` | Pipeline raised. `error` field carries the message. Decide: retry the original payload or surface to user. |
| `GET /edp-api/jobs/{id}` → `404` | edp-api restarted between POST and poll, losing the in-memory record. Re-POST the original payload; you'll get a new `job_id`, and the pipeline writes the same S3 keys (idempotent at the artifact level). |
| Poll timeout exceeded with no terminal status | Same recovery — re-POST. Two concurrent runs over the same payload race on the same S3 keys; last writer wins, bytes are equivalent. |

**Why ephemeral:** durable JobStore (DDB / Postgres) would preserve a status
record but no artifact data — the artifacts already are the persistent state.
Adding a database creates the appearance of state worth preserving across
restart when none exists. Revisit only if multi-replica + cross-replica
job-status queries become a real product need.

**Idempotency posture (POST /edp-api/jobs):**

POST is **not** server-side idempotent on `deployment_id`. Every POST gets
a fresh `job_id`, even with identical `ConfiguratorPayload`. The pipeline
writes to deterministic S3 keys derived from `deployment_id`, so re-POSTing
the same payload overwrites the same bytes — safe because the pipeline is
deterministic (same input → same bytes). Race between two concurrent POSTs
with the same payload: last writer wins, bytes are equivalent.

What this means for platform-api:
- Safe to retry on timeout / 404 without coordination.
- No 409 to handle — duplicate POSTs always succeed.
- Two parallel POSTs of the same payload waste compute (two pipelines run
  + two S3 writes per artifact) but don't corrupt output.

If platform-api wants single-flight semantics (one pipeline run per
deployment_id), enforce it client-side with a `deployment_id` lock. This
service intentionally doesn't.


## Manifest

Profile → assembly URLs lives in `edp-module-assemblies` repo as `manifest.yaml`, published to S3. `ManifestClient` fetches it from `cfg.manifest_url` on demand. `JobsService.create` calls `fetch_manifest()` once per job, wraps the snapshot in a `ManifestService` for `.resolve(profile_str)` (which returns a `ResolvedProfile` with concrete `AssemblyVariant` + `list[ResolvedPlate]`), and pins the Manifest on the `JobRecord` so `PipelineService` + `DtmGeneratorService` see the same snapshot at emit time. Closes ADR-012's torn-read mitigation by construction; no app-level cache.

`DeploymentProfile` enum and `manifest_profiles.yaml` are both at the same 7 profiles (4 commercial, 3 defense). Adding a profile to the enum without a matching `manifest_profiles.yaml` entry surfaces as a KeyError at `JobsService.create` — fail-fast at intake.

## Config

`cfg.yml` (per-env): uvicorn host/port + log level, hot-reload toggle, e2e flag, and `manifest_url` pointing at the `edp-module-assemblies` manifest object in S3.

```yaml
local:
  log_level: DEBUG
  host: '127.0.0.1'
  port: 8000
  e2e: false
  reload: true
  manifest_url: 's3://arcnode-artifacts/manifest.yaml'
beta:
  log_level: INFO
  host: '0.0.0.0'
  port: 8000
  e2e: true
  reload: false
  manifest_url: 's3://arcnode-artifacts/manifest.yaml'
```

`template-secrets.env` (committed; lists names only — actual values come from environment):

```dotenv
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
```

Region + credentials read from boto3 default chain. Bucket hardcoded `arcnode-artifacts`. LocalStack endpoint used by integration tests is injected via `S3_ENDPOINT_URL` env at test time, not stored in `cfg.yml`.

## Runtime Dependencies

Two native dependencies are required at runtime:

- **`graphviz`** (`dot` binary) — used by `SldHmiSvgService` for the runtime SVG's hierarchical layout. Production Dockerfile installs whatever Debian-slim ships (`apt install graphviz`); local dev = `pacman -S graphviz` / `apt install graphviz` / `brew install graphviz`. The HMI consumes the SVG by element id + `data-*` attributes, so layout-coordinate differences across `dot` versions don't break the runtime contract.
- **TrueType fonts** (`fonts-liberation`, `fonts-dejavu-core`) — used by `SldEngineeringService` matplotlib backend to rasterize MTEXT in the engineering PDF. Debian-slim ships no fonts by default; the Dockerfile installs both. Local dev usually already has these via the OS.

Snapshot tests (`src/drawing/test_sld_hmi_svg_snapshots.py`) ARE byte-sensitive to `dot` major version. Dev + CI must align (currently `graphviz` 13.x); regenerate baselines with `uv run pytest src/drawing/test_sld_hmi_svg_snapshots.py --snapshot-update` and review the diff in the PR.
