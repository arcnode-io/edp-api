"""ADR-018: which compute containers each grid container feeds."""

from math import ceil


def compute_feeds(compute_qty: int, grid_qty: int) -> list[list[int]]:
    """Compute container numbers fed by each grid container.

    ADR-018: grid container k feeds the next q = ceil(N / M) compute
    containers in order. Grid count is sized from site peak, so an even
    split keeps each under its rating.

    Example:
        >>> compute_feeds(compute_qty=10, grid_qty=3)
        [[1, 2, 3, 4], [5, 6, 7, 8], [9, 10]]
    """
    per_grid = ceil(compute_qty / grid_qty)
    numbers = list(range(1, compute_qty + 1))
    return [numbers[k * per_grid : (k + 1) * per_grid] for k in range(grid_qty)]
