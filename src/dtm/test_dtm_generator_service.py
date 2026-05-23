"""DtmGeneratorService unit tests for the canonical schema (PR 2)."""

import pytest

from src.dtm.dtm_generator_service import DtmGeneratorService
from src.dtm.test_dtm_generator_fixtures import (
    _make_client,
    _manifest,
    _real_catalog,
    _resolution,
)
from src.shared.schemas.dtm import EmsMode


def test_generate_emits_sim_mode() -> None:
    # Arrange
    service = DtmGeneratorService(_make_client(), template_catalog=_real_catalog())
    # Act
    actual = service.generate(
        profile="commercial_ac", resolution=_resolution(), manifest=_manifest()
    )
    # Assert
    assert actual.mode == EmsMode.LIVE


def test_generate_dissolves_modules_into_devices() -> None:
    # Arrange
    service = DtmGeneratorService(_make_client(), template_catalog=_real_catalog())
    # Act
    actual = service.generate(
        profile="commercial_ac", resolution=_resolution(), manifest=_manifest()
    )
    # Assert
    assert "compute_module_1" in actual.devices
    assert "grid_module_1" in actual.devices
    assert actual.devices["compute_module_1"].parent is None
    assert actual.devices["grid_module_1"].parent is None


def test_generate_assigns_per_template_indexed_slugs() -> None:
    # Arrange
    service = DtmGeneratorService(_make_client(), template_catalog=_real_catalog())
    # Act
    actual = service.generate(
        profile="commercial_ac", resolution=_resolution(), manifest=_manifest()
    )
    # Assert
    gpu_slugs = [s for s in actual.devices if s.startswith("gpu_node_")]
    assert sorted(gpu_slugs) == [f"gpu_node_{i}" for i in range(1, 4)]
    assert "revenue_meter_1" in actual.devices


def test_generate_parents_leaves_under_modules() -> None:
    # Arrange
    service = DtmGeneratorService(_make_client(), template_catalog=_real_catalog())
    # Act
    actual = service.generate(
        profile="commercial_ac", resolution=_resolution(), manifest=_manifest()
    )
    # Assert
    assert actual.devices["gpu_node_1"].parent == "compute_module_1"
    assert actual.devices["revenue_meter_1"].parent == "grid_module_1"


def test_generate_embeds_templates_used() -> None:
    # Arrange
    service = DtmGeneratorService(_make_client(), template_catalog=_real_catalog())
    # Act
    actual = service.generate(
        profile="commercial_ac", resolution=_resolution(), manifest=_manifest()
    )
    # Assert
    referenced_slugs = {d.template for d in actual.devices.values()}
    assert referenced_slugs <= set(actual.templates_used)
    assert actual.templates_used["revenue_meter"].equipment_id == "GRD-MTR-001"


def test_generate_expands_bus_members() -> None:
    # Arrange
    service = DtmGeneratorService(_make_client(), template_catalog=_real_catalog())
    # Act
    actual = service.generate(
        profile="commercial_ac", resolution=_resolution(), manifest=_manifest()
    )
    # Assert
    assert len(actual.buses) == 1
    bus = actual.buses[0]
    member_ids = {m.device_id for m in bus.members}
    assert "switchgear_1" in member_ids
    assert "revenue_meter_1" in member_ids
    assert "protective_relay_1" in member_ids


def test_generate_slug_counter_continues_across_containers() -> None:
    # Arrange — 2 compute containers means gpu_node count doubles
    service = DtmGeneratorService(_make_client(), template_catalog=_real_catalog())
    # Act
    actual = service.generate(
        profile="commercial_ac",
        resolution=_resolution(container_count=2),
        manifest=_manifest(),
    )
    # Assert — gpu_node_1 through gpu_node_6 (3 per container * 2)
    gpu_slugs = [s for s in actual.devices if s.startswith("gpu_node_")]
    assert len(gpu_slugs) == 6


def test_generate_unknown_profile_raises() -> None:
    # Arrange
    service = DtmGeneratorService(_make_client(), template_catalog=_real_catalog())
    # Act / Assert
    with pytest.raises(ValueError, match="not in manifest"):
        service.generate(
            profile="defense_dc_int", resolution=_resolution(), manifest=_manifest()
        )
