"""Shared serializers for ARCNODE engineering DXF + PDF deliverables.

Both formats are deterministic, vector-only. PDF specifically: all stroke
+ text content goes through matplotlib's PDF backend as path/text
operators (NOT rasterized). Reviewers' PDF viewers re-render the vector
content at whatever zoom they want without fuzz.

Configuration forces black-on-white. ezdxf's default color 7 = "BYLAYER"
which the matplotlib backend renders white-on-white if you don't override
— the engineering deliverable would arrive blank in a normal PDF viewer.

Multi-sheet output: pass `pages` as a list of `Drawing` objects. Each
ezdxf doc becomes one page in the PDF via matplotlib's PdfPages.
"""

import io

import matplotlib

# Reason: pick the non-interactive backend BEFORE importing pyplot so
# the matplotlib agg path doesn't try to attach to a display (Docker / CI).
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from ezdxf.addons.drawing import Frontend, RenderContext
from ezdxf.addons.drawing.config import (
    BackgroundPolicy,
    ColorPolicy,
    Configuration,
)
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
from ezdxf.document import Drawing
from matplotlib.backends.backend_pdf import PdfPages

# A3 landscape in inches: 420 mm x 297 mm / 25.4 mm/in
_A3_LANDSCAPE_INCHES: tuple[float, float] = (16.54, 11.69)
# Bitmap fallback DPI — only kicks in for elements matplotlib can't vectorize
# (none in our pipeline today; setting high so future raster fallbacks are sharp).
_PDF_DPI: int = 400


def serialize_dxf(doc: Drawing) -> bytes:
    """ASCII DXF bytes. ezdxf.write takes a text stream."""
    buf = io.StringIO()
    doc.write(buf, fmt="asc")
    return buf.getvalue().encode("utf-8")


def serialize_pdf(pages: list[Drawing], *, title: str) -> bytes:
    """One PDF, one page per ezdxf Drawing — black-on-white vector.

    Args:
        pages: 1+ ezdxf Drawings; each becomes a PDF page in order.
        title: PDF document metadata title (e.g. "ARCNODE SLD",
               "ARCNODE P&ID — COOLANT SYSTEM").

    Returns:
        PDF bytes ready to upload as the engineering artifact.
    """
    cfg = Configuration(
        background_policy=BackgroundPolicy.WHITE,
        color_policy=ColorPolicy.BLACK,
    )
    pdf_buf = io.BytesIO()
    with PdfPages(pdf_buf, metadata={"Title": title}) as pdf:
        for doc in pages:
            fig = plt.figure(figsize=_A3_LANDSCAPE_INCHES)
            # Reason: matplotlib stubs expect a 4-tuple, not a list.
            ax = fig.add_axes((0.0, 0.0, 1.0, 1.0))
            ax.set_axis_off()
            ctx = RenderContext(doc)
            Frontend(ctx, MatplotlibBackend(ax), config=cfg).draw_layout(
                doc.modelspace(), finalize=True
            )
            pdf.savefig(fig, dpi=_PDF_DPI, facecolor="white")
            plt.close(fig)
    return pdf_buf.getvalue()
