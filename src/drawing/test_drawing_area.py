"""Drawing area: content stays out of the border and the title block."""

import ezdxf
from ezdxf.document import Drawing

from src.drawing._drawing_area import bind_to_drawing_area, violations
from src.drawing._eng_title_block import draw_sheet_frame


def _sheet_with_line(start: tuple[float, float], end: tuple[float, float]) -> Drawing:
    doc = ezdxf.new(dxfversion="R2018", setup=True)
    msp = doc.modelspace()
    doc.layers.add("FRAME")
    draw_sheet_frame(msp)
    msp.add_line(start, end, dxfattribs={"layer": "WIRE"})
    return doc


def test_content_crossing_the_title_block_is_a_violation() -> None:
    # Arrange — a line running down into the bottom-right title block
    doc = _sheet_with_line((300, 200), (300, 20))

    # Act
    actual = violations(doc.modelspace())

    # Assert
    assert len(actual) == 1


def test_binding_scales_overflowing_content_into_the_drawing_area() -> None:
    # Arrange — a 600 mm line: wider than the sheet and through the title block
    doc = _sheet_with_line((-100, 30), (500, 30))

    # Act
    bind_to_drawing_area(doc.modelspace())

    # Assert
    assert violations(doc.modelspace()) == []


def test_content_already_inside_the_drawing_area_is_left_alone() -> None:
    # Arrange
    doc = _sheet_with_line((20, 100), (200, 100))
    line = doc.modelspace().query("LINE[layer=='WIRE']").first

    # Act
    bind_to_drawing_area(doc.modelspace())

    # Assert
    assert (tuple(line.dxf.start)[:2], tuple(line.dxf.end)[:2]) == (
        (20.0, 100.0),
        (200.0, 100.0),
    )
