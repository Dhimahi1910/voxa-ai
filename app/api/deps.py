from __future__ import annotations

from fastapi import Request

from app.container import Services


def get_services(request: Request) -> Services:
    return request.app.state.services
