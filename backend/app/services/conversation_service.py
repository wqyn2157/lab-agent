from fastapi import HTTPException
from sqlalchemy.orm import Session
from datetime import datetime

from app.common.response import PageResponse
from app.models.conversation import Conversation
from app.models.user import User
from app.models.chat_message import ChatMessage
from app.common.exceptions import BusinessException


def get_conversation_page_list(
    db: Session,
    current_user: User,
    page: int,
    page_size: int,
):
    query = db.query(Conversation).filter(Conversation.user_id == current_user.id)

    total = query.count()

    items = (
        query.order_by(
            Conversation.update_time.desc(),
            Conversation.id.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return PageResponse(
        total=total,
        list=[
            {
                "id": item.id,
                "title": item.title,
                "create_time": item.create_time,
                "update_time": item.update_time,
            }
            for item in items
        ],
    )


def get_owned_conversation(
    db: Session,
    current_user: User,
    conversation_id: int,
) -> Conversation:
    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
        .first()
    )

    if conversation is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    return conversation


def get_message_page_list(
    db: Session,
    current_user: User,
    conversation_id: int,
    page: int,
    page_size: int,
):
    get_owned_conversation(db, current_user, conversation_id)

    query = db.query(ChatMessage).filter(ChatMessage.conversation_id == conversation_id)

    total = query.count()

    items = (
        query.order_by(ChatMessage.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return PageResponse(
        total=total,
        list=[
            {
                "id": item.id,
                "role": item.role,
                "content": item.content,
                "create_time": item.create_time,
            }
            for item in reversed(items)
        ],
    )


def delete_conversation(
    db: Session,
    current_user: User,
    conversation_id: int,
):
    try:
        conversation = get_owned_conversation(db, current_user, conversation_id)

        db.query(ChatMessage).filter(
            ChatMessage.conversation_id == conversation.id
        ).delete(synchronize_session=False)

        db.delete(conversation)

        db.commit()
    except Exception:
        db.rollback()
        raise


def save_user_message(
    db: Session,
    current_user: User,
    conversation_id: int | None,
    message: str,
) -> int:
    text = message.strip()

    if not 1 <= len(text) <= 2000:
        raise HTTPException(
            status_code=422,
            detail="消息长度必须为1~2000个字符",
        )

    try:
        if conversation_id is None:
            conversation = Conversation(
                user_id=current_user.id,
                title=text[:30],
            )
            db.add(conversation)
            db.flush()
        else:
            conversation = get_owned_conversation(db, current_user, conversation_id)

        db.add(
            ChatMessage(
                conversation_id=conversation.id,
                role="user",
                content=text,
            )
        )

        conversation.update_time = datetime.now()

        saved_conversation_id = conversation.id
        db.commit()

        return saved_conversation_id
    except Exception:
        db.rollback()
        raise


def get_context_messages(
    db: Session,
    current_user: User,
    conversation_id: int,
) -> list[ChatMessage]:
    get_owned_conversation(db, current_user, conversation_id)

    items = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.conversation_id == conversation_id,
            ChatMessage.role.in_(["user", "assistant"]),
        )
        .order_by(ChatMessage.id.desc())
        .limit(20)
        .all()
    )
    return list(reversed(items))


def save_assistant_message(
    db: Session,
    current_user: User,
    conversation_id: int,
    content: str,
) -> int:
    text = content.strip()

    if not text:
        raise BusinessException(message="模型未返回有效回复，请重试")

    try:
        conversation = get_owned_conversation(db, current_user, conversation_id)

        message = ChatMessage(
            conversation_id=conversation.id,
            role="assistant",
            content=text,
        )
        db.add(message)

        conversation.update_time = datetime.now()

        db.flush()
        saved_message_id = message.id

        db.commit()
        return saved_message_id
    except Exception:
        db.rollback()
        raise
