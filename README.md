# Enhance Amazon Transactions in LunchMoney

[LunchMoney](https://mikebian.co/lunchmoney) is a indie-developed personal finance application. I spend a lot on amazon, and always thought it would be neat to break open the massive black bucket of money that's funneled into Amazon to understand what categories of spending it represents.

The trick is, Amazon doesn't have an order export. There's a sneaky extension that allows you to export your orders to a CSV file. This tool ingests that CSV and categorizes your Amazon transactions in Lunch Money.

## Setup

1. `asdf install` and `npm install` to setup node & npm packages
2. Optional: `tsc .` to compile the typescript

## Usage

1. Use the [amazon order scraper](https://github.com/philipmulcahy/azad) to pull your amazon history.
   1. Do not use the "show items not orders"
2. Get a lunch money API key. Run `cp .env-example .env` and add your API key to `.env`, or input it directly via the command line.

```shell
Usage: amazon-lunchmoney [options]

Options:
  -v, --verbose                      output verbose logs
  -f, --file <path>                  amazon history file
  -k --lunch-money-key <key>         lunch money api key
  -m --mapping-file <path>           category mapping file
  -d, --dry-run                      dry run mode (default: false)
  -n, --owner-name <name>            the name of the owner of the account, used to determine if a order is a gift
  -c, --default-category <category>  default category
  -h, --help                         display help for command
```

Here's an example command:

```shell
node out/run.js -f '~/Downloads/amazon_order_history.csv' -c Shopping -n "Michael Bianco"
```

## Development

Development with bun is easier:

```shell
bun run.ts --help
```

## TODO

- [ ] Indicate which purchases are HSA/FSA eligible and maybe generate receipt?
- [ ] publish on npm
- [ ] Should match up refunds and categorize them appropriately
- [ ] add item name to notes