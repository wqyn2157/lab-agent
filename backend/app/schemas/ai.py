from pydantic import BaseModel, ConfigDict, Field


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


class ConversationChatRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    conversation_id: int | None = Field(
        default=None,
        gt=0,
    )
    message: str = Field(
        min_length=1,
        max_length=2000,
    )
