"""ConfiguratorPayload validator unit tests (top-level rules only — grid rules in
test_configurator_grid.py)."""

import pytest
from pydantic import ValidationError

from src.shared.enums import (
    BessCoupling,
    GridPath,
    MarketRegion,
    ServiceType,
    WiresOwnerType,
)
from src.shared.schemas.configurator_grid import (
    Grid,
    Site,
    SiteLocation,
    WiresOwner,
)
from src.shared.schemas.configurator_payload import ConfiguratorPayload
from src.shared.schemas.configurator_payload_test_support import (
    _kwargs,
)


def test_rejects_bess_none() -> None:
    # Arrange — every site has a BESS
    raw = {**_kwargs(), "bess_coupling": "none"}

    # Act / Assert
    with pytest.raises(ValidationError, match="bess_coupling"):
        ConfiguratorPayload.model_validate(raw)


def test_rejects_zero_bess_capacity() -> None:
    # Arrange
    kw = _kwargs(coupling=BessCoupling.AC_COUPLED, capacity_mwh=0.0)

    # Act / Assert
    with pytest.raises(ValidationError, match="bess_capacity_mwh"):
        ConfiguratorPayload(**kw)


def test_islanding_with_bess_is_valid() -> None:
    """V9/V10 happy path: intentional_islanding=true needs BESS + a positive reserve."""
    # Arrange
    grid = Grid(
        path=GridPath.FIRM,
        service_type=ServiceType.FIRM,
        wires_owner=WiresOwner(id="oncor", name="Oncor", type=WiresOwnerType.TDSP),
        market_region=MarketRegion.ERCOT,
        intentional_islanding=True,
    )
    kw = _kwargs(
        coupling=BessCoupling.AC_COUPLED,
        capacity_mwh=5.0,
        grid=grid,
        ride_through_hours=2.0,
    )

    # Act
    payload = ConfiguratorPayload(**kw)

    # Assert
    assert payload.grid.intentional_islanding is True
    assert payload.ride_through_hours == 2.0


def test_ride_through_hours_defaults_to_zero() -> None:
    """ride_through_hours is optional, sibling of bess_capacity_mwh."""
    # Arrange
    kw = _kwargs()

    # Act
    payload = ConfiguratorPayload(**kw)

    # Assert
    assert payload.ride_through_hours == 0.0


def test_islanding_requires_ride_through_hours() -> None:
    """V10: intentional_islanding=true + ride_through_hours=0 -> ValidationError."""
    # Arrange — BESS present so V9 passes; ride_through_hours left at default 0
    grid = Grid(
        path=GridPath.FIRM,
        service_type=ServiceType.FIRM,
        wires_owner=WiresOwner(id="oncor", name="Oncor", type=WiresOwnerType.TDSP),
        market_region=MarketRegion.ERCOT,
        intentional_islanding=True,
    )
    kw = _kwargs(coupling=BessCoupling.AC_COUPLED, capacity_mwh=5.0, grid=grid)

    # Act / Assert
    with pytest.raises(
        ValidationError, match="intentional_islanding=true requires ride_through_hours"
    ):
        ConfiguratorPayload(**kw)


_NO_COORDS = Site(location=SiteLocation(lat=None, lon=None), country="US")


_FIRM = Grid(
    path=GridPath.FIRM,
    service_type=ServiceType.FIRM,
    wires_owner=WiresOwner(id="oncor", name="Oncor", type=WiresOwnerType.TDSP),
    market_region=MarketRegion.ERCOT,
)


def test_off_grid_site_needs_no_coordinates() -> None:
    # Arrange — no utility lookup off grid, so lat/lon can be unknown
    kw = _kwargs(site=_NO_COORDS)

    # Act
    payload = ConfiguratorPayload(**kw)

    # Assert
    assert payload.site.location.lat is None


def test_grid_connected_site_requires_coordinates() -> None:
    # Arrange
    kw = _kwargs(site=_NO_COORDS, grid=_FIRM)

    # Act / Assert
    with pytest.raises(ValidationError, match=r"requires site\.location lat and lon"):
        ConfiguratorPayload(**kw)
