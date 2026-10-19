"""Templates carry install tasks; dependencies must name known tasks."""

import pytest
from pydantic import ValidationError

from src.shared.schemas.template import (
    CxLevel,
    DeviceTemplate,
    InstallTask,
    TemplateKind,
)
from src.shared.schemas.template_test_support import (
    _mv,
)

# --- install_tasks ---


def test_device_template_carries_install_tasks() -> None:
    # Arrange / Act
    t = DeviceTemplate(
        template="pdu",
        kind=TemplateKind.LEAF,
        equipment_id="CMP-PDU-001",
        vendor="Server Technology",
        model="PRO3X",
        description="rack PDU",
        measurements=_mv(),
        install_tasks=[
            InstallTask(
                name="mount",
                est_minutes=20,
                crew_role="electrician",
                cx_level=CxLevel.L1,
            ),
            InstallTask(
                name="wire_input",
                depends_on=["mount"],
                est_minutes=30,
                crew_role="electrician",
                cx_level=CxLevel.L2,
            ),
        ],
    )
    # Assert
    assert len(t.install_tasks) == 2
    assert t.install_tasks[1].depends_on == ["mount"]
    assert t.install_tasks[1].cx_level == CxLevel.L2


def test_install_task_depends_on_must_be_known() -> None:
    with pytest.raises(ValidationError, match="depends_on"):
        DeviceTemplate(
            template="pdu",
            kind=TemplateKind.LEAF,
            equipment_id="CMP-PDU-001",
            vendor="Server Technology",
            model="PRO3X",
            description="rack PDU",
            measurements=_mv(),
            install_tasks=[
                InstallTask(
                    name="mount",
                    depends_on=["nonexistent"],
                    est_minutes=20,
                    crew_role="electrician",
                    cx_level=CxLevel.L1,
                ),
            ],
        )
