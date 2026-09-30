"""Command line interface for amazon-lunchmoney."""

from __future__ import annotations

import datetime
import logging
import os
from pathlib import Path

import click
from openai import OpenAI

from .amazon import date_range, is_matchable, read_csv
from .categorize import (
    ai_transaction_summary,
    build_note,
    category_name_to_id,
    order_is_gift,
    prompt_categories,
    should_update_note,
)
from .lunchmoney import LunchMoneyClient
from .matcher import find_matching_transaction

log = logging.getLogger(__name__)

# credit cards can take days to settle, and amazon may not charge for an
# order *right away*, so widen the LM query window to avoid missing charges
DAY_ADJUSTMENT = 7

# TODO this should not be hardcoded
GIFT_CATEGORY_NAME = "Gifts"


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("-v", "--verbose", is_flag=True, help="output verbose logs")
@click.option(
    "-f",
    "--file",
    "csv_file",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="amazon history file",
)
@click.option(
    "-k",
    "--lunch-money-key",
    default=lambda: os.environ.get("LUNCH_MONEY_API_KEY"),
    help="lunch money api key",
)
@click.option("-d", "--dry-run", is_flag=True, help="dry run mode")
@click.option(
    "-n",
    "--owner-names",
    multiple=True,
    help="name of the owner(s) of the account, used to determine if a order is a gift",
)
@click.option("-c", "--default-category", required=True, help="default category")
def cli(
    verbose: bool,
    csv_file: Path,
    lunch_money_key: str | None,
    dry_run: bool,
    owner_names: tuple[str, ...],
    default_category: str,
) -> None:
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    log.debug(
        "options: file=%s dry_run=%s owners=%s default_category=%s",
        csv_file,
        dry_run,
        owner_names,
        default_category,
    )

    if not lunch_money_key:
        raise click.ClickException("Lunch Money API key not set")

    client = LunchMoneyClient(token=lunch_money_key)
    categories = client.get_categories()

    prompt_cats = prompt_categories(categories)

    default_category_id = category_name_to_id(categories, default_category)
    if default_category_id is None:
        raise click.ClickException(f"Default category {default_category} not found")

    log.debug("Category match found %s", default_category_id)

    all_amazon_transactions = read_csv(csv_file)
    amazon_transactions = [t for t in all_amazon_transactions if is_matchable(t)]

    if not amazon_transactions:
        raise click.ClickException(
            f"No transactions found after filtering. Original transaction count: {len(all_amazon_transactions)}"
        )

    log.info(
        "Amazon transactions we can match: %d (out of %d)",
        len(amazon_transactions),
        len(all_amazon_transactions),
    )

    min_date, max_date = date_range(amazon_transactions)
    log.info("Matching transactions from %s to %s", min_date, max_date)

    # adjust the dates by a couple days to make sure we don't miss any transactions
    start_date = min_date - datetime.timedelta(days=DAY_ADJUSTMENT)
    end_date = max_date + datetime.timedelta(days=DAY_ADJUSTMENT)

    # TODO check if we can filter by payee in the future... can't do this right now
    all_lunchmoney_transactions = client.get_all_transactions(start_date, end_date)
    log.debug("all transactions pulled %d", len(all_lunchmoney_transactions))

    # LM does not let us search for a transaction by payee criteria, so we filter here
    # TODO do we need any sort of regex matching here? More fancy matching?
    lunchmoney_amazon_transactions = [
        t for t in all_lunchmoney_transactions if t.payee == "Amazon"
    ]
    # eliminate all refund transactions from amazon
    charges = [t for t in lunchmoney_amazon_transactions if float(t.amount) > 0]

    # only touch transactions still sitting in the default category. This assumes
    # you have a default rule set up in LM for amazon transactions.
    uncategorized = [t for t in charges if t.category_id == default_category_id]

    log.info(
        "Lunch Money transactions we can match: %d (out of %d)",
        len(uncategorized),
        len(all_lunchmoney_transactions),
    )

    normalized_owner_names = [name.lower().strip() for name in owner_names]
    openai_client: OpenAI | None = None

    for transaction in uncategorized:
        matching_amazon_transaction = find_matching_transaction(
            transaction, amazon_transactions
        )

        if matching_amazon_transaction is None:
            log.warning(
                "no match\t%s\t%s\t%s\t%s\t%s",
                transaction.id,
                transaction.amount,
                transaction.payee,
                transaction.notes,
                transaction.date,
            )
            continue

        if transaction.is_group or transaction.group_id:
            log.warning("skipping group transaction %s", transaction.id)
            continue

        target_category_name: str | None = None
        transaction_summary: str | None = None

        if order_is_gift(matching_amazon_transaction, normalized_owner_names):
            log.debug("identified gift %s", matching_amazon_transaction)
            target_category_name = GIFT_CATEGORY_NAME
        else:
            if openai_client is None:
                openai_client = OpenAI()
            summary_response = ai_transaction_summary(
                matching_amazon_transaction.items, prompt_cats, openai_client
            )
            transaction_summary = summary_response.summary
            log.debug(
                "AI summary '%s' for items %s",
                transaction_summary,
                matching_amazon_transaction.items,
            )

            # kind of silly to convert to name, but makes the rest of the code more simple
            if summary_response.id is not None:
                log.debug(
                    "AI chose category %s for items: %s",
                    summary_response.id,
                    matching_amazon_transaction.items,
                )
                match = next(
                    (c for c in prompt_cats if c.id == summary_response.id), None
                )
                target_category_name = match.name if match else None
            else:
                log.warning(
                    "AI could not match transaction %s", matching_amazon_transaction
                )

        new_note = build_note(
            matching_amazon_transaction.orderid, transaction.notes, transaction_summary
        )
        update_note = should_update_note(
            transaction.notes, matching_amazon_transaction.orderid
        )

        if target_category_name is None:
            log.info(
                "no rule match for\t%s\t%s",
                transaction.id,
                matching_amazon_transaction.categories,
            )

            # TODO we want to update the transaction to have a note, even if we don't change the category
            if not dry_run and update_note:
                updated = client.update_transaction(transaction.id, notes=new_note)
                if not updated:
                    log.error("failed to update transaction %s", transaction.id)
                else:
                    log.info("updated notes for transaction %s", transaction.id)
            continue

        log.debug(
            "match\t%s : %s : %s : %s : %s",
            matching_amazon_transaction.date,
            transaction.date,
            transaction.amount,
            matching_amazon_transaction.total,
            transaction.id,
        )

        new_category_id = category_name_to_id(categories, target_category_name)
        if new_category_id is None:
            log.error("invalid category name %s", target_category_name)
            continue

        log.info("updating transaction %s", transaction.id)
        log.debug("content of update %s %s", new_note, new_category_id)

        if not dry_run:
            updated = client.update_transaction(
                transaction.id,
                category_id=new_category_id,
                notes=new_note if update_note else None,
            )
            if not updated:
                log.error("failed to update transaction %s", transaction.id)
            else:
                log.info("updated transaction %s", transaction.id)

    log.info("Remaining uncategorized transactions: %d", len(amazon_transactions))
