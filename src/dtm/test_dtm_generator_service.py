"""DtmGeneratorService unit tests with a mocked ManifestClient."""

from unittest.mock import MagicMock
from uuid import UUID

import pytest

from src.bom_generator.manifest_models import (
    AssemblyVariant,
    Manifest,
    PlateUrls,
    ProfileAssemblies,
)
from src.dtm.dtm_generator_service import DtmGeneratorService
from src.shared.enums import (
    BessCoupling,
    ClimateZone,
    DeploymentProfile,
    EmsTarget,
    GpuVariant,
    SourcingTier,
)
from src.shared.schemas.dtm import BlockingKind, EmsMode, ProtocolKind
from src.shared.schemas.module_resolution import ModuleResolution

DEPLOYMENT_ID: UUID = UUID("12345678-1234-1234-1234-123456789abc")


def _av(*, type_: str, variant: str, with_topology: bool = True) -> AssemblyVariant:
    base = f"s3://arcnode-artifacts/assemblies/{type_.replace('_', '-')}/{variant}"
    return AssemblyVariant(
        bom=f"{base}/bom.yaml",
        step=f"{base}/assembly.step",
        glb=f"{base}/assembly.glb",
        topology_yaml=f"{base}/topology.yaml" if with_topology else None,
    )


def _manifest(*, with_grid: bool = True, with_topology: bool = True) -> Manifest:
    """Minimal manifest with one compute + optional grid + commercial_ac profile."""
    assemblies = {
        "compute_container": {
            "commercial-ac": _av(
                type_="compute_container",
                variant="commercial-ac",
                with_topology=with_topology,
            )
        },
    }
    if with_grid:
        assemblies["grid_container"] = {
            "commercial-ac": _av(
                type_="grid_container",
                variant="commercial-ac",
                with_topology=with_topology,
            ),
        }
    return Manifest(
        version="0.1.0",
        assemblies=assemblies,
        plates={"CG": PlateUrls(spec="s3://test/CG.yaml", step="s3://test/CG.step")},
        profiles={
            "commercial_ac": ProfileAssemblies(
                compute_container="commercial-ac",
                grid_container="commercial-ac" if with_grid else None,
                interface_plates=["CG"],
            ),
        },
    )


def _modbus_bms_topology() -> dict:
    return {
        "devices": [
            {
                "device_type": "bms",
                "description": "Tesla Megapack BMS",
                "host": "mock-modbus-server",
                "port": 502,
                "protocol_config": {
                    "protocol": "modbus_tcp",
                    "unit_id": 1,
                    "point_maps": [
                        {
                            "name": "soc",
                            "function_code": 3,
                            "start_address": 0,
                            "count": 1,
                        }
                    ],
                },
            }
        ]
    }


def _empty_topology() -> dict:
    return {"devices": []}


def _resolution(
    *,
    profile: DeploymentProfile = DeploymentProfile.COMMERCIAL_AC,
    container_count: int = 1,
    coupling: BessCoupling = BessCoupling.AC_COUPLED,
    bess_mwh: float = 5.0,
) -> ModuleResolution:
    return ModuleResolution(
        deployment_id=DEPLOYMENT_ID,
        deployment_profile=profile,
        compute_container_count=container_count,
        grid_container_present=coupling != BessCoupling.NONE,
        bess_coupling=coupling,
        bess_capacity_mwh=bess_mwh,
        sourcing_tier=SourcingTier.COMMERCIAL,
        ems_target=EmsTarget.AWS_STANDARD,
        gpu_variant=GpuVariant.H100_SXM,
        gpu_count=container_count * 56,
        climate_zone=ClimateZone.TEMPERATE,
    )


def _make_client(*, with_grid: bool = True, with_topology: bool = True) -> MagicMock:
    client = MagicMock()
    client.fetch_manifest.return_value = _manifest(
        with_grid=with_grid, with_topology=with_topology
    )

    def fetch_topo(url: str) -> dict:
        if "compute-container" in url:
            return _modbus_bms_topology()
        if "grid-container" in url:
            return _empty_topology()
        raise ValueError(f"unmocked topology url: {url}")

    client.fetch_topology_yaml.side_effect = fetch_topo
    return client


def test_dtm_emits_sim_mode() -> None:
    # arrange
    service = DtmGeneratorService(_make_client())
    # act
    actual = service.generate(profile="commercial_ac", resolution=_resolution())
    # assert
    assert actual.ems_mode == EmsMode.SIM


def test_devices_replicated_per_compute_container() -> None:
    # arrange
    service = DtmGeneratorService(_make_client())
    expected_modules = 3
    expected_devices = 3  # 1 per compute topology x 3 containers
    # act
    actual = service.generate(
        profile="commercial_ac", resolution=_resolution(container_count=3)
    )
    # assert
    compute_modules = [
        m for m in actual.modules if m.module_type == "compute_container"
    ]
    compute_devices = [
        d for d in actual.devices if d.module_id.startswith("compute_container_")
    ]
    assert len(compute_modules) == expected_modules
    assert len(compute_devices) == expected_devices


def test_grid_module_present_when_profile_has_grid() -> None:
    # arrange
    service = DtmGeneratorService(_make_client(with_grid=True))
    # act
    actual = service.generate(profile="commercial_ac", resolution=_resolution())
    # assert
    grid_modules = [m for m in actual.modules if m.module_type == "grid_container"]
    assert len(grid_modules) == 1


def test_grid_module_absent_when_profile_has_no_grid() -> None:
    # arrange
    client = _make_client(with_grid=False)
    service = DtmGeneratorService(client)
    # act
    actual = service.generate(
        profile="commercial_ac",
        resolution=_resolution(coupling=BessCoupling.NONE, bess_mwh=0.0),
    )
    # assert
    grid_modules = [m for m in actual.modules if m.module_type == "grid_container"]
    assert grid_modules == []


def test_devices_carry_module_id_fk() -> None:
    # arrange
    service = DtmGeneratorService(_make_client())
    expected_compute_devices = 2  # 1 device per topology x 2 containers
    # act
    actual = service.generate(
        profile="commercial_ac", resolution=_resolution(container_count=2)
    )
    # assert
    module_ids = {m.module_id for m in actual.modules}
    for d in actual.devices:
        assert d.module_id in module_ids
    compute_devices = [d for d in actual.devices if "compute" in d.module_id]
    assert len(compute_devices) == expected_compute_devices


def test_sizing_params_derived_from_resolution() -> None:
    # arrange
    service = DtmGeneratorService(_make_client())
    expected_bess_kwh = 5000.0
    # act
    actual = service.generate(profile="commercial_ac", resolution=_resolution())
    # assert
    assert actual.sizing_params.E_BESS_total_kWh == expected_bess_kwh
    assert actual.sizing_params.P_compute_total_kW > 0


def test_unknown_profile_raises() -> None:
    # arrange
    service = DtmGeneratorService(_make_client())
    # act / assert
    with pytest.raises(ValueError, match="not in manifest"):
        service.generate(profile="dod_dc_int", resolution=_resolution())


def test_topology_missing_skips_devices_but_keeps_modules() -> None:
    # arrange
    service = DtmGeneratorService(_make_client(with_topology=False))
    # act
    actual = service.generate(profile="commercial_ac", resolution=_resolution())
    # assert — modules present (from resolution) but no devices
    compute_modules = [
        m for m in actual.modules if m.module_type == "compute_container"
    ]
    assert len(compute_modules) == 1
    assert actual.devices == []


def test_modbus_protocol_carries_through() -> None:
    # arrange
    service = DtmGeneratorService(_make_client())
    # act
    actual = service.generate(profile="commercial_ac", resolution=_resolution())
    # assert
    bms = next(d for d in actual.devices if d.device_type == "bms")
    assert bms.protocol_config.protocol == ProtocolKind.MODBUS_TCP


def test_device_inherits_default_blocking() -> None:
    # arrange — topology yaml omits blocking; spec default applies
    service = DtmGeneratorService(_make_client())
    # act
    actual = service.generate(profile="commercial_ac", resolution=_resolution())
    # assert
    bms = next(d for d in actual.devices if d.device_type == "bms")
    assert bms.blocking == [BlockingKind.LIVE_MODE]


def test_device_inherits_explicit_blocking_from_topology() -> None:
    # arrange — topology yaml declares blocking=[]; generator carries it through
    client = MagicMock()
    client.fetch_manifest.return_value = _manifest(with_grid=False)

    monitoring_only_topology = {
        "devices": [
            {
                "device_type": "monitor",
                "description": "monitoring-only device",
                "host": "10.0.0.5",
                "port": 502,
                "protocol_config": _modbus_bms_topology()["devices"][0][
                    "protocol_config"
                ],
                "blocking": [],
            }
        ]
    }
    client.fetch_topology_yaml.return_value = monitoring_only_topology
    service = DtmGeneratorService(client)
    # act
    actual = service.generate(
        profile="commercial_ac",
        resolution=_resolution(coupling=BessCoupling.NONE, bess_mwh=0.0),
    )
    # assert
    monitor = next(d for d in actual.devices if d.device_type == "monitor")
    assert monitor.blocking == []
