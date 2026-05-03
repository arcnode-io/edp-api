"""Device Topology Manifest — what edp-api emits, what ems-device-api revises."""

from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class EmsMode(StrEnum):
    """EMS execution mode. SIM on initial emit; ems-device-api flips to LIVE."""

    SIM = "sim"
    LIVE = "live"


class ProtocolKind(StrEnum):
    """Supported on-the-wire protocols. Ethernet TCP only at MVP."""

    MODBUS_TCP = "modbus_tcp"
    DNP3_TCP = "dnp3_tcp"
    SNMP = "snmp"
    CANOPEN_GW = "canopen_gw"
    REDFISH = "redfish"


class PointMap(BaseModel):
    """Modbus / DNP3 register slot."""

    name: str
    function_code: int  # modbus FC: 3=holding, 4=input
    start_address: int
    count: int


class OidMap(BaseModel):
    """SNMP OID slot."""

    name: str
    oid: str


class PdoMap(BaseModel):
    """CANopen PDO mapping."""

    name: str
    cob_id: int
    byte_offset: int
    byte_length: int


class RedfishResourceMap(BaseModel):
    """Redfish resource path slot."""

    name: str
    uri: str


class SnmpV3Creds(BaseModel):
    """SNMPv3 user + auth/priv algorithms."""

    user: str
    auth_proto: str  # SHA256, SHA512
    priv_proto: str  # AES128, AES256


class ModbusTcpConfig(BaseModel):
    """Per-device Modbus TCP binding."""

    protocol: Literal[ProtocolKind.MODBUS_TCP]
    unit_id: int
    point_maps: list[PointMap]


class Dnp3TcpConfig(BaseModel):
    """Per-device DNP3 TCP binding."""

    protocol: Literal[ProtocolKind.DNP3_TCP]
    master_addr: int
    outstation_addr: int
    point_maps: list[PointMap]


class SnmpConfig(BaseModel):
    """Per-device SNMP v3 binding."""

    protocol: Literal[ProtocolKind.SNMP]
    creds: SnmpV3Creds
    oid_maps: list[OidMap]


class CanopenGwConfig(BaseModel):
    """Per-device CANopen-over-Ethernet gateway binding."""

    protocol: Literal[ProtocolKind.CANOPEN_GW]
    gateway_vendor: str
    node_id: int
    pdo_maps: list[PdoMap]


class RedfishConfig(BaseModel):
    """Per-device Redfish binding."""

    protocol: Literal[ProtocolKind.REDFISH]
    username: str
    password_secret_ref: str
    service_root: str = "/redfish/v1"
    resource_maps: list[RedfishResourceMap]


ProtocolConfig = Annotated[
    ModbusTcpConfig | Dnp3TcpConfig | SnmpConfig | CanopenGwConfig | RedfishConfig,
    Field(discriminator="protocol"),
]


class SizingParams(BaseModel):
    """Aggregate sizing for the deployment — drives EMS bookkeeping."""

    P_compute_total_kW: float
    E_BESS_total_kWh: float
    T_coolant_setpoint_C: float


class Module(BaseModel):
    """One container instance."""

    module_id: str
    module_type: str
    container_position: str
    description: str


class Device(BaseModel):
    """One physical device inside a Module."""

    device_uuid: UUID
    device_type: str
    module_id: str  # FK -> Module.module_id
    host: str
    port: int
    protocol_config: ProtocolConfig
    description: str


class Dtm(BaseModel):
    """Top-level DTM. SIM at edp-api emit; ems-device-api flips to LIVE."""

    deployment_uuid: UUID
    ems_mode: EmsMode = EmsMode.SIM
    sizing_params: SizingParams
    modules: list[Module]
    devices: list[Device]

    @model_validator(mode="after")
    def fk_modules(self) -> "Dtm":
        """Every Device.module_id must reference an existing Module.module_id."""
        ids = {m.module_id for m in self.modules}
        for d in self.devices:
            if d.module_id not in ids:
                raise ValueError(
                    f"device {d.device_uuid}: module_id {d.module_id!r} not in modules"
                )
        return self
