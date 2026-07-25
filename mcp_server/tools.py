"""MCP tool definitions for the ParkPilot parking system (URS-08 to URS-15).

Each tool is a thin, strictly-typed wrapper over the existing service layer so
that the dashboard, the REST API and AI agents all read the same logic.
"""

from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Optional

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from db.session import Session
from services.analytics_service import AnalyticsService
from services.anomaly_service import MONITORED_LOTS, AnomalyService
from mcp_server.security import rate_limited

ANOMALY_TYPES = ("stuck_slot", "pipeline_inactive", "device_offline")


@contextmanager
def session_scope():
    """หนึ่ง session ต่อการเรียก tool หนึ่งครั้ง"""
    db = Session()
    try:
        yield db
    finally:
        db.close()


def _validate_lot(lot_id: str) -> str:
    if lot_id not in MONITORED_LOTS:
        raise ToolError(
            f"Unknown lot_id '{lot_id}'. Valid values: {', '.join(MONITORED_LOTS)}."
        )
    return lot_id


def _parse_date(value: Optional[str], field: str, default: datetime) -> datetime:
    if value is None:
        return default
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise ToolError(
            f"Invalid {field} '{value}'. Expected ISO 8601, "
            f"for example '2026-07-25' or '2026-07-25T14:30:00'."
        )


def _resolve_range(
    start_date: Optional[str], end_date: Optional[str], default_days: int = 7
) -> tuple[datetime, datetime]:
    now = datetime.utcnow()
    end = _parse_date(end_date, "end_date", now)
    start = _parse_date(start_date, "start_date", end - timedelta(days=default_days))

    if start > end:
        raise ToolError(
            f"start_date ({start.isoformat()}) must be earlier than "
            f"end_date ({end.isoformat()})."
        )
    return start, end


def register_tools(mcp: FastMCP) -> None:
    """ลงทะเบียน tool ทั้งหมดเข้ากับ FastMCP instance ที่ส่งเข้ามา"""

    @mcp.tool()
    @rate_limited
    def get_live_occupancy(lot_id: str = "CAMT_01") -> dict:
        """Get the current occupancy snapshot for a parking lot (URS-08).

        Use this to answer "how full is the lot right now" or "how many spaces
        are left". Returns total, occupied and available space counts, the
        occupancy rate as a percentage, and how old the reading is.

        Args:
            lot_id: Parking lot identifier. One of "CAMT_01" or "CAMT_02".
        """
        _validate_lot(lot_id)
        with session_scope() as db:
            snapshot = AnalyticsService(db).get_live_occupancy(lot_id)

        if snapshot is None:
            raise ToolError(
                f"No occupancy data has been recorded for lot {lot_id} yet. "
                f"The detection pipeline may not be running."
            )
        return snapshot

    @mcp.tool()
    @rate_limited
    def check_slot_status(spot_id: str, lot_id: str = "CAMT_01") -> dict:
        """Check the current state of one specific parking slot (URS-09).

        Use this for questions about an individual slot, such as
        "is slot A3 free?" or "how long has slot B7 been occupied?".

        Args:
            spot_id: Slot identifier as reported by the detection pipeline, e.g. "A3".
            lot_id: Parking lot identifier. One of "CAMT_01" or "CAMT_02".
        """
        _validate_lot(lot_id)
        with session_scope() as db:
            status = AnalyticsService(db).check_slot_status(lot_id, spot_id)

        if status is None:
            raise ToolError(
                f"Slot '{spot_id}' is not known in lot {lot_id}. "
                f"Use find_available_slots to list the slots this lot reports."
            )
        return status

    @mcp.tool()
    @rate_limited
    def find_available_slots(lot_id: str = "CAMT_01") -> dict:
        """List the parking slots that are free right now (URS-12).

        Use this when the administrator wants the specific slot IDs that are
        open, rather than just a count.

        Args:
            lot_id: Parking lot identifier. One of "CAMT_01" or "CAMT_02".
        """
        _validate_lot(lot_id)
        with session_scope() as db:
            result = AnalyticsService(db).find_available_slots(lot_id)

        if result["known_spots"] == 0:
            raise ToolError(
                f"No slot-level events have been recorded for lot {lot_id} yet. "
                f"The detection pipeline may not be running."
            )
        return result

    @mcp.tool()
    @rate_limited
    def analyze_occupancy_trends(
        lot_id: str = "CAMT_01",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> dict:
        """Analyse historical occupancy trends hour by hour (URS-10).

        Use this for questions about patterns over time, such as
        "when is the lot busiest?" or "how was occupancy last Tuesday?".
        Returns an hourly average occupancy series plus the peak hour.

        Args:
            lot_id: Parking lot identifier. One of "CAMT_01" or "CAMT_02".
            start_date: ISO 8601 start, e.g. "2026-07-18". Defaults to 7 days before end_date.
            end_date: ISO 8601 end, e.g. "2026-07-25". Defaults to now.
        """
        _validate_lot(lot_id)
        start, end = _resolve_range(start_date, end_date)

        with session_scope() as db:
            trends = AnalyticsService(db).get_occupancy_trends(lot_id, start, end)

        return trends.model_dump(mode="json")

    @mcp.tool()
    @rate_limited
    def get_dwell_time_stats(
        lot_id: str = "CAMT_01",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> dict:
        """Get vehicle dwell time and throughput statistics (URS-11).

        Use this for questions such as "how long do cars stay on average?",
        "how many vehicles came in this week?" or "what was peak occupancy?".

        Args:
            lot_id: Parking lot identifier. One of "CAMT_01" or "CAMT_02".
            start_date: ISO 8601 start, e.g. "2026-07-18". Defaults to 7 days before end_date.
            end_date: ISO 8601 end, e.g. "2026-07-25". Defaults to now.
        """
        _validate_lot(lot_id)
        start, end = _resolve_range(start_date, end_date)

        with session_scope() as db:
            kpis = AnalyticsService(db).get_kpis(lot_id, start, end)

        kpis["period_start"] = start.isoformat()
        kpis["period_end"] = end.isoformat()
        return kpis

    @mcp.tool()
    @rate_limited
    def get_system_anomalies(
        anomaly_type: Optional[str] = None,
        include_reviewed: bool = False,
        limit: int = 50,
    ) -> dict:
        """Retrieve flagged system anomalies (URS-13).

        Anomalies are detected automatically every few minutes and cover stuck
        slots, an inactive detection pipeline, and offline edge devices or
        cameras. By default this returns only unresolved, unreviewed anomalies.

        Args:
            anomaly_type: Optional filter. One of "stuck_slot", "pipeline_inactive", "device_offline".
            include_reviewed: Set true to also return anomalies an administrator already reviewed.
            limit: Maximum anomalies to return, 1 to 200. Defaults to 50.
        """
        if anomaly_type is not None and anomaly_type not in ANOMALY_TYPES:
            raise ToolError(
                f"Unknown anomaly_type '{anomaly_type}'. "
                f"Valid values: {', '.join(ANOMALY_TYPES)}."
            )

        with session_scope() as db:
            anomalies = AnomalyService(db).get_anomalies(
                anomaly_type=anomaly_type,
                include_reviewed=include_reviewed,
                limit=limit,
            )

        return {"count": len(anomalies), "anomalies": anomalies}

    @mcp.tool()
    @rate_limited
    def mark_anomaly_reviewed(anomaly_id: int, reviewed_by: str) -> dict:
        """Mark a flagged anomaly as officially reviewed by an administrator (URS-14).

        Use this after an administrator confirms they have seen and handled an
        anomaly. Reviewed anomalies stop appearing in the default
        get_system_anomalies listing.

        Args:
            anomaly_id: The anomaly_id returned by get_system_anomalies.
            reviewed_by: Email address of the administrator performing the review.
        """
        with session_scope() as db:
            anomaly = AnomalyService(db).mark_anomaly_reviewed(anomaly_id, reviewed_by)

        if anomaly is None:
            raise ToolError(
                f"No anomaly found with anomaly_id {anomaly_id}. "
                f"Use get_system_anomalies to list current anomaly IDs."
            )
        return anomaly

    @mcp.tool()
    @rate_limited
    def get_system_health(lot_id: str = "CAMT_01") -> dict:
        """Get the operational status of the edge board and cameras (URS-13 support).

        Use this to answer "is camera 2 online?" or "is the system healthy?".
        Returns an overall status of Healthy, Degraded or Critical, an uptime
        score, and the per-device status.

        Args:
            lot_id: Parking lot identifier. One of "CAMT_01" or "CAMT_02".
        """
        _validate_lot(lot_id)
        with session_scope() as db:
            health = AnalyticsService(db).get_system_health_status(lot_id)

        return health.model_dump(mode="json")
