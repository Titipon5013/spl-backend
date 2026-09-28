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
        kpis: Optional[dict] = None,
    ) -> tuple[bytes, str, str]:
        dataset = self._collect_lot_data(lot_id, start_date, end_date, kpis)
        return self._render(
            [dataset], start_date, end_date, export_format, f"parkpilot-{lot_id}"
        )

    def export_combined_analytics(
        self,
        lot_ids: list[str],
        start_date: datetime,
        end_date: datetime,
        export_format: str,
        kpis_by_lot: Optional[dict] = None,
    ) -> tuple[bytes, str, str]:
        """รวมหลายลานไว้ในไฟล์เดียว (หนึ่ง section ต่อลาน) สำหรับอีเมลรายงานรายสัปดาห์"""
        kpis_by_lot = kpis_by_lot or {}
        datasets = [
            self._collect_lot_data(
                lot_id, start_date, end_date, kpis_by_lot.get(lot_id)
            )
            for lot_id in lot_ids
        ]
        return self._render(
            datasets, start_date, end_date, export_format, "parkpilot-weekly"
        )

    def _collect_lot_data(
        self,
        lot_id: str,
        start_date: datetime,
        end_date: datetime,
        kpis: Optional[dict] = None,
    ) -> dict:
        trends = self.analytics.get_occupancy_trends(lot_id, start_date, end_date)
        # รับ kpis ที่คำนวณไว้แล้วจาก weekly summary ได้ เพื่อให้ CSV/PDF ตรงกับ record ที่เก็บ
        if kpis is None:
            kpis = self.analytics.get_kpis(lot_id, start_date, end_date)
        heatmap = self.analytics.get_heatmap_data(lot_id, start_date, end_date)
        return {"lot_id": lot_id, "trends": trends, "kpis": kpis, "heatmap": heatmap}

    def _render(
        self,
        datasets: list[dict],
        start_date: datetime,
        end_date: datetime,
        export_format: str,
        filename_prefix: str,
    ) -> tuple[bytes, str, str]:
        if export_format == "csv":
            content = self._build_csv(datasets)
            media_type = "text/csv"
        elif export_format == "pdf":
            content = self._build_pdf(datasets, start_date, end_date)
            media_type = "application/pdf"
        else:
            raise ValueError(f"Unsupported export format: {export_format}")

        filename = f"{filename_prefix}-{start_date.date()}-{end_date.date()}"
        suffix = "csv" if export_format == "csv" else "pdf"
        return content, f"{filename}.{suffix}", media_type

    def _build_csv(self, datasets: list[dict]) -> bytes:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["ParkPilot Analytics Export"])
        for data in datasets:
            kpis = data["kpis"]
            writer.writerow([])
            writer.writerow(["Lot ID", data["lot_id"]])
            writer.writerow(["KPI", "Value"])
            writer.writerow(["Utilization %", kpis["utilization_percentage"]])
            writer.writerow(["Peak Occupancy", kpis["peak_occupancy"]])
            writer.writerow(["Vehicle Count", kpis["vehicle_count"]])
            writer.writerow(["Avg Dwell Time (min)", kpis["avg_dwell_time_minutes"]])
            writer.writerow([])
            writer.writerow(["Hour", "Average Occupancy"])
            for point in data["trends"].trends:
                writer.writerow([point.time_label, point.average_occupancy])
            writer.writerow([])
            writer.writerow(["Spot ID", "Occupancy %", "Total Events"])
            for spot in data["heatmap"].spots:
                writer.writerow(
                    [spot.spot_id, spot.occupancy_percentage, spot.total_events]
                )
        return buffer.getvalue().encode("utf-8")

    def _build_pdf(
        self,
        datasets: list[dict],
        start_date: datetime,
        end_date: datetime,
    ) -> bytes:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        styles = getSampleStyleSheet()
        elements = [
            Paragraph("ParkPilot Analytics Report", styles["Title"]),
            Paragraph(
                f"Range: {start_date.date()} to {end_date.date()}",
                styles["Normal"],
            ),
            Spacer(1, 12),
        ]

        for data in datasets:
            elements.append(Paragraph(f"Lot: {data['lot_id']}", styles["Heading2"]))
            elements.append(self._kpi_table(data["kpis"]))
            elements.append(Spacer(1, 12))

            trend_rows = [["Hour", "Average Occupancy"]] + [
                [point.time_label, str(point.average_occupancy)]
                for point in data["trends"].trends
            ]
            elements.append(Paragraph("Occupancy Trends", styles["Heading3"]))
            elements.append(self._grid_table(trend_rows))
            elements.append(Spacer(1, 12))

            heatmap_rows = [["Spot ID", "Occupancy %", "Total Events"]] + [
                [spot.spot_id, str(spot.occupancy_percentage), str(spot.total_events)]
                for spot in data["heatmap"].spots
            ]
            elements.append(Paragraph("Heatmap (Occupancy by Spot)", styles["Heading3"]))
            elements.append(self._grid_table(heatmap_rows))
            elements.append(Spacer(1, 16))

        doc.build(elements)
        return buffer.getvalue()

    def _kpi_table(self, kpis: dict) -> Table:
        table = Table(
            [
                ["KPI", "Value"],
                ["Utilization %", str(kpis["utilization_percentage"])],
                ["Peak Occupancy", str(kpis["peak_occupancy"])],
                ["Vehicle Count", str(kpis["vehicle_count"])],
                ["Avg Dwell Time (min)", str(kpis["avg_dwell_time_minutes"])],
            ]
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a8a")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ]
            )
        )
        return table

    def _grid_table(self, rows: list[list[str]]) -> Table:
        table = Table(rows)
        table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey)]))
        return table
