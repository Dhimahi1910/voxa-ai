"""Outcome-driven customer emails: configurable templates, idempotent via the notifications table."""
from __future__ import annotations

import asyncio
import base64
import logging
import re
from email.message import EmailMessage
from string import Template
from typing import Protocol

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Business, Policy, Settings, load_yaml
from app.core.timeutil import utcnow
from app.models import Customer, Notification
from app.models.enums import NotificationStatus

log = logging.getLogger(__name__)
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class EmailBackend(Protocol):
    def send(self, to: str, subject: str, body: str) -> str: ...


class GmailBackend:
    """Gmail API via a service account with domain-wide delegation, sending as GMAIL_SENDER."""

    def __init__(self, settings: Settings):
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        creds = service_account.Credentials.from_service_account_file(
            settings.google_application_credentials, scopes=["https://www.googleapis.com/auth/gmail.send"]
        ).with_subject(settings.gmail_sender)
        self._svc = build("gmail", "v1", credentials=creds, cache_discovery=False)
        self._sender = settings.gmail_sender

    def send(self, to: str, subject: str, body: str) -> str:
        msg = EmailMessage()
        msg["To"], msg["From"], msg["Subject"] = to, self._sender, subject
        msg.set_content(body)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        return self._svc.users().messages().send(userId="me", body={"raw": raw}).execute().get("id", "")


class EmailService:
    def __init__(self, settings: Settings, policy: Policy, business: Business, backend: EmailBackend | None = None,
                 templates: dict | None = None):
        self._s, self._policy, self._biz, self._backend = settings, policy, business, backend
        self._tpl = templates or load_yaml(settings, "email_templates_file")

    def render(self, kind: str, customer: Customer, extra: dict[str, str] | None = None) -> tuple[str, str]:
        t = self._tpl["templates"][kind]
        b = self._biz
        ctx = {"name": customer.name or "there", "company_name": b.company_name, "agent_name": b.agent_name,
               "company_phone": b.company_phone, "company_website": b.company_website, "next_attempt": "", "callback_time": "", "meeting_time": "", "meeting_mode": ""} | (extra or {})
        body = Template(t["body"]).safe_substitute(ctx)
        body = re.sub(r"\n{3,}", "\n\n", body).strip() + "\n\n" + Template(self._tpl.get("signature", "")).safe_substitute(ctx).strip()
        return Template(t["subject"]).safe_substitute(ctx), body

    async def send(self, session: AsyncSession, customer: Customer, kind: str, dedupe_key: str,
                   extra: dict[str, str] | None = None, *, suppressed: bool = False) -> str:
        """Returns one of: sent, skipped, duplicate, disabled, no_email, failed. Safe to call repeatedly."""
        if kind not in self._policy.notifications.enabled_kinds:
            return "disabled"
        if suppressed:  # e.g. do-not-call customer
            return "skipped"
        if not _EMAIL.match(customer.email or ""):
            return "no_email"
        note = Notification(dedupe_key=dedupe_key, kind=kind, customer_id=customer.id, to_email=customer.email)
        session.add(note)
        try:
            await session.commit()  # reserve first; a unique violation means someone already handled this email
        except IntegrityError:
            await session.rollback()
            return "duplicate"
        if not self._s.enable_email_sending or self._backend is None:
            note.status = NotificationStatus.SKIPPED.value
            await session.commit()
            log.info("DRY-RUN: email not sent", extra={"kind": kind, "customer_id": customer.id})
            return "skipped"
        subject, body = self.render(kind, customer, extra)
        try:
            note.provider_message_id = await asyncio.to_thread(self._backend.send, customer.email, subject, body)
            note.status, note.sent_at = NotificationStatus.SENT.value, utcnow()
            result = "sent"
        except Exception as exc:  # noqa: BLE001 - any backend failure is recorded, never raised into the call flow
            note.status, note.error = NotificationStatus.FAILED.value, str(exc)[:500]
            log.error("email failed", extra={"kind": kind, "customer_id": customer.id, "error": str(exc)[:200]})
            result = "failed"
        await session.commit()
        return result
