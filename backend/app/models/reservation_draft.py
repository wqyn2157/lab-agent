from datetime import datetime

from sqlalchemy import ForeignKey, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
from app.models.equipment import Equipment
from app.models.lab import Lab
from app.models.reservation import Reservation
from app.models.user import User


class ReservationDraft(Base):
    __tablename__ = "reservation_drafts"
    __table_args__ = {"comment": "预约待确认单"}

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), comment="预约人", nullable=False
    )
    lab_id: Mapped[int] = mapped_column(
        ForeignKey("labs.id"), comment="实验室", nullable=False
    )
    equipment_id: Mapped[int | None] = mapped_column(
        ForeignKey("equipments.id"), comment="设备，空表示预约实验室", nullable=True
    )
    date: Mapped[str] = mapped_column(String(20), comment="预约日期", nullable=False)
    start_time: Mapped[str] = mapped_column(
        String(20), comment="开始时间", nullable=False
    )
    end_time: Mapped[str] = mapped_column(
        String(20), comment="结束时间", nullable=False
    )
    remark: Mapped[str | None] = mapped_column(
        String(255), comment="备注", nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20),
        comment="确认状态：pending/confirmed/cancelled/expired",
        default="pending",
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(
        String(64), comment="确认凭证的SHA-256摘要", nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime, comment="到期时间", nullable=False
    )
    idempotency_key: Mapped[str | None] = mapped_column(
        String(255), comment="首次确认使用的幂等键", nullable=True
    )
    reservation_id: Mapped[int | None] = mapped_column(
        ForeignKey("reservation.id"), comment="确认后生成的预约记录", nullable=True
    )

    user: Mapped[User] = relationship()
    lab: Mapped[Lab] = relationship()
    equipment: Mapped[Equipment | None] = relationship()
    reservation: Mapped[Reservation | None] = relationship()
