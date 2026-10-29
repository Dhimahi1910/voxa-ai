from __future__ import annotations

from enum import StrEnum


class CallOutcome(StrEnum):
    """What happened from the customer's side. Values match the spreadsheet vocabulary."""

    CONNECTED = "Connected"
    NOT_RECEIVED = "Not Received"
    NOT_RESPONDED = "Not Responded"
    RESCHEDULED = "Rescheduled"
    ENDED = "Ended"


class CallState(StrEnum):
    """Technical lifecycle of the call attempt, independent of the customer outcome."""

    PENDING = "pending"      # row reserved, provider not yet contacted (blocks duplicates)
    DIALING = "dialing"      # request sent; provider answer not yet recorded
    INITIATED = "initiated"  # provider accepted the call
    COMPLETED = "completed"  # provider details fetched and processed
    FAILED = "failed"        # provider rejected / technical error; no call was placed
    UNKNOWN = "unknown"      # crashed mid-dial: we cannot tell whether a call went out; never auto-redialled


class MeetingStatus(StrEnum):
    SCHEDULED = "Scheduled"
    NOT_SCHEDULED = "Not Scheduled"


class TaskKind(StrEnum):
    CALL = "call"
    REMINDER = "reminder"


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class NotificationStatus(StrEnum):
    SENDING = "sending"  # reserved; if we crash here we do NOT resend (cannot know if it left)
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"  # dry-run or disabled
