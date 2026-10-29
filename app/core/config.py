"""Environment settings (secrets, endpoints, safety switches) and file-based business policy."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

import yaml
from pydantic import BaseModel, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./voice_agent.sqlite3"

    voice_api_base_url: str = "https://voice-agent.edesy.in"
    voice_api_key: SecretStr = SecretStr("")
    voice_agent_id: int | None = None
    voice_from_number: str = ""
    voice_provider: str = ""
    public_base_url: str = ""
    webhook_secret: SecretStr = SecretStr("")

    google_application_credentials: str = ""
    google_sheets_spreadsheet_id: str = ""
    google_sheets_worksheet_name: str = "Sheet1"
    gmail_sender: str = ""

    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = "gemini-2.5-flash"
    llm_api_base_url: str = "https://generativelanguage.googleapis.com"

    timezone: str = "Asia/Kolkata"
    api_keys: SecretStr = SecretStr("")
    log_level: str = "INFO"
    policy_file: str = "config/policy.yaml"
    system_prompt_file: str = "config/system_prompt.md"
    email_templates_file: str = "config/email_templates.yaml"
    sheet_columns_file: str = "config/sheet_columns.yaml"
    business_file: str = "config/business.yaml"

    scheduler_enabled: bool = False
    enable_real_calls: bool = False
    enable_email_sending: bool = False
    sheets_dry_run: bool = True

    http_timeout_seconds: float = 20.0

    @field_validator("voice_agent_id", mode="before")
    @classmethod
    def _blank_agent(cls, v):
        return None if v in ("", None) else v

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def admin_keys(self) -> list[str]:
        return [k.strip() for k in self.api_keys.get_secret_value().split(",") if k.strip()]

    def path(self, value: str) -> Path:
        p = Path(value)
        return p if p.is_absolute() else ROOT / p


class Requirement(BaseModel):
    key: str
    label: str = ""
    description: str = ""


class Business(BaseModel):
    company_name: str = "voxai"
    agent_name: str = "Veesha"
    company_phone: str = ""
    company_website: str = ""
    business_description: str = ""
    requirements: list[Requirement] = Field(default_factory=list)


class Window(BaseModel):
    start: str
    end: str


class RetryRule(BaseModel):
    enabled: bool = True
    delay_minutes: int = 1440
    window: Window | None = None


class Policy(BaseModel):
    class CallingHours(BaseModel):
        start: str = "09:00"
        end: str = "19:00"
        days: list[Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]] = ["mon", "tue", "wed", "thu", "fri", "sat"]

    class DailyRun(BaseModel):
        hour: int = 9
        minute: int = 50

    class Calls(BaseModel):
        max_attempts: int = 3
        min_gap_minutes: int = 120
        batch_limit: int = 50
        pause_between_calls_seconds: float = 5
        default_country: str = "IN"

    class Retry(BaseModel):
        not_received: RetryRule = RetryRule()
        not_responded: RetryRule = RetryRule()
        ended: RetryRule = RetryRule()

    class Callback(BaseModel):
        default_delay_minutes: int = 60
        min_lead_minutes: int = 10
        max_days_ahead: int = 14

    class Meeting(BaseModel):
        reminders_minutes_before: list[int] = [1440, 60]

    class PostCall(BaseModel):
        poll_attempts: int = 6
        poll_interval_seconds: float = 10
        reconcile_after_minutes: int = 10
        dialing_unknown_after_minutes: int = 10
        stale_task_minutes: int = 15

    class Notifications(BaseModel):
        enabled_kinds: list[str] = Field(default_factory=list)

    calling_hours: CallingHours = CallingHours()
    daily_run: DailyRun = DailyRun()
    calls: Calls = Calls()
    retry: Retry = Retry()
    callback: Callback = Callback()
    meeting: Meeting = Meeting()
    post_call: PostCall = PostCall()
    notifications: Notifications = Notifications()


@lru_cache
def get_settings() -> Settings:
    return Settings()


def load_policy(settings: Settings | None = None) -> Policy:
    s = settings or get_settings()
    p = s.path(s.policy_file)
    return Policy.model_validate(yaml.safe_load(p.read_text()) or {}) if p.exists() else Policy()


def load_yaml(settings: Settings, name: str) -> dict:
    p = settings.path(getattr(settings, name))
    return yaml.safe_load(p.read_text()) or {}


def load_business(settings: Settings | None = None) -> Business:
    s = settings or get_settings()
    p = s.path(s.business_file)
    return Business.model_validate(yaml.safe_load(p.read_text()) or {}) if p.exists() else Business()
