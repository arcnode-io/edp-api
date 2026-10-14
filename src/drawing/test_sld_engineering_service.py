"""SldEngineeringService: site one-line + typical compute container (2 sheets)."""

import io
import re
from datetime import UTC, datetime
from uuid import UUID

import ezdxf
from ezdxf.entities import Text

from src.bom_generator.bom_test_support import ORDER
from src.bom_generator.bom_models import BomSection
from src.bom_generator.bom_models import Bom, BomLineItem, ProcurementPath
from src.drawing.conftest import make_device, make_dtm
from src.drawing.sld_engineering_service import (
    SldEngineeringOutputs,
    SldEngineeringService,
)

DEPLOYMENT_ID: UUID = UUID("00000000-0000-0000-0000-000000000042")


def _bom(profile: str, compute_qty: int, grid_qty: int) -> Bom:
    xfm = BomLineItem(
        section=BomSection.COMPUTE,
        ref_des="C1",
        part_number="Trihal TRI100013684152509 (1000 kVA, 13.8 kV / 415V)",
        vendor="Schneider Electric",
        description="transformer",
        qty=grid_qty,
        procurement_path=ProcurementPath.CATALOG,
        equipment_id="GRD-XFM-001",
    )
    return Bom(
        deployment_id=DEPLOYMENT_ID,
        profile=profile,
        manifest_version="0.0.0-test",
        generated_at=datetime.now(UTC),
        compute_container_qty=compute_qty,
        grid_container_qty=grid_qty,
        order=ORDER,
        line_items=[xfm],
    )


def _sld(profile: str, compute_qty: int, grid_qty: int) -> SldEngineeringOutputs:
    dtm = make_dtm(devices={"pdu_1": make_device("pdu_1", template="pdu")})
    return SldEngineeringService().generate(
        dtm, bom=_bom(profile, compute_qty, grid_qty), profile=profile
    )


def _texts(outputs: SldEngineeringOutputs) -> str:
    doc = ezdxf.read(io.StringIO(outputs.dxf.decode("utf-8")))
    return " | ".join(
        t.dxf.text for t in doc.modelspace().query("TEXT") if isinstance(t, Text)
    )


def test_pdf_has_a_site_sheet_and_a_typical_compute_sheet() -> None:
    # Act
    outputs = _sld("commercial_ac", compute_qty=10, grid_qty=3)

    # Assert
    assert len(re.findall(rb"/Type /Page\b", outputs.pdf)) == 2


def test_site_sheet_splits_compute_feeders_over_grid_containers() -> None:
    # Act
    texts = _texts(_sld("commercial_ac", compute_qty=10, grid_qty=3))

    # Assert — G1 feeds C1-C4; G2-G3 is drawn once as typical (ADR-018)
    assert "COMPUTE C1-C4" in texts
    assert "GRID CONTAINERS G2-G3 (TYPICAL OF 2)" in texts


def test_ac_battery_ties_in_at_mv_through_customer_gear() -> None:
    # Act
    texts = _texts(_sld("commercial_ac", compute_qty=2, grid_qty=1))

    # Assert — ADR-016
    assert "T-BESS STEP-UP, BESS AC TO 13.8 kV — BY OTHERS" in texts
    assert "GRD-PCS-001" not in texts


def test_dc_ext_battery_lands_on_the_pcs_pair() -> None:
    # Act
    texts = _texts(_sld("commercial_dc_ext", compute_qty=2, grid_qty=1))

    # Assert — PCS pair on the battery pad, AC in through BG-AC (ADR-022)
    assert "GRD-PCS-001 x2 ON BATTERY PAD (ADR-022)" in texts
    assert "STEP-UP" not in texts


def test_labels_come_from_the_bom_or_say_part_tbd() -> None:
    # Act
    texts = _texts(_sld("commercial_ac", compute_qty=2, grid_qty=1))

    # Assert — Trihal is in the BOM; the LV switchboard isn't selected yet
    assert "Schneider Electric Trihal TRI100013684152509" in texts
    assert "PART TBD" in texts


def test_compute_sheet_is_typical_of_every_compute_container() -> None:
    # Act
    texts = _texts(_sld("commercial_ac", compute_qty=10, grid_qty=3))

    # Assert
    assert "COMPUTE CONTAINER C1-C10 (TYPICAL OF 10)" in texts


def test_poi_meter_sits_at_the_utility_service() -> None:
    # Act
    texts = _texts(_sld("commercial_ac", compute_qty=10, grid_qty=3))

    # Assert — ADR-020: one meter at the POI, none inside the grid containers
    assert texts.count("POI METER") == 1
    assert "POI METER GRD-MTR-001 AT UTILITY SERVICE (ADR-020)" in texts
