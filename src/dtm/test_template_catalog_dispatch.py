"""Real catalog: DER dispatch and operating envelope templates."""

from pathlib import Path


from src.dtm.template_loader import TemplateLoader


def test_load_real_catalog_operating_envelope_is_published_by_der_control_api() -> None:
    # Arrange — the DOE arrives as an IEEE 2030.5 DERControl to ems-der-control-api,
    # which publishes it (DispatchPublisher); the DNP3 RTU is mock DERMS, not ours.
    repo_root = Path(__file__).resolve().parents[2]
    catalog = TemplateLoader(root=repo_root / "device_templates").load_catalog()
    envelope = catalog["operating_envelope"]
    # Act / Assert
    for name in ("import_limit", "export_limit", "status"):
        m = envelope.measurements[name]
        assert m.binding is None
        assert m.publisher is not None and m.publisher.value == "der_control_api"
    assert envelope.install_tasks == []


def test_load_real_catalog_includes_der_dispatch() -> None:
    """Recreated to match ems-der-control-api's post-clean-slate rebuild
    (DispatchPublisher/DispatchState/DispatchCommandSubscriber) — not the
    old shape resurrected blindly, verified against that repo's real code.
    """
    # Arrange
    repo_root = Path(__file__).resolve().parents[2]
    loader = TemplateLoader(root=repo_root / "device_templates")
    # Act
    catalog = loader.load_catalog()
    # Assert
    dd = catalog["der_dispatch"]
    assert dd.kind.value == "leaf"

    tap = dd.measurements["target_active_power"]
    assert tap.publisher is not None and tap.publisher.value == "der_control_api"
    assert tap.binding is None
    present = dd.measurements["target_setpoint_present"]
    assert (present.type, present.publisher) == ("bool", tap.publisher)
    # Ordinals match DispatchMode.java; set over the broker, not an open PUT
    mode = dd.measurements["dispatch_mode"]
    assert (mode.values, mode.publisher) == ({0: "AUTO", 1: "MANUAL"}, tap.publisher)
    set_mode = dd.commands["set_dispatch_mode"]
    assert (set_mode.verb, set_mode.target, set_mode.payload) == (
        "set",
        "dispatch_mode",
        "enum",
    )
    assert set_mode.fanout == dd.commands["approve_dispatch"].fanout
    # Operator reserve: effective floor = max(supplier floor, operator reserve)
    reserve = dd.measurements["operator_reserve"]
    assert (reserve.unit, reserve.publisher) == ("watt_hours", tap.publisher)
    set_reserve = dd.commands["set_operator_reserve"]
    assert (set_reserve.target, set_reserve.payload, set_reserve.fanout) == (
        "operator_reserve",
        "float",
        set_mode.fanout,
    )

    der_event_state = dd.measurements["der_event_state"]
    assert der_event_state.type == "enum"
    assert der_event_state.values == {
        0: "IDLE",
        1: "PENDING",
        2: "ARMED",
        3: "ACTIVE",
        4: "REJECTED",
    }
    # Which DERProgram the governing event came from (2030.5 has no reason field)
    program = dd.measurements["der_event_program"]
    assert (program.values, program.publisher) == (
        {0: "NONE", 1: "DLR_LINE_CONSTRAINT", 2: "ERCOT_FLEX"},
        tap.publisher,
    )

    shortfall = dd.measurements["dispatch_shortfall"]
    assert shortfall.type == "bool"
    assert shortfall.publisher is not None
    assert shortfall.publisher.value == "der_control_api"

    # Gateway-computed, no binding: it sums whatever distribute-parent
    # devices exist (ems-industrial-gateway/src/der_dispatch.rs), a formula
    # that doesn't fit either existing synthetic mode (der_dispatch has no
    # contains: relationship to bess_module — siblings, not parent/child).
    # local_process, not gateway: Publisher.GATEWAY's own docstring promises
    # it's always paired with a synthetic binding, which doesn't apply here.
    actual = dd.measurements["actual_active_power"]
    assert actual.type == "float"
    assert actual.publisher is not None
    assert actual.publisher.value == "local_process"
    assert actual.binding is None

    approve = dd.commands["approve_dispatch"]
    assert approve.verb == "enable"
    assert approve.target == "event_active"
    assert approve.fanout is not None and approve.fanout.value == "der_control_api"

    reject = dd.commands["reject_dispatch"]
    assert reject.verb == "disable"
    assert reject.target == "event_active"
    assert reject.fanout is not None and reject.fanout.value == "der_control_api"
