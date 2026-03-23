"""GraphIQ — Neo4j sync pipeline.

Full bootstrap + incremental 15-second loop.
Pulls from PostgreSQL and MERGEs into Neo4j.

Usage:
    cd graphiq/
    python scripts/neo4j_bootstrap.py
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncpg
from app.core.config import settings
from app.storage.neo4j import Neo4jStore

logger = logging.getLogger("neo4j_sync")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

# ── Node bootstrap queries (1 per entity type) ────────────────────────────────

_CUSTOMER_CYPHER = """
UNWIND $rows AS row
MERGE (c:Customer {id: row.business_partner})
SET c.name = row.business_partner_full_name,
    c.country = row.country,
    c.is_blocked = row.is_blocked
"""

_ORDER_CYPHER = """
UNWIND $rows AS row
MERGE (o:SalesOrder {id: row.sales_order})
SET o.creation_date = row.creation_date,
    o.total_net_amount = toFloat(coalesce(row.total_net_amount, '0')),
    o.currency = row.transaction_currency,
    o.customer_id = row.sold_to_party
"""

_DELIVERY_CYPHER = """
UNWIND $rows AS row
MERGE (d:Delivery {id: row.delivery_document})
SET d.creation_date = row.creation_date,
    d.status = row.goods_movement_status
"""

_INVOICE_CYPHER = """
UNWIND $rows AS row
MERGE (i:Invoice {id: row.billing_document})
SET i.billing_date = row.billing_document_date,
    i.total_net_amount = toFloat(coalesce(row.total_net_amount, '0')),
    i.currency = row.transaction_currency,
    i.accounting_doc = row.accounting_document
"""

_JOURNAL_CYPHER = """
UNWIND $rows AS row
MERGE (j:JournalEntry {id: row.accounting_document + '_' + row.fiscal_year + '_' + row.accounting_document_item})
SET j.posting_date = row.posting_date,
    j.amount = toFloat(coalesce(row.amount_in_document_currency, '0')),
    j.currency = row.currency,
    j.clearing_doc = row.clearing_accounting_document
"""

_PAYMENT_CYPHER = """
UNWIND $rows AS row
MERGE (p:Payment {id: row.accounting_document + '_' + row.fiscal_year})
SET p.posting_date = row.posting_date,
    p.amount = toFloat(coalesce(row.amount_in_transaction_currency, '0')),
    p.currency = row.transaction_currency,
    p.customer_id = row.customer
"""

_PRODUCT_CYPHER = """
UNWIND $rows AS row
MERGE (p:Product {id: row.product})
SET p.description = row.product_description
"""

_PLANT_CYPHER = """
UNWIND $rows AS row
MERGE (pl:Plant {id: row.plant})
SET pl.name = row.plant_name
"""

# ── Relationship bootstrap queries ────────────────────────────────────────────

_REL_CUSTOMER_ORDER = """
MATCH (c:Customer {id: row.sold_to_party})
MATCH (o:SalesOrder {id: row.sales_order})
MERGE (c)-[:PLACED]->(o)
"""

_REL_ORDER_DELIVERY = """
UNWIND $rows AS row
MATCH (o:SalesOrder {id: row.reference_sd_document})
MATCH (d:Delivery {id: row.delivery_document})
MERGE (o)-[:DELIVERED_BY]->(d)
"""

_REL_DELIVERY_INVOICE = """
UNWIND $rows AS row
MATCH (d:Delivery {id: row.reference_sd_document})
MATCH (i:Invoice {id: row.billing_document})
MERGE (d)-[:BILLED_BY]->(i)
"""

_REL_INVOICE_JOURNAL = """
UNWIND $rows AS row
MATCH (i:Invoice {id: row.billing_document})
MATCH (j:JournalEntry) WHERE j.id STARTS WITH row.accounting_document + '_'
MERGE (i)-[:POSTED_AS]->(j)
"""

_REL_JOURNAL_PAYMENT = """
UNWIND $rows AS row
MATCH (j:JournalEntry) WHERE j.id STARTS WITH row.accounting_document + '_'
MATCH (p:Payment) WHERE p.id STARTS WITH row.clearing_accounting_document + '_'
MERGE (j)-[:CLEARED_BY]->(p)
"""

_REL_ORDER_PRODUCT = """
UNWIND $rows AS row
MATCH (o:SalesOrder {id: row.sales_order})
MATCH (p:Product {id: row.material})
MERGE (o)-[:INCLUDES]->(p)
"""

_REL_PRODUCT_PLANT = """
UNWIND $rows AS row
MATCH (p:Product {id: row.product})
MATCH (pl:Plant {id: row.plant})
MERGE (p)-[:PRODUCED_AT]->(pl)
"""

_REL_PAYMENT_CUSTOMER = """
UNWIND $rows AS row
MATCH (p:Payment {id: row.accounting_document + '_' + row.fiscal_year})
MATCH (c:Customer {id: row.customer})
MERGE (p)-[:FOR_CUSTOMER]->(c)
"""


async def _pg_fetch_all(conn: asyncpg.Connection, sql: str) -> list[dict]:
    rows = await conn.fetch(sql)
    return [dict(r) for r in rows]


async def bootstrap(pg_conn: asyncpg.Connection, neo4j: Neo4jStore) -> None:
    """Run full bootstrap: all nodes, then all relationships."""
    logger.info("Bootstrapping Neo4j nodes...")

    # Customers
    rows = await _pg_fetch_all(pg_conn, "SELECT business_partner, business_partner_full_name, country, is_blocked FROM business_partners LIMIT 10000")
    await neo4j.run_batch_write(_CUSTOMER_CYPHER, rows)
    logger.info("Merged %d Customer nodes", len(rows))

    # Sales Orders
    rows = await _pg_fetch_all(pg_conn, "SELECT sales_order, creation_date::text as creation_date, total_net_amount::text, transaction_currency, sold_to_party FROM sales_order_headers LIMIT 50000")
    await neo4j.run_batch_write(_ORDER_CYPHER, rows)
    logger.info("Merged %d SalesOrder nodes", len(rows))

    # Deliveries
    rows = await _pg_fetch_all(pg_conn, "SELECT delivery_document, creation_date::text, goods_movement_status FROM outbound_delivery_headers LIMIT 50000")
    await neo4j.run_batch_write(_DELIVERY_CYPHER, rows)
    logger.info("Merged %d Delivery nodes", len(rows))

    # Invoices
    rows = await _pg_fetch_all(pg_conn, "SELECT billing_document, billing_document_date::text, total_net_amount::text, transaction_currency, accounting_document FROM billing_document_headers LIMIT 50000")
    await neo4j.run_batch_write(_INVOICE_CYPHER, rows)
    logger.info("Merged %d Invoice nodes", len(rows))

    # Journal entries
    rows = await _pg_fetch_all(pg_conn, "SELECT accounting_document, fiscal_year, accounting_document_item, posting_date::text, amount_in_document_currency::text, currency, clearing_accounting_document FROM journal_entry_items_accounts_receivable LIMIT 100000")
    await neo4j.run_batch_write(_JOURNAL_CYPHER, rows)
    logger.info("Merged %d JournalEntry nodes", len(rows))

    # Payments
    rows = await _pg_fetch_all(pg_conn, "SELECT accounting_document, fiscal_year, posting_date::text, amount_in_transaction_currency::text, transaction_currency, customer FROM payment_accounts_receivable LIMIT 50000")
    if rows:
        await neo4j.run_batch_write(_PAYMENT_CYPHER, rows)
        logger.info("Merged %d Payment nodes", len(rows))

    # Products
    rows = await _pg_fetch_all(pg_conn, "SELECT product, product_description FROM product_description WHERE language = 'EN' LIMIT 50000")
    if rows:
        await neo4j.run_batch_write(_PRODUCT_CYPHER, rows)
        logger.info("Merged %d Product nodes", len(rows))

    # Plants
    rows = await _pg_fetch_all(pg_conn, "SELECT plant, plant_name FROM plant LIMIT 10000")
    if rows:
        await neo4j.run_batch_write(_PLANT_CYPHER, rows)
        logger.info("Merged %d Plant nodes", len(rows))

    # ── Relationships ─────────────────────────────────────────────────────────
    logger.info("Building relationships...")

    rows = await _pg_fetch_all(pg_conn, "SELECT DISTINCT sold_to_party, sales_order FROM sales_order_headers LIMIT 50000")
    if rows:
        batch_cypher = "UNWIND $rows AS row " + _REL_CUSTOMER_ORDER.strip()
        await neo4j.run_batch_write(batch_cypher, rows)

    rows = await _pg_fetch_all(pg_conn, "SELECT DISTINCT reference_sd_document, delivery_document FROM outbound_delivery_items WHERE reference_sd_document IS NOT NULL LIMIT 50000")
    if rows:
        await neo4j.run_batch_write(_REL_ORDER_DELIVERY, rows)

    rows = await _pg_fetch_all(pg_conn, "SELECT DISTINCT reference_sd_document, billing_document FROM billing_document_items WHERE reference_sd_document IS NOT NULL LIMIT 50000")
    if rows:
        await neo4j.run_batch_write(_REL_DELIVERY_INVOICE, rows)

    rows = await _pg_fetch_all(pg_conn, "SELECT DISTINCT billing_document, accounting_document FROM billing_document_headers WHERE accounting_document IS NOT NULL LIMIT 50000")
    await neo4j.run_batch_write(_REL_INVOICE_JOURNAL, rows)

    rows = await _pg_fetch_all(pg_conn, "SELECT DISTINCT accounting_document, clearing_accounting_document FROM journal_entry_items_accounts_receivable WHERE clearing_accounting_document IS NOT NULL LIMIT 100000")
    await neo4j.run_batch_write(_REL_JOURNAL_PAYMENT, rows)

    rows = await _pg_fetch_all(pg_conn, "SELECT DISTINCT sales_order, material FROM sales_order_items WHERE material IS NOT NULL LIMIT 50000")
    if rows:
        await neo4j.run_batch_write(_REL_ORDER_PRODUCT, rows)

    rows = await _pg_fetch_all(pg_conn, "SELECT DISTINCT product, plant FROM product_plants LIMIT 50000")
    if rows:
        await neo4j.run_batch_write(_REL_PRODUCT_PLANT, rows)

    rows = await _pg_fetch_all(pg_conn, "SELECT DISTINCT accounting_document, fiscal_year, customer FROM payment_accounts_receivable WHERE customer IS NOT NULL LIMIT 50000")
    if rows:
        await neo4j.run_batch_write(_REL_PAYMENT_CUSTOMER, rows)

    neo4j.record_sync()
    logger.info("Neo4j bootstrap complete.")


async def main() -> None:
    logger.info("Connecting...")
    pg_conn = await asyncpg.connect(settings.postgres_url)
    neo4j = await Neo4jStore.create(settings.neo4j_url, settings.neo4j_user, settings.neo4j_password)
    try:
        await bootstrap(pg_conn, neo4j)
    finally:
        await pg_conn.close()
        await neo4j.close()


if __name__ == "__main__":
    asyncio.run(main())
