"""Regions, request builder and flag-code helper for sizing tests; import explicitly."""

from src.shared.enums import (
    BessCoupling,
    DeploymentContext,
    FlexLevel,
    GpuVariant,
    OnsiteGenerationType,
)
from src.shared.schemas.configurator_grid import OnsiteGeneration
from src.shared.schemas.grid_regions import (
    FlexPreset,
    GridRegionsConfig,
    RegionDefaults,
)
from src.shared.schemas.sizing import (
    SizingFlagCode,
    SizingGridInput,
    SizingPreview,
    SizingPreviewRequest,
)

_REGIONS = GridRegionsConfig(
    defaults=RegionDefaults(distribution_limit_mw=20, distribution_near_mw=15),
    regions={},
    flex_levels={
        FlexLevel.STANDARD: FlexPreset(
            depth_pct=50,
            max_duration_h=4,
            max_events_yr=40,
            min_interval_h=20,
            notice_s=600,
        ),
    },
)


_NO_GEN = OnsiteGeneration(type=OnsiteGenerationType.NONE)


def _request(**overrides: object) -> SizingPreviewRequest:
    base: dict[str, object] = {
        "gpu_variant": GpuVariant.B200,
        "target_gpu_count": 56,
        "bess_coupling": BessCoupling.AC_COUPLED,
        "bess_capacity_mwh": 5.0,
        "deployment_context": DeploymentContext.COMMERCIAL,
        "onsite_generation": _NO_GEN,
        "grid": SizingGridInput(),
    }
    base.update(overrides)
    return SizingPreviewRequest.model_validate(base)


def _codes(preview: SizingPreview) -> set[SizingFlagCode]:
    return {f.code for f in preview.flags}
