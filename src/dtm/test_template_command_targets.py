"""Every command acts on a measurement of its own template (device-api's rule).

power_cap is exempt: a fleet cap's target is the key it matches on each
child's own command, so the parent publishes no such channel.
"""

from pathlib import Path

from src.dtm.template_loader import TemplateLoader

_ROOT = Path(__file__).resolve().parents[2] / "device_templates"


def test_every_command_targets_a_measurement_of_its_template() -> None:
    # Arrange — device-api refuses its whole catalog otherwise
    catalog = TemplateLoader(root=_ROOT).load_catalog()

    # Act
    orphans = [
        (name, cmd_name, cmd.target)
        for name, t in catalog.items()
        for cmd_name, cmd in t.commands.items()
        if cmd.target not in t.measurements
        and not (cmd.binding and cmd.binding.protocol == "power_cap")
    ]

    # Assert
    assert orphans == []
