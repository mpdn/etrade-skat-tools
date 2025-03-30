sales-skat.txt: ./convert-sales.py usd.csv sales-etrade.txt
	./convert-sales.py

usd.csv:
	curl --output usd.csv 'https://www.nationalbanken.dk/api/currencyrates?format=csv&lang=en&isoCodes=USD'