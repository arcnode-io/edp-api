"""Where a deployment sits and what generates on site (V7).

Split out of configurator_grid.py (200-line budget).
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.shared.enums import OnsiteGenerationType


class SiteLocation(BaseModel):
    """Site coordinates — input to platform-api's /grid/resolve.

    Null only off grid (no utility to resolve); ConfiguratorPayload enforces it.
    """

    model_config = ConfigDict(extra="forbid")

    lat: float | None = Field(ge=-90, le=90)
    lon: float | None = Field(ge=-180, le=180)
    address: str | None = None


class Site(BaseModel):
    """Where the deployment physically sits."""

    model_config = ConfigDict(extra="forbid")

    location: SiteLocation
    country: str  # ISO 3166-1 alpha-2, uppercase, exactly 2 chars
    state: str | None = None

    @field_validator("country")
    @classmethod
    def country_is_iso_alpha2(cls, v: str) -> str:
        """country must be an uppercase 2-letter ISO 3166-1 alpha-2 code."""
        if len(v) != 2 or not v.isalpha() or not v.isupper():
            raise ValueError("country must be an uppercase 2-letter ISO 3166-1 code")
        return v


class OnsiteGeneration(BaseModel):
    """Behind-the-meter generation — independent of grid.path."""

    model_config = ConfigDict(extra="forbid")

    type: OnsiteGenerationType
    capacity_mw: float | None = None

    @model_validator(mode="after")
    def capacity_matches_type(self) -> "OnsiteGeneration":
        """V7: capacity_mw > 0 iff type != none; null iff type == none."""
        if self.type == OnsiteGenerationType.NONE:
            if self.capacity_mw is not None:
                raise ValueError("capacity_mw must be null when type=none")
        elif self.capacity_mw is None or self.capacity_mw <= 0:
            raise ValueError("capacity_mw must be > 0 when type != none")
        return self
