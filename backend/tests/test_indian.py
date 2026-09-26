"""Indian number formatting: crore and lakh, digits grouped 2-2-3. Pure."""
from __future__ import annotations

from decimal import Decimal

from riskengine.indian import group, inr_text


def test_digits_group_two_two_three() -> None:
    assert group(15_000_000) == "1,50,00,000"
    assert group(105_000.5, 2) == "1,05,000.50"
    assert group(999) == "999"
    assert group(-1234567) == "-12,34,567"
    assert group(-0.001, 2) == "0.00"


def test_money_reads_in_crore_and_lakh() -> None:
    assert inr_text(15_000_000) == "₹1.50 Cr"
    assert inr_text(1_017_000) == "₹10.17 L"
    assert inr_text(63_947.4) == "₹63,947"
    assert inr_text(-250_000) == "-₹2.50 L"
    assert "15,000,000" not in inr_text(15_000_000)
    assert inr_text(Decimal("15000000.00")) == "₹1.50 Cr"  # model fields are Decimals
