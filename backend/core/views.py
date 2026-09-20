"""Read-only comparison API. No database, no serializers, no ViewSets.

One job: run the identical seeded shock twice, controls off and controls on,
and return the difference. The engine is called directly and nothing is
persisted, so this endpoint cannot fail on a missing migration or an empty
table while a judge is watching.

Parameters come from riskengine's own defaults rather than the active
RiskPolicy row, deliberately: the page must render with an empty database.
"""
from __future__ import annotations

from django.http import Http404, JsonResponse

from riskengine.controls import ControlStack
from riskengine.engine import Engine, Frame
from riskengine.params import DEFAULT_PARAMS
from riskengine.scenario import by_key, library

MAX_POINTS = 300


def scenarios(_request) -> JsonResponse:
    return JsonResponse(
        {
            "scenarios": [
                {
                    "slug": s.key,
                    "name": s.title,
                    "summary": s.summary,
                    "layer": s.layer.value,
                    "instrument": s.instrument,
                    "ist_label": s.ist_label,
                    "expected_class": s.expected_class,
                }
                for s in library()
            ]
        }
    )


def _series(frames: list[Frame]) -> list[dict]:
    """Downsample to <=MAX_POINTS. Prices are sampled at the bucket head, but
    liquidations are SUMMED across the bucket -- sampling a spiky count would
    drop most of the cascade on the floor."""
    total = len(frames)
    if total == 0:
        return []
    step = max(1, -(-total // MAX_POINTS))
    out: list[dict] = []
    for start in range(0, total, step):
        bucket = frames[start : start + step]
        head = bucket[0]
        out.append(
            {
                "t": head.tick,
                "oracle": round(head.composite, 2) if head.composite else None,
                "mark": round(head.mark, 2),
                "ltp": round(head.book_mid, 2),
                "liquidations": sum(f.liquidated_this_tick for f in bucket),
            }
        )
    return out


def _run(scenario, controls: ControlStack) -> dict:
    result = Engine(scenario, DEFAULT_PARAMS, controls).run()
    s = result.summary
    return {
        "liquidated": s.accounts_liquidated,
        "unnecessary": s.unnecessary_liquidations,
        "adl": s.adl_accounts,
        "user_loss_inr": round(s.user_loss, 2),
        "accounts_total": s.accounts_total,
        "trough_pct": round(s.trough_mark_pct, 2),
        "series": _series(result.frames),
    }


def compare(_request, slug: str) -> JsonResponse:
    try:
        scenario = by_key(slug)
    except KeyError:
        raise Http404(f"unknown scenario {slug!r}")

    off = _run(scenario, ControlStack.none())
    on = _run(scenario, ControlStack.full())

    def drop(before: float, after: float) -> float:
        if not before:
            return 0.0
        return round((1.0 - after / before) * 100.0, 1)

    return JsonResponse(
        {
            "scenario": {
                "slug": scenario.key,
                "name": scenario.title,
                "summary": scenario.summary,
                "instrument": scenario.instrument,
                "ist_label": scenario.ist_label,
                "layer": scenario.layer.value,
                "liable_layer_note": scenario.liable_layer_note,
                "seed": scenario.seed,
            },
            "assumed_scale_note": scenario.assumed_scale_note,
            "off": off,
            "on": on,
            "delta": {
                "liquidated_pct": drop(off["liquidated"], on["liquidated"]),
                "loss_pct": drop(off["user_loss_inr"], on["user_loss_inr"]),
                "unnecessary_pct": drop(off["unnecessary"], on["unnecessary"]),
                "adl_pct": drop(off["adl"], on["adl"]),
            },
        }
    )
