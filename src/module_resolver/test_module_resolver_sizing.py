"""The resolver sizes servers, containers and the dc_ext PCS fleet."""

from src.module_resolver.module_resolver_service import ModuleResolverService
from src.shared.enums import (
    BessCoupling,
)
from src.module_resolver.module_resolver_test_support import (
    _payload,
)


def test_rounds_up_to_whole_servers_not_whole_containers() -> None:
    """100 GPUs -> 13 servers of 8 (104 GPUs) in 2 containers: 7 + 6."""
    # Arrange
    service = ModuleResolverService()
    payload = _payload(gpu_count=100)

    # Act
    actual = service.resolve(payload)

    # Assert
    assert (
        actual.gpu_node_count,
        actual.gpu_count,
        actual.compute_container_count,
    ) == (13, 104, 2)


def test_one_server_order_is_one_partial_container() -> None:
    # Arrange
    service = ModuleResolverService()
    payload = _payload(gpu_count=8)

    # Act
    actual = service.resolve(payload)

    # Assert
    assert (actual.gpu_node_count, actual.compute_container_count) == (1, 1)


def test_grid_container_count_follows_compute_load() -> None:
    """17 H100 containers x 62.6 kW = 1.06 MW -> 2 grid containers."""
    # Arrange
    service = ModuleResolverService()
    payload = _payload(gpu_count=17 * 56)

    # Act
    actual = service.resolve(payload)

    # Assert
    assert actual.grid_container_count == 2


def test_dc_ext_pcs_count_follows_the_battery_not_the_grid_containers() -> None:
    """90 H100 containers off grid: 6.174 MW → 6 PCS, though 8 grid containers."""
    # Arrange
    service = ModuleResolverService()
    payload = _payload(
        coupling=BessCoupling.DC_EXTERNAL_PCS, capacity_mwh=10, gpu_count=90 * 56
    )

    # Act
    actual = service.resolve(payload)

    # Assert
    assert (actual.grid_container_count, actual.pcs_count) == (8, 6)


def test_no_pcs_unless_dc_ext() -> None:
    # Arrange
    service = ModuleResolverService()
    payload = _payload(coupling=BessCoupling.AC_COUPLED)

    # Act
    actual = service.resolve(payload)

    # Assert
    assert actual.pcs_count == 0
