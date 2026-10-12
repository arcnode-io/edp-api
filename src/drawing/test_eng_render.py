"""serialize_pdf: every page is an A3 sheet, whatever the content extents."""

import io
import re

import ezdxf

from src.drawing._eng_render import serialize_dxf, serialize_pdf

# A3 landscape in PDF points (1/72 in)
A3_POINTS: tuple[float, float] = (16.54 * 72, 11.69 * 72)


def test_page_is_a3_even_when_content_is_a_thin_strip() -> None:
    # Arrange — a long thin line used to stretch the page to 16 x 2 in
    doc = ezdxf.new(dxfversion="R2018")
    doc.modelspace().add_line((0, 0), (2000, 10))

    # Act
    pdf = serialize_pdf([doc], title="t")

    # Assert
    boxes = re.findall(rb"/MediaBox \[ ?0 0 ([\d.]+) ([\d.]+)", pdf)
    actual = [(round(float(w)), round(float(h))) for w, h in boxes]
    assert actual == [(round(A3_POINTS[0]), round(A3_POINTS[1]))]


def test_dxf_lays_every_sheet_side_by_side() -> None:
    # Arrange
    sheets = []
    for label in ("one", "two"):
        doc = ezdxf.new(dxfversion="R2018")
        doc.modelspace().add_text(label).set_placement((10, 10))
        sheets.append(doc)

    # Act
    dxf = serialize_dxf(sheets)

    # Assert — sheet 2 sits one sheet width + gap to the right
    doc = ezdxf.read(io.StringIO(dxf.decode("utf-8")))
    actual = {t.dxf.text: round(t.dxf.insert.x) for t in doc.modelspace().query("TEXT")}
    assert actual == {"one": 10, "two": 10 + 450}
