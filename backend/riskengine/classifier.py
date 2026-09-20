"""Abnormal Price Event test and root-cause classification.

The APE test (publish this in the T&Cs, before the event, not after). A fill or
liquidation is an Abnormal Price Event only if all three hold:

 1. Deviation  - the execution price differs from the Reference Composite Price
                 in the same 1-second window by more than the Non-Reviewable
                 Range for that tier
 2. Reversion  - the deviation retraces >=50% within 60 seconds, i.e. it was a
                 wick and not a repricing
 3. Counterfactual survival - the account held sufficient margin to survive at
                 the Reference Composite Price

Non-Reviewable Ranges, per tier (proposed parameters, seeded into RiskPolicy):
    Tier 1  BTC, ETH, SPY, mega-cap US equities        3%   off-hours 5%
    Tier 2  SOL, gold, large-cap equities, indices     5%   off-hours 8%
    Tier 3  long-tail crypto, pre-IPO perps           10%   off-hours 15%

Root-cause classes, which decide who pays (research brief 5.2):
    A  genuine move, healthy oracle, adequate depth   -> no remedy, publish tape
    B  thin book / venue-local wick, mark tracked      -> fee rebate + dated fix
    C  oracle or index defect on our HIP-3 market      -> FULL make-whole
    D  our app/API outage blocked top-up or close      -> make-whole in window
    E  UPI/PSP delay on a funded deposit               -> make-whole
    F  venue defect or ADL                             -> no cash liability;
                                                          file evidence pack,
                                                          publish the response,
                                                          goodwill at a cap
    G  identifiable manipulation                       -> freeze, report to
                                                          FIU-IND and the venue,
                                                          Incident Reserve

The classifier must return the evidence that produced the verdict, not just the
letter, because the report has to show its working and the whole policy stands
on being replicable by the user.
"""
