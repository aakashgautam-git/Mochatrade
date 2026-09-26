"""Numbers the way an Indian reader reads them.

Money is in crore and lakh, never millions, and digits group 2-2-3 from the
right: 1,50,00,000, not 15,000,000. One module so the engine's log, the
classifier's working, the comms templates and the admin all print a number the
same way. Pure: no locale, which differs between machines.
"""
from __future__ import annotations

from decimal import Decimal

CRORE = 1_00_00_000.0
LAKH = 1_00_000.0


def group(value: float | Decimal, places: int = 0) -> str:
    """Indian digit grouping: group(15000000) == '1,50,00,000'."""
    value = float(value)
    text = f"{abs(value):.{places}f}"
    whole, _, frac = text.partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join([*groups, tail])
    sign = "-" if value < 0 and float(text) != 0 else ""
    return f"{sign}{whole}{'.' + frac if frac else ''}"


def inr_text(value: float | Decimal) -> str:
    """Money in a sentence a user reads: '₹1.50 Cr', '₹10.17 L', '₹63,947'."""
    value = float(value)
    v = abs(value)
    sign = "-" if value < 0 and v >= 0.5 else ""
    if v >= CRORE:
        return f"{sign}₹{v / CRORE:.2f} Cr"
    if v >= LAKH:
        return f"{sign}₹{v / LAKH:.2f} L"
    return f"{sign}₹{group(v)}"
