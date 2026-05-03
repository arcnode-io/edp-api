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
See [`platform-api`](https://gitlab.com/arcnode-io/platform-api) for platform api

## DTM Data Flow

DTM = stitched from two sources:

1. **`ConfiguratorPayload` -> `ModuleResolution`** — profile, container counts, sizing.
2. **Per-assembly topology yaml** (lives in `edp-module-assemblies` repo, fetched by URL from `hardware_selector_map.yaml`) — device list per assembly: `device_type`, `protocol_config`, `host`, `port`, `description`. Authoritative for SIM-mode network coords.

`dtm_generator` instantiates the topology N times (one per container instance), assigns `module_id` + `device_uuid = uuid5(deployment_id, ...)` for determinism, emits `Dtm` with `ems_mode=SIM`. ems-device-api owns LIVE flips (rewrites `host`/`port` on commissioning, increments `dtm_version`).

DTM is self-describing in both modes — EMS reads `(host, port)` and polls. No mode-aware lookups in EMS code.

## Artifacts

| #  | Artifact                      | URL Format(s)    | Source and Target                                                                             |
|----|-------------------------------|------------------|-----------------------------------------------------------------------------------------------|
| 1  | Bill of Materials             | json + xlsx      | created by internal BOM generator service and put into artifact_s3                            |
| 2  | Compute Container 3D          | step + glb       | selected from artifact_s3. put by edp-module-assemblies                                       |
| 3  | Grid Container 3D             | step + glb       | selected from artifact_s3 defense, commercial-dc, commercial-ac put by edp-module-assemblies  |
| 4  | Interface Plates              | step + dxf + pdf | fetched from artifact_s3. put by edp-module-assemblies                                        |
| 5  | Single Line Diagram           | dxf + pdf        | created by internal drawing_generator                                                         |
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
participant hardware_selector
participant bom_generator
participant dtm_generator
participant drawing_generator
participant installation_graph_generator
database artifact_s3

platform_api -> edp_api: POST /edp-api/jobs { ConfiguratorPayload }
edp_api -> platform_api: 202 { job_id, status_url, edp_artifact_urls[] }

edp_api -> module_resolver: ConfiguratorPayload
module_resolver -> edp_api: ModuleResolution

edp_api -> hardware_selector: select(profile)
hardware_selector -> edp_api: { compute_container, grid_container, interface_plates[] } urls

edp_api -> bom_generator: ModuleResolution
bom_generator -> artifact_s3: bom.json + bom.xlsx
bom_generator -> artifact_s3: cable_hose_schedule.json + .xlsx

edp_api -> dtm_generator: ModuleResolution
dtm_generator -> artifact_s3: dtm.json

edp_api -> drawing_generator: ModuleResolution
drawing_generator -> artifact_s3: sld.dxf + sld.pdf
drawing_generator -> artifact_s3: pid.dxf + pid.pdf

edp_api -> drawing_generator: ModuleResolution + dtm
drawing_generator -> artifact_s3: comms.dxf + comms.pdf

edp_api -> installation_graph_generator: ModuleResolution
installation_graph_generator -> artifact_s3: install_graph.dxf + .pdf

platform_api -> edp_api: GET /edp-api/jobs/{job_id}
edp_api -> platform_api: { status: complete, edp_artifact_urls[] }
```


## Source Layout

NestJS-style: each feature folder owns its `*_service.py` (work) + `*_module.py` (DI). 

```
src/
├── module_resolver/
│   ├── module_resolver_service.py   # ConfiguratorPayload → ModuleResolution
│   ├── deployment_profile.py        # profile derivation logic
│   └── module_resolver_module.py    # DI
├── bom/
│   ├── bom_generator_service.py     # ModuleResolution → bom.json/.xlsx + cable_hose_schedule
│   ├── bom_models.py                # BomLineItem, BomDocument, ScheduleEntry
│   └── bom_module.py
├── drawing/
│   ├── drawing_generator_service.py # SLD + P&ID + comms
│   ├── sld.py                       # single line diagram authoring
│   ├── pid.py                       # P&ID authoring
│   ├── comms.py                     # comms diagram authoring
│   └── drawing_module.py
├── installation_graph/
│   ├── installation_graph_service.py
│   └── installation_graph_module.py
├── dtm/
│   ├── dtm_generator_service.py     # ModuleResolution → dtm.json
│   ├── dtm_models.py                # Dtm, Module, Device, ProtocolConfig discriminated union
│   └── dtm_module.py
├── hardware_selector/
│   ├── hardware_selector_service.py # reads ../../hardware_selector_map.yaml at startup
│   └── hardware_selector_module.py
├── shared/
│   ├── schemas/
│   │   ├── configurator_payload.py
│   │   └── module_resolution.py
│   ├── enums.py                     # all StrEnums
│   └── utils/
│       ├── excel.py
│       └── dxf.py                   # ezdxf wrapper
├── pipeline/
│   ├── artifact_writer.py
│   ├── assembly_artifacts.py
│   ├── job_result.py
│   ├── pipeline_service.py
│   └── pipeline_module.py
├── jobs/
│   ├── job_record.py
│   ├── job_store.py
│   ├── jobs_service.py
│   ├── jobs_controller.py
│   └── jobs_module.py
├── app_controller.py
├── app_module.py
├── config.py
└── main.py
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
    # 11 profiles. dod_dc_int excluded — CATL-integrated PCS not DoD-procurable.
    COMMERCIAL_NO_BESS = "commercial_no_bess"
    COMMERCIAL_AC      = "commercial_ac"
    COMMERCIAL_DC_EXT  = "commercial_dc_ext"
    COMMERCIAL_DC_INT  = "commercial_dc_int"   # CATL — flag in notes upstream
    FEDERAL_NO_BESS    = "federal_no_bess"
    FEDERAL_AC         = "federal_ac"
    FEDERAL_DC_EXT     = "federal_dc_ext"
    FEDERAL_DC_INT     = "federal_dc_int"
    DOD_NO_BESS        = "dod_no_bess"
    DOD_AC             = "dod_ac"
    DOD_DC_EXT         = "dod_dc_ext"


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
# | sovereign_government | none               | federal_no_bess       |
# | sovereign_government | ac_coupled         | federal_ac            |
# | sovereign_government | dc_external_pcs    | federal_dc_ext        |
# | sovereign_government | dc_integrated_pcs  | federal_dc_int        |
# | defense_forward      | none               | dod_no_bess           |
# | defense_forward      | ac_coupled         | dod_ac                |
# | defense_forward      | dc_external_pcs    | dod_dc_ext            |
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


# === DTM ===

class EmsMode(StrEnum):
    SIM  = "sim"
    LIVE = "live"


class ProtocolKind(StrEnum):
    MODBUS_TCP = "modbus_tcp"
    DNP3_TCP   = "dnp3_tcp"
    SNMP       = "snmp"
    CANOPEN_GW = "canopen_gw"
    REDFISH    = "redfish"


class PointMap(BaseModel):
    name:           str
    function_code:  int   # modbus FC: 3=holding, 4=input, ...
    start_address:  int
    count:          int


class OidMap(BaseModel):
    name: str
    oid:  str


class PdoMap(BaseModel):
    name:        str
    cob_id:      int
    byte_offset: int
    byte_length: int


class RedfishResourceMap(BaseModel):
    name: str
    uri:  str   # e.g. "/redfish/v1/Chassis/1/Thermal"


class SnmpV3Creds(BaseModel):
    user:       str
    auth_proto: str   # SHA256, SHA512
    priv_proto: str   # AES128, AES256


class ModbusTcpConfig(BaseModel):
    protocol:   Literal[ProtocolKind.MODBUS_TCP]
    unit_id:    int
    point_maps: list[PointMap]


class Dnp3TcpConfig(BaseModel):
    protocol:        Literal[ProtocolKind.DNP3_TCP]
    master_addr:     int
    outstation_addr: int
    point_maps:      list[PointMap]


class SnmpConfig(BaseModel):
    protocol: Literal[ProtocolKind.SNMP]
    creds:    SnmpV3Creds
    oid_maps: list[OidMap]


class CanopenGwConfig(BaseModel):
    protocol:       Literal[ProtocolKind.CANOPEN_GW]
    gateway_vendor: str
    node_id:        int
    pdo_maps:       list[PdoMap]


class RedfishConfig(BaseModel):
    protocol:            Literal[ProtocolKind.REDFISH]
    username:            str
    password_secret_ref: str                       # ref into vault, never inline
    service_root:        str = "/redfish/v1"
    resource_maps:       list[RedfishResourceMap]


ProtocolConfig = Annotated[
    ModbusTcpConfig | Dnp3TcpConfig | SnmpConfig | CanopenGwConfig | RedfishConfig,
    Field(discriminator="protocol"),
]


class SizingParams(BaseModel):
    P_compute_total_kW:    float
    E_BESS_total_kWh:      float
    T_coolant_setpoint_C:  float


class Module(BaseModel):
    module_id:          str
    module_type:        str
    container_position: str
    description:        str


class Device(BaseModel):
    device_uuid:     UUID
    device_type:     str
    module_id:       str               # FK -> Module.module_id
    host:            str               # SIM: from assembly topology yaml; LIVE: ems-device-api rewrites
    port:            int               # SIM: from assembly topology yaml; LIVE: ems-device-api rewrites
    protocol_config: ProtocolConfig
    description:     str


class Dtm(BaseModel):
    deployment_uuid: UUID
    ems_mode:        EmsMode = EmsMode.SIM     # hardcoded SIM on initial emit; ems-device-api owns LIVE flip
    sizing_params:   SizingParams
    modules:         list[Module]
    devices:         list[Device]

    @model_validator(mode="after")
    def fk_modules(self) -> "Dtm":
        ids = {m.module_id for m in self.modules}
        for d in self.devices:
            if d.module_id not in ids:
                raise ValueError(f"device {d.device_uuid}: module_id {d.module_id!r} not in modules")
        return self
```

## Storage

Pipeline writes deterministic keys under shared `arcnode-artifacts` bucket:

```
s3://arcnode-artifacts/edp/{deployment_id}/{artifact_name}.{ext}
```

URLs are pure functions of `ConfiguratorPayload` — known at POST time, returned in `202` response. Generators are pure writers; write failure fails the whole job and platform-api retries.

`{artifact_name}` mapping (lowercase, snake_case):

| ArtifactKind         | artifact_name              |
|----------------------|----------------------------|
| BOM                  | `bom`                      |
| COMPUTE_CONTAINER_3D | `compute_container`        |
| GRID_CONTAINER_3D    | `grid_container`           |
| INTERFACE_PLATE      | `plate_{plate_id_lower}`   |
| SLD                  | `sld`                      |
| PID_COOLING          | `pid_cooling`              |
| COMMS_DIAGRAM        | `comms`                    |
| CABLE_HOSE_SCHEDULE  | `cable_hose_schedule`      |
| INSTALLATION_GRAPH   | `installation_graph`       |
| DTM                  | `dtm`                      |

Example: `s3://arcnode-artifacts/edp/{uuid}/plate_cg.step`


## Hardware Selector Maps

Profile -> assembly URLs lives at top-level [`hardware_selector_map.yaml`](hardware_selector_map.yaml). 11 profiles (`dod_dc_int` excluded — CATL exclusion). Loaded by `hardware_selector_service.py` at startup.

## Config

`cfg.yml` (per-env): only `s3_endpoint_url` — null in prod (real AWS), LocalStack URL in local/test.

```yaml
local:
  s3_endpoint_url: "http://localhost:4566"
beta:
  s3_endpoint_url: null
prod:
  s3_endpoint_url: null
```

`template-secrets.env` (committed; lists names only):

```dotenv
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
```

Region + credentials read from boto3 default chain. Bucket hardcoded `arcnode-artifacts`.
