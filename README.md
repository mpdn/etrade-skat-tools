# etrade-skat-tools

Tooling for reporting sales of stock from a ETrade stock plan to the Danish tax authorities (Skat). This tool does the time and currency conversions necessary for entering stock plan sales into Værdipapirsystemet in Skat.

This software is provided without warranty of any kind. Use at your own risk.

## Requirements

You must to be able to run `python3`, `curl`, and `make`. These are installed by default on macOS and most Linux distributions.

## Usage

- Go to the [orders page](https://us.etrade.com/etx/sp/stockplan#/myAccount/orders) for your stock plan.
- Select the year you are interested in and click apply.
- For each order, copy the table under "Order History" and paste it into [sales-etrade.txt](sales-etrade.txt).
- Run `make` - this will automatically download exchange rates and apply the conversions.
- Open the output in [sales-skat.txt](sales-skat.txt) and enter the sales in the Værdipapirsystem.

If you run this again in the future, you may need new to update the currency exchange rates. To do so, simply delete `usd.csv`.