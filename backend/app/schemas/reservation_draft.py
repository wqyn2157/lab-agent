from pydantic import BaseModel, ConfigDict, Field


class ConfirmReservationDraftRequest(BaseModel):
    confirmation_token: str = Field(
        min_length=1,
        max_length=128,
        description="生成待确认单时返回的原始确认凭证",
    )
    idempotency_key: str = Field(
        min_length=1,
        max_length=255,
        description="本次确认的幂等键，重试时保持不变",
    )
    model_config = ConfigDict(extra="forbid")


class CancelReservationDraftRequest(BaseModel):
    confirmation_token: str = Field(
        min_length=1,
        max_length=128,
        description="待确认单的原始确认凭证",
    )

    model_config = ConfigDict(extra="forbid")
