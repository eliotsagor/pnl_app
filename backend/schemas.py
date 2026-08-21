"""Pydantic request/response models for the API."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class SaveDayRequest(BaseModel):
    sheet_values: dict[str, float]


class AddToStrategyRequest(BaseModel):
    sheet_name: str
    amount: float


class AddMappingRequest(BaseModel):
    label: str
    sheet_name: str


class BackfillRequest(BaseModel):
    start: date
    end: date | None = None


class FetchDayRequest(BaseModel):
    trade_date: date


class SaveSnapshotRequest(BaseModel):
    job_id: str
    label: str = ""


class CompleteSchwabLoginRequest(BaseModel):
    received_url: str
    state: str
