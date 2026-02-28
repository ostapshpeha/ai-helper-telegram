import re
import time
from collections import defaultdict

# ---------------------------------------------------------------------------
# Rate limiter — sliding window, in-memory
# ---------------------------------------------------------------------------
_timestamps: dict[int, list[float]] = defaultdict(list)

RATE_LIMIT = 5  # max messages
RATE_WINDOW = 60  # seconds


def is_rate_limited(user_id: int) -> bool:
    """Returns True if the user exceeded the rate limit and should be blocked."""
    now = time.monotonic()
    _timestamps[user_id] = [t for t in _timestamps[user_id] if now - t < RATE_WINDOW]
    if len(_timestamps[user_id]) >= RATE_LIMIT:
        return True
    _timestamps[user_id].append(now)
    return False


# ---------------------------------------------------------------------------
# Banned users — in-memory set
# ---------------------------------------------------------------------------
_banned: set[int] = set()


def is_banned(user_id: int) -> bool:
    return user_id in _banned


def ban_user(user_id: int) -> None:
    _banned.add(user_id)
    _warnings.pop(user_id, None)


def unban_user(user_id: int) -> bool:
    """Returns True if the user was actually in the ban list."""
    if user_id in _banned:
        _banned.discard(user_id)
        return True
    return False


# ---------------------------------------------------------------------------
# Content violation — keyword detection + warn-then-ban
# ---------------------------------------------------------------------------

_VIOLATION_RE = re.compile(
    r"\b(" r"сука" r"|хуй" r"|підар" r")\b",
    re.IGNORECASE,
)

_warnings: dict[int, int] = defaultdict(int)


def contains_violation(text: str) -> bool:
    return bool(_VIOLATION_RE.search(text))


def handle_violation(user_id: int) -> tuple[bool, str]:
    """
    Call when a message contains a violation.
    Returns (was_banned, reply_text).
    First offence → warning. Second → ban.
    """
    _warnings[user_id] += 1
    if _warnings[user_id] == 1:
        return False, (
            "⚠️ Будь ласка, дотримуйтесь коректного спілкування. "
            "Повторне порушення призведе до блокування."
        )
    ban_user(user_id)
    return True, "🚫 Вас заблоковано за порушення правил спілкування."
