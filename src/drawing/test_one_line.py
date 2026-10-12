"""compute_feeds: compute containers split evenly over grid containers (ADR-018)."""

from src.drawing._one_line import compute_feeds


def test_compute_containers_fill_grid_containers_in_order() -> None:
    # Act
    actual = compute_feeds(compute_qty=10, grid_qty=3)

    # Assert — q = ceil(10 / 3) = 4 each, the last takes the rest
    assert actual == [[1, 2, 3, 4], [5, 6, 7, 8], [9, 10]]
