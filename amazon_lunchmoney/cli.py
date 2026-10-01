"""Command line interface for amazon-lunchmoney."""

from __future__ import annotations

import datetime
import os
from pathlib import Path

import click
from pydantic_ai import Agent

from .amazon import date_range, is_matchable
from .categorize import (
    TransactionSummary,
    ai_transaction_summary,
    build_note,
    category_name_to_id,
    create_agent,
    order_is_gift,
    prompt_categories,
    should_update_note,
)
from .config import get_model_name
from .formats import (
    FORMAT_AMAZON_SHOPPING_MCP,
    FORMAT_AZAD,
    read_orders,
)
from .log import log, setup_logging
from .lunchmoney import LunchMoneyClient
from .matcher import find_matching_transaction
from .version import __version__

# credit cards can take days to settle, and amazon may not charge for an
# order *right away*, so widen the LM query window to avoid missing charges
DAY_ADJUSTMENT = 7

# TODO this should not be hardcoded
GIFT_CATEGORY_NAME = "Gifts"


def echo_cli_version(ctx: click.Context, param: click.Parameter, value: bool) -> None:
    if not value or ctx.resilient_parsing:
        return

    prog_name = ctx.find_root().info_name or "amazon-lunchmoney"
    click.echo(f"{prog_name}, version {__version__}")
    click.echo(f"model: {get_model_name()}")
    ctx.exit()


@click.command(
    "amazon-lunchmoney", context_settings={"help_option_names": ["-h", "--help"]}
)
@click.option(
    "--version",
    is_flag=True,
    expose_value=False,
    is_eager=True,
    callback=echo_cli_version,
    help="Show the version and configured model and exit.",
)
@click.option("-v", "--verbose", is_flag=True, help="output verbose logs")
@click.option(
    "-f",
    "--file",
    "history_file",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="amazon history file",
)
@click.option(
    "--format",
    "file_format",
    type=click.Choice([FORMAT_AZAD, FORMAT_AMAZON_SHOPPING_MCP]),
    default=FORMAT_AZAD,
    show_default=True,
    help="order history file format",
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
@click.option(
    "-l",
    "--limit",
    type=click.IntRange(min=1),
    default=None,
    help="limit the number of input order transactions to process",
)
def cli(
    verbose: bool,
    history_file: Path,
    file_format: str,
    lunch_money_key: str | None,
    dry_run: bool,
    owner_names: tuple[str, ...],
    default_category: str,
    limit: int | None,
) -> None:
    if verbose:
        setup_logging(verbose=True)

    log.debug(
        "options",
        file=history_file,
        format=file_format,
        dry_run=dry_run,
        owners=owner_names,
        default_category=default_category,
        limit=limit,
    )

    if not lunch_money_key:
        raise click.ClickException("Lunch Money API key not set")

    client = LunchMoneyClient(token=lunch_money_key)
    categories = client.get_categories()

    prompt_cats = prompt_categories(categories)

    default_category_id = category_name_to_id(categories, default_category)
    if default_category_id is None:
        raise click.ClickException(f"Default category {default_category} not found")

    log.debug("category match found", category_id=default_category_id)

    all_amazon_transactions = read_orders(history_file, file_format)
    if limit is not None:
        all_amazon_transactions = all_amazon_transactions[:limit]

    amazon_transactions = [t for t in all_amazon_transactions if is_matchable(t)]

    if not amazon_transactions:
        raise click.ClickException(
            f"No transactions found after filtering. Original transaction count: {len(all_amazon_transactions)}"
        )

    log.info(
        "amazon transactions we can match",
        matchable=len(amazon_transactions),
        total=len(all_amazon_transactions),
    )

    min_date, max_date = date_range(amazon_transactions)
    log.info("matching transactions date range", start_date=min_date, end_date=max_date)

    # adjust the dates by a couple days to make sure we don't miss any transactions
    start_date = min_date - datetime.timedelta(days=DAY_ADJUSTMENT)
    end_date = max_date + datetime.timedelta(days=DAY_ADJUSTMENT)

    # TODO check if we can filter by payee in the future... can't do this right now
    all_lunchmoney_transactions = client.get_all_transactions(start_date, end_date)
    log.debug("all transactions pulled", count=len(all_lunchmoney_transactions))

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
        "lunch money transactions we can match",
        matchable=len(uncategorized),
        total=len(all_lunchmoney_transactions),
    )

    normalized_owner_names = [name.lower().strip() for name in owner_names]
    ai_agent: Agent[None, TransactionSummary] | None = None

    for transaction in uncategorized:
        matching_amazon_transaction = find_matching_transaction(
            transaction, amazon_transactions
        )

        if matching_amazon_transaction is None:
            log.warning(
                "no match",
                id=transaction.id,
                amount=transaction.amount,
                payee=transaction.payee,
                notes=transaction.notes,
                date=transaction.date,
            )
            continue

        if transaction.is_group or transaction.group_id:
            log.warning("skipping group transaction", id=transaction.id)
            continue

        target_category_name: str | None = None
        transaction_summary: str | None = None

        if order_is_gift(matching_amazon_transaction, normalized_owner_names):
            log.debug("identified gift", transaction=matching_amazon_transaction)
            target_category_name = GIFT_CATEGORY_NAME
        else:
            if ai_agent is None:
                ai_agent = create_agent()
            summary_response = ai_transaction_summary(
                matching_amazon_transaction.items, prompt_cats, ai_agent
            )
            transaction_summary = summary_response.summary
            log.debug(
                "ai summary for items",
                summary=transaction_summary,
                items=matching_amazon_transaction.items,
            )

            # kind of silly to convert to name, but makes the rest of the code more simple
            if summary_response.id is not None:
                log.debug(
                    "ai chose category for items",
                    category_id=summary_response.id,
                    items=matching_amazon_transaction.items,
                )
                match = next(
                    (c for c in prompt_cats if c.id == summary_response.id), None
                )
                target_category_name = match.name if match else None
            else:
                log.warning(
                    "ai could not match transaction",
                    transaction=matching_amazon_transaction,
                )

        new_note = build_note(
            matching_amazon_transaction.orderid, transaction.notes, transaction_summary
        )
        update_note = should_update_note(
            transaction.notes, matching_amazon_transaction.orderid
        )

        if target_category_name is None:
            log.info(
                "no rule match",
                id=transaction.id,
                categories=matching_amazon_transaction.categories,
            )

            # TODO we want to update the transaction to have a note, even if we don't change the category
            if not dry_run and update_note:
                updated = client.update_transaction(transaction.id, notes=new_note)
                if not updated:
                    log.error("failed to update transaction", id=transaction.id)
                else:
                    log.info("updated notes for transaction", id=transaction.id)
            continue

        log.debug(
            "match found",
            amazon_date=matching_amazon_transaction.date,
            transaction_date=transaction.date,
            transaction_amount=transaction.amount,
            amazon_total=matching_amazon_transaction.total,
            id=transaction.id,
        )

        new_category_id = category_name_to_id(categories, target_category_name)
        if new_category_id is None:
            log.error("invalid category name", category_name=target_category_name)
            continue

        log.info("updating transaction", id=transaction.id)
        log.debug("content of update", note=new_note, category_id=new_category_id)

        if not dry_run:
            updated = client.update_transaction(
                transaction.id,
                category_id=new_category_id,
                notes=new_note if update_note else None,
            )
            if not updated:
                log.error("failed to update transaction", id=transaction.id)
            else:
                log.info("updated transaction", id=transaction.id)

    log.info("remaining uncategorized transactions", count=len(amazon_transactions))
