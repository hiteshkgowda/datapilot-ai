"""PDF rendering for reports.

Separates the rendering *view model* (the dataclasses below) from the
orchestration that fills it (``ReportService``). The builder is pure layout: it
turns a :class:`ReportModel` into PDF bytes via ReportLab, and visually
separates deterministic content from AI-generated content.

Charts are rendered from the *existing* Plotly ``chart_spec`` via kaleido. If
kaleido cannot export an image, the section degrades to a data table.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from io import BytesIO
from typing import Any, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# Maximum rows shown when a chart degrades to a data table.
_MAX_TABLE_ROWS = 15


def figure_to_png(chart_spec: dict) -> Optional[bytes]:
    """Render a Plotly figure spec to PNG bytes, or ``None`` on failure.

    Returns ``None`` if kaleido is unavailable or export fails, so callers can
    fall back to a table representation.
    """
    try:
        import plotly.graph_objects as go
        import plotly.io as pio

        figure = go.Figure(chart_spec)
        return pio.to_image(
            figure, format="png", width=900, height=500, scale=2, engine="kaleido"
        )
    except Exception:
        return None


@dataclass(frozen=True)
class StatRow:
    """One row of the key-statistics table."""

    column: str
    count: int
    mean: float
    minimum: float
    maximum: float
    total: float


@dataclass(frozen=True)
class ChartSection:
    """A single chart, rendered as an image or (fallback) a data table."""

    title: str
    chart_type: Optional[str]
    render_mode: str  # "image" or "table"
    image_png: Optional[bytes] = None
    table: Optional[list[dict[str, Any]]] = None


@dataclass(frozen=True)
class QASection:
    """An AI-generated question/answer section (non-deterministic)."""

    question: str
    answer: str
    chart: Optional[ChartSection] = None


@dataclass(frozen=True)
class ReportModel:
    """The full view model handed to :class:`PdfBuilder`."""

    report_id: str
    report_version: str
    generated_at: datetime
    dataset_id: str
    dataset_filename: str
    summary: dict[str, Any]
    statistics: list[StatRow] = field(default_factory=list)
    charts: list[ChartSection] = field(default_factory=list)
    insights: list[str] = field(default_factory=list)
    qa_sections: list[QASection] = field(default_factory=list)


def _fmt(value: Any) -> str:
    """Format a numeric value for display."""
    if isinstance(value, float):
        return f"{value:,.4g}"
    return str(value)


class PdfBuilder:
    """Render a :class:`ReportModel` into PDF bytes."""

    def __init__(self) -> None:
        styles = getSampleStyleSheet()
        self._title = styles["Title"]
        self._h2 = styles["Heading2"]
        self._h3 = styles["Heading3"]
        self._body = styles["BodyText"]
        self._meta = ParagraphStyle(
            "meta", parent=self._body, fontSize=8, textColor=colors.grey
        )
        self._group_deterministic = ParagraphStyle(
            "det",
            parent=self._h2,
            backColor=colors.HexColor("#e6f4ea"),
            borderPadding=6,
            textColor=colors.HexColor("#1e4620"),
        )
        self._group_ai = ParagraphStyle(
            "ai",
            parent=self._h2,
            backColor=colors.HexColor("#fff3cd"),
            borderPadding=6,
            textColor=colors.HexColor("#7a5b00"),
        )

    def build(self, model: ReportModel) -> bytes:
        """Build the PDF and return its bytes."""
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            title=f"Data Report — {model.dataset_filename}",
            leftMargin=20 * mm,
            rightMargin=20 * mm,
            topMargin=18 * mm,
            bottomMargin=18 * mm,
        )
        story: list[Any] = []

        # --- Title & metadata ---
        story.append(Paragraph("Data Report", self._title))
        story.append(Paragraph(model.dataset_filename, self._h3))
        story.append(
            Paragraph(
                f"Report ID: {model.report_id}<br/>"
                f"Report version: {model.report_version}<br/>"
                f"Generated at: {model.generated_at.isoformat()}<br/>"
                f"Dataset ID: {model.dataset_id}",
                self._meta,
            )
        )
        story.append(Spacer(1, 8 * mm))

        # --- Deterministic group ---
        story.append(
            Paragraph("Deterministic Analysis", self._group_deterministic)
        )
        story.append(Spacer(1, 4 * mm))
        self._add_summary(story, model)
        self._add_statistics(story, model)
        self._add_charts(story, model)
        self._add_insights(story, model)

        # --- AI-generated group (optional) ---
        if model.qa_sections:
            story.append(Spacer(1, 6 * mm))
            story.append(HRFlowable(width="100%", color=colors.grey))
            story.append(
                Paragraph(
                    "AI-Generated Sections (non-deterministic)", self._group_ai
                )
            )
            story.append(
                Paragraph(
                    "The following answers were produced by a language model "
                    "and may vary between runs.",
                    self._meta,
                )
            )
            story.append(Spacer(1, 4 * mm))
            self._add_qa_sections(story, model)

        doc.build(story)
        return buffer.getvalue()

    # ------------------------------------------------------------------ #
    # Deterministic sections
    # ------------------------------------------------------------------ #
    def _add_summary(self, story: list[Any], model: ReportModel) -> None:
        story.append(Paragraph("Dataset Summary", self._h3))
        summary = model.summary
        rows = [
            ["Filename", model.dataset_filename],
            ["Rows", _fmt(summary.get("rows", 0))],
            ["Columns", _fmt(summary.get("columns", 0))],
            [
                "Column names",
                Paragraph(", ".join(summary.get("column_names", [])), self._body),
            ],
        ]
        story.append(self._key_value_table(rows))
        story.append(Spacer(1, 5 * mm))

    def _add_statistics(self, story: list[Any], model: ReportModel) -> None:
        if not model.statistics:
            return
        story.append(Paragraph("Key Statistics", self._h3))
        header = ["Column", "Count", "Mean", "Min", "Max", "Sum"]
        data = [header] + [
            [
                row.column,
                _fmt(row.count),
                _fmt(row.mean),
                _fmt(row.minimum),
                _fmt(row.maximum),
                _fmt(row.total),
            ]
            for row in model.statistics
        ]
        story.append(self._grid_table(data, header_row=True))
        story.append(Spacer(1, 5 * mm))

    def _add_charts(self, story: list[Any], model: ReportModel) -> None:
        if not model.charts:
            return
        story.append(Paragraph("Charts", self._h3))
        for chart in model.charts:
            self._add_chart_section(story, chart)

    def _add_chart_section(self, story: list[Any], chart: ChartSection) -> None:
        label = chart.title
        if chart.chart_type:
            label = f"{label} ({chart.chart_type})"
        story.append(Paragraph(label, self._body))
        if chart.render_mode == "image" and chart.image_png:
            story.append(
                Image(BytesIO(chart.image_png), width=160 * mm, height=89 * mm)
            )
        elif chart.table:
            story.append(
                Paragraph(
                    "(chart image unavailable — showing underlying data)",
                    self._meta,
                )
            )
            story.append(self._records_table(chart.table))
        story.append(Spacer(1, 5 * mm))

    def _add_insights(self, story: list[Any], model: ReportModel) -> None:
        if not model.insights:
            return
        story.append(Paragraph("Insights", self._h3))
        for insight in model.insights:
            story.append(Paragraph(f"• {insight}", self._body))
        story.append(Spacer(1, 4 * mm))

    # ------------------------------------------------------------------ #
    # AI-generated sections
    # ------------------------------------------------------------------ #
    def _add_qa_sections(self, story: list[Any], model: ReportModel) -> None:
        for qa in model.qa_sections:
            story.append(Paragraph(f"<b>Q:</b> {qa.question}", self._body))
            story.append(Paragraph(f"<b>A:</b> {qa.answer}", self._body))
            if qa.chart is not None:
                self._add_chart_section(story, qa.chart)
            story.append(Spacer(1, 4 * mm))

    # ------------------------------------------------------------------ #
    # Table helpers
    # ------------------------------------------------------------------ #
    def _key_value_table(self, rows: list[list[Any]]) -> Table:
        table = Table(rows, colWidths=[40 * mm, 120 * mm])
        table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f2f2f2")),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        return table

    def _grid_table(self, data: list[list[Any]], header_row: bool) -> Table:
        table = Table(data)
        style = [
            ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
        ]
        if header_row:
            style += [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#34495e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ]
        table.setStyle(TableStyle(style))
        return table

    def _records_table(self, records: list[dict[str, Any]]) -> Table:
        clipped = records[:_MAX_TABLE_ROWS]
        columns = list(clipped[0].keys()) if clipped else []
        data = [columns] + [
            [_fmt(row.get(col, "")) for col in columns] for row in clipped
        ]
        return self._grid_table(data, header_row=True)
