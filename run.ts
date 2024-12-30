import { LunchMoney, Transaction as LunchMoneyTransaction } from "lunch-money";
import { readCSV, AmazonTransaction, getAllTransactionsPaging } from "./util.js";
import * as dateFns from "date-fns";
import fs from "fs";
import { Command } from "commander";
import log, { LogLevelNames, debug } from "loglevel";
import prefix from "loglevel-plugin-prefix";

import { OpenAI } from "openai";


// add expected log level prefixes
prefix.reg(log);
log.enableAll();
prefix.apply(log);

// from docs: https://lunchmoney.dev/#update-transaction
const LUNCHMONEY_NOTE_LIMIT = 350

if (process.env.LOG_LEVEL) {
  const logLevelFromEnv = process.env.LOG_LEVEL.toLowerCase() as LogLevelNames;
  log.setLevel(logLevelFromEnv);
} else {
  log.setLevel(log.levels.INFO);
}

const program = new Command();
program.name("amazon-lunchmoney");

// the fact that all option schema is extracted from a single string is annoying, node libs are so poorly designed!
program
  .option("-v, --verbose", "output verbose logs")
  .requiredOption("-f, --file <path>", "amazon history file")
  .option("-k --lunch-money-key <key>", "lunch money api key")
  .option("-d, --dry-run", "dry run mode", false)
  .option(
    "-n, --owner-names <name...>",
    "name of the owner(s) of the account, used to determine if a order is a gift",
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

// regardless of if the user chooses to use chatgpt, let's generate a prompt for the user
const promptCategories =   lunchMoneyCategories
    .filter(
      (category) =>
        !category.is_income &&
        !category.archived &&
        !category.exclude_from_budget &&
        !category.is_group,
    )
    // limit the data passed to chatgpt
const promptCategoriesJson = JSON.stringify(
  promptCategories.map(({ id, name, description }) => ({
      id,
      name,
      description,
    })),
);

function generateSummaryPrompt(transactionItems: string) {
  return `
Here is a list of categories in a personal finance tool:

\`\`\`json
${promptCategoriesJson}
\`\`\`

Here is a description of a group of items purchased from Amazon:

\`\`\`
${transactionItems}
\`\`\`

Pick the category that best matches the list of items above. Include only the ID in an \`id\` JSON field.

Summary the items purchased into a handful of words. Include this summary in a \`summary\` JSON field.

Here is an example response:

\`\`\`json
{
  "id": 123,
  "summary": "Online groceries"
}
\`\`\`

Include only raw JSON, no codefences.
`  
}

interface AITransactionSummary {
  id: number | null;
  summary: string;
}

async function aiTransactionSummary(transactionItems: string): Promise<AITransactionSummary> {
  const prompt = generateSummaryPrompt(transactionItems);
  const openai = new OpenAI();

  const response = await openai.chat.completions.create({
    model: "gpt-4o-mini",
    messages: [{ role: 'user', content: prompt }],
    max_tokens: 50,
    temperature: 0,
  });

  const chosenText = response.choices[0].message?.content;
  
  if(!chosenText) {
    return { id: null, summary: "" };
  }

  const parsedResponse = JSON.parse(chosenText)

  const chosenId = parseInt(parsedResponse.id, 10);

  if (isNaN(chosenId) || !promptCategories.some((cat) => cat.id === chosenId)) {
    return { id: null, summary: parsedResponse.summary };
  }

  return parsedResponse;
}

// find a LM category ID by name
function categoryNameToId(categoryName: string) {
  return lunchMoneyCategories.find(
    (category) => !category.is_group && category.name === categoryName,
  )?.id;
}

// default is pulled from CLI options
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
  // filter out
  //    - $0 transactions(paid by gift card), they'll be no matching entry in LM
  //    - transactions that do not have a category set
  //    - transactions with a "pending" item (could not be scraped)
  //    - transactions without a date
  (transaction) =>
    transaction.total !== "0" &&
    transaction.date !== "pending" &&
    transaction.date !== "?" &&
    transaction.date !== "" &&
    transaction.items !== "pending" &&
    transaction.items !== "",
);

if (amazonTransactions.length === 0) {
  log.error(
    "No transactions found after filtering. Original transaction count:",
    allAmazonTransactions.length,
  );
  process.exit(1);
}

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

// TODO check if we can filter by payee in the future... can't do this right now
// const allLunchMoneyTransactions = await lunchMoney.getTransactions({
//   start_date: dateFns.format(startDate, "yyyy-MM-dd"),
//   end_date: dateFns.format(endDate, "yyyy-MM-dd"),
// });

const allLunchMoneyTransactions = await getAllTransactionsPaging(
  lunchMoney,
  startDate,
  endDate,
);

log.debug("all transactions pulled", allLunchMoneyTransactions.length);

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
      parseFloat(amazonTransaction.total).toFixed(2) ===
        normalizedPaymentAmount
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

const ownerNames: string[] = options.ownerNames.map((name: string) =>
  name.toLowerCase().trim(),
);

function orderIsGift(transaction: AmazonTransaction) {
  // in some cases '0' is returned by the scraper, we want to exclude these values
  if (!ownerNames || !transaction.to || transaction.to === "0") {
    return false;
  }

  return !ownerNames.includes(transaction.to.toLowerCase().trim());
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
  // NOTE this will not be hit since we are filtering out transactions that have already been categorized from the LM side
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
  let transactionSummary = null

  if (orderIsGift(matchingAmazonTransaction)) {
    log.debug("identified gift", matchingAmazonTransaction);
    // TODO this should not be hardcoded
    targetCategoryName = "Gifts";
  } else  {
    const summaryResponse = await aiTransactionSummary(matchingAmazonTransaction.items);
    transactionSummary = summaryResponse.summary;
    log.debug(`AI summary '${transactionSummary}' for items ${matchingAmazonTransaction.items}`);

    // kind of silly to convert to name, but makes the rest of the code more simple
    if (summaryResponse.id) {
      log.debug(`AI chose category ${summaryResponse.id} for items: ${matchingAmazonTransaction.items}`);
      targetCategoryName = promptCategories.find((cat) => cat.id === summaryResponse.id)?.name ?? null;
    } else {
      log.warn("AI could not match transaction", matchingAmazonTransaction);
    }
  }

  // null is actually printed, which is why we need ""
  let newNote = `#${matchingAmazonTransaction.orderid} ${
    uncategorizedLunchMoneyAmazonTransaction.notes || ""
    }`.trim();
  
  // add AI generated summary
  if (transactionSummary) {
    newNote += `. ${transactionSummary}`;
  }

  // truncate to max characters
  newNote = newNote.substring(0, LUNCHMONEY_NOTE_LIMIT);
  
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
