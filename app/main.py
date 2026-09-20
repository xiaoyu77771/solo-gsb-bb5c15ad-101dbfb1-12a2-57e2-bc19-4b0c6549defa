"""FastAPI entrypoint for the civil schedule expansion service."""
from __future__ import annotations

from fastapi import FastAPI
from zoneinfo import ZoneInfo

from .core import expand, format_offset
from .schemas import ExpandRequest, ExpandResponse, InstanceOut

app = FastAPI(
    title="Civil Schedule Expansion API",
    summary="Expand a weekday-based local schedule into UTC instants with DST handling",
    version="1.0.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/expand", response_model=ExpandResponse)
def post_expand(req: ExpandRequest) -> ExpandResponse:
    tz = ZoneInfo(req.timezone)
    instances = expand(
        tz=tz,
        start=req.start_date,
        end=req.end_date,
        weekdays=req.weekdays,
        moment=req.local_time,
        gap_strategy=req.gap_strategy,
        fold_strategy=req.fold_strategy,
    )
    return ExpandResponse(
        timezone=req.timezone,
        count=len(instances),
        instances=[
            InstanceOut(
                local=inst.local.isoformat(),
                offset=format_offset(inst.offset),
                utc=inst.utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                reason=inst.reason,
            )
            for inst in instances
        ],
    )
