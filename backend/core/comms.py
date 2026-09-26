"""Comms: templates per audience and channel, and the language guardrails.

What you say during an incident creates more liability than the incident.
Robinhood's $70M FINRA penalty was for misleading statements as much as for
the downtime. So every word that leaves the building is checked against rules
taken from the research brief, and each rule says where it came from:

    research 6, "What you explicitly do NOT do at 3am": argue on X, promise a
      number before you've computed it, say "your funds are safe" before you've
      verified solvency, say "market conditions".
    research 6, T+5 FIRST PUBLIC WORD: no cause, no blame, what we see, what we
      turned on, next update at HH:MM.
    research 6, T+15: if it is C/D/E, say so. T+30: "N users, ₹X aggregate,
      between HH:MM-HH:MM IST", citing the APE policy that already existed.
      T+60: what happened, who is affected, what we are paying, when it lands,
      the date of the full RCA.
    research 5 and 5.3: trades stand (no reversal), and above the cap the
      payout is announced as pro-rata, never paid silently short.
    research 9: a number and a deadline, not "we're investigating"; a named
      human; a shipped mechanism change with a date; never tell users it was
      their fault for using the leverage we sold them.

A BLOCK finding stops a draft from being approved or published. A WARN is
shown to the author and the approver and recorded with the update.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any, Callable

from django.utils import timezone

from riskengine.classifier import LABELS
from riskengine.indian import inr_text

BLOCK = "block"
WARN = "warn"

AUDIENCES = {
    "PUBLIC": "Everyone",
    "AFFECTED": "Affected users",
    "VENUE": "The venue (Hyperliquid)",
    "REGULATOR": "Regulators",
}

X_LIMIT = 280
"""X's limit on a post. A platform fact, not a policy."""

TELEGRAM_LIMIT = 4096
"""Telegram's limit on one message. A platform fact, not a policy."""

RCA_DAYS = 14
"""SEBI's technical-glitch framework, adopted voluntarily (research 7): RCA within 14 days."""

PRELIM_DAYS = 1
"""Same framework: preliminary report at T+1."""

PLAYBOOK_UPDATES_MIN = (5, 15, 30, 45, 60)
"""The playbook's public-update clock, research 6."""


@dataclass(frozen=True, slots=True)
class Finding:
    rule: str
    severity: str
    message: str
    source: str
    match: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Facts:
    """What the incident has actually established, so the guardrails can tell
    a computed number from a promised one."""

    code: str
    instrument: str
    scenario: str
    classified: bool
    category: str
    affected: int
    claims_open: bool
    total_claims: float
    payable: float
    shortfall: float
    pro_rata: bool
    ratio: float
    cap: float
    names: tuple[str, ...]
    declared_at: datetime
    drill_seconds: int
    event_from_tick: int | None
    event_to_tick: int | None
    controls: str
    provisional_deadline: datetime | None
    solvency_note: str
    mark_on_last_trade: bool = False
    """Class C came from our market marking positions to the last traded
    price, not from a bad oracle print: the classifier's LTP signal."""


def _ist(dt: datetime) -> str:
    return timezone.localtime(dt).strftime("%H:%M")


def _date(dt: datetime) -> str:
    return timezone.localtime(dt).strftime("%d %b %Y")


def _at(facts: Facts, seconds: int) -> datetime:
    return facts.declared_at + timedelta(seconds=seconds)


def next_update_seconds(drill_seconds: int, slot_minutes: int = 0) -> int:
    """The next public-update slot on the playbook clock after now; every 30
    minutes once the first hour is over.

    `slot_minutes` is the slot the update being written fills. An update sent
    ahead of its slot promises the one after it: the preliminary call sent at
    T+14 fills T+15, so its next update is the number at T+30, not T+15.
    """
    after = max(drill_seconds, slot_minutes * 60)
    for minute in PLAYBOOK_UPDATES_MIN:
        if minute * 60 > after:
            return minute * 60
    return after - after % 1800 + 1800


TEMPLATE_SLOT_MIN = {"first-word": 5, "preliminary": 15, "the-number": 30, "reopen": 45}
"""The playbook slot each public template fills, research 6."""


def next_update_for(template: str, drill_seconds: int) -> int:
    return next_update_seconds(drill_seconds, TEMPLATE_SLOT_MIN.get(template, 0))


# --------------------------------------------------------------------------
# Guardrails
# --------------------------------------------------------------------------

_I = re.IGNORECASE

AMOUNT = re.compile(r"(?:₹|\bRs\.?\s?|\bINR\s?)\s?[\d,.]+(?:\s?(?:L|lakh|Cr|crore)\b)?|\b\d[\d,.]*\s?(?:lakh|crore)\b", _I)
COUNT = re.compile(r"\b(\d[\d,]*)\s+(?:users|accounts|traders|people|customers)\b", _I)
TIME = re.compile(r"\b(?:[01]?\d|2[0-3])[:.][0-5]\d\b")
NEXT_UPDATE = re.compile(r"next update\b[^.]{0,20}?\b(?:[01]?\d|2[0-3])[:.][0-5]\d", _I)
DATE = re.compile(
    r"\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}\b|\b\d{4}-\d{2}-\d{2}\b", _I
)


def _amount_value(text: str) -> float | None:
    number = re.search(r"\d[\d,]*(?:\.\d+)?", text)
    if not number:
        return None
    value = float(number.group(0).replace(",", ""))
    low = text.lower()
    if "cr" in low:
        value *= 1e7
    elif re.search(r"\bl\b|lakh", low):
        value *= 1e5
    return value


RULES: list[tuple[str, str, re.Pattern[str], str, str]] = [
    ("market-conditions", BLOCK, re.compile(r"market\s+conditions", _I),
     'Banned phrase. "Market conditions" says nothing and reads as evasion: say what failed and what we turned on.',
     "Research 6: what you do NOT do at 3am"),
    ("argue", BLOCK, re.compile(r"\bFUD\b|fake news|misinformation|you(?:'re| are) wrong|false (?:claims|rumou?rs)|\blies\b|\bliars?\b|\btrolls?\b", _I),
     "Do not argue in public. State what we know and when the next update lands.",
     "Research 6: do not argue on X"),
    ("blame-users", BLOCK, re.compile(
        r"your (?:own )?fault|you should(?:n't| not)? have|you chose|over-?leverag|\breckless|\bgambl|irresponsib|user error|should not have used", _I),
     "Never tell users it was their fault for using the leverage we sold them.",
     "Research 9, point 6"),
    ("blame-others", BLOCK, re.compile(
        r"not our fault|(?:hyperliquid|the venue|the exchange|npci|the bank|our bank|the psp|upi)(?:'s)? fault|\bblame (?:on )?(?:hyperliquid|the venue|npci|the bank|upi)", _I),
     "No blame. Name what failed, not who to blame; the evidence pack does the rest.",
     "Research 6: no cause, no blame"),
    ("rollback-promise", BLOCK, re.compile(
        r"\b(?:will|we'll|to|going to|shall)\s+(?:be\s+)?(?:roll(?:ed)?\s+back|revers(?:e|ed)|cancel(?:led)?|undo(?:ne)?)\b|\broll(?:ing)?\s+back\s+(?:the\s+)?(?:trades|liquidations|fills)", _I),
     "Trades stand: fills are on-chain and non-custodial, so a reversal is not ours to promise. We compensate instead.",
     "Research 5"),
    ("placeholder", BLOCK, re.compile(r"\[[^\]]{1,40}\]"),
     "Fill the bracketed placeholder before this goes anywhere.",
     "House rule"),
]

WARN_RULES: list[tuple[str, re.Pattern[str], str, str]] = [
    ("vague-time", re.compile(r"\b(?:soon|shortly|asap|as soon as possible|in due course)\b", _I),
     "Give a time, HH:MM IST. 'Soon' is not a deadline.", "Research 9, point 1"),
    ("inconvenience", re.compile(r"sorry for (?:any|the) inconvenience", _I),
     "A generic apology. Say what happened to their money and what we are doing about it.", "Research 9"),
    ("guarantee", re.compile(r"\bguarantee", _I),
     "A guarantee needs a published cap behind it. Say what is promised and its limit.", "Research 5.3"),
]


def lint(
    headline: str,
    body: str,
    *,
    channel: str,
    audience: str,
    template: str,
    facts: Facts,
    solvency_verified: bool,
    has_next_update_at: bool,
) -> list[Finding]:
    text = f"{headline}\n{body}"
    out: list[Finding] = []

    for rule, severity, pattern, message, source in RULES:
        if rule == "placeholder":
            continue
        m = pattern.search(text)
        if m:
            out.append(Finding(rule, severity, message, source, m.group(0)))

    m = re.search(r"\[[^\]]{1,40}\]", text)
    if m:
        out.append(Finding("placeholder", BLOCK, "Fill the bracketed placeholder before this goes anywhere.", "House rule", m.group(0)))
    m = re.search(r"\{\{[^}]{1,40}\}\}", text)
    if m and audience != "AFFECTED":
        out.append(Finding("merge-field", BLOCK, "Merge fields are only filled per recipient on a message to affected users.", "House rule", m.group(0)))

    m = re.search(r"(?:your\s+)?(?:funds|money|assets|balances?|deposits)\s+(?:are|is|remain)\s+(?:safe|secure|safu)|\bSAFU\b", text, _I)
    if m and not solvency_verified:
        out.append(Finding("funds-safe", BLOCK,
                           'Not before solvency is verified. Tick the attestation once OPS has reconciled, and say what was checked.',
                           "Research 6: what you do NOT do at 3am", m.group(0)))

    amounts = [a.group(0) for a in AMOUNT.finditer(text)]
    counts = [int(c.group(1).replace(",", "")) for c in COUNT.finditer(text)]
    if amounts and not facts.claims_open:
        out.append(Finding("number-before-computed", BLOCK,
                           "A rupee figure before claims are computed is a promise we have not costed. Open claims first.",
                           "Research 6: never promise a number before you've computed it", amounts[0]))
    if counts and not facts.classified:
        out.append(Finding("number-before-computed", BLOCK,
                           "A count of affected users before the affected set is classified is a guess.",
                           "Research 6: never promise a number before you've computed it", f"{counts[0]}"))
    if counts and facts.classified and counts[0] != facts.affected:
        out.append(Finding("number-mismatch", WARN,
                           f"The classified affected set is {facts.affected}; this says {counts[0]}.",
                           "Research 6, T+30", f"{counts[0]}"))
    if amounts and facts.claims_open:
        known = [v for v in (facts.total_claims, facts.payable, facts.shortfall, facts.cap) if v > 0]
        for a in amounts:
            value = _amount_value(a)
            if value is not None and value >= 1000 and not any(abs(value - k) <= 0.02 * k for k in known):
                out.append(Finding("number-mismatch", WARN,
                                   f"{a} matches none of the computed figures: claimed {inr_text(facts.total_claims)}, "
                                   f"payable {inr_text(facts.payable)}.",
                                   "Research 6, T+30", a))
                break

    if facts.claims_open and facts.pro_rata:
        m = re.search(r"\bin full\b|fully (?:compensat|reimburs|refund|covered)|100\s?%|every rupee|all (?:of )?(?:your |their )?losses", text, _I)
        if m:
            out.append(Finding("full-when-pro-rata", BLOCK,
                               f"The cap binds: cash is paid at {facts.ratio:.1%} of every claim. Announce it as pro-rata; "
                               f"never paid silently short.", "Research 5.3", m.group(0)))
        elif re.search(r"made whole", text, _I) and not re.search(r"pro-?rata", text, _I):
            out.append(Finding("made-whole-pro-rata", WARN,
                               "With the cap binding, 'made whole' needs the word pro-rata next to it.",
                               "Research 5.3", "made whole"))

    public = audience == "PUBLIC"
    if public and template == "first-word":
        m = re.search(r"caused by|\bdue to\b|\bbecause\b|root cause (?:is|was)|the cause (?:is|was)|triggered by|\bresult of\b|\bblame", text, _I)
        if m:
            out.append(Finding("cause-in-first-word", BLOCK,
                               "The first public word carries no cause and no blame: what we see, what we turned on, next update.",
                               "Research 6, T+5", m.group(0)))
    if public and template != "handover" and not has_next_update_at and not NEXT_UPDATE.search(text):
        out.append(Finding("no-next-update", BLOCK,
                           "Commit to a next update time: 'Next update at HH:MM IST'.",
                           "Research 6, T+5", None))
    if public and template == "handover" and not DATE.search(text):
        out.append(Finding("rca-date", WARN, "Publish the date of the full RCA.", "Research 6, T+60", None))
    if public and facts.classified and facts.category in {"C", "D", "E"} and template in {"preliminary", "the-number", "handover"}:
        if not re.search(r"\b(?:our|we)\b[^.]{0,60}\b(?:fault|error|outage|oracle|price feed|failure|mistake|app|api|systems?|side)\b"
                         r"|\b(?:is|was) ours\b|\bon us\b", text, _I):
            out.append(Finding("own-it", WARN,
                               f"This is class {facts.category}: {LABELS[facts.category].lower()}. Say it is ours.",
                               "Research 6, T+15", None))
    if public and template == "the-number" and not re.search(r"abnormal price event|\bAPE\b", text, _I):
        out.append(Finding("cite-policy", WARN, "Cite the Abnormal Price Event policy that already existed.", "Research 6, T+30", None))
    if public and facts.names and not any(n and n.lower() in text.lower() for n in facts.names):
        out.append(Finding("named-human", WARN, "A named human owns this. Sign it.", "Research 9, point 4", None))
    if re.search(r"\binvestigating\b|\blooking into\b", text, _I) and not TIME.search(text) and not amounts:
        out.append(Finding("investigating-only", WARN,
                           "'We're investigating' is not an update: give a number or a deadline.", "Research 9, point 1", None))
    # "Technical glitch" is the SEBI framework's own term, so a notice to the regulator may use it.
    if facts.classified and audience != "REGULATOR" and re.search(r"\bglitch\b|technical (?:issue|difficult)", text, _I):
        out.append(Finding("vague-glitch", WARN,
                           "Say what failed: our price feed, our app and API, UPI settlement, or the venue.", "Research 6", None))
    for rule, pattern, message, source in WARN_RULES:
        m = pattern.search(text)
        if m:
            out.append(Finding(rule, WARN, message, source, m.group(0)))

    if channel == "X" and len(body) > X_LIMIT:
        out.append(Finding("x-length", BLOCK, f"X allows {X_LIMIT} characters; this body is {len(body)}.", "Platform limit", None))
    if channel == "TELEGRAM" and len(body) > TELEGRAM_LIMIT:
        out.append(Finding("telegram-length", BLOCK, f"Telegram allows {TELEGRAM_LIMIT} characters; this is {len(body)}.", "Platform limit", None))
    if audience in {"VENUE", "REGULATOR", "AFFECTED"} and channel not in {"EMAIL", "WHATSAPP"}:
        out.append(Finding("private-channel", BLOCK,
                           f"A message to {AUDIENCES[audience].lower()} goes by email or direct message, never a public channel.",
                           "House rule", None))
    return out


def blocking(findings: list[Finding]) -> list[Finding]:
    return [f for f in findings if f.severity == BLOCK]


# --------------------------------------------------------------------------
# Templates
# --------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Template:
    key: str
    audience: str
    channels: tuple[str, ...]
    title: str
    when: str
    render: Callable[[Facts, str], tuple[str, str]]


PUBLIC_CHANNELS = ("STATUS_PAGE", "X", "WHATSAPP", "TELEGRAM")


def _sign(f: Facts) -> str:
    return f" — {f.names[0]}" if f.names and f.names[0] else ""


def _next(f: Facts, template: str) -> str:
    return _ist(_at(f, next_update_for(template, f.drill_seconds)))


def _first_word(f: Facts, channel: str) -> tuple[str, str]:
    since = _ist(f.declared_at)
    if channel == "X":
        return (f"Abnormal price moves on {f.instrument}",
                f"We see abnormal price moves on {f.instrument} since {since} IST. Turned on: {f.controls}. "
                f"Next update at {_next(f, 'first-word')} IST.{_sign(f)}")
    return (f"Abnormal price moves on {f.instrument}",
            f"Since {since} IST we are seeing abnormal price moves on {f.instrument}. What we have turned on: {f.controls}. "
            f"We have not confirmed a cause and we will not guess. Next update at {_next(f, 'first-word')} IST.{_sign(f)}")


def _preliminary(f: Facts, channel: str) -> tuple[str, str]:
    ours = f.classified and f.category in {"C", "D", "E"}
    what = {
        "C": (
            "our market marked positions to the last traded price instead of our published reference price"
            if f.mark_on_last_trade else "our own price feed published a wrong price"
        ),
        "D": "our app and order API went down while prices moved",
        "E": "UPI deposits sent to us settled late, after positions were closed",
    }.get(f.category, "")
    if ours:
        body = (f"Preliminary finding: {what}. This one is ours, class {f.category} under our published Abnormal Price "
                f"Event policy. Trades stand; affected users are compensated under that policy, without filing a ticket. "
                f"Next update at {_next(f, 'preliminary')} IST, with the number.{_sign(f)}")
        if channel == "X":
            body = (f"Preliminary: {what}. That is on us (class {f.category}, our published APE policy). "
                    f"Compensation follows, no ticket needed. Next update {_next(f, 'preliminary')} IST.{_sign(f)}")
        return ("Preliminary finding: the fault is ours", body)
    if f.classified:
        return (f"Update on {f.instrument}",
                f"Preliminary finding: {LABELS[f.category].lower()}, not a fault on our side. We are publishing the "
                f"evidence tape so anyone can check it. What stays on: {f.controls}. Next update at {_next(f, 'preliminary')} IST.{_sign(f)}")
    return (f"Update on {f.instrument}",
            f"We are checking all three layers: the venue, our market and our own app and payments. What stays on: "
            f"{f.controls}. Next update at {_next(f, 'preliminary')} IST.{_sign(f)}")


def _window(f: Facts) -> str:
    if f.event_from_tick is None or f.event_to_tick is None:
        return ""
    return f" between {_ist(_at(f, f.event_from_tick))} and {_ist(_at(f, f.event_to_tick))} IST"


def _the_number(f: Facts, channel: str) -> tuple[str, str]:
    if not f.claims_open:
        return (f"Update on {f.instrument}",
                f"We are computing the affected set and each account's claim. We will publish the number once it is "
                f"computed, not an estimate. Next update at {_next(f, 'preliminary')} IST.{_sign(f)}")
    deadline = f" Provisional credit lands by {_ist(f.provisional_deadline)} IST, as locked trading credit." if f.provisional_deadline else ""
    cap = (f" Claims total {inr_text(f.total_claims)}, above our published per-incident cap of {inr_text(f.cap)}, so every "
           f"claim is paid {f.ratio:.1%} in cash and the rest as a non-cash make-good: pro-rata, announced as pro-rata."
           if f.pro_rata else "")
    ours = f.category in {"C", "D", "E"}
    if channel == "X":
        return (f"{f.affected} users affected",
                f"{f.affected} users, {inr_text(f.total_claims)} claimed{_window(f)}.{' That is on us.' if ours else ''} Paid under our published Abnormal "
                f"Price Event policy{', pro-rata above the cap' if f.pro_rata else ''}. Next update {_next(f, 'the-number')} IST.{_sign(f)}")
    return (f"{f.affected} users affected, {inr_text(f.total_claims)} claimed",
            f"{f.affected} users are affected, {inr_text(f.total_claims)} in aggregate{_window(f)}."
            f"{' This one is ours.' if ours else ''} Compensation follows our "
            f"Abnormal Price Event policy, published before this happened.{deadline}{cap} Next update at {_next(f, 'the-number')} IST.{_sign(f)}")


def _reopen(f: Facts, channel: str) -> tuple[str, str]:
    return (f"Reopening {f.instrument} in stages",
            f"We are reopening {f.instrument} in stages: reduce-only, then post-only, then full trading, each gate only "
            f"after prices have been healthy for five minutes. Trading resumes through a short auction, never straight into "
            f"continuous trading. Next update at {_next(f, 'reopen')} IST.{_sign(f)}")


def _handover(f: Facts, channel: str) -> tuple[str, str]:
    rca = _date(f.declared_at + timedelta(days=RCA_DAYS))
    what = LABELS.get(f.category, "Under investigation").lower() if f.classified else "still being classified"
    who = f"{f.affected} users" if f.classified else "being established from the tape"
    paying = (f"{inr_text(f.payable)} in cash to {f.affected} users" + (f", pro-rata at {f.ratio:.1%} above the cap" if f.pro_rata else "")
              if f.claims_open else "to be published with the claims")
    return ("What happened, and what we are paying",
            f"What happened: {what}. Who is affected: {who}. What we are paying: {paying}. When it lands: "
            f"provisional credit first, cash after a published reconciliation. The fix ships on [ship date]. The full root-cause "
            f"analysis is published by {rca}.{_sign(f)}")


def _affected_email(f: Facts, channel: str) -> tuple[str, str]:
    return ("Your account and this incident",
            "Hello {{name}},\n\nYour account {{account}} was force-closed at {{closed_at}} IST during incident "
            f"{f.code} on {f.instrument}. Under our published Abnormal Price Event policy it is class {{{{class}}}}: "
            "{{class_reason}}\n\nWhat we are paying you: {{cash}} in cash{{make_good}}. "
            "It lands as provisional, locked trading credit by {{deadline}} IST and becomes withdrawable after the reconciliation "
            "we publish. You do not need to file anything.\n\nYour own status page, with the evidence tape for your account: "
            "{{status_link}}\n\n" + (f"{f.names[0]}, MochaTrade" if f.names else "MochaTrade"))


def _venue_pack(f: Facts, channel: str) -> tuple[str, str]:
    return (f"Evidence pack: {f.code}, {f.instrument}",
            f"Hyperliquid team,\n\nWe are filing an evidence pack on behalf of our affected users for incident {f.code} on "
            f"{f.instrument}{_window(f)}. Attached: the per-source oracle tape, our mark series, every liquidation fill with "
            f"its stage, depth snapshots per second, and our classification ({f.category if f.classified else 'pending'}). "
            f"We ask for your review and your published response, which we will post alongside ours.\n\n"
            + (f"{f.names[0]}, MochaTrade" if f.names else "MochaTrade"))


def _sebi_notice(f: Facts, channel: str) -> tuple[str, str]:
    prelim = _date(f.declared_at + timedelta(days=PRELIM_DAYS))
    rca = _date(f.declared_at + timedelta(days=RCA_DAYS))
    return (f"Technical glitch notice: {f.code}",
            f"We report a technical glitch under the SEBI framework for broker technical glitches, which MochaTrade adopts "
            f"voluntarily. Incident {f.code} began at {_ist(f.declared_at)} IST on {_date(f.declared_at)}. Classification: "
            f"{LABELS.get(f.category, 'pending') if f.classified else 'pending'}. Users affected: {f.affected}. "
            f"This notice is within one hour of detection. A preliminary report follows by {prelim} and the root-cause "
            f"analysis by {rca}. Glitch data is retained for two years.\n\n"
            + (f"{f.names[0]}, MochaTrade" if f.names else "MochaTrade"))


def _fiu_report(f: Facts, channel: str) -> tuple[str, str]:
    return (f"Report of suspected market manipulation: {f.code}",
            f"MochaTrade reports suspected manipulation on {f.instrument}{_window(f)}: two or more venues printed prices "
            f"beyond our published Non-Reviewable Range on the same side at the same time, and our book followed. "
            f"{f.affected} of our users were force-closed inside the episode. We have frozen what we can, notified the venue, "
            f"and preserved the per-source tape, fills and account records for your review.\n\n"
            + (f"{f.names[0]}, MochaTrade" if f.names else "MochaTrade"))


TEMPLATES: list[Template] = [
    Template("first-word", "PUBLIC", PUBLIC_CHANNELS, "Update 1: first public word", "T+5", _first_word),
    Template("preliminary", "PUBLIC", PUBLIC_CHANNELS, "Update 2: preliminary call", "T+15", _preliminary),
    Template("the-number", "PUBLIC", PUBLIC_CHANNELS, "Update 3: the number", "T+30", _the_number),
    Template("reopen", "PUBLIC", PUBLIC_CHANNELS, "Staged reopening", "T+45", _reopen),
    Template("handover", "PUBLIC", ("STATUS_PAGE", "EMAIL"), "Handover: what happened and what we pay", "T+60", _handover),
    Template("your-account", "AFFECTED", ("EMAIL", "WHATSAPP"), "Your account (one per affected user)", "T+30-45", _affected_email),
    Template("venue-evidence-pack", "VENUE", ("EMAIL",), "Evidence pack to the venue", "Class F or G", _venue_pack),
    Template("sebi-glitch-notice", "REGULATOR", ("EMAIL",), "Technical glitch notice (SEBI framework, voluntary)", "Within 1 hour", _sebi_notice),
    Template("fiu-ind-report", "REGULATOR", ("EMAIL",), "Suspected manipulation report to FIU-IND", "Class G", _fiu_report),
]

TEMPLATE_BY_KEY = {t.key: t for t in TEMPLATES}
