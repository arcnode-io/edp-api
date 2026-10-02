"""Module-level bindings that name which children they act on."""

from src.shared.schemas.template_module_bindings import (
    PowerCapBinding,
    SyntheticBinding,
)


def test_synthetic_rollup_names_the_child_template_it_sums() -> None:
    # Arrange / Act — a compute module's children are pdu, gpu_node, cdu, switch
    b = SyntheticBinding(
        protocol="synthetic",
        operation="sum",
        source_measurement="input_power",
        child_template="pdu",
    )
    # Assert
    assert (b.child_template, b.source_measurement) == ("pdu", "input_power")


def test_power_cap_names_the_child_template_and_its_cap_commands() -> None:
    # Arrange
    commands = [f"set_gpu_{n}_power_limit" for n in range(1, 9)]
    # Act
    b = PowerCapBinding(
        protocol="power_cap", child_template="gpu_node", child_commands=commands
    )
    # Assert
    assert (b.child_template, b.child_commands) == ("gpu_node", commands)
