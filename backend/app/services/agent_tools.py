from datetime import datetime
import json
from sqlalchemy.orm import Session
from langchain_core.tools import tool
import traceback
from app.database import SessionLocal
from app.schemas.reservation import ReservationCreateRequest
from app.services import reservation_draft_service
from app.common.exceptions import BusinessException
from app.models.user import User
from app.services import equipment_service, kb_service, lab_service, reservation_service


def build_tools(db: Session, current_user: User):
    current_user_id = current_user.id

    @tool
    def search_lab_docs(query: str) -> str:
        """根据用户的提问检索知识库"""

        try:
            return kb_service.search(query) or "没有检索到相关的资料"
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)

    @tool
    def list_open_labs(keywords: str = "") -> str:
        """查询开放的实验室列表"""
        try:
            keywords = keywords.strip() or None

            with SessionLocal() as tool_db:
                page = lab_service.get_lab_page_list(
                    tool_db,
                    page=1,
                    page_size=10,
                    keywords=keywords,
                    status=1,
                )

                rows = [
                    {
                        "id": item.id,
                        "name": item.name,
                        "location": item.location,
                        "capacity": item.capacity,
                        "open_time": item.open_time,
                        "close_time": item.close_time,
                    }
                    for item in page.list
                ]

                return json.dumps(
                    {"total": page.total, "labs": rows},
                    ensure_ascii=False,
                )

        except Exception:
            traceback.print_exc()
            return json.dumps(
                {"ok": False, "error": "查询实验室失败，请稍候重试"},
                ensure_ascii=False,
            )

    @tool
    def list_lab_equipments(lab_id: int, keywords: str = "") -> str:
        """查询某个实验室的设备列表"""
        try:
            with SessionLocal() as tool_db:
                page = equipment_service.get_equipment_page_list(
                    tool_db,
                    page=1,
                    page_size=10,
                    lab_id=lab_id,
                    keywords=keywords.strip() or None,
                )

                rows = [
                    {
                        "id": item.id,
                        "name": item.name,
                        "lab_id": item.lab_id,
                        "lab_name": item.lab_name,
                        "spec": item.spec,
                        "quantity": item.quantity,
                        "status": item.status,
                    }
                    for item in page.list
                ]

                return json.dumps(
                    {"total": page.total, "equipments": rows},
                    ensure_ascii=False,
                )

        except Exception:
            traceback.print_exc()
            return json.dumps(
                {"ok": False, "error": "查询设备失败，请稍候重试"},
                ensure_ascii=False,
            )

    @tool
    def get_reservation_page_list(
        status: int | None = None,
        user_id: int | None = None,
        created_date: str | None = None,
    ) -> str:
        """查询预约记录。created_date 是提交日期，格式 YYYY-MM-DD，
        不是预约使用日期。结果最多返回第一页的 10 条记录。
        """
        try:
            with SessionLocal() as tool_db:
                tool_user = tool_db.get(User, current_user_id)

                if tool_user is None or tool_user.status != 1:
                    raise BusinessException(
                        message="当前账号不可用",
                        code=403,
                    )

                page = reservation_service.get_reservation_page_list(
                    tool_db,
                    tool_user,
                    page=1,
                    page_size=10,
                    status=status,
                    user_id=user_id,
                    created_date=created_date,
                )

                rows = [
                    {
                        "id": item.id,
                        "lab_name": item.lab_name,
                        "type": item.type,
                        "equipment_name": item.equipment_name,
                        "date": item.date,
                        "start_time": item.start_time,
                        "end_time": item.end_time,
                        "remark": item.remark,
                        "status": item.status,
                        "create_time": item.create_time.isoformat(),
                    }
                    for item in page.list
                ]

                return json.dumps(
                    {
                        "created_date": created_date,
                        "status_filter": status,
                        "total": page.total,
                        "returned_count": len(rows),
                        "has_more": page.total > len(rows),
                        "reservations": rows,
                    },
                    ensure_ascii=False,
                )

        except BusinessException as exc:
            return json.dumps(
                {"ok": False, "error": exc.message},
                ensure_ascii=False,
            )

        except Exception:
            traceback.print_exc()
            return json.dumps(
                {"ok": False, "error": "查询预约记录失败，请稍候重试"},
                ensure_ascii=False,
            )

    @tool(response_format="content_and_artifact")
    def prepare_lab_reservation(
        lab_id: int,
        date: str,
        start_time: str,
        end_time: str,
        equipment_id: int | None = None,
        remark: str | None = None,
    ) -> tuple[str, dict | None]:
        """生成实验室或设备的带确认单，不创建真实预约"""
        try:
            data = ReservationCreateRequest(
                lab_id=lab_id,
                equipment_id=equipment_id,
                date=date,
                start_time=start_time,
                end_time=end_time,
                remark=remark,
            )

            with SessionLocal() as tool_db:
                user = tool_db.get(User, current_user_id)

                if user is None or user.status != 1:
                    raise BusinessException(message="当前账号不可用", code=403)

                draft, confirmation_token = (
                    reservation_draft_service.create_reservation_draft(
                        tool_db, user, data
                    )
                )

                summary = {
                    "ok": True,
                    "message": "待确认单已生成，请在确认卡片中点击确认。",
                    "draft_id": draft.id,
                    "lab_id": draft.lab_id,
                    "lab_name": draft.lab.name,
                    "equipment_id": draft.equipment_id,
                    "equipment_name": (
                        draft.equipment.name if draft.equipment else None
                    ),
                    "date": draft.date,
                    "start_time": draft.start_time,
                    "end_time": draft.end_time,
                    "remark": draft.remark,
                    "status": draft.status,
                    "expires_at": draft.expires_at.isoformat(),
                }

                card_data = {
                    **summary,
                    "confirmation_token": confirmation_token,
                }

                return json.dumps(summary, ensure_ascii=False), card_data

        except BusinessException as exc:
            return (
                json.dumps(
                    {"ok": False, "error": exc.message},
                    ensure_ascii=False,
                ),
                None,
            )
        except Exception:
            traceback.print_exc()
            return (
                json.dumps(
                    {"ok": False, "error": "生成确认单失败，请稍候重试"},
                    ensure_ascii=False,
                ),
                None,
            )

    @tool
    def get_today() -> str:
        """获取服务器当前的日期"""
        now = datetime.now()
        return now.strftime("%Y-%m-%d")

    return [
        search_lab_docs,
        list_open_labs,
        list_lab_equipments,
        prepare_lab_reservation,
        get_today,
        get_reservation_page_list,
    ]
