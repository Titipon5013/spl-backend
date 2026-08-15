from sqlalchemy import Integer, String, Column, Enum, DateTime, func, ForeignKey, Float, Boolean, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, relationship, Mapped, mapped_column
from enums import RoleEnum, RequestStatus, ApprovalStatus, AuthProvider
from datetime import datetime

class Base(DeclarativeBase):
    pass


class Admin(Base):
    __tablename__ = "admins"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String, nullable=True)
    role = Column(Enum(RoleEnum, name="roleenum"), nullable=False, default=RoleEnum.operator)
    oauth_sub = Column(String, unique=True, index=True, nullable=True)
    auth_provider = Column(
        Enum(AuthProvider, name="authprovider"),
        nullable=False,
        default=AuthProvider.local,
    )
    approval_status = Column(
        Enum(ApprovalStatus, name="approvalstatus"),
        nullable=False,
        default=ApprovalStatus.approved,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    revoked_at = Column(DateTime, nullable=True)


class ParkingSnapshot(Base):
    __tablename__ = "parking_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    lot_id = Column(String, default="CAMT_01", nullable=False)
    timestamp = Column(DateTime(), nullable=False)
    available_spaces = Column(Integer, nullable=False)
    total_spaces = Column(Integer, default=30, nullable=False)
    occupied_spaces = Column(Integer, nullable=False)
    occupacy_rate = Column(Float, nullable=False)  # 👈 พิมพ์ตกตัว n ไป
    confidence= Column(Float, nullable=False)
    processing_time_seconds = Column(Float, nullable=False)


class ParkingSnapshot2(Base):
    __tablename__ = "parking_snapshots_camera2"

    id = Column(Integer, primary_key=True, index=True)
    lot_id = Column(String, default="CAMT_02", nullable=False)
    timestamp = Column(DateTime(), nullable=False)
    available_spaces = Column(Integer, nullable=False)
    total_spaces = Column(Integer, default=30, nullable=False)
    occupied_spaces = Column(Integer, nullable=False)
    occupacy_rate = Column(Float, nullable=False)
    confidence= Column(Float, nullable=False)
    processing_time_seconds = Column(Float, nullable=False)


# User table
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, nullable=False)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True)

    license_plates = relationship("LicensePlate", back_populates="user", cascade="all, delete-orphan")
    license_plate_requests = relationship("LicensePlateRequest", back_populates="user", cascade="all, delete-orphan")


# License Plates table
class LicensePlate(Base):
    __tablename__ = "license_plates"

    id = Column(Integer, primary_key=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    plate_number = Column(String, nullable=False, unique=True)
    plate_image_url = Column(String, nullable=False)

    user = relationship("User", back_populates="license_plates")


# License Plate Requests table
class LicensePlateRequest(Base):
    __tablename__ = "license_plate_requests"

    id = Column(Integer, primary_key=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    plate_number = Column(String, nullable=False)
    plate_image_url = Column(String, nullable=False)
    submitted_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    status = Column(Enum(RequestStatus, name="requeststatus"), default=RequestStatus.pending, nullable=False)

    user = relationship("User", back_populates="license_plate_requests")


class EntryRecord(Base):
    __tablename__ = "entry_records"

    id = Column(Integer, primary_key=True, index=True)
    plate_number = Column(String, nullable=False)
    plate_image_url = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)


class ParkingEventLog(Base):
    __tablename__ = "parking_event_logs"

    id = Column(Integer, primary_key=True, index=True)
    lot_id = Column(String(50), index=True)
    spot_id = Column(String(50), index=True)
    is_occupied = Column(Boolean, default=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

class DeviceHealth(Base):
    __tablename__ = "device_health"
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String(50), index=True, unique=True)  # เช่น "orange_pi_main"
    device_type = Column(String(20))                         # "board", "camera_1", "camera_2"
    status = Column(String(20))                              # "online", "offline"
    last_seen = Column(DateTime, default=datetime.utcnow)


class SystemAnomaly(Base):
    """ความผิดปกติของระบบที่ตรวจพบอัตโนมัติ (URS-13, URS-14)

    หนึ่งแถวคือความผิดปกติหนึ่งครั้ง ตัวตรวจจับจะไม่สร้างแถวใหม่
    ถ้าความผิดปกติเดิมยังไม่ถูกแก้ (resolved_at เป็น NULL)
    """
    __tablename__ = "system_anomalies"

    id = Column(Integer, primary_key=True, index=True)
    anomaly_type = Column(String(30), index=True, nullable=False)  # stuck_slot, pipeline_inactive, device_offline
    severity = Column(String(10), nullable=False)                  # warning, critical
    lot_id = Column(String(50), index=True, nullable=True)
    spot_id = Column(String(50), index=True, nullable=True)
    device_id = Column(String(50), index=True, nullable=True)
    details = Column(String(500), nullable=False)
    detected_at = Column(DateTime, default=datetime.utcnow, index=True, nullable=False)
    resolved_at = Column(DateTime, nullable=True)
    reviewed_by = Column(String(255), nullable=True)                # อีเมลของแอดมินที่ตรวจสอบ
    reviewed_at = Column(DateTime, nullable=True)


class AdminAlertSubscription(Base):
    """Feature 4: linked admin LINE identity + push preferences (UC-10 / UC-11).

    One row per LINE user. Linking happens via /link <secret> on the admin bot.
    muted=True stops push alerts but still allows conversational queries.
    """
    __tablename__ = "admin_alert_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    line_user_id = Column(String(64), unique=True, index=True, nullable=False)
    admin_id = Column(Integer, ForeignKey("admins.id"), nullable=True)
    # CSV of anomaly types; empty/default means all known types
    alert_types = Column(
        String(200),
        nullable=False,
        default="stuck_slot,pipeline_inactive,device_offline",
    )
    muted = Column(Boolean, nullable=False, default=False)
    linked_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class AdminAlertDelivery(Base):
    """Feature 4: dedupe log so each anomaly is pushed at most once per LINE user."""
    __tablename__ = "admin_alert_deliveries"
    __table_args__ = (
        UniqueConstraint("anomaly_id", "line_user_id", name="uq_admin_alert_delivery"),
    )

    id = Column(Integer, primary_key=True, index=True)
    anomaly_id = Column(Integer, ForeignKey("system_anomalies.id"), nullable=False, index=True)
    line_user_id = Column(String(64), nullable=False, index=True)
    sent_at = Column(DateTime, default=datetime.utcnow, nullable=False)