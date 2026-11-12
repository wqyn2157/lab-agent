from datetime import timedelta, datetime
import hashlib
import secrets

from sqlalchemy.orm import Session
from app.schemas.reservation_draft import CancelReservationDraftRequest
from app.models.reservation_draft import ReservationDraft
from app.models.user import User
from app.schemas.reservation import ReservationCreateRequest
from app.services.reservation_service import validate_reservation, create_reservation
from app.common.exceptions import BusinessException
from app.schemas.reservation_draft import ConfirmReservationDraftRequest

DRAFT_TTL_MINUTES = 10


def create_reservation_draft(
    db: Session, current_user: User, data: ReservationCreateRequest
) -> tuple[ReservationDraft, str]:
    """生成确认单，不创建真正的预约"""
    validate_reservation(db, current_user, data)

    confirmation_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(confirmation_token.encode("utf-8")).hexdigest()

    draft = ReservationDraft(
        user_id=current_user.id,
        lab_id=data.lab_id,
        equipment_id=data.equipment_id,
        date=data.date,
        start_time=data.start_time,
        end_time=data.end_time,
        remark=data.remark,
        status="pending",
        token_hash=token_hash,
        expires_at=datetime.now() + timedelta(minutes=DRAFT_TTL_MINUTES),
    )

    try:
        db.add(draft)
        db.commit()
        db.refresh(draft)
    except Exception:
        db.rollback()
        raise

    return draft, confirmation_token


def confirm_reservation_draft(
    db: Session, current_user: User, draft_id: int, data: ConfirmReservationDraftRequest
) -> int:
    """确认待确认单，返回预约编号"""
    try:
        if current_user.role != "student":
            raise BusinessException(message="只有学生可以提交预约", code=403)
        draft = (
            db.query(ReservationDraft)
            .filter(
                ReservationDraft.id == draft_id,
                ReservationDraft.user_id == current_user.id,
            )
            .populate_existing()
            .with_for_update()
            .first()
        )

        if draft is None:
            raise BusinessException(message="带确认单不存在", code=404)

        token_hash = hashlib.sha256(data.confirmation_token.encode("utf-8")).hexdigest()

        if not secrets.compare_digest(token_hash, draft.token_hash):
            raise BusinessException(message="确认凭证无效", code=403)

        if draft.status == "confirmed":
            if draft.idempotency_key != data.idempotency_key:
                raise BusinessException(
                    message="该确认订单已使用其他幂等键确认",
                    code=409,
                )
            if draft.reservation_id is None:
                raise BusinessException(message="确认单缺少关联预约")

            reservation_id = draft.reservation_id

        else:
            if draft.status != "pending":
                raise BusinessException(message="确认订单当前无法确认", code=409)

            if draft.expires_at <= datetime.now():
                raise BusinessException(message="确认订单已过期，请重新生成", code=409)

            reservation_data = ReservationCreateRequest(
                lab_id=draft.lab_id,
                equipment_id=draft.equipment_id,
                date=draft.date,
                start_time=draft.start_time,
                end_time=draft.end_time,
                remark=draft.remark,
            )

            reservation = create_reservation(
                db, current_user, reservation_data, commit=False
            )

            reservation_id = reservation.id
            draft.status = "confirmed"
            draft.idempotency_key = data.idempotency_key
            draft.reservation_id = reservation_id

        db.commit()
        return reservation_id

    except Exception:
        db.rollback()
        raise


def cancel_reservation_draft(
    db: Session,
    current_user: User,
    draft_id: int,
    data: CancelReservationDraftRequest,
) -> str:
    """取消待确认单，返回取消后的状态。"""
    try:
        if current_user.role != "student":
            raise BusinessException(message="只有学生可以取消待确认单", code=403)

        draft = (
            db.query(ReservationDraft)
            .filter(
                ReservationDraft.id == draft_id,
                ReservationDraft.user_id == current_user.id,
            )
            .populate_existing()
            .with_for_update()
            .first()
        )

        if draft is None:
            raise BusinessException(message="待确认单不存在", code=404)

        token_hash = hashlib.sha256(data.confirmation_token.encode("utf-8")).hexdigest()

        if not secrets.compare_digest(token_hash, draft.token_hash):
            raise BusinessException(message="确认凭证无效", code=403)

        if draft.status == "confirmed":
            raise BusinessException(
                message="该确认单已生成预约，无法取消待确认单",
                code=409,
            )

        if draft.status not in ("pending", "cancelled", "expired"):
            raise BusinessException(message="当前状态无法取消", code=409)

        if draft.status == "pending":
            draft.status = (
                "expired" if draft.expires_at <= datetime.now() else "cancelled"
            )

        status = draft.status
        db.commit()
        return status

    except Exception:
        db.rollback()
        raise
