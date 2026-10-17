"""The 13.8 kV site bus: every grid container and the battery pad on one bus."""

import pytest

from src.dtm.dtm_generator_service import DtmGeneratorService
from src.dtm.test_dtm_generator_fixtures import (
    _make_client,
    _manifest,
    _real_catalog,
    _resolution,
)
from src.shared.enums import BessCoupling


@pytest.mark.parametrize(
    ("coupling", "battery"),
    [
        (BessCoupling.AC_COUPLED, "bess_module_1"),
        (BessCoupling.DC_EXTERNAL_PCS, "bess_module_dc_1"),
    ],
)
def test_the_battery_and_grid_containers_share_the_site_bus(
    coupling: BessCoupling, battery: str
) -> None:
    # Arrange — the SLD site sheet: the POI meter at the utility tie, each
    # G's MV breaker and the battery on 13.8 kV
    service = DtmGeneratorService(_make_client(), template_catalog=_real_catalog())
    resolution = _resolution(grid_container_count=2).model_copy(
        update={"bess_coupling": coupling}
    )

    # Act
    dtm = service.generate(
        profile="commercial_ac", resolution=resolution, manifest=_manifest()
    )

    # Assert
    actual = [
        (b.type, [(m.device_id, m.port) for m in b.members])
        for b in dtm.buses
        if b.bus_id == "site_mv_1"
    ]
    assert actual == [
        (
            "ac",
            [
                ("poi_meter_1", "voltage_in"),
                ("switchgear_1", "line_in"),
                ("switchgear_2", "line_in"),
                (battery, "ac_out"),
            ],
        )
    ]


def test_each_grid_container_feeds_its_compute_containers_over_lv_main() -> None:
    # Arrange — ADR-018: 5 compute over 2 grid → G1 feeds C1-C3, G2 C4-C5;
    # each G's transformer secondary feeds its switchboard
    service = DtmGeneratorService(_make_client(), template_catalog=_real_catalog())
    resolution = _resolution(container_count=5, grid_container_count=2)

    # Act
    dtm = service.generate(
        profile="commercial_ac", resolution=resolution, manifest=_manifest()
    )

    # Assert
    actual = {
        b.bus_id: (b.type, [(m.device_id, m.port) for m in b.members])
        for b in dtm.buses
        if b.bus_id.startswith("lv_main")
    }
    feeds = [f"compute_module_{n}" for n in range(1, 6)]
    assert actual == {
        "lv_main_1": (
            "ac",
            [("transformer_1", "lv_out"), ("lv_switchboard_1", "feeder_out")]
            + [(c, "ac_in") for c in feeds[:3]],
        ),
        "lv_main_2": (
            "ac",
            [("transformer_2", "lv_out"), ("lv_switchboard_2", "feeder_out")]
            + [(c, "ac_in") for c in feeds[3:]],
        ),
    }
