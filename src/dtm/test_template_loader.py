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


def _write_poi_meter(dir_: Path) -> None:
    (dir_ / "poi_meter.yaml").write_text("""
template: poi_meter
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
      data_type: int16
""".lstrip())


def test_load_catalog_loads_one_leaf(tmp_path: Path) -> None:
    # Arrange
    (tmp_path / "leaf").mkdir()
    (tmp_path / "module").mkdir()
    _write_poi_meter(tmp_path / "leaf")
    loader = TemplateLoader(root=tmp_path)
    # Act
    catalog = loader.load_catalog()
    # Assert
    assert "poi_meter" in catalog
    assert catalog["poi_meter"].equipment_id == "GRD-MTR-001"


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
    # Arrange — leaf missing its required vendor
    (tmp_path / "leaf").mkdir()
    (tmp_path / "module").mkdir()
    (tmp_path / "leaf" / "bad.yaml").write_text("""
template: no_vendor
kind: leaf
equipment_id: GRD-MTR-001
model: T-1
description: missing vendor
""".lstrip())
    loader = TemplateLoader(root=tmp_path)
    # Act / Assert
    with pytest.raises(TemplateLoadError, match="schema validation failed"):
        loader.load_catalog()


def test_load_real_catalog_size() -> None:
    # Arrange
    repo_root = Path(__file__).resolve().parents[2]
    loader = TemplateLoader(root=repo_root / "device_templates")
    # Act
    catalog = loader.load_catalog()
    # Assert
    leaves = [t for t in catalog.values() if t.kind.value == "leaf"]
    modules = [t for t in catalog.values() if t.kind.value == "module"]
    assert len(leaves) == 22
    assert len(modules) == 5
    # DLR line rating is the utility/DERMS's equipment, not ours
    assert "line_rating" not in catalog


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


def test_load_catalog_rejects_duplicate_slug(tmp_path: Path) -> None:
    # Arrange — two files claiming the same slug
    (tmp_path / "leaf").mkdir()
    (tmp_path / "module").mkdir()
    _write_poi_meter(tmp_path / "leaf")
    (tmp_path / "leaf" / "poi_meter_dup.yaml").write_text("""
template: poi_meter
kind: leaf
equipment_id: GRD-MTR-001
vendor: Schneider Electric
model: ION9000
description: dup
measurements:
  v:
    unit: volts
    type: float
    binding: { protocol: modbus_tcp, function_code: 4, address: 100, data_type: int16 }
""".lstrip())
    loader = TemplateLoader(root=tmp_path)
    # Act / Assert
    with pytest.raises(TemplateLoadError, match="duplicate template slug"):
        loader.load_catalog()


def test_load_catalog_rejects_unresolved_contains(tmp_path: Path) -> None:
    # Arrange — module references a leaf that doesn't exist
    (tmp_path / "leaf").mkdir()
    (tmp_path / "module").mkdir()
    _write_poi_meter(tmp_path / "leaf")
    (tmp_path / "module" / "broken_module.yaml").write_text("""
template: broken_module
kind: module
description: refs a leaf that doesn't exist
contains:
  - template: nonexistent_leaf
    qty: 1
measurements:
  rollup:
    unit: watts
    type: float
    publisher: local_process
""".lstrip())
    loader = TemplateLoader(root=tmp_path)
    # Act / Assert
    with pytest.raises(TemplateLoadError, match="not in catalog"):
        loader.load_catalog()
