"""Wires settings, policy and integrations together. Workflows receive this instead of importing integrations."""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Business, Policy, Settings, load_business, load_policy
from app.services.ai_analysis_service import AIAnalysisService, DryRunLLM, GeminiClient
from app.services.email_service import EmailService, GmailBackend
from app.services.google_sheets_service import GoogleSheetsService
from app.services.voice_service import VoiceClient, build_voice_client


@dataclass
class Services:
    settings: Settings
    policy: Policy
    business: Business
    sessions: async_sessionmaker[AsyncSession]
    voice: VoiceClient
    analysis: AIAnalysisService
    email: EmailService
    sheets: GoogleSheetsService | None
    _locks: dict = field(default_factory=dict)  # per-call in-process locks (DB idempotency is the real guard)


def build_services(settings: Settings, sessions: async_sessionmaker[AsyncSession]) -> Services:
    policy = load_policy(settings)
    business = load_business(settings)
    llm = GeminiClient(settings) if settings.llm_api_key.get_secret_value() else DryRunLLM()
    backend = GmailBackend(settings) if settings.enable_email_sending else None
    sheets_ready = settings.google_application_credentials and settings.google_sheets_spreadsheet_id
    return Services(
        settings=settings, policy=policy, business=business, sessions=sessions,
        voice=build_voice_client(settings),
        analysis=AIAnalysisService(llm, settings, business),
        email=EmailService(settings, policy, business, backend),
        sheets=GoogleSheetsService(settings) if sheets_ready else None,
    )
