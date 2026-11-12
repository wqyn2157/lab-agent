from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends

from app.common.response import Response
from app.database import get_db
from app.dependencies.auth import get_current_admin, get_current_user
from app.models.user import User
from app.schemas.reservation import AuditReservationRequest, ReservationCreateRequest
from app.services import reservation_service
from app.services import reservation_draft_service
from app.schemas.reservation_draft import ConfirmReservationDraftRequest
from app.schemas.reservation_draft import CancelReservationDraftRequest

router = APIRouter(prefix="/reservation", tags=["预约相关接口"])


@router.get("/list")
def get_reservation_page_list(
    page: int = 1,
    page_size: int = 10,
    status: int | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    user_id: int | None = None,
):
    res = reservation_service.get_reservation_page_list(
        db, current_user, page, page_size, status, user_id
    )
    return Response.success(data=res)


@router.post("")
def create_reservation(
    data: ReservationCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    reservation_service.create_reservation(db, current_user, data)
    return Response.success()


@router.put("/{reservation_id}/cancel")
def cancel_reservation(
    reservation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    reservation_service.cancel_reservation(db, current_user, reservation_id)
    return Response.success()


@router.put("/{reservation_id}/audit")
def audit_reservation(
    reservation_id: int,
    data: AuditReservationRequest,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    reservation_service.audit_reservation(db, reservation_id, data.status)
    return Response.success()


@router.post("/drafts")
def create_reservation_draft(
    data: ReservationCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    draft, confirmation_token = reservation_draft_service.create_reservation_draft(
        db, current_user, data
    )

    return Response.success(
        message="待确认单已生成，请确认预约信息",
        data={
            "draft_id": draft.id,
            "lab_id": draft.lab_id,
            "equipment_id": draft.equipment_id,
            "date": draft.date,
            "start_time": draft.start_time,
            "end_time": draft.end_time,
            "remark": draft.remark,
            "status": draft.status,
            "expires_at": draft.expires_at,
            "confirmation_token": confirmation_token,
        },
    )


@router.post("/drafts/{draft_id}/confirm")
def confirm_reservation_draft(
    draft_id: int,
    data: ConfirmReservationDraftRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    reservation_id = reservation_draft_service.confirm_reservation_draft(
        db, current_user, draft_id, data
    )

    return Response.success(
        message="预约已提交，等待管理员审核", data={"reservation_id": reservation_id}
    )


@router.post("/drafts/{draft_id}/cancel")
def cancel_reservation_draft(
    draft_id: int,
    data: CancelReservationDraftRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    status = reservation_draft_service.cancel_reservation_draft(
        db, current_user, draft_id, data
    )

    return Response.success(
        message="确认单取消" if status == "cancelled" else "确认单已过期",
        data={"draft_id": draft_id, "status": status},
    )
