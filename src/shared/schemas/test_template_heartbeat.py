"""A template declares the keep-alive its device needs from the EMS."""

from pathlib import Path

from src.dtm.template_loader import TemplateLoader
from src.shared.schemas.template_heartbeat import Heartbeat
from src.shared.schemas.template_protocols import ModbusBinding

_ROOT = Path(__file__).resolve().parents[3] / "device_templates"


def test_catl_bms_wants_a_counter_at_0x0380_every_second() -> None:
    # Arrange — CATL BMS raises "EMS heartbeat fault" without it
    catalog = TemplateLoader(root=_ROOT).load_catalog()

    # Act
    actual = catalog["bess_catl"].heartbeat

    # Assert
    assert actual == Heartbeat(
        binding=ModbusBinding(
            protocol="modbus_tcp",
            function_code=6,
            address=0x0380,
            data_type="uint16",
        ),
        counter_modulo=256,
        period_s=1.0,
    )
