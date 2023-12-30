import { LunchMoney, Transaction as LunchMoneyTransaction } from "lunch-money";
import { readCSV, AmazonTransaction } from "./util.js";
import dotenv from "dotenv";
import dateFns from "date-fns";
import fs from "fs";
import { Command } from "commander";
import log, { LogLevelNames } from "loglevel";
import prefix from "loglevel-plugin-prefix";

dotenv.config();

// add expected log level prefixes
prefix.reg(log);
log.enableAll();
prefix.apply(log);

if (process.env.LOG_LEVEL) {
  const logLevelFromEnv = process.env.LOG_LEVEL.toLowerCase() as LogLevelNames;
  log.setLevel(logLevelFromEnv);
} else {
  log.setLevel(log.levels.INFO);
}

const program = new Command();

program
  .option("-v, --verbose", "output verbose logs")
  .requiredOption("-f, --file <path>", "amazon history file")
  .option("-m --lunch-money-key <key>", "lunch money api key")
  .option("-d, --dry-run", "dry run mode", false)
  .option(
    "-n, --owner-name <name>",
    "the name of the owner of the account, used to determine if a order is a gift",
  )
  .requiredOption("-c, --default-category <category>", "default category");

program.parse(process.argv);

const options = program.opts();

if (options.debug) {
  log.setLevel(log.levels.DEBUG);
}

log.debug(options);

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
    (category) => !category.is_group && category.name === categoryName,
  )?.id;
}

const defaultCategoryId = categoryNameToId(defaultCategoryName);

if (!defaultCategoryId) {
  log.error(`Default category ${defaultCategoryName} not found`);
  process.exit(1);
}

log.debug("Category match found", defaultCategoryId);

// test if file exists on the file system before reading it
if (!fs.existsSync(csvFile)) {
  log.error(`File ${csvFile} does not exist`);
  process.exit(1);
}

const allAmazonTransactions = await readCSV(csvFile);
const amazonTransactions = allAmazonTransactions.filter(
  // filter out $0 transactions (paid by gift card), they'll be no matching entry in LM
  // also filter out transactions that do not have a category set
  (transaction) => transaction.total !== "0" && transaction.categories,
);

log.info(
  `Amazon transactions we can match: ${amazonTransactions.length} (out of ${allAmazonTransactions.length})`,
);

// determine starting and ending date range from the dates in the order history scrape file
let maxDate: Date | null = null;
let minDate: Date | null = null;

for (const transaction of amazonTransactions) {
  const date = new Date(transaction.date);
  if (!maxDate || date > maxDate) maxDate = date;
  if (!minDate || date < minDate) minDate = date;
}

if (!maxDate || !minDate) {
  log.error("No dates found in file");
  process.exit(1);
}

log.info(`Matching transactions from ${minDate} to ${maxDate}`);

// adjust the dates by a couple days to make sure we don't miss any transactions
// credit cards can take days to settle, and amazon may not charge for a transaction *right away*
const DAY_ADJUSTMENT = 7;

const startDate = dateFns.subDays(minDate, DAY_ADJUSTMENT);
const endDate = dateFns.addDays(maxDate, DAY_ADJUSTMENT);

const allLunchMoneyTransactions = await lunchMoney.getTransactions({
  start_date: dateFns.format(startDate, "yyyy-MM-dd"),
  end_date: dateFns.format(endDate, "yyyy-MM-dd"),
});

// LM does not all us to search for a transaction by payee criteria, so we need to apply that filter here
const lunchMoneyAmazonTransactionsWithRefunds =
  allLunchMoneyTransactions.filter(
    // TODO do we need to any sort of regex matching here? More fancy matching?
    (transaction) => transaction.payee === "Amazon",
  );
const lunchMoneyAmazonTransactions =
  lunchMoneyAmazonTransactionsWithRefunds.filter(
    // eliminate all refund transactions from amazno
    (transaction) => parseFloat(transaction.amount) > 0,
  );

// we only use this transformation for logging and debugging
const uncategorizedLunchMoneyAmazonTransactions =
  lunchMoneyAmazonTransactions.filter(
    // filter out transactions that have already been categorized manually
    // this assumes you have a default rule set up in LM for amazon transaction
    (transaction) => transaction.category_id === defaultCategoryId,
  );

log.info(
  `Lunch Money transactions we can match: ${uncategorizedLunchMoneyAmazonTransactions.length} (out of ${allLunchMoneyTransactions.length})`,
);

function findMatchingLunchMoneyTransaction(
  uncategorizedTransaction: LunchMoneyTransaction,
  remainingAmazonTransactions: AmazonTransaction[],
) {
  const normalizedPaymentAmount = parseFloat(
    uncategorizedTransaction.amount,
  ).toFixed(2);

  const parsedDate = new Date(uncategorizedTransaction.date);

  // first, we match on amount, then we prioritize matches by date
  // the reason for this is the date of the transaction can be very different from the date of the amazon transaction
  const possibleMatches = remainingAmazonTransactions.filter(
    (amazonTransaction) =>
      // TODO there are probably some FPA errors lurking here, but I'm lazy
      parseFloat(amazonTransaction.total) ===
        parseFloat(uncategorizedTransaction.amount) ||
      // if the txn has multiple payments, we'll need to check the payments column for a match
      amazonTransaction.payments.includes(normalizedPaymentAmount),
  );

  if (possibleMatches.length === 0) {
    return null;
  }

  // if there are multiple possible matches, we'll want to sort by the closest date
  // the sort builtin mutates the array, which is really annoying. Sigh.
  possibleMatches.sort(
    (one: AmazonTransaction, two: AmazonTransaction) =>
      Math.abs(dateFns.differenceInDays(parsedDate, new Date(one.date))) -
      Math.abs(dateFns.differenceInDays(parsedDate, new Date(two.date))),
  );

  const matchingTransaction = possibleMatches[0];
  const matchingTransactionIndex = remainingAmazonTransactions.findIndex(
    (txn) => txn.orderid.trim() === matchingTransaction.orderid.trim(),
  );

  log.debug("removing matched transaction", matchingTransaction.orderid);

  // once we find a match, we don't watch to try matching this transaction again, so we remove it from the array
  return remainingAmazonTransactions.splice(matchingTransactionIndex, 1)[0];
}

// TODO this should be an input json, but I'm losing motivation here...
const categoryRules: { [key: string]: string } = {
  "Tools & Home Improvement": "House Maintenance",
  "Patio, Lawn & Garden": "House Maintenance",
  "Power & Hand Tools": "House Maintenance",
  "Home & Kitchen›Furniture": "House Maintenance",
  "Appliances›Parts & Accessories": "House Maintenance",

  "Baby Products": "Kids",
  "Toys & Games›Kids": "Kids",
  "Toys & Games›Stuffed Animals & Plush Toys": "Kids",
  "Toys & Games›Dress Up & Pretend Play": "Kids",
  "Toys & Games›Sports & Outdoor Play": "Kids",
  "Arts, Crafts & Sewing": "Kids",
  "Health & Household›Oral Care›Baby & Child Dental Care": "Kids",
  "Toys & Games": "Kids",

  "Health & Household›Health Care": "Health Expenses",
  "Health & Household›Vitamins, Minerals & Supplements": "Health Expenses",
  "Health & Household›Medical Supplies & Equipment": "Health Expenses",

  Automotive: "Auto",
  "Cell Phones & Accessories›Accessories›Automobile Accessories": "Auto",

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
  // in some cases '0' is returned by the scraper, we want to exclude these values
  if (!options.ownerName || !transaction.to || transaction.to === "0") {
    return false;
  }

  return transaction.to !== options.ownerName;
}

for (const uncategorizedLunchMoneyAmazonTransaction of lunchMoneyAmazonTransactions) {
  const matchingAmazonTransaction = findMatchingLunchMoneyTransaction(
    uncategorizedLunchMoneyAmazonTransaction,
    amazonTransactions,
  );

  if (!matchingAmazonTransaction) {
    log.warn(
      `no match\t${uncategorizedLunchMoneyAmazonTransaction.id}\t${uncategorizedLunchMoneyAmazonTransaction.amount}\t${uncategorizedLunchMoneyAmazonTransaction.payee}\t${uncategorizedLunchMoneyAmazonTransaction.notes}\t${uncategorizedLunchMoneyAmazonTransaction.date}`,
    );
    continue;
  }

  // TODO maybe allow for an overwrite option?
  if (
    uncategorizedLunchMoneyAmazonTransaction.category_id !== defaultCategoryId
  ) {
    log.debug("already categorized, but matched. Skipping");
    continue;
  }

  if (
    uncategorizedLunchMoneyAmazonTransaction.is_group ||
    uncategorizedLunchMoneyAmazonTransaction.group_id
  ) {
    log.warn(
      `skipping group transaction ${uncategorizedLunchMoneyAmazonTransaction.id}`,
    );
    continue;
  }

  let targetCategoryName: string | null = null;

  if (orderIsGift(matchingAmazonTransaction)) {
    log.debug("identified gift", matchingAmazonTransaction);
    // TODO this should not be hardcoded
    targetCategoryName = "Gifts";
  } else {
    const matchingKey = Object.keys(categoryRules).find((key) =>
      matchingAmazonTransaction.categories.startsWith(key),
    );

    if (matchingKey) {
      targetCategoryName = categoryRules[matchingKey];
    }
  }

  // null is actually printed, which is why we need ""
  const newNote = `#${matchingAmazonTransaction.orderid} ${
    uncategorizedLunchMoneyAmazonTransaction.notes || ""
  }`.trim();
  const shouldUpdateNote = !(
    uncategorizedLunchMoneyAmazonTransaction.notes || ""
  ).includes(matchingAmazonTransaction.orderid);

  if (!targetCategoryName) {
    log.info(
      `no rule match for\t${uncategorizedLunchMoneyAmazonTransaction.id}\t${matchingAmazonTransaction.categories}`,
    );

    // TODO we want to update the transaction to have a note, even if we don't change the category
    if (!options.dryRun && shouldUpdateNote) {
      const response = await lunchMoney.updateTransaction(
        uncategorizedLunchMoneyAmazonTransaction.id,
        {
          notes: newNote,
        },
      );

      if (!response.updated) {
        log.error("failed to update transaction", response);
      } else {
        log.info(response);
      }
    }
    continue;
  }

  log.debug(
    `match\t${matchingAmazonTransaction.date} : ${uncategorizedLunchMoneyAmazonTransaction.date} : ${uncategorizedLunchMoneyAmazonTransaction.amount} : ${matchingAmazonTransaction.total} : ${uncategorizedLunchMoneyAmazonTransaction.id}`,
  );

  const newCategoryId = categoryNameToId(targetCategoryName);
  if (!newCategoryId) {
    log.error("invalid category name", targetCategoryName);
    continue;
  }

  log.info(
    `updating transaction ${uncategorizedLunchMoneyAmazonTransaction.id}`,
  );
  log.debug("content of update", newNote, newCategoryId);

  if (!options.dryRun) {
    const updateOptions: any = { category_id: newCategoryId };

    if (shouldUpdateNote) {
      updateOptions.notes = newNote;
    }

    const response = await lunchMoney.updateTransaction(
      uncategorizedLunchMoneyAmazonTransaction.id,
      updateOptions,
    );

    if (!response.updated) {
      log.error("failed to update transaction", response);
    } else {
      log.info(response);
    }
  }
}

log.info(`Remaining uncategorized transactions: ${amazonTransactions.length}`);
