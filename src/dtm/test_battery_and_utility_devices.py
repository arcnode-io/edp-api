"""Order-sized battery units and the utility-facing devices in the DTM."""

import pytest

from src.dtm.dtm_generator_service import DtmGeneratorService
from src.dtm.test_dtm_generator_fixtures import (
    _make_client,
    _manifest,
    _real_catalog,
    _resolution,
)
from src.shared.enums import GridPath, MarketRegion, ServiceType, WiresOwnerType
from src.shared.schemas.configurator_grid import Grid, WiresOwner

_FIRM_ERCOT = Grid(
    path=GridPath.FIRM,
    service_type=ServiceType.FIRM,
    wires_owner=WiresOwner(id="oncor", name="Oncor", type=WiresOwnerType.TDSP),
    market_region=MarketRegion.ERCOT,
)


def test_one_megapack_per_3854_kwh_of_ordered_energy() -> None:
    # Arrange — 10 MWh / 3.854 MWh per Megapack 2 XL → 3 units, so the
    # module's derived range is 3 x 1.927 MW
    service = DtmGeneratorService(_make_client(), template_catalog=_real_catalog())
    resolution = _resolution().model_copy(update={"bess_capacity_mwh": 10.0})

    # Act
    dtm = service.generate(
        profile="commercial_ac", resolution=resolution, manifest=_manifest()
    )

    # Assert
    actual = [
        (d.device_id, d.parent, d.display_name)
        for d in dtm.devices.values()
        if d.template == "bess_rack"
    ]
    assert actual == [
        ("bess_rack_1", "bess_module_1", "BESS-1-MP-1"),
        ("bess_rack_2", "bess_module_1", "BESS-1-MP-2"),
        ("bess_rack_3", "bess_module_1", "BESS-1-MP-3"),
    ]


@pytest.mark.parametrize(
    ("grid", "expected"),
    [
        (None, []),
        (_FIRM_ERCOT, ["der_dispatch", "operating_envelope"]),
    ],
)
def test_grid_connected_orders_carry_the_utility_devices(
    grid: Grid | None, expected: list[str]
) -> None:
    # Arrange — der-control-api publishes under these fixed device ids
    service = DtmGeneratorService(_make_client(), template_catalog=_real_catalog())
    resolution = _resolution() if grid is None else _resolution(grid=grid)

    # Act
    dtm = service.generate(
        profile="commercial_ac", resolution=resolution, manifest=_manifest()
    )

    # Assert
    actual = sorted(
        d.device_id
        for d in dtm.devices.values()
        if d.template in {"der_dispatch", "operating_envelope"}
    )
    assert actual == expected
