import csv
import io
from datetime import datetime
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from services.analytics_service import AnalyticsService


class ExportService:
    def __init__(self, db: Session):
        self.db = db
        self.analytics = AnalyticsService(db)

    def export_analytics(
        self,
        lot_id: str,
        start_date: datetime,
        end_date: datetime,
        export_format: str,
    ) -> tuple[bytes, str, str]:
        trends = self.analytics.get_occupancy_trends(lot_id, start_date, end_date)
        kpis = self.analytics.get_kpis(lot_id, start_date, end_date)
        heatmap = self.analytics.get_heatmap_data(lot_id, start_date, end_date)

        if export_format == "csv":
            content = self._build_csv(lot_id, trends, kpis, heatmap)
            filename = f"parkpilot-{lot_id}-{start_date.date()}-{end_date.date()}.csv"
            media_type = "text/csv"
        elif export_format == "pdf":
            content = self._build_pdf(lot_id, trends, kpis, heatmap, start_date, end_date)
            filename = f"parkpilot-{lot_id}-{start_date.date()}-{end_date.date()}.pdf"
            media_type = "application/pdf"
        else:
            raise ValueError(f"Unsupported export format: {export_format}")

        return content, filename, media_type

    def _build_csv(self, lot_id, trends, kpis, heatmap) -> bytes:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["ParkPilot Analytics Export"])
        writer.writerow(["Lot ID", lot_id])
        writer.writerow([])
        writer.writerow(["KPI", "Value"])
        writer.writerow(["Utilization %", kpis["utilization_percentage"]])
        writer.writerow(["Peak Occupancy", kpis["peak_occupancy"]])
        writer.writerow(["Vehicle Count", kpis["vehicle_count"]])
        writer.writerow(["Avg Dwell Time (min)", kpis["avg_dwell_time_minutes"]])
        writer.writerow([])
        writer.writerow(["Hour", "Average Occupancy"])
        for point in trends.trends:
            writer.writerow([point.time_label, point.average_occupancy])
        writer.writerow([])
        writer.writerow(["Spot ID", "Occupancy %", "Total Events"])
        for spot in heatmap.spots:
            writer.writerow([spot.spot_id, spot.occupancy_percentage, spot.total_events])
        return buffer.getvalue().encode("utf-8")

    def _build_pdf(self, lot_id, trends, kpis, heatmap, start_date, end_date) -> bytes:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        styles = getSampleStyleSheet()
        elements = [
            Paragraph("ParkPilot Analytics Report", styles["Title"]),
            Paragraph(f"Lot: {lot_id}", styles["Normal"]),
            Paragraph(
                f"Range: {start_date.date()} to {end_date.date()}",
                styles["Normal"],
            ),
            Spacer(1, 12),
        ]

        kpi_data = [
            ["KPI", "Value"],
            ["Utilization %", str(kpis["utilization_percentage"])],
            ["Peak Occupancy", str(kpis["peak_occupancy"])],
            ["Vehicle Count", str(kpis["vehicle_count"])],
            ["Avg Dwell Time (min)", str(kpis["avg_dwell_time_minutes"])],
        ]
        kpi_table = Table(kpi_data)
        kpi_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a8a")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ]
            )
        )
        elements.extend([kpi_table, Spacer(1, 16)])

        trend_data = [["Hour", "Average Occupancy"]]
        for point in trends.trends:
            trend_data.append([point.time_label, str(point.average_occupancy)])
        trend_table = Table(trend_data)
        trend_table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey)]))
        elements.extend([Paragraph("Occupancy Trends", styles["Heading2"]), trend_table])

        doc.build(elements)
        return buffer.getvalue()
