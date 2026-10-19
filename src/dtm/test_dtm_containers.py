"""How containers land in the DTM: grid feeders, buses, tags, GPU variant, battery, partial last container."""

import pytest

from src.shared.enums import BessCoupling, GpuVariant
from src.dtm.dtm_generator_service import DtmGeneratorService
from src.dtm.test_dtm_generator_fixtures import (
    _make_client,
    _manifest,
    _real_catalog,
    _resolution,
)


def test_feeder_grid_containers_add_relays_but_keep_one_poi_meter() -> None:
    # Arrange
    service = DtmGeneratorService(_make_client(), template_catalog=_real_catalog())

    # Act
    dtm = service.generate(
        profile="commercial_ac",
        resolution=_resolution(grid_container_count=3),
        manifest=_manifest(),
    )

    # Assert — a site has one POI; every grid container protects its own feeder
    templates = [d.template for d in dtm.devices.values()]
    actual = (templates.count("poi_meter"), templates.count("protective_relay"))
    assert actual == (1, 3)


def test_each_grid_container_gets_its_own_bus() -> None:
    # Arrange
    service = DtmGeneratorService(_make_client(), template_catalog=_real_catalog())

    # Act
    dtm = service.generate(
        profile="commercial_ac",
        resolution=_resolution(grid_container_count=2),
        manifest=_manifest(),
    )

    # Assert — numbered like device slugs; the feeder bus holds only its own gear
    actual = {
        b.bus_id: sorted(m.device_id for m in b.members)
        for b in dtm.buses
        if b.bus_id.startswith("ac_main")
    }
    assert actual == {
        "ac_main_1": ["protective_relay_1", "switchgear_1", "transformer_1"],
        "ac_main_2": ["protective_relay_2", "switchgear_2", "transformer_2"],
    }


def test_every_device_carries_its_site_unique_tag() -> None:
    # Arrange — tags are per container in topology; the DTM prefixes the
    # container (C1, C2, G1) so every device has one site-unique tag
    service = DtmGeneratorService(_make_client(), template_catalog=_real_catalog())

    # Act
    actual = service.generate(
        profile="commercial_ac",
        resolution=_resolution(container_count=2),
        manifest=_manifest(),
    )

    # Assert
    names = {d: dev.display_name for d, dev in actual.devices.items()}
    assert (names["compute_module_2"], names["gpu_node_4"], names["poi_meter_1"]) == (
        "C2",
        "C2-NODE-1",
        "G1-MTR-POI",
    )


def test_an_h100_order_gets_h100_nodes_under_an_h100_module() -> None:
    # Arrange — the profile maps H100 orders to the H100 compute container
    service = DtmGeneratorService(_make_client(), template_catalog=_real_catalog())

    # Act
    actual = service.generate(
        profile="commercial_ac",
        resolution=_resolution(gpu_variant=GpuVariant.H100_SXM),
        manifest=_manifest(),
    )

    # Assert
    templates = {d.template for d in actual.devices.values() if d.parent is None}
    nodes = {d.template for d in actual.devices.values() if "node" in d.template}
    assert ("compute_module_h100" in templates, nodes) == (True, {"gpu_node_h100"})


@pytest.mark.parametrize(
    ("coupling", "module", "template"),
    [
        (BessCoupling.AC_COUPLED, "bess_module", "bess_rack"),
        (BessCoupling.DC_EXTERNAL_PCS, "bess_module_dc", "bess_catl"),
    ],
)
def test_the_customers_battery_is_in_the_device_data(
    coupling: BessCoupling, module: str, template: str
) -> None:
    # Arrange — QA: the battery was in no artifact. The EMS supervises it.
    service = DtmGeneratorService(_make_client(), template_catalog=_real_catalog())
    resolution = _resolution().model_copy(update={"bess_coupling": coupling})

    # Act
    actual = service.generate(
        profile="commercial_ac", resolution=resolution, manifest=_manifest()
    )

    # Assert
    batteries = {
        (actual.devices[d.parent].template, d.template)
        for d in actual.devices.values()
        if d.parent is not None and d.template.startswith("bess")
    }
    assert batteries == {(module, template)}


def test_the_last_container_holds_only_the_servers_ordered() -> None:
    # Arrange — 8 servers: C1 full, C2 one server (fixture tops out at 3)
    service = DtmGeneratorService(_make_client(), template_catalog=_real_catalog())
    resolution = _resolution(container_count=2).model_copy(update={"gpu_node_count": 8})

    # Act
    dtm = service.generate(
        profile="commercial_ac", resolution=resolution, manifest=_manifest()
    )

    # Assert
    actual = sorted(
        d.display_name or "" for d in dtm.devices.values() if d.template == "gpu_node"
    )
    assert actual == ["C1-NODE-1", "C1-NODE-2", "C1-NODE-3", "C2-NODE-1"]
