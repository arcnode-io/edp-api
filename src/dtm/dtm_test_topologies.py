"""Inline mock topologies for DTM generator tests, decoupled from edp-module-assemblies."""

COMPUTE_TOPOLOGY: dict = {
    "devices": [
        {
            "template": "gpu_node",
            "tag": f"NODE-{i}",
            "description": f"node {i}",
            "connection": {"host": "mock-redfish-server", "port": 8443},
        }
        for i in range(1, 4)  # 3 nodes for test simplicity
    ]
    + [
        {
            "template": "cdu",
            "tag": "CDU-1",
            "description": "cdu",
            "connection": {"host": "mock-redfish-server", "port": 8443},
        }
    ],
    "buses": [],
}


# H100 container: its own node + module templates (power cap targets them)
H100_COMPUTE_TOPOLOGY: dict = {
    "module_template": "compute_module_h100",
    "devices": [
        {
            "template": "gpu_node_h100",
            "tag": f"NODE-{i}",
            "description": f"node {i}",
            "connection": {"host": "mock-redfish-server", "port": 8443},
        }
        for i in range(1, 4)
    ],
    "buses": [],
}


GRID_TOPOLOGY: dict = {
    "devices": [
        {
            "template": "switchgear",
            "tag": "SWG-1",
            "description": "swg",
            "connection": {"host": "mock-modbus-server", "port": 502, "unit_id": "1"},
        },
        {
            "template": "poi_meter",
            "tag": "MTR-POI",
            "description": "meter",
            "connection": {"host": "mock-modbus-server", "port": 502, "unit_id": "2"},
        },
        {
            "template": "protective_relay",
            "tag": "RLY-1",
            "description": "relay",
            "connection": {"host": "mock-dnp3-server", "port": 20000},
        },
        {"template": "transformer", "tag": "T1", "description": "xfmr"},
        {"template": "lv_switchboard", "tag": "SWBD-1", "description": "swbd"},
    ],
    # Feeder bus as edp-module-assemblies writes it; the POI meter goes on
    # site_mv (site_buses)
    "buses": [
        {
            "bus_id": "ac_main",
            "type": "ac",
            "members": [
                {"device_template": "switchgear", "port": "line_out"},
                {"device_template": "protective_relay", "port": "line_in"},
                {"device_template": "transformer", "port": "hv_in"},
            ],
        }
    ],
}


# Feeder grid container: primary minus the POI meter
FEEDER_TOPOLOGY: dict = {
    "devices": [d for d in GRID_TOPOLOGY["devices"] if d["template"] != "poi_meter"],
    "buses": GRID_TOPOLOGY["buses"],
}
