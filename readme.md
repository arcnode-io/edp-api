# EDP API 📦📐

![](https://img.shields.io/gitlab/pipeline-status/arcnode-io/edp-api?branch=main&logo=gitlab)
![](https://gitlab.com/arcnode-io/edp-api/badges/main/coverage.svg)
![](https://img.shields.io/badge/ty_checked-gray?logo=astral)
![](https://img.shields.io/badge/3.13-gray?logo=python)
![](https://img.shields.io/badge/web_framework-fastapi-27a699)

> Stateless Engineering Deployment Package generator — sizing inputs in, 8 EDP artifacts out

## About

`edp-api` has a single responsibility: generate the Engineering Deployment Package. It takes a sizing payload and returns the 8 EDP artifacts (BoM, drawings, schedules, manifests). It does not handle email, delivery routing, ISO building, or CFN URL construction — those live in [`platform-api`](https://gitlab.com/arcnode-io/platform-api), which is the only client of this API.

The pipeline is stateless and deterministic. Same input → same artifacts.

See [`arcnode`](https://gitlab.com/arcnode-io/arcnode) for the system-level overview.

## Sequence

```plantuml
participant platform_api
participant edp_api
participant sizing_engine
participant bom_layer
participant drawing_layer
database artifact_store
participant interface_plates_cicd

interface_plates_cicd -> artifact_store: push updated plate drawings (dxf)

platform_api -> edp_api: POST /edp-api/jobs
edp_api -> platform_api: { job_id, status_url }
edp_api -> sizing_engine: compute module counts + sizes
sizing_engine -> bom_layer: structured sizing JSON
sizing_engine -> drawing_layer: structured sizing JSON
bom_layer -> artifact_store: BoM xlsx
drawing_layer -> artifact_store: SLD, P&ID, Comm Diagram
drawing_layer -> artifact_store: pull latest plate drawings
platform_api -> edp_api: GET /edp-api/jobs/{job_id}
edp_api -> platform_api: { status, edp_artifacts[] }
```

## Artifacts

| # | Artifact | Format | Producer | Notes |
|---|---|---|---|---|
| 1 | Bill of Materials | xlsx | bom_layer | Five sections: CUSTOM, ELEC, COOL, DATA, MECH (+ MODULE) |
| 2 | Interface Plate Drawings | dxf | drawing_layer | Plate variants selected by sizing engine, see `edp-interface-plates` |
| 3 | Single Line Diagram | pdf | drawing_layer | Electrical SLD |
| 4 | P&ID — Cooling System | pdf | drawing_layer | Coolant loop with sized pipe DN |
| 5 | Communication Network Diagram | dxf | drawing_layer | EMS comms backbone |
| 6 | Cable and Hose Schedule | xlsx | bom_layer | Lengths from standard range (1.0/1.5/2.0/3.0 m) |
| 7 | Installation Graph | pdf | drawing_layer | Sequenced install steps |
| 8 | Device Topology Manifest | json | comms_topology_service | Defines deployment_uuid, modules, devices, protocols, addresses. Consumed by `ems-device-api POST /topology`. |
