---
name: generate-engineering-drawing
description: Build a new paper-grade engineering drawing generator (P&ID, comms diagram, installation graph, cable+hose schedule) by extending the shared title-block + render path used by SLD-eng + P&ID-cooling. Two-phase: TDD the structure, then visual loop check at 400dpi.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Agent
---

# Generate ARCNODE Engineering Drawing

For paper-grade DXF + PDF engineering deliverables that ship inside the
EDP (BOM-adjacent CAD documents). Already-shipped instances:

- `sld_engineering_service.py` — Single Line Diagram (IEC 60617 symbols).
- `pid_cooling_service.py` — P&ID Cooling (ISA 5.1 symbols, 2 sheets).

This skill encodes the converged patterns so the next drawing
(comms_diagram, installation_graph, cable_hose_schedule) lands in ~1 day
not ~3.

## Shared infrastructure (do NOT duplicate)

| File | Purpose |
|---|---|
| `src/drawing/_eng_render.py` | `serialize_dxf(doc)` + `serialize_pdf(pages, *, title)`. Forces BLACK-on-WHITE via ezdxf Configuration — engineering PDFs must be reviewer-readable in any PDF viewer. Vector all the way down (no rasterization). |
| `src/drawing/_eng_title_block.py` | `draw_sheet_frame(msp)` + `draw_title_block(msp, dtm, *, title, profile, sheet_n, sheet_m)`. ISO 5457 sheet frame, ISO 7200-lite title block with ARCNODE logo glyph in the 30mm left strip, 4 text rows in the 170mm right column. |
| `src/drawing/_arcnode_logo.py` | `arcnode_logo_polylines()` — cached SVG-path-to-polyline converter. Used by `_eng_title_block` only. |

## Phase 1: TDD structure

1. **Pick the artifact slot.** Confirm it has reserved URLs in
   `src/pipeline/artifact_urls.py` (formats: usually `dxf` + `pdf`). If
   not, that's a separate PR.
2. **Failing test first.** Put `test_<artifact>_service.py` next to the
   service. Cover:
   - `generate()` returns a Pydantic `*Outputs(dxf: bytes, pdf: bytes)`.
   - PDF starts with `%PDF-`.
   - If multi-sheet: PDF has the expected page count (regex
     `r"/Type\s*/Page(?!s)"` — see `test_pid_cooling_service.py`).
   - DXF round-trips through `ezdxf.read(io.StringIO(...))`.
   - DXF carries the deployment_uuid in an MTEXT entity.
   - DXF has expected per-device blocks (`INSERT` entities matching the DTM).
3. **Skeleton service.** Mirror `pid_cooling_service.py`:
   - `class FooOutputs(BaseModel)` with `dxf: bytes` + `pdf: bytes`,
     `model_config = {"arbitrary_types_allowed": True}`.
   - `class FooService` with `generate(dtm, profile="") -> FooOutputs`.
   - Build one or more ezdxf `Drawing` instances inside `_build_sheetN`.
   - Use `serialize_dxf` + `serialize_pdf` from `_eng_render`.
   - Use `draw_sheet_frame` + `draw_title_block` from `_eng_title_block`.
4. **Symbol module.** `src/drawing/_<artifact>_symbols.py`. Each
   `ensure_*_block(doc) -> str` function is idempotent — name your block,
   check if it exists, build if not, return name. Caller INSERTs.
5. **Layout module.** `src/drawing/_<artifact>_layout.py`. Pure
   coordinates + placement logic. No drawing calls. Caller composes.

Verification gate: all tests green, `uv run poe checks` clean.

## Phase 2: Visual loop (max ~5 iterations)

After the test suite is green, the rendering is NOT done. Defaults
produce mediocre layouts — iterate visually.

```bash
# 1. Generate from a representative DTM fixture (use src/drawing/conftest.py helpers).
uv run python <<'PY'
from src.drawing.<service>_service import <Service>Service
from src.drawing.conftest import make_device, make_dtm, make_template
dtm = make_dtm(devices={...}, templates={...})
out = <Service>Service().generate(dtm, profile="commercial_ac")
open("/tmp/<service>.pdf","wb").write(out.pdf)
PY

# 2. Render at 400dpi (preview-quality; production PDF is always vector).
pdftoppm -r 400 /tmp/<service>.pdf /tmp/<service> -png

# 3. Inspect via Read tool. Look for:
#    - Pipe/bus/wire crossings — usually fixable with orthogonal routing.
#    - Labels overlapping symbols or other labels.
#    - Text running off the title-block column (shorten title or shrink char_height).
#    - Equipment positioned outside the manifold/bus extent.
#    - Tag numbers reading wrong direction (ISA convention: top-to-bottom increasing).
#    - Unicode chars rendering as squares — matplotlib's default font may lack them;
#      fall back to ASCII (< > instead of ◀ ▶).

# 4. Edit the layout constants in `_<artifact>_layout.py` or fix specific routing
#    in the service. Re-run from step 1. Max ~5 iterations.

# 5. When converged: SVG export (matplotlib Frontend->savefig svg) makes a great
#    preview file to share. PDF is the production artifact.
```

## Wiring into the pipeline

1. `src/drawing/drawing_module.py` — add `self.<service> = <Service>()`.
2. `src/jobs/jobs_module.py` — pass `<service>=drawing_module.<service>`
   into `PipelineService(...)`.
3. `src/pipeline/pipeline_service.py`:
   - Add the service to `__init__` + store on `self._<service>`.
   - In `run()`: pre-compute the outputs once via
     `self._<service>.generate(dtm, profile=profile)`.
   - Pass the outputs into `_run_one(...)`.
   - In `_run_one`: 2 new branches —
     `ArtifactKind.<KIND> and ref.format == "dxf"` → upload dxf bytes,
     `ArtifactKind.<KIND> and ref.format == "pdf"` → upload pdf bytes.
4. `src/pipeline/test_pipeline_service.py`:
   - Add `<service>_service=<Service>Service()` to `_build_pipeline`.
   - Add a `test_<artifact>_uploads_real_dxf_and_pdf()` test.
   - If `test_unimplemented_kinds_get_stub_bytes` used `ArtifactKind.<KIND>`
     as its still-stubbed example, switch it to a still-stubbed kind.

## Converged design conventions

### Color + lineweight

- ezdxf entities at color 256 (BYLAYER) on a layer with color 7. The
  shared `_eng_render` forces BLACK foreground + WHITE background so the
  default white-on-white that ezdxf produces becomes black-on-white in
  the PDF. **Do NOT set entity colors explicitly** — the shared render
  config handles it.

### Title block

- Title text up to ~35 chars at body width 167mm: `char_height` at
  `row_height * 0.35` works. Longer titles wrap. Shorten the title.
- Body rows at `row_height * 0.22` fits the deployment_uuid + a 60-char
  timestamp+profile row.
- Sheet `n/m` always present even on single-sheet drawings; pass
  `sheet_n=1, sheet_m=1` explicitly (defaults exist).

### Sheet frame

- ISO 5457: 5mm inset border. Don't draw outside it.
- A3 landscape: 420x297 mm. Equipment placement margin: 30mm from each
  edge minimum.
- Title block consumes 200x50mm in bottom-right; everything else must
  clear that region.

### Symbols

- One `ensure_*_block` function per symbol type. Block name is the only
  identity — call returns the existing block if already in the doc.
- Per-instance aliases (e.g. `equip_cdu_{device_id}`) wrap the shared
  symbol block in another block whose body is a single INSERT. Tests
  query INSERTs by per-instance name; DXF stays compact since geometry
  lives in the shared base block.
- Symbol-relative coordinates: origin at the symbol's geometric center.
  Caller INSERTs at the destination point, ezdxf does the translation.

### Layout

- Constants in `_<artifact>_layout.py` as module-level `Final[float]`.
- Layout calc functions are pure (no ezdxf calls), return list of
  dataclass `Placement(insert_x, insert_y)` for the caller to INSERT.
- v1 layouts are deterministic per DTM. Plate/bus/manifold counts that
  exceed v1 capacity (e.g. >5 DLC plates per CDU) document as a v2
  concern in the layout module's docstring rather than failing loud.

### Tag numbering (ISA / IEC convention)

- Top-to-bottom: tag numbers INCREASE going down (TT-1001 = topmost).
- Per-loop offset: when multiple CDUs/loops on one sheet, prefix tag
  numbers by 100*loop_index so they don't collide.
- 4-digit format: `f"TT-{1001 + i:04d}"`.

### BY OTHERS placeholders (P&ID convention)

- Dashed-line rectangles via the `DASHED` linetype.
- Labels include "(BY OTHERS)" as literal text in the symbol.
- Boundary line: dashed vertical with "<  BY OTHERS" / "ARCNODE SCOPE  >"
  ASCII arrows (NOT Unicode ◀ ▶ — matplotlib Agg backend renders those
  as empty squares).

## Compounding learnings

### sld_engineering — converged 2026-05-22 (initial), 2026-05-23 (refactor)

- IEC 60617 symbols hand-authored in `_sld_eng_symbols.py`. Circuit
  breaker S00286, switch disconnector S00282, meter S00313, battery
  S00306, plus rectangle fallback.
- Source-side identification per bus reuses `_iec_61850.py::source_member_index`
  (MMXU.W) — same rule as the HMI SVG. Backward-compat test enforces.
- Title block originally 180x40mm with no logo; grew to 200x50mm to
  accommodate the ARCNODE glyph in a 30mm left strip.
- ezdxf default color 7 = white. WAS shipping blank PDFs. The
  `BackgroundPolicy.WHITE + ColorPolicy.BLACK` Configuration fixed it.

### pid_cooling — converged 2026-05-23 (3 visual iters)

**Iter 1 issues:**
- Title text "P&ID — COOLANT SYSTEM (RACK-INTERNAL)" wrapped in the
  title-block column.
- Manifold spanned y=150-210; topmost DLC plate at y=230 was outside
  the manifold (orphan pipe stub).
- Tag numbers ran backwards (TT-1003 at top, should be 1001).
- Unicode arrows ▶ ◀ rendered as empty squares.
- Facility return path had an orphan vertical with no horizontal join.

**Fixes that worked:**
- Shorter title strings: "P&ID — RACK COOLANT" + "P&ID — FACILITY COOLANT".
- Plate stack top y = manifold top (210) so plates sit within manifold extent.
- `enumerate(zip(...))` for ascending tag indices.
- `<` `>` ASCII fallback for boundary direction labels.
- 4-segment orthogonal return path with intermediate y=260 above all gear.

**Iter 2:** Tank → CDU supply was diagonal. Fixed with 2-segment
orthogonal route via the pump's y-coord.

**Iter 3:** Visual review showed clean orthogonal pipework, all symbols
properly connected, title blocks fit on one line. Ship.

### Chug-along gate

Skill is "done" when the next drawing (comms_diagram, installation_graph)
runs clean visual loop in ≤2 iterations. If iter 3+ still has layout
issues on the second drawing, refine this skill before iter 4.

## Reference: ezdxf gotchas

- `ezdxf.read(stream)` wants a TEXT stream (`io.StringIO`), not bytes.
- `doc.write(buf, fmt="asc")` writes ASCII DXF; `fmt="bin"` for binary.
- Block-INSERT vs raw entity placement: prefer blocks for anything
  reused (per-template symbol, per-instance alias). Reduces DXF size,
  makes query-by-name straightforward.
- `LWPolyline` close=True draws the closing segment; for open polylines
  pass close=False (default).
- DASHED linetype is in the default linetype set when ezdxf.new(...,
  setup=True). Without setup=True you get a one-line empty linetype dict.
- MTEXT vs TEXT: use MTEXT for multi-line / longer strings (handles
  width-based wrapping); TEXT for single-character labels (faster,
  smaller). MTEXT `attachment_point=4` = middle-left anchor.

## Reference: matplotlib PDF gotchas

- Set `matplotlib.use("Agg")` BEFORE `import matplotlib.pyplot` —
  otherwise it tries to attach to a display in headless contexts.
- `Figure.add_axes` wants a 4-tuple, not a list, per the stubs:
  `fig.add_axes((0.0, 0.0, 1.0, 1.0))`.
- `pdf.savefig(fig, dpi=N, facecolor="white")` — facecolor is required;
  PdfPages doesn't honor figure facecolor automatically.
- Liberation Sans + DejaVu Sans are the only fonts in Debian-slim with
  `fonts-liberation fonts-dejavu-core` installed (see Dockerfile).
  Don't rely on MS fonts (Arial, Calibri) — substituted silently.
