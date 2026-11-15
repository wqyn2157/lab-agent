import json
import traceback
from fastapi import Query, Path
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from app.common.response import Response
from app.database import get_db, SessionLocal
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.ai import ConversationChatRequest
from app.services import agent_service, conversation_service
from sqlalchemy.orm import Session

router = APIRouter(prefix="/ai", tags=["AI相关的API"])


# @router.post("/chat")
# def chat(
#     data: ChatRequest,
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db),
# ):
#     content = agent_service.run_agent(db, current_user, data)
#     return Response.success(data=ChatMessage(role="assistant", content=content))


@router.post("/chat/stream")
async def chat(
    data: ConversationChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = current_user.id

    conversation_id = conversation_service.save_user_message(
        db,
        current_user,
        data.conversation_id,
        data.message,
    )

    try:
        history = agent_service._build_conversation_history(
            db, current_user, conversation_id
        )
    finally:
        db.rollback()

    async def event_gen():
        first_event = {
            "type": "conversation",
            "conversation_id": conversation_id,
        }
        yield f"data: {json.dumps(first_event, ensure_ascii=False)}\n\n"

        try:
            with SessionLocal() as stream_db:
                stream_user = stream_db.get(User, user_id)

                if stream_user is None or stream_user.status != 1:
                    error = {
                        "type": "error",
                        "message": "当前账号不可用",
                    }
                    yield f"data: {json.dumps(error, ensure_ascii=False)}\n\n"
                    return

                async for event in agent_service.stream_agent(
                    stream_db,
                    stream_user,
                    conversation_id,
                    history,
                ):
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception:
            traceback.print_exc()
            error = {
                "type": "error",
                "message": "聊天服务暂时不可用，请稍候重试",
            }
            yield f"data: {json.dumps(error, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/conversations")
def get_conversations(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = conversation_service.get_conversation_page_list(
        db, current_user, page, page_size
    )
    return Response.success(data=result)


@router.get("/conversations/{conversation_id}/messages")
def get_conversation_messages(
    conversation_id: int = Path(gt=0),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = conversation_service.get_message_page_list(
        db, current_user, conversation_id, page, page_size
    )
    return Response.success(data=result)


@router.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: int = Path(gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversation_service.delete_conversation(db, current_user, conversation_id)
    return Response.success(message="会话已删除")
