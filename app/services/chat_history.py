import logging

from app.models.ligtning import ChatLog

logger = logging.getLogger(__name__)


async def save_chat_turn(
    user_id: int,
    user_message: str,
    agent_response: str,
    tools_called: list[str],
) -> ChatLog | None:
    try:
        log = ChatLog(
            session_id=str(user_id),
            user_message=user_message,
            agent_response=agent_response,
            tools_called=tools_called,
        )
        await log.insert()
        return log
    except Exception:
        logger.exception("Failed to persist chat turn for user %s", user_id)
        return None
