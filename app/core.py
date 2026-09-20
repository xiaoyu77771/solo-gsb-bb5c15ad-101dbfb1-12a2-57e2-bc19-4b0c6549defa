"""Civil schedule expansion with explicit DST gap/fold handling.

Classification of a naive local wall-clock time uses a UTC round trip:

* attach the zone with ``fold=0`` and ``fold=1`` and convert both to UTC;
* convert both UTC instants back to local wall time;
* if both round trips reproduce the wall time and the UTC instants agree,
  the time is **normal**; if they disagree, the wall time occurs twice
  (**fold**); if neither round trip reproduces it, the wall time never
  occurred (**gap**).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from enum import Enum
from zoneinfo import ZoneInfo

MAX_RANGE_DAYS = 366


class GapStrategy(str, Enum):
    """How to handle a wall-clock time that does not exist (spring forward)."""

    skip = "skip"
    shift_forward = "shift_forward"


class FoldStrategy(str, Enum):
    """How to handle a wall-clock time that occurs twice (fall back)."""

    first = "first"
    second = "second"
    both = "both"


@dataclass(frozen=True)
class Instance:
    local: datetime  # wall clock actually scheduled (naive)
    offset: timedelta  # UTC offset in effect for that wall clock
    utc: datetime  # the instant, as aware UTC
    reason: str  # why this instance exists


def _classify(naive: datetime, tz: ZoneInfo) -> tuple[str, datetime, datetime]:
    """Classify ``naive`` wall time in ``tz`` via a UTC round trip.

    Returns ``(kind, utc_fold0, utc_fold1)`` where kind is one of
    ``"normal"``, ``"gap"`` or ``"fold"``.  For gaps, ``utc_fold0`` is the
    later instant (wall time read with the pre-gap offset); for folds,
    ``utc_fold0`` is the earlier of the two real occurrences.
    """
    utc_fold0 = naive.replace(tzinfo=tz, fold=0).astimezone(timezone.utc)
    utc_fold1 = naive.replace(tzinfo=tz, fold=1).astimezone(timezone.utc)
    ok_fold0 = utc_fold0.astimezone(tz).replace(tzinfo=None) == naive
    ok_fold1 = utc_fold1.astimezone(tz).replace(tzinfo=None) == naive
    if ok_fold0 and ok_fold1:
        if utc_fold0 == utc_fold1:
            return "normal", utc_fold0, utc_fold1
        return "fold", utc_fold0, utc_fold1
    if not ok_fold0 and not ok_fold1:
        return "gap", utc_fold0, utc_fold1
    # Degenerate case (exactly one fold maps back): treat the valid side as normal.
    valid = utc_fold0 if ok_fold0 else utc_fold1
    return "normal", valid, valid


def _instance(utc_dt: datetime, tz: ZoneInfo, reason: str) -> Instance:
    local_aware = utc_dt.astimezone(tz)
    return Instance(
        local=local_aware.replace(tzinfo=None),
        offset=local_aware.utcoffset() or timedelta(0),
        utc=utc_dt,
        reason=reason,
    )


def expand(
    tz: ZoneInfo,
    start: date,
    end: date,
    weekdays: set[int],
    moment: time,
    gap_strategy: GapStrategy,
    fold_strategy: FoldStrategy,
) -> list[Instance]:
    """Expand the schedule into concrete instances.

    The result is deduplicated by UTC instant and stably sorted by UTC.
    """
    instances: list[Instance] = []
    day = start
    one_day = timedelta(days=1)
    while day <= end:
        if day.weekday() in weekdays:
            naive = datetime.combine(day, moment)
            kind, utc_fold0, utc_fold1 = _classify(naive, tz)
            if kind == "normal":
                instances.append(_instance(utc_fold0, tz, "normal"))
            elif kind == "gap":
                if gap_strategy is GapStrategy.shift_forward:
                    # utc_fold0 reads the missing wall time with the pre-gap
                    # offset; as an instant it lands exactly one gap-delta
                    # later, i.e. the wall time shifted forward by the delta.
                    instances.append(_instance(utc_fold0, tz, "gap_shift_forward"))
                # GapStrategy.skip -> no instance for this day.
            else:  # fold
                if fold_strategy in (FoldStrategy.first, FoldStrategy.both):
                    instances.append(_instance(utc_fold0, tz, "fold_first"))
                if fold_strategy in (FoldStrategy.second, FoldStrategy.both):
                    instances.append(_instance(utc_fold1, tz, "fold_second"))
        day += one_day

    instances.sort(key=lambda inst: inst.utc)  # stable: ties keep date order
    seen: set[datetime] = set()
    unique: list[Instance] = []
    for inst in instances:
        if inst.utc not in seen:
            seen.add(inst.utc)
            unique.append(inst)
    return unique


def format_offset(offset: timedelta) -> str:
    """Format a UTC offset as ``+HH:MM`` / ``-HH:MM``."""
    total = int(offset.total_seconds())
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    return f"{sign}{total // 3600:02d}:{(total % 3600) // 60:02d}"
