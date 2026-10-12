"""Loads DKK-per-USD exchange rates from usd.csv and exposes lookups by date.

usd.csv is downloaded from Nationalbanken when it is missing or wasn't fetched today.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime, date
from decimal import Decimal
from functools import cache
from pathlib import Path
from urllib.request import urlopen
import csv

_PATH = Path(__file__).with_name('usd.csv')

_URL = ('https://www.nationalbanken.dk/api/currencyrates'
        '?format=csv&lang=en&isoCodes=USD')

@dataclass
class _ExchangeRate:
    date: date
    dkk_per_usd: Decimal

@cache
def _rates() -> list[_ExchangeRate]:
    if not _PATH.exists() or date.fromtimestamp(_PATH.stat().st_mtime) < date.today():
        tmp = _PATH.with_suffix('.csv.tmp')
        with urlopen(_URL) as response:
            tmp.write_bytes(response.read())
        tmp.replace(_PATH)

    rates: list[_ExchangeRate] = []
    with open(_PATH, newline='') as csvfile:
        # Skip the two header lines.
        csvfile.readline()
        csvfile.readline()

        for row in csv.DictReader(csvfile, delimiter=';'):
            rate_date = datetime.strptime(row["Date"], "%d-%m-%Y").date()
            dkk_per_usd = Decimal(row["US dollars"]) / 100
            rates.append(_ExchangeRate(rate_date, dkk_per_usd))

    rates.sort(key=lambda r: r.date)
    return rates

def dkk_per_usd_for(d: date) -> Decimal:
    """Most recent published rate on or before d.

    Rates are only published on days the DK market is open, so a DK-only holiday
    gets the preceding rate, which still applies through the holiday.
    """

    rates = _rates()
    index = bisect_right(rates, d, key=lambda r: r.date)
    return rates[max(index - 1, 0)].dkk_per_usd
