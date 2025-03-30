#!/usr/bin/python3

from bisect import bisect_right
from collections import defaultdict
from datetime import datetime, date
from decimal import Decimal
from typing import Self
from zoneinfo import ZoneInfo
import csv
import locale
from dataclasses import dataclass

# Otherwise strptime fails to parse AM/PM
locale.setlocale(locale.LC_ALL, 'en_US')

@dataclass
class ExchangeRate:
    date: date
    dkk_per_usd: Decimal

# List of exchange rates sorted by date
usd: list[ExchangeRate] = []

with open('usd.csv', newline='') as csvfile:
    #Skip the two header lines
    csvfile.readline()
    csvfile.readline()

    for row in csv.DictReader(csvfile, delimiter=';'):
        closing_date = datetime.strptime(row["Date"], "%d-%m-%Y").date()
        dollars = Decimal(row["US dollars"]) / 100
        usd.append(ExchangeRate(closing_date, dollars))
    
    usd.sort(key=lambda rate: rate.date)

@dataclass
class Sale:
    quantity: int
    sum_dkk: Decimal

    def __add__(self, other: Self) -> Self:
        return Sale(self.quantity + other.quantity, self.sum_dkk + other.sum_dkk)

# Orders may have many transactions executed at the same time - so for reporting to Skat we
# coalesce any that happen at the same time.
sales: dict[datetime, Sale] = defaultdict(lambda: Sale(0, 0))

with open('sales-etrade.txt') as input:
    for line in input:
        [transaction, datetime_et, quantity_str, price_usd] = line.split('\t')
        
        if transaction in ['Order Placed', 'Transaction']:
            # Either header or order placement - not relevant
            continue

        if transaction != 'Order Executed':
            raise ValueError(f'Unexpected transaction type: {transaction}')
        
        datetime_dk = datetime \
            .strptime(datetime_et, '%m/%d/%Y %I:%M:%S %p ET') \
            .replace(tzinfo=ZoneInfo('America/New_York')) \
            .astimezone(ZoneInfo('Europe/Copenhagen'))
        
        date_dk = datetime_dk.date()
        
        # We need to find the exchange rate for the given date. This is complicated by the fact that
        # there is only set an exchange rate on days the DK market is open, so eg. a DK-only holiday
        # may not have an exchange rate set yet can still have a transaction.
        #
        # In this case, _I think_ the most recent exchange rate is the one that should be applied,
        # as that still holds for the holiday.
        #
        # To get this we use `bisect_right(usd, d, ..) - 1`. `bisect_right` will return the
        # lowest index `i` such that `usd[i].date > d`. `i - 1` will thus be the largest index `j`
        # where `usd[j].date <= d`.

        usd_index = bisect_right(usd, date_dk, key=lambda rate: rate.date)

        if usd_index == len(usd):
            raise ValueError(f'No exchange rate found for {date_dk} (usd.csv out of date?)')

        dkk_per_usd = usd[usd_index - 1].dkk_per_usd
        quantity = int(quantity_str)
        sum_dkk = quantity * Decimal(price_usd) * dkk_per_usd

        sales[datetime_dk] += Sale(quantity, sum_dkk)

with open('sales-skat.txt', 'w') as output:
    for (datetime_dk, sale) in sorted(sales.items()):
        date_str = datetime_dk.strftime('%d-%m-%Y')
        time = datetime_dk.strftime('%H:%M:%S')
        sum = format(sale.sum_dkk, '.2f').replace('.', ',')

        print(f'Salg  {date_str}  {time}  {-sale.quantity:>4}  {sum:>10}', file=output)
