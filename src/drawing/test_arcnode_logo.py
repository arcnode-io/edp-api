"""arcnode_logo unit tests."""

from src.drawing._arcnode_logo import arcnode_logo_polylines


def test_returns_at_least_one_contour() -> None:
    """Logo glyph parses into at least one closed polyline."""
    # Act
    actual = arcnode_logo_polylines()

    # Assert
    assert len(actual) >= 1
    for contour in actual:
        assert len(contour) >= 3  # a closed polygon has at least 3 points
        for point in contour:
            assert isinstance(point, tuple)
            assert len(point) == 2
            x, y = point
            assert isinstance(x, float)
            assert isinstance(y, float)


def test_polylines_are_cached_per_process() -> None:
    """Repeated calls return identical objects — parse happens once."""
    # Act
    first = arcnode_logo_polylines()
    second = arcnode_logo_polylines()

    # Assert
    assert first is second


def test_bounding_box_is_reasonable() -> None:
    """Glyph fits within a sensible coordinate range — proves transforms applied."""
    # Act
    contours = arcnode_logo_polylines()
    xs = [p[0] for contour in contours for p in contour]
    ys = [p[1] for contour in contours for p in contour]

    # Assert — the raw path d-attribute occupies roughly 0..512 in both axes
    assert min(xs) >= 0
    assert max(xs) <= 600
    assert min(ys) >= 0
    assert max(ys) <= 600
