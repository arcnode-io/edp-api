"""spec_to_catalog_line: how a spec becomes a BOM line."""

from src.bom_generator.bom_models import BomSection, ProcurementPath
from src.bom_generator.spec_lines import spec_to_catalog_line


def test_an_engineered_to_order_spec_names_its_reference_design() -> None:
    # Arrange — vendor known (Square D QED-2) but bought by RFQ against our spec
    spec = {
        "equipment_id": "GRD-LVS-001",
        "vendor": "Schneider Electric (Square D)",
        "model_number": "QED-2 switchboard, engineered to order",
        "procurement_path": "engineered_to_order",
        "description": "1600 A switchboard",
    }

    # Act
    line = spec_to_catalog_line(spec, 1, BomSection.GRID, "G1: SWBD-1")

    # Assert
    assert (line.procurement_path, line.vendor, line.part_number, line.notes) == (
        ProcurementPath.ENGINEERED_TO_ORDER,
        "Schneider Electric (Square D)",
        "QED-2 switchboard, engineered to order",
        "Reference design; bought by RFQ against spec GRD-LVS-001.",
    )
