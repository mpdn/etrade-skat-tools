#!/usr/bin/env python3

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo
from dataclasses import dataclass

from skat_format import dkk, skat_date
import usd_rates

@dataclass
class Order:
    quantity: int
    sum_dkk: Decimal

    def __add__(self, other: Order) -> Order:
        return Order(
            quantity=self.quantity + other.quantity,
            sum_dkk=self.sum_dkk + other.sum_dkk
        )

# Orders may have many transactions executed at the same time - so for reporting
# to Skat we coalesce any that happen at the same time.
orders: dict[datetime, Order] = defaultdict(lambda: Order(0, Decimal(0)))

with open(Path(__file__).with_name('orders-etrade.txt')) as etrade_file:
    for line in etrade_file:
        if len(line.strip()) == 0:
            # Empty line, skip
            continue

        [transaction, datetime_et, quantity_str, price_per_share] = line.strip().split('\t')
        
        if transaction in ['Order Placed', 'Transaction']:
            # Either header or order placement - not relevant
            continue

        if transaction != 'Order Executed':
            raise ValueError(f'Unexpected transaction type: {transaction}')
        
        datetime_dk = datetime \
            .strptime(datetime_et, '%m/%d/%Y %I:%M:%S %p ET') \
            .replace(tzinfo=ZoneInfo('America/New_York')) \
            .astimezone(ZoneInfo('Europe/Copenhagen'))

        dkk_per_usd = usd_rates.dkk_per_usd_for(datetime_dk.date())
        quantity = int(quantity_str)
        sum_dkk = quantity * Decimal(price_per_share) * dkk_per_usd

        orders[datetime_dk] += Order(quantity, sum_dkk)

with open(Path(__file__).with_name('orders-skat.txt'), 'w') as skat_file:
    for (datetime_dk, order) in sorted(orders.items()):
        date_str = skat_date(datetime_dk)
        time = datetime_dk.strftime('%H:%M:%S')
        sum_dkk = dkk(order.sum_dkk)

        print(f'Salg  {date_str}  {time}  {-order.quantity:>4}  {sum_dkk:>10}', file=skat_file)
