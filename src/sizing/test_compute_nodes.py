"""The last compute container holds only the servers ordered, and their PDUs."""

import pytest

from src.sizing.compute_nodes import dropped_tags


@pytest.mark.parametrize(
    ("nodes", "expected"),
    [
        (7, set()),
        (
            4,
            {"NODE-5", "NODE-6", "NODE-7", "PDU-A3", "PDU-B3"},
        ),
        (
            1,
            {
                *(f"NODE-{i}" for i in range(2, 8)),
                *("PDU-A2", "PDU-A3", "PDU-B2", "PDU-B3"),
            },
        ),
    ],
)
def test_a_partial_container_drops_unused_servers_and_pdus(
    nodes: int, expected: set[str]
) -> None:
    # Act — 3 servers per PDU per side (34.5 kVA, A/B failover)
    actual = dropped_tags(nodes)

    # Assert
    assert actual == expected
