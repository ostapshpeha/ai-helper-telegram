from datetime import datetime
from typing import List
from enum import IntEnum
from pydantic import Field
from beanie import Document


class FeedbackScore(IntEnum):
    POSITIVE = 1
    NEUTRAL = 0
    NEGATIVE = -1


class ChatLog(Document):
    session_id: str
    user_message: str
    agent_response: str
    tools_called: List[str] = []
    feedback: FeedbackScore = FeedbackScore.NEUTRAL
    created_at: datetime = Field(default_factory=lambda: datetime.utcnow())

    class Settings:
        name = "chat_logs"
