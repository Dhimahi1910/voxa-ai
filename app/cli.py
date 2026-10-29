"""Local helper commands:  python -m app.cli <command>"""
from __future__ import annotations

import argparse
import asyncio
import json

from app.container import build_services
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.phone import normalize_phone
from app.db import dispose_engine, init_engine
from app.models import Customer
from app.repositories import customer_repository as customers
from app.scheduler import JOBS


def render_prompt(sv) -> str:
    """Fill business values; leave {customer_name}/{current_date} for the provider to fill per call."""
    text = sv.settings.path(sv.settings.system_prompt_file).read_text()
    b = sv.business
    for k, v in {"agent_name": b.agent_name, "company_name": b.company_name, "business_description": b.business_description.strip()}.items():
        text = text.replace("{" + k + "}", v)
    return text


async def main() -> None:
    ap = argparse.ArgumentParser(prog="app.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    seed = sub.add_parser("seed", help="add/update one customer in the local database")
    seed.add_argument("--name", required=True); seed.add_argument("--phone", required=True); seed.add_argument("--email", default="")
    job = sub.add_parser("run", help="run a job once"); job.add_argument("job", choices=sorted(JOBS))
    pp = sub.add_parser("push-prompt", help="show (default) or push the system prompt to the voice agent")
    pp.add_argument("--confirm", action="store_true", help="actually update the agent (needs ENABLE_REAL_CALLS=true)")
    args = ap.parse_args()

    settings = get_settings()
    setup_logging(settings.log_level)
    sv = build_services(settings, init_engine(settings.database_url))
    try:
        if args.cmd == "seed":
            phone = normalize_phone(args.phone, sv.policy.calls.default_country)
            if not phone:
                raise SystemExit("invalid phone number")
            async with sv.sessions() as s:
                c = await customers.get_by_phone(s, phone) or Customer(phone=phone)
                c.name, c.email = args.name, args.email
                s.add(c)
                await s.commit()
                print(f"customer {c.id}: {c.name} {c.phone}")
        elif args.cmd == "run":
            print(json.dumps(await JOBS[args.job](sv), indent=2, default=str))
        elif args.cmd == "push-prompt":
            prompt = render_prompt(sv)
            if not args.confirm:
                print(prompt, "\n\n(preview only; pass --confirm to push)")
            else:
                await sv.voice.update_agent({"prompt": prompt, "promptChangeNote": "synced from config/system_prompt.md"})
                print("agent prompt updated" if settings.enable_real_calls else "DRY-RUN: nothing sent (ENABLE_REAL_CALLS=false)")
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
