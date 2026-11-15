from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = {"comment": "AI会话"}

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
        comment="所属用户",
    )
    title: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="会话标题",
    )
