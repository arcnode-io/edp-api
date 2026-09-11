"""All StrEnums used across edp-api. Single source of truth."""

from enum import StrEnum


class PrimaryWorkload(StrEnum):
    """What the GPUs will primarily run."""

    AI_TRAINING = "ai_training"
    AI_INFERENCE = "ai_inference"
    MIXED = "mixed"


class GpuVariant(StrEnum):
    """Supported GPU variants."""

    H100_SXM = "h100_sxm"
    B200 = "b200"


class BessCoupling(StrEnum):
    """How the BESS is coupled to the bus."""

    AC_COUPLED = "ac_coupled"
    DC_INTEGRATED_PCS = "dc_integrated_pcs"
    DC_EXTERNAL_PCS = "dc_external_pcs"
    NONE = "none"


class ClimateZone(StrEnum):
    """Site climate band — drives cooling sizing."""

    SUBARCTIC = "subarctic"
    TEMPERATE = "temperate"
    ARID_HOT = "arid_hot"
    TROPICAL = "tropical"


class DeploymentContext(StrEnum):
    """Customer / procurement classification."""

    COMMERCIAL = "commercial"
    SOVEREIGN_GOVERNMENT = "sovereign_government"
    DEFENSE_FORWARD = "defense_forward"


class AwsPartition(StrEnum):
    """Target AWS partition (or air-gapped)."""

    STANDARD = "standard"
    GOVCLOUD = "govcloud"
    NONE = "none"


class OnsiteGenerationType(StrEnum):
    """Behind-the-meter generation at the site, independent of grid.path."""

    NONE = "none"
    NUCLEAR = "nuclear"
    SOLAR = "solar"


class GridPath(StrEnum):
    """The customer's chosen grid-participation path — mutually exclusive."""

    OFF_GRID = "off_grid"
    FLEXIBLE = "flexible"
    FIRM = "firm"
    GRID_REVENUE = "grid_revenue"


class InterconnectionLevel(StrEnum):
    """Where the site connects to the utility grid. Server-derived (rule IL)."""

    DISTRIBUTION = "distribution"
    TRANSMISSION = "transmission"


class WiresOwnerType(StrEnum):
    """Utility ownership structure — drives interconnection process/timeline."""

    IOU = "iou"
    COOP = "coop"
    MUNI = "muni"
    TDSP = "tdsp"
    FEDERAL = "federal"
    OTHER = "other"


class MarketRegion(StrEnum):
    """ISO / RTO the deployment's utility sits in, or non_rto.

    Renamed from WholesaleMarket; adds NON_RTO for utilities outside any
    ISO/RTO footprint. v1 ships ERCOT only — other regions reserved so the
    enum doesn't need a schema migration when they come online.
    """

    ERCOT = "ercot"
    CAISO = "caiso"
    MISO = "miso"
    PJM = "pjm"
    ISO_NE = "isone"
    NYISO = "nyiso"
    SPP = "spp"
    NON_RTO = "non_rto"


class ServiceType(StrEnum):
    """Firm (always-on) vs flexible (curtailable) grid service."""

    FIRM = "firm"
    FLEXIBLE = "flexible"


class FlexLevel(StrEnum):
    """Preset flex-obligation depth, or custom for site-specific numbers."""

    LIGHT = "light"
    STANDARD = "standard"
    HEAVY = "heavy"
    CUSTOM = "custom"


class ExportMode(StrEnum):
    """Whether the site exports power back to the grid."""

    NON_EXPORT = "non_export"
    LIMITED_EXPORT = "limited_export"
    EXPORT = "export"


class MarketAccess(StrEnum):
    """How the site participates in wholesale market revenue programs."""

    NONE = "none"
    RETAIL_PROGRAM = "retail_program"
    AGGREGATED = "aggregated"
    DIRECT = "direct"


class MarketProgram(StrEnum):
    """Specific ERCOT DER revenue program. Only ERCOT ships programs in v1."""

    ERCOT_ADER = "ercot_ader"
    ERCOT_DGR = "ercot_dgr"


class SourcingTier(StrEnum):
    """Procurement sourcing tier — derived from DeploymentContext."""

    COMMERCIAL = "commercial"
    FEDERAL_CIVILIAN = "federal_civilian"
    DOD_ELIGIBLE = "dod_eligible"


class EmsTarget(StrEnum):
    """Where the EMS will run — derived from AwsPartition."""

    AWS_STANDARD = "aws_standard"
    AWS_GOVCLOUD = "aws_govcloud"
    AIR_GAPPED = "air_gapped"


class DeploymentProfile(StrEnum):
    """7 profiles — mirrors edp-module-assemblies/manifest_profiles.yaml exactly.

    `defense_dc_int` excluded: CATL-integrated PCS isn't procurable for any
    federal/defense customer. Hardware build variants are commercial vs
    defense only — sourcing tier (procurement path) is tracked separately
    by SourcingTier.

    Adding a profile here without a corresponding entry in
    edp-module-assemblies/manifest_profiles.yaml will surface as a
    KeyError at JobsService.create — fail-fast at intake.
    """

    COMMERCIAL_NO_BESS = "commercial_no_bess"
    COMMERCIAL_AC = "commercial_ac"
    COMMERCIAL_DC_EXT = "commercial_dc_ext"
    COMMERCIAL_DC_INT = "commercial_dc_int"
    DEFENSE_NO_BESS = "defense_no_bess"
    DEFENSE_AC = "defense_ac"
    DEFENSE_DC_EXT = "defense_dc_ext"
