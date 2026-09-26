"""Phase 10: the language guardrails and the templates, without a database.

Every rule is the research brief's, and every example below is a sentence a
tired founder might actually type at 3am.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone as dt_timezone

import pytest

from core import comms
from core.comms import BLOCK, WARN, Facts, lint

T0 = datetime(2026, 9, 26, 22, 0, tzinfo=dt_timezone.utc)

FRESH = Facts(
    code="INC-20260927-01", instrument="BTC-PERP", scenario="The macro cascade", classified=False,
    category="", affected=0, claims_open=False, total_claims=0.0, payable=0.0, shortfall=0.0,
    pro_rata=False, ratio=1.0, cap=1.5e7, names=("Asha Rao", "Dev Mehta"), declared_at=T0,
    drill_seconds=300, event_from_tick=None, event_to_tick=None,
    controls="reduce-only, a liquidation throttle and a 3x leverage cap", provisional_deadline=None,
    solvency_note="",
)
QUANTIFIED = replace(
    FRESH, classified=True, category="C", affected=319, claims_open=True, total_claims=1.563e7,
    payable=1.5e7, shortfall=0.063e7, pro_rata=True, ratio=0.96, event_from_tick=170, event_to_tick=420,
    drill_seconds=1900,
)

OK_TAIL = " Next update at 04:25 IST. Asha Rao"


def rules(text: str, facts: Facts = FRESH, **kw) -> dict[str, str]:
    params = {"channel": "STATUS_PAGE", "audience": "PUBLIC", "template": "", "solvency_verified": False, "has_next_update_at": False}
    params.update(kw)
    return {f.rule: f.severity for f in lint("Update", text, facts=facts, **params)}


def test_market_conditions_is_banned() -> None:
    assert rules("Liquidations happened due to market conditions." + OK_TAIL)["market-conditions"] == BLOCK


def test_funds_safe_needs_verified_solvency() -> None:
    assert rules("Your funds are safe." + OK_TAIL)["funds-safe"] == BLOCK
    assert "funds-safe" not in rules("Your funds are safe: we reconciled every balance at 04:10 IST." + OK_TAIL, solvency_verified=True)


def test_no_number_before_it_is_computed() -> None:
    assert rules("About ₹2 Cr is affected." + OK_TAIL)["number-before-computed"] == BLOCK
    assert rules("300 users are affected." + OK_TAIL)["number-before-computed"] == BLOCK
    clean = rules("319 users, ₹1.56 Cr claimed, paid pro-rata under our Abnormal Price Event policy." + OK_TAIL, QUANTIFIED)
    assert "number-before-computed" not in clean and "number-mismatch" not in clean
    assert rules("250 users are affected." + OK_TAIL, QUANTIFIED)["number-mismatch"] == WARN
    assert rules("₹9 Cr is affected, pro-rata." + OK_TAIL, QUANTIFIED)["number-mismatch"] == WARN


def test_never_blame_users_argue_or_point_at_others() -> None:
    assert rules("You should not have used 50x." + OK_TAIL)["blame-users"] == BLOCK
    assert rules("This is FUD." + OK_TAIL)["argue"] == BLOCK
    assert rules("This was Hyperliquid's fault." + OK_TAIL)["blame-others"] == BLOCK


def test_the_first_public_word_has_no_cause() -> None:
    assert rules("Prices fell because an oracle broke." + OK_TAIL, template="first-word")["cause-in-first-word"] == BLOCK
    assert "cause-in-first-word" not in rules("We have not confirmed a cause and we will not guess." + OK_TAIL, template="first-word")


def test_every_public_update_commits_to_a_next_time() -> None:
    assert rules("We are seeing abnormal moves. Asha Rao")["no-next-update"] == BLOCK
    assert "no-next-update" not in rules("We are seeing abnormal moves. Asha Rao", has_next_update_at=True)
    assert "no-next-update" not in rules("What happened, and the RCA date. Asha Rao", template="handover")


def test_a_binding_cap_is_announced_as_pro_rata() -> None:
    assert rules("Everyone is compensated in full." + OK_TAIL, QUANTIFIED)["full-when-pro-rata"] == BLOCK
    assert rules("Affected users will be made whole." + OK_TAIL, QUANTIFIED)["made-whole-pro-rata"] == WARN
    assert "made-whole-pro-rata" not in rules("Made whole, pro-rata above the cap." + OK_TAIL, QUANTIFIED)


def test_trades_stand() -> None:
    assert rules("We will roll back the liquidations." + OK_TAIL)["rollback-promise"] == BLOCK
    assert "rollback-promise" not in rules("Trades stand; nothing is rolled back." + OK_TAIL)


def test_channel_limits_and_private_audiences() -> None:
    assert rules("x" * 281 + OK_TAIL, channel="X")["x-length"] == BLOCK
    assert rules("Evidence pack." + OK_TAIL, audience="VENUE", channel="X")["private-channel"] == BLOCK
    assert rules("Hello {{name}}." + OK_TAIL)["merge-field"] == BLOCK
    assert "merge-field" not in rules("Hello {{name}}.", audience="AFFECTED", channel="EMAIL")


def test_own_it_at_t15_when_it_is_ours() -> None:
    assert rules("An update on prices." + OK_TAIL, QUANTIFIED, template="preliminary")["own-it"] == WARN
    assert "own-it" not in rules("It was our price feed that failed." + OK_TAIL, QUANTIFIED, template="preliminary")


@pytest.mark.parametrize("facts", [FRESH, QUANTIFIED, replace(QUANTIFIED, category="A", pro_rata=False, ratio=1.0)], ids=["fresh", "quantified-C", "class-A"])
def test_every_template_renders_clean_except_the_ship_date_a_human_must_commit(facts) -> None:
    for t in comms.TEMPLATES:
        for channel in t.channels:
            headline, body = t.render(facts, channel)
            blocks = [f for f in lint(headline, body, channel=channel, audience=t.audience, template=t.key, facts=facts,
                                      solvency_verified=False, has_next_update_at=False) if f.severity == BLOCK]
            expected = {"placeholder"} if t.key == "handover" else set()
            assert {f.rule for f in blocks} == expected, (t.key, channel, [f.message for f in blocks], body)
            if channel == "X":
                assert len(body) <= comms.X_LIMIT, (t.key, len(body))


def test_the_number_waits_for_the_number() -> None:
    headline, body = comms.TEMPLATE_BY_KEY["the-number"].render(FRESH, "STATUS_PAGE")
    assert "once it is computed" in body and "₹" not in body
    headline, body = comms.TEMPLATE_BY_KEY["the-number"].render(QUANTIFIED, "STATUS_PAGE")
    assert "319 users" in body and "pro-rata" in body and "Abnormal Price Event" in body


def test_next_update_follows_the_playbook_clock() -> None:
    assert comms.next_update_seconds(0) == 300
    assert comms.next_update_seconds(400) == 900
    assert comms.next_update_seconds(3600) == 5400
