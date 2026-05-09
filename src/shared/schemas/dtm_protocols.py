"""Protocol-level DTM types.

Split out from dtm.py so the top-level schema stays under the file-size budget.
Owns the placeholder sentinel + ProvisionedInt because Dnp3 binding fields are
the primary site for utility-assigned values.
"""

from enum import StrEnum
from typing import Annotated, Final, Literal

from pydantic import BaseModel, Field

# Sentinel used in DTM YAML for fields the utility assigns at commissioning.
# Presence of this value in any field flags a Device as still pending.
# Reason: typed as Final without explicit annotation so the type is the
# Literal string, not str — lets ProvisionedInt accept it cleanly.
PROVISIONED_AT_COMMISSIONING: Final = "PROVISIONED_AT_COMMISSIONING"

# Int field that may carry the placeholder until the utility provisions it.
ProvisionedInt = int | Literal["PROVISIONED_AT_COMMISSIONING"]


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
    master_addr: ProvisionedInt
    outstation_addr: ProvisionedInt
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
