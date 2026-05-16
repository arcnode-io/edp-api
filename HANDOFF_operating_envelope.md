# Handoff: operating_envelope + line_rating templates + publisher schema rename

> **Audience:** industrial-engineer agent
> **Three coupled deliverables in one stream:** (A) publisher-identity schema rename across two repos, (B) new `operating_envelope` leaf template (DOE per IEEE 2030.5), (C) new `line_rating` leaf template (per IEEE 738). Do A first — B and C both use the new enum value.

## Why

`line_controller` (current publisher identity in AsyncAPI schema) is a coined shorthand. It conflates two distinct standards-track concepts:

- **DOE (Dynamic Operating Envelope)** per IEEE 2030.5 / CSIP-AUS — `opModImpLimW`, `opModExpLimW` at a connection point, in **watts**. Canonical industry term per AEMO, AER, CSIP-AUS Explainer v1.2, MDPI 2025 review.
- **Line rating** per IEEE 738 — conductor ampacity, in **amps**. Subdivided into:
  - **DLR (Dynamic Line Rating)** — temp + wind + solar + sag, voluntary. FERC moving toward.
  - **AAR (Ambient-Adjusted Rating)** — temperature + forecast only, hourly. FERC Order 881 **mandates** this, not DLR.

Producer repo `dlr-operating-envelope` (renamed from `dlr-utility-envelope`) does **full IEEE 738** locally (ambient + solar + rain → DLR), then derives DOE limits in watts at the POI. So this single producer publishes **both** line_rating (amps) AND operating_envelope (watts).

## A. Schema rename `line_controller` → `operating_envelope`

`line_controller` was the placeholder publisher identity. Rename to match the canonical role (publisher of operating envelope + line rating data).

**Affected repos:**

| Repo | File | Count | Kind |
|---|---|---:|---|
| `ems-device-api` | `src/templates/template.schema.ts` | 4 | enum + const map |
| `ems-device-api` | `src/templates/template.schema.test.ts` | 11 | tests |
| `ems-device-api` | `src/templates/template_loader.service.test.ts` | 1 | fixture |
| `ems-device-api` | `src/topology/dtm.schema.test.ts` | 1 | fixture |
| `ems-device-api` | `tests/fixtures/templates.ts` | ? | recheck |
| `ems-device-api` | `tests/mqtt.test.ts` | 1 | test |
| `ems-device-api` | `tests/seed.test.ts` | 1 | test |
| `ems-device-api` | `tests/topology.test.ts` | 2 | test |
| `ems-device-api` | `readme.md` L88, L94, L99, L102, L107 | 5 | sequence diagrams |
| `edp-api` | `src/shared/schemas/measurement.py` | 3 | `Publisher.LINE_CONTROLLER` enum + prose L4, L31 (`line-controller/analyst`) |
| `edp-api` | `src/shared/schemas/template.py` | 3 + 2 prose (L65, L85: `line-controller`/`line-controller-handled`) |
| `ems` | `system_adr.md` L41, L42 | 2 | prose in language-used section (`line-controller-pst`, `line-controller-dlr` → `dlr-pst-sim`, `dlr-operating-envelope`) |
| `edp-api` | `src/shared/schemas/test_template.py` | 4 | tests |
| `edp-api` | `src/shared/schemas/test_template_measurement_command.py` | 6 | tests |
| `edp-api` | `device_templates/module/bess_module.yaml` | 5 | `publisher:`/`fanout:` |
| `edp-api` | `device_templates/module/grid_module.yaml` | 3 | same |
| `edp-api` | `device_templates/module/compute_module.yaml` | 2 | same |

**Total:** ~50 occurrences. Verify with `grep -rn 'line_controller\|LINE_CONTROLLER' --include='*.{ts,py,yaml,md}'` in each repo before/after.

**Rename pattern:**

```
"line_controller"   → "operating_envelope"     (snake_case enum value)
LINE_CONTROLLER     → OPERATING_ENVELOPE       (enum identifier)
Publisher.LINE_CONTROLLER → Publisher.OPERATING_ENVELOPE

"line-controller"   → "operating-envelope"     (kebab in prose/docstrings)
"line-controller-dlr"  → "dlr-operating-envelope"   (repo name in prose)
"line-controller-pst"  → "dlr-pst-sim"               (repo name in prose)
```

**AsyncAPI contract impact:** publisher value string changes. Channel paths + payload schemas unchanged. Consumers (`ems-industrial-gateway`, `ems-hmi`) parse `/asyncapi` at runtime; verify HMI doesn't hardcode `"line_controller"` for filter/display.

## B. New leaf template `operating_envelope.yaml`

**Path:** `edp-api/device_templates/leaf/operating_envelope.yaml`
**Spec basis:** IEEE 2030.5 DERControlBase + CSIP-AUS

```yaml
template: operating_envelope
kind: leaf
description: Utility-published DOE per IEEE 2030.5 / CSIP-AUS (DERControlBase)

measurements:
  import_limit:                # opModImpLimW (IEEE 2030.5 § DERControlBase)
    unit: watts
    type: float
    poll_rate_hz: 1            # OPEN Q5
    display_name_default: "Import Limit"
    binding:
      protocol: mqtt_sub       # OPEN Q3
      topic: <see Q2>
      data_type: float

  export_limit:                # opModExpLimW
    unit: watts
    type: float
    poll_rate_hz: 1
    display_name_default: "Export Limit"
    binding: {...}

  status:
    unit: none
    type: enum
    poll_rate_hz: 1
    display_name_default: "Status"
    values: { 0: OK, 1: STALE, 2: INVALID, 3: COMM_FAIL }
    binding: {...}
```

## C. New leaf template `line_rating.yaml`

**Path:** `edp-api/device_templates/leaf/line_rating.yaml`
**Spec basis:** IEEE 738. Distinct from DOE — different domain (transmission line ampacity vs DER export limits at POI).

```yaml
template: line_rating
kind: leaf
description: Utility-published rating per IEEE 738 (DLR or AAR)

measurements:
  dynamic_line_rating:         # OR ambient_adjusted_rating — see Q1
    unit: amps
    type: float
    poll_rate_hz: 1            # OPEN Q5
    display_name_default: "Dynamic Line Rating"
    binding: {...}

  # Conditional — include only if publisher emits as distinct quantity (see Q4):
  # network_thermal_headroom:
  #   unit: amps
  #   type: float
  #   poll_rate_hz: 1
  #   display_name_default: "Network Thermal Headroom"
  #   binding: {...}

  status:
    unit: none
    type: enum
    poll_rate_hz: 1
    display_name_default: "Status"
    values: { 0: OK, 1: STALE, 2: INVALID, 3: COMM_FAIL }
    binding: {...}
```

## Open questions (resolve before implementing)

1. **DLR or AAR for `dlr-operating-envelope` producer?**
   The producer does full IEEE 738 with ambient + solar + rain → genuine DLR. Field name `dynamic_line_rating` is correct. If a future upstream publisher only emits temperature-adjusted, use `ambient_adjusted_rating`. Confirm what your sim publishes.

2. **MQTT topic shape.**
   Existing dlr publish pattern (per `dlr-operating-envelope/readme.md`):
   ```
   sites/{site_id}/devices/{device_id}/measurements/{name}/{unit}
   ```
   Match this for both templates, or carve a new topic family for DOE (e.g., `sites/{site_id}/poi/{poi_id}/envelope/...`)? DOE is POI-scoped, not device-scoped — may warrant separate hierarchy.

3. **Binding protocol for self-publishing devices.**
   Existing leaf templates (`revenue_meter.yaml`) use `modbus_tcp` etc. — gateway dials those. `operating_envelope` and `line_rating` self-publish to MQTT. Need new binding value (`mqtt_sub`? `native_mqtt`? `none`?) — check `ems-industrial-gateway` for what it expects on the consumer side.

4. **`network_thermal_headroom` — drop or include?**
   - If consumer-derived (`limit − site_flow`) → drop, consumer computes.
   - If publisher emits as distinct quantity (capacity remaining on segment upstream of POC, per ENWL Technical Limits methodology / Gridsight) → include in `line_rating.yaml` as `unit: amps`.
   - Confirm what `dlr-operating-envelope` publisher actually emits.

5. **Poll rate.**
   1 Hz fits demo (Pi can compute fast). Real CSIP-AUS DOE feeds: 5-minute cadence for envelope, 1-sec for raw DLR. Confirm 1 Hz is the right MVP for both templates, or split: `line_rating @ 1 Hz`, `operating_envelope @ 0.0033 Hz` (5-min).

6. **Device entry in seed/topology.**
   `revenue_meter.yaml` has `equipment_id`/`vendor`/`model`. Do `operating_envelope` and `line_rating` get these? Vendor would be arcnode (own producer). equipment_id pattern: `GRD-OE-001`, `GRD-LR-001`? Match existing GRID-side naming.

## Out of scope

- DLR / PST sim repos (already renamed; no further changes)
- AsyncAPI codegen pipeline (auto-regenerates downstream of schema)
- HMI filter UI (if it hardcoded `"line_controller"` — separate task)
- Headroom site-derivation logic (BESS-side, different team)
- FERC Order 881 AAR compliance work (out of arcnode scope)

## Acceptance criteria

- [ ] Grep `line_controller`/`LINE_CONTROLLER` in `ems-device-api` and `edp-api` returns zero (exclude `.git/`, `.venv/`, `node_modules/`, `coverage/`)
- [ ] `ems-device-api` tests pass (zod schema + AsyncAPI generation)
- [ ] `edp-api` tests pass (template loader + schema validation)
- [ ] `bess_module.yaml`, `grid_module.yaml`, `compute_module.yaml` use `publisher: operating_envelope` and `fanout: operating_envelope`
- [ ] New `operating_envelope.yaml` and `line_rating.yaml` leaf templates load via `template_loader` without error
- [ ] AsyncAPI spec `GET /asyncapi` shows `operating_envelope` as publisher attribution on relevant channels
- [ ] HMI smoke test — manual against `/asyncapi` consumer surface
- [ ] One MR per repo, coordinated merge (ems-device-api first — edp-api consumes its schema)

## Order of operations

1. Resolve open questions 1-6 with PM
2. ems-device-api: schema rename + tests
3. edp-api: schema rename + 3 module template updates + tests
4. New `operating_envelope.yaml` leaf template
5. New `line_rating.yaml` leaf template
6. Verify AsyncAPI generation
7. Coordinated push; HMI smoke

## References

- Producer: `dlr-operating-envelope` (gitlab: arcnode-io/dlr-operating-envelope) — IEEE 738 sensors + DOE derivation
- Sibling: `dlr-pst-sim` (ESP32 demo PST), `dlr-pcb` (real PCB hw)
- Topic structure: `ems/topic_structure_adr.md`
- Topology + DTM: `ems/system_adr.md`
- Existing leaf template shape: `edp-api/device_templates/leaf/revenue_meter.yaml`
- Existing module template using `line_controller`: `edp-api/device_templates/module/bess_module.yaml`

### Standards

- IEEE 2030.5 — `opModImpLimW`, `opModExpLimW` (DERControlBase): https://zepben.github.io/evolve/docs/2030-5/2030-5/SmartGrid/IEEE2030-5/DER/DERControlBase/
- CSIP-AUS Explainer v1.2 (May 2025): https://static1.squarespace.com/static/67ec72f228086e2ba4f8e438/t/684f71d7b1a5ec0335fa7edd/1750036960820/CSIP-AUS-v1.2-explainer-May-2025-release.pdf
- AER Export Limits Guidance Note (Oct 2024): https://www.aer.gov.au/system/files/2024-10/Export%20Limits%20Guidance%20Note.pdf
- DOE Review (MDPI 2025): https://www.mdpi.com/2673-3951/6/2/29
- FERC Order 881 (AAR mandate): https://www.federalregister.gov/documents/2024/07/15/2024-14666/implementation-of-dynamic-line-ratings
- Static vs AAR vs DLR (Ferro Power Solutions): https://ferropowersolutions.com/news/static-ambient-adjusted-and-dynamic-line-ratings-what-they-mean-for-modern-utilities/
- ENWL Technical Limits methodology (network headroom): https://www.enwl.co.uk/globalassets/get-connected/connections-gif-images/technical-limits-enwl-methodology.pdf
- Ampacimon FERC 881 DLR Handbook: https://www.ampacimon.com/news/ferc-order-881-comprehensive-handbook-for-dynamic-line-rating-implementation
