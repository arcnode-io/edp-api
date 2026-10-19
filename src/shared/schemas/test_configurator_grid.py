"""Unit tests for Site/OnsiteGeneration/WiresOwner/FlexObligation/Grid validators."""

import pytest
from pydantic import ValidationError

from src.shared.enums import (
    OnsiteGenerationType,
)
from src.shared.schemas.configurator_grid import (
    OnsiteGeneration,
    Site,
    SiteLocation,
)

# --- Site ---


def test_site_happy_path() -> None:
    # Arrange / Act
    site = Site(location=SiteLocation(lat=32.7, lon=-96.8), country="US", state="TX")
    # Assert
    assert site.country == "US"


def test_site_rejects_lowercase_country() -> None:
    with pytest.raises(ValidationError, match="uppercase 2-letter"):
        Site(location=SiteLocation(lat=32.7, lon=-96.8), country="us")


def test_site_rejects_non_2_char_country() -> None:
    with pytest.raises(ValidationError, match="uppercase 2-letter"):
        Site(location=SiteLocation(lat=32.7, lon=-96.8), country="USA")


# --- OnsiteGeneration (V7) ---


def test_onsite_generation_none_type_happy_path() -> None:
    gen = OnsiteGeneration(type=OnsiteGenerationType.NONE, capacity_mw=None)
    assert gen.capacity_mw is None


def test_onsite_generation_none_type_rejects_capacity() -> None:
    with pytest.raises(ValidationError, match="must be null when type=none"):
        OnsiteGeneration(type=OnsiteGenerationType.NONE, capacity_mw=5.0)


def test_onsite_generation_solar_requires_positive_capacity() -> None:
    gen = OnsiteGeneration(type=OnsiteGenerationType.SOLAR, capacity_mw=10.0)
    assert gen.capacity_mw == 10.0


def test_onsite_generation_solar_rejects_null_capacity() -> None:
    with pytest.raises(ValidationError, match="must be > 0 when type != none"):
        OnsiteGeneration(type=OnsiteGenerationType.SOLAR, capacity_mw=None)


def test_onsite_generation_solar_rejects_zero_capacity() -> None:
    with pytest.raises(ValidationError, match="must be > 0 when type != none"):
        OnsiteGeneration(type=OnsiteGenerationType.SOLAR, capacity_mw=0.0)
