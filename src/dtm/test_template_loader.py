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


def _write_revenue_meter(dir_: Path) -> None:
    (dir_ / "revenue_meter.yaml").write_text("""
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
""".lstrip())


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
    (tmp_path / "leaf" / "bad.yaml").write_text("""
template: empty
kind: leaf
equipment_id: GRD-MTR-001
vendor: Test
model: T-1
description: empty
""".lstrip())
    loader = TemplateLoader(root=tmp_path)
    # Act / Assert
    with pytest.raises(TemplateLoadError, match="schema validation failed"):
        loader.load_catalog()


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
    pub = m.measurements["state_of_charge"].publisher
    assert pub is not None and pub.value == "line_controller"
    fanout = m.commands["set_active_power"].fanout
    assert fanout is not None and fanout.value == "line_controller"


def test_load_catalog_rejects_duplicate_slug(tmp_path: Path) -> None:
    # Arrange — two files claiming the same slug
    (tmp_path / "leaf").mkdir()
    (tmp_path / "module").mkdir()
    _write_revenue_meter(tmp_path / "leaf")
    (tmp_path / "leaf" / "revenue_meter_dup.yaml").write_text("""
template: revenue_meter
kind: leaf
equipment_id: GRD-MTR-001
vendor: Schneider Electric
model: ION9000
description: dup
measurements:
  v:
    unit: volts
    type: float
    binding: { protocol: modbus_tcp, function_code: 4, address: 100 }
""".lstrip())
    loader = TemplateLoader(root=tmp_path)
    # Act / Assert
    with pytest.raises(TemplateLoadError, match="duplicate template slug"):
        loader.load_catalog()
