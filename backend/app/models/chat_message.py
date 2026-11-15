from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = {"comment": "AI聊天消息"}

    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id"),
        nullable=False,
        index=True,
        comment="所属会话",
    )
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="消息角色：user/assistant",
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="消息正文",
    )
