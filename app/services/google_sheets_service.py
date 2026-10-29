"""Google Sheets as customer source and reporting sink. Isolated here: nothing else imports googleapiclient for Sheets."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Protocol

from app.core.config import Settings, load_yaml
from app.core.phone import normalize_phone
from app.schemas.customer import SheetCustomer

log = logging.getLogger(__name__)

CLEAR = "__CLEAR__"           # explicit instruction to blank a cell
MAX_CELL = 49000              # Sheets limit is 50,000 characters per cell
_TRUTHY = {"yes", "y", "true", "1", "dnc", "do not call"}


def col_letter(idx: int) -> str:
    s = ""
    idx += 1
    while idx:
        idx, r = divmod(idx - 1, 26)
        s = chr(65 + r) + s
    return s


def merge_updates(existing: dict[str, str], new: dict[str, Any]) -> dict[str, str]:
    """Fields to write. Empty/None never overwrites an existing value; unchanged values are skipped."""
    out: dict[str, str] = {}
    for field, value in new.items():
        if value is None:
            continue
        text = str(value)
        if text == CLEAR:
            if existing.get(field, ""):
                out[field] = ""
            continue
        text = text.strip()
        if not text:
            continue
        text = text[:MAX_CELL]
        if text != existing.get(field, ""):
            out[field] = text
    return out


class SheetsAPI(Protocol):
    def read_all(self) -> list[list[str]]: ...
    def write_cells(self, cells: dict[str, str]) -> None: ...  # A1 range -> value


class GoogleSheetsAPI:
    def __init__(self, settings: Settings):
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        creds = service_account.Credentials.from_service_account_file(
            settings.google_application_credentials, scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        self._svc = build("sheets", "v4", credentials=creds, cache_discovery=False)
        self._id, self._tab = settings.google_sheets_spreadsheet_id, settings.google_sheets_worksheet_name

    def read_all(self) -> list[list[str]]:
        res = self._svc.spreadsheets().values().get(spreadsheetId=self._id, range=f"'{self._tab}'").execute()
        return res.get("values", [])

    def write_cells(self, cells: dict[str, str]) -> None:
        body = {"valueInputOption": "USER_ENTERED",
                "data": [{"range": f"'{self._tab}'!{a1}", "values": [[v]]} for a1, v in cells.items()]}
        self._svc.spreadsheets().values().batchUpdate(spreadsheetId=self._id, body=body).execute()


class GoogleSheetsService:
    def __init__(self, settings: Settings, api: SheetsAPI | None = None, columns: dict[str, str] | None = None):
        self._s = settings
        self._api = api
        cfg = load_yaml(settings, "sheet_columns_file")
        self.columns = columns or (cfg["columns"] | {f"req.{k}": h for k, h in cfg.get("requirement_columns", {}).items()})
        self._country = "IN"

    def _get_api(self) -> SheetsAPI:
        if self._api is None:
            self._api = GoogleSheetsAPI(self._s)
        return self._api

    # ---- reading -------------------------------------------------------------------------------------------
    def _parse(self, rows: list[list[str]]) -> tuple[dict[str, int], list[tuple[int, dict[str, str]]]]:
        if not rows:
            return {}, []
        header = {h.strip(): i for i, h in enumerate(rows[0])}
        out = []
        for n, row in enumerate(rows[1:], start=2):
            out.append((n, {f: (row[header[h]].strip() if h in header and header[h] < len(row) else "")
                            for f, h in self.columns.items()} | {"_raw": {h: row[i] for h, i in header.items() if i < len(row)}}))
        return header, out

    async def fetch_customers(self) -> list[SheetCustomer]:
        rows = await asyncio.to_thread(self._get_api().read_all)
        _, parsed = self._parse(rows)
        mapped = set(self.columns.values())
        result = []
        for n, r in parsed:
            phone = normalize_phone(r["phone"], self._country)
            if not phone:
                if r["phone"]:
                    log.warning("skipping row with invalid phone", extra={"row": n})
                continue
            try:
                count = int(float(r["call_count"] or 0))
            except ValueError:
                count = 0
            result.append(SheetCustomer(
                row_number=n, name=r["name"], phone=phone, email=r["email"],
                do_not_call=r["do_not_call"].lower() in _TRUTHY, call_count=count,
                call_status=r["call_status"], meeting_status=r["meeting_status"],
                extra={k: v for k, v in r["_raw"].items() if k not in mapped and v},
            ))
        return result

    # ---- writing -------------------------------------------------------------------------------------------
    async def update_customer(self, phone: str, values: dict[str, Any]) -> dict[str, str]:
        """Merge `values` (logical field -> value) into the customer's row. Returns what was (or would be) written."""
        rows = await asyncio.to_thread(self._get_api().read_all)
        header, parsed = self._parse(rows)
        row = next(((n, r) for n, r in parsed if normalize_phone(r["phone"], self._country) == phone), None)
        if row is None:
            log.warning("customer row not found in sheet", extra={"phone_tail": phone[-4:]})
            return {}
        n, existing = row
        changes = merge_updates(existing, values)
        cells = {f"{col_letter(header[self.columns[f]])}{n}": v
                 for f, v in changes.items() if self.columns.get(f) in header}
        if not cells:
            return {}
        if self._s.sheets_dry_run:
            log.info("DRY-RUN: sheet not written", extra={"row": n, "fields": sorted(changes)})
        else:
            await asyncio.to_thread(self._get_api().write_cells, cells)
        return changes
