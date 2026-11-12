"""Stage 2 schemas: every feed record and traveller question is validated before any logic touches it."""
from datetime import datetime, timedelta
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from . import config

Status = Literal["ON_TIME", "BOARDING", "DELAYED", "GATE_CLOSED", "DEPARTED", "CANCELLED", "LANDED", "EXPECTED"]


class FeedRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Literal["FIDS", "AIRLINE"]
    flight_no: str = Field(pattern=r"^[A-Z]{2}\d{2,4}$")
    status: Optional[Status] = None
    gate: Optional[str] = Field(default=None, pattern=r"^(A[1-6]|B([1-9]|1[0-2]))$")
    boarding_time: Optional[datetime] = None
    est_time: Optional[datetime] = None
    belt: Optional[int] = Field(default=None, ge=1, le=8)
    updated_at: datetime

    @field_validator("boarding_time", "est_time", "updated_at")
    @classmethod
    def must_have_timezone(cls, v):
        if v is not None and v.tzinfo is None:
            raise ValueError("timestamp must include a timezone")
        return v

    @model_validator(mode="after")
    def not_from_the_future(self):
        from .clock import now
        if self.updated_at > now() + timedelta(minutes=2):
            raise ValueError("updated_at is in the future (clock skew or bad feed)")
        return self

    def to_store(self) -> dict:
        d = self.model_dump(exclude_none=True)
        for k in ("boarding_time", "est_time", "updated_at"):
            if k in d:
                d[k] = d[k].isoformat()
        return d


class QuestionIn(BaseModel):
    text: str = Field(min_length=1, max_length=config.MAX_QUESTION_CHARS)
    session_id: str = Field(min_length=1, max_length=64)
