# etrade-skat-tools

Tooling for reporting income from E*TRADE stock plans to the Danish tax authorities (Skat).

This software is provided without warranty of any kind. Use at your own risk.

## Requirements

Python 3.10 or newer is required to execute the scripts.

`income.py` needs `openpyxl` to load Excel sheets. The easiest way of installing this is via a virtual environment:

```shell
# Set up environment
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# Run a script
.venv/bin/python income.py
```

## Scripts

All currency conversion between USD and DKK uses the reference rate published by Danmarks Nationalbank. The `usd.csv` file is automatically fetched and refreshed as needed at most once a day. On days without a published rate, such as weekends and Danish holidays, the most recent earlier rate is used.

### `orders.py` - Convert executed orders to Skat's Værdipapirsystem

`orders.py` converts sell orders from the format reported by E*TRADE to what is expected by Skat's Værdipapirsystem, including converting time and currency.

Usage:
- Go to the [Orders page](https://us.etrade.com/etx/sp/stockplan#/myAccount/orders) for your stock plan.
- Select the year you are interested in and click apply.
- Create a file named `orders-etrade.txt` in this directory.
- For each benefit type, copy the table under "Order History" and paste it into this file.
- Run `python3 orders.py`.
- Open the output in `orders-skat.txt`. The format corresponds to the rows and columns in the Værdipapirsystem.

### `income.py` - Estimate taxable income

`income.py` estimates taxable income from RSU vests and ESPP discount gains, including an estimate of future income for the preliminary income assessment, i.e. the contribution from the stock plan on B-skat in the forskudsopgørelse.

The ESPP is modeled as follows (constants can be changed in [`income.py`](income.py)):
- A fraction of wage is invested into purchasing shares.
- The ESPP program is divided into offerings of 24 months (`OFFERING_MONTHS`).
- Shares are purchased every 6 months (`PURCHASE_CADENCE`).
- The purchase price is determined by:
  - First setting the price to the lower of the market price at the start of the offering (grant date) and at the purchase date.
  - Then applying a percentage discount.
- The taxable income is the bargain element: the difference between the purchase price and the market price on the purchase date.

For RSUs, the taxable income is simply the quantity times the market price on the vest date.

To project this into the future, we make a number of simplifying assumptions:
- That the stock price stays at its price on the day the document was downloaded. The script derives this from the first RSU grant with unvested shares, so there must be at least one.
- That the USD/DKK currency rate remains at the most recent published rate when the script is run.
- That every future purchase uses the same total dollar contribution and discount rate as the most recent ESPP purchase. This in turn assumes that the same fraction of the wage is invested in the ESPP program and that the wage remains constant.
- That purchases in the current offering keep its grant-date price for the lookback, and that later offerings start at the current stock price.

We project ESPPs for the next 48 months past the last ESPP purchase date, extended to the end of that calendar year (`PROJECT_HORIZON`). Future RSU vests are taken from the schedule.

Stock splits must be listed in `SPLITS` in [`income.py`](income.py). E*TRADE reports RSU quantities adjusted for splits, but ESPP quantities and prices as they were before the split. The script converts ESPP purchases made before a listed split to post-split shares. If a split is missing from `SPLITS`, projected ESPP income will be wrong.

Usage:
- Go to the [Benefits History page](https://us.etrade.com/etx/sp/stockplan#/myAccount/benefitHistory) for your stock plan.
- Press "Download" and then "Download Expanded".
- Put the resulting `BenefitHistory.xlsx` in this directory.
- Run `.venv/bin/python income.py`.
- Open the output in `income.txt`. It will contain estimated taxable income for historical and future vests and ESPP purchases, and yearly totals for past, in-progress, and future years. Estimated amounts are marked `est.`.
