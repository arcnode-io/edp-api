"""Site-level buses joining containers: 13.8 kV site bus + one LV bus per G.

Container topology yamls only bus their own gear; these buses say how the
containers connect to each other, so the HMI SLD can draw the whole site.
"""

from src.dtm.dtm_generator_internals import assign_slug
from src.shared.schemas.dtm import Bus, BusMember, Device
from src.shared.schemas.module_resolution import ModuleResolution
from src.sizing.compute_feeds import compute_feeds


def site_bus(
    battery: str, by_template: dict[str, list[str]], slug_counter: dict[str, int]
) -> Bus:
    """The 13.8 kV site bus (by others, ADR-018): POI meter, each G's MV breaker, battery.

    Source side first: the POI meter (G1 only) watches the utility tie.
    Every battery ties in here through customer gear (ADR-016, ADR-022), so
    the battery module is the member; the step-up and MV disconnect are
    by others and not in the device data.
    """
    meters = [
        BusMember(device_id=m, port="voltage_in")
        for m in by_template.get("poi_meter", [])
    ]
    breakers = [
        BusMember(device_id=sw, port="line_in")
        for sw in by_template.get("switchgear", [])
    ]
    return Bus(
        bus_id=assign_slug("site_mv", slug_counter),
        type="ac",
        members=[*meters, *breakers, BusMember(device_id=battery, port="ac_out")],
    )


def lv_main_buses(
    resolution: ModuleResolution,
    devices: dict[str, Device],
    by_template: dict[str, list[str]],
    slug_counter: dict[str, int],
) -> list[Bus]:
    """One LV bus per grid container: transformer secondary, switchboard, the compute it feeds.

    Reason: ADR-018's even split lives in compute_feeds; putting it in the
    DTM keeps consumers from re-deriving a sizing rule.
    """
    # Compute modules are the top-level devices named C1…CN.
    modules = {
        d.display_name: d.device_id for d in devices.values() if d.parent is None
    }
    switchboards = by_template.get("lv_switchboard", [])
    transformers = by_template.get("transformer", [])
    # Reason: ProfileAssemblies.grid_container is optional; no grid, no LV bus.
    if not switchboards:
        return []
    feeds = compute_feeds(
        resolution.compute_container_count, resolution.grid_container_count
    )
    return [
        Bus(
            bus_id=assign_slug("lv_main", slug_counter),
            type="ac",
            members=[
                BusMember(device_id=xfmr, port="lv_out"),
                BusMember(device_id=swbd, port="feeder_out"),
                *(BusMember(device_id=modules[f"C{n}"], port="ac_in") for n in fed),
            ],
        )
        for xfmr, swbd, fed in zip(transformers, switchboards, feeds, strict=True)
    ]
