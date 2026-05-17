"""All StrEnums used across edp-api. Single source of truth."""

from enum import StrEnum


class EnergySource(StrEnum):
    """Primary energy source for the deployment."""

    NUCLEAR = "nuclear"
    SOLAR = "solar"
    GRID_HYBRID = "grid_hybrid"
    OFF_GRID = "off_grid"


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


class GridConnection(StrEnum):
    """Grid interconnection mode."""

    NONE = "none"
    GRID_TIED = "grid_tied"
    GRID_BACKUP = "grid_backup"


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


class WholesaleMarket(StrEnum):
    """ISO / RTO the deployment participates in.

    v1 ships ERCOT only. Other ISOs are reserved so the enum doesn't
    need a schema migration when they come online — the website disables
    them at the form layer and the ConfiguratorPayload validator rejects
    them on the backend.
    """

    ERCOT = "ercot"
    CAISO = "caiso"
    MISO = "miso"
    PJM = "pjm"
    ISO_NE = "isone"
    NYISO = "nyiso"
    SPP = "spp"


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
