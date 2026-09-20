"""Counterfactual equity, make-whole sizing and the funding waterfall.

Policy: trades stand, people get made whole. Never reverse, always compensate,
decide by a rule published first. Four reasons, all citable: fills are on-chain
and non-custodial so reversal is literally unavailable; reversal creates a
second set of victims among legitimate counterparties (JELLY); Indian precedent
is hostile to annulment (SAT/Emkay, where the tribunal held that the annulment
clause "is not intended to give relief to a trader guilty of negligence"); and
CFTC/FIA best practice is that all trades stand, with price adjustment
preferred over cancellation.

Responsibilities
----------------
- Counterfactual equity: re-run each affected account against the Reference
  Composite Price instead of the disputed mark, and take the difference.
- Apply the remedy matrix by class, including the explicit exclusion for
  customers who experienced trading losses under normal circumstances (the OKX
  Jan 2019 notice is the template: name the exact windows, set a crediting
  deadline, exclude normal losses, do not roll back).
- The speed clause, which is the thing that actually keeps users: for clear-cut
  C/D/E signatures, push provisional credit within 60 minutes as locked trading
  credit, converted to withdrawable cash after a published reconciliation. Do
  not make a liquidated user file a ticket to get their own money back.
- The funding waterfall, drawn down in order:
      1. recovery from the at-fault party (attacker / vendor SLA / PSP)
      2. Incident Reserve - ring-fenced, publicly visible balance, funded by
         10% of builder-code fee revenue until it reaches 2x the worst modelled
         30-day loss
      3. corporate treasury, up to a published per-incident cap
      4. tech E&O insurance
      5. beyond the cap, pro-rata by a published formula plus a non-cash
         make-good, announced as pro-rata and never paid silently short
- Report the India tax overlay: VDA gains are taxed at a flat 30% with no loss
  set-off, plus 1% TDS, so a wiped-out Indian trader eats 100% of the loss with
  zero deductibility. The trust damage from an identical event is strictly
  worse here, and compensation credits themselves carry characterisation risk
  and may need grossing up.
"""
