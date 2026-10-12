#!/usr/bin/env python3

from __future__ import annotations

from datetime import datetime, date
from decimal import Decimal
from dataclasses import dataclass
from itertools import groupby
from pathlib import Path
from types import SimpleNamespace

import openpyxl

from skat_format import dkk, skat_date
import usd_rates

@dataclass
class ESPPPurchase:
    date: date
    symbol: str
    qty: int
    price: Decimal
    grant_date: date   # start of the offering period; shared by all its windows
    discount: Decimal  # plan discount as a fraction, e.g. 0.15

@dataclass
class Event:
    date: date
    kind: str       # 'Vest' or 'ESPP'
    label: str      # Grant number for vests, symbol for ESPP
    quantity: int
    sum_usd: Decimal
    estimated: bool

    @property
    def sum_dkk(self) -> Decimal:
        return self.sum_usd * usd_rates.dkk_per_usd_for(self.date)

def col_finder(ws):
    """Return a `col(name, after=0)` callable that resolves header names to indices.

    `after` disambiguates when a header name repeats (the RS sheet shares e.g.
    'Granted Qty.' across its Grant / Vest Schedule sections); pass the index of
    a unique anchor column to pick the occurrence in the section you want.
    """
    headers = next(ws.iter_rows(min_row=1, max_row=1, values_only=True))
    def col(name: str, after: int = 0) -> int:
        try:
            return headers.index(name, after)
        except ValueError:
            raise KeyError(f'Column {name!r} not found in headers after index {after}')
    return col

wb = openpyxl.load_workbook(Path(__file__).with_name('BenefitHistory.xlsx'), data_only=True)

# ---------------------------------------------------------------------------
# RSU vests from the 'Restricted Stock' sheet
# ---------------------------------------------------------------------------

ws_rsu = wb['Restricted Stock']

_rsu = col_finder(ws_rsu)
_vest_section = _rsu('Vest Period')
RSU = SimpleNamespace(
    record_type=_rsu('Record Type'),
    grant_number=_rsu('Grant Number'),
    market_value=_rsu('Est. Market Value'),
    unvested=_rsu('Unvested Qty.'),
    vest_period=_vest_section,
    vest_date=_rsu('Vest Date', after=_vest_section),
    vest_granted=_rsu('Granted Qty.', after=_vest_section),
    tax_description=_rsu('Tax Description'),
    taxable_gain=_rsu('Taxable Gain'),
)
rsu_rows = list(ws_rsu.iter_rows(min_row=2, values_only=True))

# Derive the current share price (USD) from any grant that still has unvested shares,
# so future vests/ESPP can be estimated at today's market value.
current_price_usd: Decimal | None = None
for row in rsu_rows:
    if row[RSU.record_type] == 'Grant' and row[RSU.unvested]:
        current_price_usd = Decimal(str(row[RSU.market_value])) / Decimal(row[RSU.unvested])
        break

if current_price_usd is None:
    raise ValueError('Could not derive current share price from Grant rows')

# Index the Denmark Tax Withholding entries by (grant, vest period) so each
# Vest Schedule row can look up its actual taxable gain in USD.
tax_by_period: dict[tuple[str, int], Decimal] = {}
for row in rsu_rows:
    if row[RSU.record_type] == 'Tax Withholding' and row[RSU.tax_description] == 'Denmark':
        tax_by_period[(row[RSU.grant_number], row[RSU.vest_period])] = Decimal(str(row[RSU.taxable_gain]))

events: list[Event] = []
for row in rsu_rows:
    if row[RSU.record_type] != 'Vest Schedule':
        continue

    grant = row[RSU.grant_number]
    vest_date = datetime.strptime(row[RSU.vest_date], '%m/%d/%Y').date()
    granted_qty = int(row[RSU.vest_granted])

    sum_usd = tax_by_period.get((grant, row[RSU.vest_period]))
    estimated = sum_usd is None
    if sum_usd is None:
        sum_usd = Decimal(granted_qty) * current_price_usd

    events.append(Event(vest_date, 'Vest', grant, granted_qty, sum_usd, estimated))

# ---------------------------------------------------------------------------
# ESPP purchases from the 'ESPP' sheet
#
# DK taxable income on an ESPP purchase is the bargain element:
#   (Purchase Date FMV - Purchase Price) * Quantity
# converted to DKK at the purchase-date rate.
# ---------------------------------------------------------------------------

ws_espp = wb['ESPP']
_espp = col_finder(ws_espp)
ESPP = SimpleNamespace(
    record_type=_espp('Record Type'),
    symbol=_espp('Symbol'),
    purchase_date=_espp('Purchase Date'),
    purchase_price=_espp('Purchase Price'),
    qty=_espp('Purchased Qty.'),
    fmv=_espp('Purchase Date FMV'),
    grant_date=_espp('Grant Date'),
    discount=_espp('Discount Percent'),
)

# Stock splits per symbol as (first split-adjusted trading day, ratio). The
# 'Restricted Stock' sheet is split-adjusted, but the 'ESPP' sheet keeps the
# pre-split quantities and prices, so those are converted to current shares to
# be comparable with the current share price.
SPLITS = {
    'CRWD': [(date(2026, 7, 2), 4)],
}

def split_factor(symbol: str, d: date) -> int:
    """Number of current shares that one share held on `d` has become."""
    factor = 1
    for split_date, ratio in SPLITS.get(symbol, []):
        if d < split_date:
            factor *= ratio
    return factor

# The most recent actual purchase, which the projection below extrapolates from.
last: ESPPPurchase | None = None
for row in ws_espp.iter_rows(min_row=2, values_only=True):
    if row[ESPP.record_type] != 'Purchase':
        continue
    purchase_date = datetime.strptime(row[ESPP.purchase_date], '%d-%b-%Y').date()
    split = split_factor(row[ESPP.symbol], purchase_date)
    p = ESPPPurchase(
        date=purchase_date,
        symbol=row[ESPP.symbol],
        qty=int(row[ESPP.qty]) * split,
        price=Decimal(str(row[ESPP.purchase_price])) / split,
        grant_date=datetime.strptime(row[ESPP.grant_date], '%d-%b-%Y').date(),
        # 'Discount Percent' arrives as a string like '15%'
        discount=Decimal(str(row[ESPP.discount]).rstrip('%')) / 100,
    )
    # 'Purchase Date FMV' arrives as a string like '$169.32'
    fmv = Decimal(str(row[ESPP.fmv]).lstrip('$')) / split
    bargain_usd = (fmv - p.price) * Decimal(p.qty)
    events.append(Event(p.date, 'ESPP', p.symbol, p.qty, bargain_usd, estimated=False))
    if last is None or p.date > last.date:
        last = p

# Project future ESPP purchases up to the horizon. Purchases recur every
# PURCHASE_CADENCE months after the last actual one. The plan has
# a lookback: Purchase Price = (1 - discount) * min(Grant Date FMV, Purchase
# Date FMV), so the grant-date price caps the price across every window of an
# offering, which runs OFFERING_MONTHS from its Grant Date. We assume the same
# dollar contribution (a fixed % of wage) and estimate the purchase-date FMV
# at the current share price. Two estimation rules:
#
#   * Windows still inside the last actual purchase's offering are capped by
#     that offering's grant-date price, recovered from the last actual
#     Purchase Price. If the share price has since fallen below the grant-date
#     FMV, the lookback resets the price to current * (1 - discount).
#   * Windows in later offerings have an unknown Grant Date FMV, assumed equal
#     to the current price, so price = current * (1 - discount) and the
#     bargain depends only on the contribution and discount, not the FMV level.
OFFERING_MONTHS = 24     # length of an ESPP offering period
PURCHASE_CADENCE = 6     # months between purchase windows
PROJECT_HORIZON = 48     # project purchases this many months past the last actual one

def add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    return date(d.year + m // 12, m % 12 + 1, d.day)

if last is not None:
    dollars = last.price * Decimal(last.qty)
    offering_ends = add_months(last.grant_date, OFFERING_MONTHS)
    # Round the horizon up to the end of its calendar year so we always
    # project full years rather than cutting off mid-year.
    horizon = add_months(last.date, PROJECT_HORIZON)
    horizon = date(horizon.year, 12, 31)

    window_date = add_months(last.date, PURCHASE_CADENCE)
    while window_date <= horizon:
        price = current_price_usd * (1 - last.discount)
        if window_date < offering_ends:
            # Same offering: the grant-date price still caps the Purchase Price.
            price = min(price, last.price)
        qty = int(dollars // price)

        bargain_usd = (current_price_usd - price) * Decimal(qty)
        events.append(Event(window_date, 'ESPP', last.symbol, qty, bargain_usd, estimated=True))
        window_date = add_months(window_date, PURCHASE_CADENCE)

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

events.sort(key=lambda e: (e.date, e.kind, e.label))

with open(Path(__file__).with_name('income.txt'), 'w') as out:
    for e in events:
        date_str = skat_date(e.date)
        sum_str = dkk(e.sum_dkk)
        marker = '  est.' if e.estimated else ''
        print(f'{e.kind:<4}  {date_str}  {e.label:<8}  {e.quantity:>4}  {sum_str:>14}{marker}', file=out)

    print(file=out)
    print('--- Yearly totals ---', file=out)
    # events is sorted by date, so each year's events are contiguous.
    for year, group in groupby(events, key=lambda e: e.date.year):
        year_events = list(group)
        total_qty = sum(e.quantity for e in year_events)
        total_dkk = sum((e.sum_dkk for e in year_events), Decimal(0))
        marker = '  (incl. estimates)' if any(e.estimated for e in year_events) else ''
        total_str = dkk(total_dkk)
        print(f'{year}  {total_qty:>4} shares  {total_str:>14} DKK{marker}', file=out)
