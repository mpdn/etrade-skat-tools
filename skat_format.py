"""Number and date formatting shared by the Skat-facing outputs."""

from datetime import date
from decimal import Decimal

def dkk(amount: Decimal) -> str:
    """Format a DKK amount with the Danish decimal comma."""
    return format(amount, '.2f').replace('.', ',')

def skat_date(d: date) -> str:
    return d.strftime('%d-%m-%Y')
