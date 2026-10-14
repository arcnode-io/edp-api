"""Reference designators: device tags per container range, runs compressed."""

from src.bom_generator.bom_ref_des import ref_des


def test_runs_of_tags_compress_under_their_container_range() -> None:
    # Arrange
    pdus = ["PDU-A1", "PDU-A2", "PDU-A3", "PDU-B1", "PDU-B2", "PDU-B3"]

    # Act
    actual = ref_des([("C", 1, 10, pdus)])

    # Assert
    assert actual == "C1-C10: PDU-A1…A3, PDU-B1…B3"


def test_groups_with_the_same_tags_merge() -> None:
    # Arrange — primary G1 and feeders G2-G3 each hold relay RLY-1
    groups = [("G", 1, 1, ["RLY-1"]), ("G", 2, 3, ["RLY-1"])]

    # Act
    actual = ref_des(groups)

    # Assert
    assert actual == "G1-G3: RLY-1"
