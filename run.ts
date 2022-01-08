// github:lunch-money/lunch-money-js

import { LunchMoney, Transaction as LunchMoneyTransaction } from "lunch-money";
import { readCSV, writeCSV } from "./util.js";
import dotenv from "dotenv";
import humanInterval from "human-interval";
import dateFns from "date-fns";
import fs from "fs";
import _, { find } from "underscore";
import repl from "repl";
import { Command } from "commander";
import { AmazonTransaction } from "./util";
import log from "loglevel";
import prefix from "loglevel-plugin-prefix";

dotenv.config();

// add expected log level prefixes
prefix.reg(log);
log.enableAll();
prefix.apply(log);

if (process.env.LOG_LEVEL) {
  log.setLevel(log.levels[process.env.LOG_LEVEL.toUpperCase()]);
} else {
  log.setLevel(log.levels.INFO);
}

const program = new Command();

program
  .option("-v, --verbose", "output verbose logs")
  .requiredOption("-f, --file <path>", "amazon history file")
  .option("-m", "--lunch-money-key <key>", "lunch money api key")
  .option("-d, --dry-run", "dry run mode", false)
  .option(
    "-n, --owner-name <name>",
    "the name of the owner of the account, used to determine if a order is a gift"
  )
  .requiredOption("-c, --default-category <category>", "default category");

program.parse(process.argv);

const options = program.opts();
if (options.debug) console.log(options);

const csvFile = options.file;
const lunchMoneyKey = options.lunchMoneyKey ?? process.env.LUNCH_MONEY_API_KEY;
const defaultCategoryName = options.defaultCategory;

if (!lunchMoneyKey) {
  log.error("Lunch Money API key not set");
  process.exit(1);
}

const lunchMoney = new LunchMoney({ token: lunchMoneyKey });
const lunchMoneyCategories = await lunchMoney.getCategories();

function categoryNameToId(categoryName: string) {
  return lunchMoneyCategories.find(
    (category) => !category.is_group && category.name === categoryName
  )?.id;
}

const defaultCategoryId = categoryNameToId(defaultCategoryName);

if (!defaultCategoryId) {
  console.error(`Default category ${defaultCategoryName} not found`);
  process.exit(1);
}

log.debug(`Category match found: ${defaultCategoryId}`);

// test if file exists on the file system before reading it
if (!fs.existsSync(csvFile)) {
  console.error(`File ${csvFile} does not exist`);
  process.exit(1);
}

const allAmazonTransactions = await readCSV(csvFile);
const amazonTransactions = allAmazonTransactions.filter(
  // filter out $0 transactions (paid by gift card)
  (transaction) => transaction.total !== "0" && transaction.categories
);

log.info(
  `Amazon transactions we can match: ${amazonTransactions.length} (out of ${allAmazonTransactions.length})`
);

// determine starting and ending date range from the dates in the file
let maxDate: Date | null = null;
let minDate: Date | null = null;

for (const transaction of amazonTransactions) {
  const date = new Date(transaction.date);
  if (!maxDate || date > maxDate) maxDate = date;
  if (!minDate || date < minDate) minDate = date;
}

if (!maxDate || !minDate) {
  console.error("No dates found in file");
  process.exit(1);
}

console.log(`Matching transactions from ${minDate} to ${maxDate}`);

// adjust the dates by a couple dates to make sure we don't miss any transactions
// credit cards can take days to settle, and amazon may not charge for a transaction *right away*
const DAY_ADJUSTMENT = 7;
const startDate = dateFns.subDays(minDate, DAY_ADJUSTMENT);
const endDate = dateFns.addDays(maxDate, DAY_ADJUSTMENT);

const allLunchMoneyTransactions = await lunchMoney.getTransactions({
  start_date: dateFns.format(startDate, "yyyy-MM-dd"),
  end_date: dateFns.format(endDate, "yyyy-MM-dd"),
});

// LM does not all us to search for a transaction by payee criteria, so we need to filter here
const lunchMoneyAmazonTransactionsWithRefunds =
  allLunchMoneyTransactions.filter(
    // TODO do we need to any sort of regex matching here? More fancy matching?
    (transaction) => transaction.payee === "Amazon"
  );
const lunchMoneyAmazonTransactions =
  lunchMoneyAmazonTransactionsWithRefunds.filter(
    // eliminate all refund transactions
    (transaction) => parseFloat(transaction.amount) > 0
  );

const uncategorizedLunchMoneyAmazonTransactions =
  lunchMoneyAmazonTransactions.filter(
    // filter out transactions that have already been categorized manually
    // this assumes you have a default rule set up in LM for amazon transaction
    (transaction) => transaction.category_id === defaultCategoryId
  );

console.log(
  `Lunch Money transactions we can match: ${uncategorizedLunchMoneyAmazonTransactions.length} (out of ${allLunchMoneyTransactions.length})`
);

function findMatchingLunchMoneyTransaction(
  uncategorizedTransaction: LunchMoneyTransaction,
  remainingAmazonTransactions: AmazonTransaction[]
) {
  const normalizedPaymentAmount = parseFloat(
    uncategorizedTransaction.amount
  ).toFixed(2);

  const parsedDate = new Date(uncategorizedTransaction.date);

  // first, we match on amount, then we prioritize matches by date
  // the reason for this is the date of the transaction can be very different from the date of the amazon transaction
  const possibleMatches = remainingAmazonTransactions.filter(
    (amazonTransaction) =>
      parseFloat(amazonTransaction.total) ===
        parseFloat(uncategorizedTransaction.amount) ||
      // if the txn has multiple payments, we'll need to check the payments column for a match
      amazonTransaction.payments.includes(normalizedPaymentAmount)
  );

  if (possibleMatches.length === 0) {
    return null;
  }

  // the sort builtin mutates the array, which is really annoying. Sigh.
  // if there are multiple possible matches, we'll want to sort by the closest date
  possibleMatches.sort(
    (one: AmazonTransaction, two: AmazonTransaction) =>
      Math.abs(dateFns.differenceInDays(parsedDate, new Date(one.date))) -
      Math.abs(dateFns.differenceInDays(parsedDate, new Date(two.date)))
  );

  const matchingTransaction = possibleMatches[0];
  const matchingTransactionIndex = remainingAmazonTransactions.findIndex(
    (txn) => txn.orderid === matchingTransaction.orderid
  );

  log.debug("removing match", matchingTransaction.orderid);

  // once we find a match, we don't watch to try matching this transaction again
  return remainingAmazonTransactions.splice(matchingTransactionIndex, 1)[0];
}

// TODO this should be an input json, but I'm losing motivation here...
const categoryRules: { [key: string]: string } = {
  "Tools & Home Improvement": "House Maintenance",
  "Patio, Lawn & Garden": "House Maintenance",
  "Power & Hand Tools": "House Maintenance",
  "Home & Kitchen›Furniture": "House Maintenance",

  "Baby Products": "Kids",
  "Toys & Games›Kids": "Kids",
  "Toys & Games›Stuffed Animals & Plush Toys": "Kids",
  "Toys & Games›Dress Up & Pretend Play": "Kids",
  "Toys & Games›Sports & Outdoor Play": "Kids",

  "Health & Household›Health Care": "Health Expenses",
  "Health & Household›Vitamins, Minerals & Supplements": "Health Expenses",
  "Health & Household›Medical Supplies & Equipment": "Health Expenses",

  Automotive: "Auto Service",

  "Kindle Store": "Books",
  Books: "Books",

  "Grocery & Gourmet Food": "Groceries",

  "Clothing, Shoes & Jewelry": "Clothing",
  "Beauty & Personal Care": "Personal Care",

  "Sports & Outdoors›Sports": "Entertainment",
  "Sports & Outdoors›Outdoor Recreation": "Entertainment",
  "Sports & Outdoors›Exercise & Fitness": "Gym",
};

function orderIsGift(transaction: AmazonTransaction) {
  // in some cases '0' is returned by the scrapers, we want to exclude these values
  if (!options.ownerName || !transaction.to || transaction.to === "0") {
    return false;
  }

  return transaction.to != options.ownerName;
}

for (const uncategorizedAmazonTransaction of lunchMoneyAmazonTransactions) {
  const matchingAmazonTransaction = findMatchingLunchMoneyTransaction(
    uncategorizedAmazonTransaction,
    amazonTransactions
  );

  if (!matchingAmazonTransaction) {
    log.warn(
      `no match\t${uncategorizedAmazonTransaction.id}\t${uncategorizedAmazonTransaction.amount}\t${uncategorizedAmazonTransaction.payee}\t${uncategorizedAmazonTransaction.notes}\t${uncategorizedAmazonTransaction.date}`
    );
    continue;
  }

  // TODO maybe allow for an overwrite?
  if (uncategorizedAmazonTransaction.category_id !== defaultCategoryId) {
    log.debug("already categorized, but matched. Skipping");
    continue;
  }

  let targetCategoryName: string | null = null;

  if (orderIsGift(matchingAmazonTransaction)) {
    log.debug("identified gift", matchingAmazonTransaction);
    targetCategoryName = "Gifts";
  } else {
    const matchingKey = Object.keys(categoryRules).find((key) =>
      matchingAmazonTransaction.categories.startsWith(key)
    );

    if (matchingKey) {
      targetCategoryName = categoryRules[matchingKey];
    }
  }

  if (!targetCategoryName) {
    log.info(
      `no rule\t${uncategorizedAmazonTransaction.id}\t${matchingAmazonTransaction.categories}`
    );

    // TODO we want to update the transaction to have a note, even if we don't change the categry

    continue;
  }

  log.debug(
    `match\t${matchingAmazonTransaction.date} : ${uncategorizedAmazonTransaction.date} : ${uncategorizedAmazonTransaction.amount} : ${matchingAmazonTransaction.total} : ${uncategorizedAmazonTransaction.id}`
  );

  const newCategoryId = categoryNameToId(targetCategoryName);
  if (!newCategoryId) {
    log.error("invalid category name", targetCategoryName);
    continue;
  }

  // null is actually printed, which is why we need ""
  const newNote = `#${matchingAmazonTransaction.orderid} ${
    uncategorizedAmazonTransaction.notes || ""
  }`.trim();

  log.info(`updating transaction ${uncategorizedAmazonTransaction.id}`);
  log.debug("content of update", newNote, newCategoryId);

  if (!options.dryRun) {
    const response = await lunchMoney.updateTransaction(
      uncategorizedAmazonTransaction.id,
      {
        category_id: newCategoryId,
        notes: newNote,
      }
    );

    if (!response.updated) {
      log.error("failed to update transaction", response);
    } else {
      log.info(response);
    }
  }
}

log.info(`Remaining uncategorized transactions: ${amazonTransactions.length}`);
