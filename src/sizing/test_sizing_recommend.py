"""limit_state / interconnection_level / recommend / effective_service_type tests.

Split from test_sizing_internals.py by concern (same production module) —
same pattern as test_template.py / test_template_protocols.py for template.py.
"""

from src.shared.enums import (
    BessCoupling,
    DeploymentContext,
    GridPath,
    MarketRegion,
    ServiceType,
)
from src.shared.schemas.grid_regions import RegionDefaults
from src.shared.schemas.sizing import LimitState, SizingGridInput
from src.sizing.sizing_internals import (
    ETA_C,
    ETA_D,
    effective_service_type,
    interconnection_level,
    limit_state,
    recommend,
)

_DEFAULTS = RegionDefaults(distribution_limit_mw=20, distribution_near_mw=15)


def test_limit_state_within() -> None:
    assert limit_state(10, _DEFAULTS) == LimitState.WITHIN


def test_limit_state_near_at_boundary() -> None:
    assert limit_state(15, _DEFAULTS) == LimitState.NEAR


def test_limit_state_at_limit_is_near_not_over() -> None:
    """Exactly at the limit: over is strictly-greater-than, so this falls to near."""
    assert limit_state(20, _DEFAULTS) == LimitState.NEAR


def test_limit_state_over_above_limit() -> None:
    assert limit_state(20.1, _DEFAULTS) == LimitState.OVER


def test_interconnection_level_distribution_at_limit() -> None:
    assert interconnection_level(20, _DEFAULTS).value == "distribution"


def test_interconnection_level_transmission_above_limit() -> None:
    assert interconnection_level(20.1, _DEFAULTS).value == "transmission"


def test_recommend_defense_forward_always_off_grid() -> None:
    path, reason = recommend(
        deployment_context=DeploymentContext.DEFENSE_FORWARD,
        market_region=MarketRegion.ERCOT,
        limit_state=LimitState.WITHIN,
        bess_coupling=BessCoupling.AC_COUPLED,
        grid_peak_mw=5,
    )
    assert path == GridPath.OFF_GRID
    assert "forward deployments" in reason


def test_recommend_unresolved_region_is_off_grid() -> None:
    path, _ = recommend(
        deployment_context=DeploymentContext.COMMERCIAL,
        market_region=None,
        limit_state=LimitState.WITHIN,
        bess_coupling=BessCoupling.AC_COUPLED,
        grid_peak_mw=5,
    )
    assert path == GridPath.OFF_GRID


def test_recommend_flexible_when_bess_present_and_not_over() -> None:
    path, reason = recommend(
        deployment_context=DeploymentContext.COMMERCIAL,
        market_region=MarketRegion.ERCOT,
        limit_state=LimitState.NEAR,
        bess_coupling=BessCoupling.AC_COUPLED,
        grid_peak_mw=5,
    )
    assert path == GridPath.FLEXIBLE
    assert "5.0 MW" in reason


def test_recommend_firm_when_no_bess_and_not_over() -> None:
    path, _ = recommend(
        deployment_context=DeploymentContext.COMMERCIAL,
        market_region=MarketRegion.ERCOT,
        limit_state=LimitState.WITHIN,
        bess_coupling=BessCoupling.NONE,
        grid_peak_mw=5,
    )
    assert path == GridPath.FIRM


def test_recommend_none_when_over_limit() -> None:
    path, reason = recommend(
        deployment_context=DeploymentContext.COMMERCIAL,
        market_region=MarketRegion.ERCOT,
        limit_state=LimitState.OVER,
        bess_coupling=BessCoupling.AC_COUPLED,
        grid_peak_mw=50,
    )
    assert path is None
    assert "transmission-level" in reason


def test_effective_service_type_explicit_wins() -> None:
    grid = SizingGridInput(path=GridPath.FIRM, service_type=ServiceType.FIRM)
    assert effective_service_type(grid) == ServiceType.FIRM


def test_effective_service_type_flexible_path_implies_flexible() -> None:
    grid = SizingGridInput(path=GridPath.FLEXIBLE)
    assert effective_service_type(grid) == ServiceType.FLEXIBLE


def test_effective_service_type_null_when_unresolved() -> None:
    grid = SizingGridInput()
    assert effective_service_type(grid) is None


def test_eta_constants_are_symmetric() -> None:
    """Both charge/discharge efficiencies are the same OEM placeholder today."""
    assert ETA_D == ETA_C == 0.95
