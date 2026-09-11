"""Sizing math unit tests — worked examples, reserve, flex, site/grid peak.

Recommend/limit_state/effective_service_type are in test_sizing_recommend.py
(same production module, split by concern — same pattern as
test_template.py / test_template_protocols.py for template.py)."""

import pytest

from src.shared.enums import FlexLevel, GpuVariant, OnsiteGenerationType
from src.shared.schemas.configurator_grid import FlexObligation, OnsiteGeneration
from src.sizing.sizing_internals import (
    ETA_D,
    firm_onsite_mw,
    flex_preview,
    grid_peak_mw,
    reserve_mwh,
    site_peak_mw,
)


def _flex(**overrides: object) -> FlexObligation:
    base: dict[str, object] = {
        "level": FlexLevel.STANDARD,
        "depth_pct": 50,
        "max_duration_h": 4,
        "max_events_yr": 40,
        "min_interval_h": 20,
        "notice_s": 600,
    }
    base.update(overrides)
    return FlexObligation.model_validate(base)


# --- 5.4 worked examples (must match to 3dp) ---


def test_worked_example_one_no_reserve() -> None:
    """P_g=5, d=0.5, t_e=4, t_i=20, ride_through_hours=0."""
    # Arrange
    e_r = reserve_mwh(ride_through_hours=0, grid_peak_mw=5)

    # Act
    preview = flex_preview(
        grid_peak_mw=5, flex_obligation=_flex(), e_reserve_mwh=e_r, usable_mwh=5
    )

    # Assert
    assert e_r == 0
    assert round(preview.e_flex_mwh, 3) == 10.526
    assert round(preview.p_recharge_mw, 3) == 0.554
    assert round(preview.p_contract_mw, 3) == 5.554


def test_worked_example_two_with_reserve() -> None:
    """[A1] Same + ride_through_hours=2, usable=12."""
    # Arrange
    e_r = reserve_mwh(ride_through_hours=2, grid_peak_mw=5)

    # Act
    preview = flex_preview(
        grid_peak_mw=5, flex_obligation=_flex(), e_reserve_mwh=e_r, usable_mwh=12
    )

    # Assert
    assert round(e_r, 3) == 10.526
    assert round(preview.e_min_usable_mwh, 3) == 21.053
    assert round(preview.bess_covers_h, 3) == 0.560
    assert preview.gpu_cap_pct_during_shortfall == 50.0


# --- reserve_mwh ---


def test_reserve_mwh_zero_ride_through() -> None:
    assert reserve_mwh(ride_through_hours=0, grid_peak_mw=10) == 0


def test_reserve_mwh_scales_with_grid_peak() -> None:
    # E_r = ride_through_hours * P_g / ETA_D
    assert reserve_mwh(ride_through_hours=1, grid_peak_mw=ETA_D) == pytest.approx(1.0)


# --- flex_preview edge cases ---


def test_bess_covers_h_zero_when_no_usable_bess() -> None:
    e_r = reserve_mwh(ride_through_hours=0, grid_peak_mw=5)
    preview = flex_preview(
        grid_peak_mw=5, flex_obligation=_flex(), e_reserve_mwh=e_r, usable_mwh=0
    )
    assert preview.bess_covers_h == 0


def test_bess_covers_h_full_duration_when_grid_peak_zero() -> None:
    """d*P_g == 0 (site fully covered by firm onsite gen) -> bess_covers_h = t_e."""
    e_r = reserve_mwh(ride_through_hours=0, grid_peak_mw=0)
    preview = flex_preview(
        grid_peak_mw=0, flex_obligation=_flex(), e_reserve_mwh=e_r, usable_mwh=0
    )
    assert preview.bess_covers_h == 4.0


def test_gpu_cap_none_when_bess_covers_full_duration() -> None:
    e_r = reserve_mwh(ride_through_hours=0, grid_peak_mw=5)
    preview = flex_preview(
        grid_peak_mw=5, flex_obligation=_flex(), e_reserve_mwh=e_r, usable_mwh=1000
    )
    assert preview.bess_covers_h == 4.0
    assert preview.gpu_cap_pct_during_shortfall is None


# --- site_peak_mw / firm_onsite_mw / grid_peak_mw ---


def test_site_peak_mw_b200_one_container() -> None:
    assert site_peak_mw(GpuVariant.B200, 56) == pytest.approx(0.080)


def test_site_peak_mw_rounds_up_to_full_container() -> None:
    # 57 GPUs -> 2 containers
    assert site_peak_mw(GpuVariant.B200, 57) == pytest.approx(0.160)


def test_firm_onsite_mw_nuclear_counts() -> None:
    gen = OnsiteGeneration(type=OnsiteGenerationType.NUCLEAR, capacity_mw=5.0)
    assert firm_onsite_mw(gen) == 5.0


def test_firm_onsite_mw_solar_counts_zero() -> None:
    gen = OnsiteGeneration(type=OnsiteGenerationType.SOLAR, capacity_mw=5.0)
    assert firm_onsite_mw(gen) == 0.0


def test_firm_onsite_mw_none_is_zero() -> None:
    gen = OnsiteGeneration(type=OnsiteGenerationType.NONE)
    assert firm_onsite_mw(gen) == 0.0


def test_grid_peak_mw_never_negative() -> None:
    assert grid_peak_mw(site_peak=5.0, firm_onsite=10.0) == 0.0
