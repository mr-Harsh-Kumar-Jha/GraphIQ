"""GraphIQ — Data ingestion script for JSONL data files.

Reads JSONL files from the data/ subdirectories and bulk-inserts
into PostgreSQL with camelCase → snake_case column mapping.
SAP document numbers zero-padded to 10 digits at ingestion time.

Usage:
    cd graphiq/
    python scripts/ingest_data.py
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import asyncpg

sys.path.insert(0, str(Path(__file__).parent.parent))
from app.core.config import settings  # type: ignore

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("ingest")

DATA_DIR = Path(__file__).parent.parent / "data"

# ── camelCase → snake_case ────────────────────────────────────────────────────

_CAMEL_RE = re.compile(r"(?<!^)(?=[A-Z])")


def _to_snake(name: str) -> str:
    return _CAMEL_RE.sub("_", name).lower()


# ── SAP document number padding ───────────────────────────────────────────────

_DOC_PAD_COLS = {
    "billing_document",
    "delivery_document",
    "sales_order",
    "accounting_document",
    "clearing_accounting_document",
    "reference_sd_document",
    "cancelled_billing_document",
    "business_partner",
    "customer",
    "sold_to_party",
}
_DOC_PAD_RE = re.compile(r"^\d{1,10}$")


def _pad(value: str) -> str:
    v = value.strip()
    if v and _DOC_PAD_RE.match(v):
        return v.zfill(10)
    return v


# ── datetime parsing ──────────────────────────────────────────────────────────

def _parse_iso_datetime(value: str) -> datetime | None:
    """Parse strings like '2025-11-06T00:00:00.000Z' to datetime."""
    v = value.strip()
    if not v:
        return None
    if v.endswith("Z"):
        v = v.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(v)
    except ValueError:
        return None


# ── Table → data pattern (ordered for FK safety) ──────────────────────────────

TABLE_SOURCES = [
    # Master / dimension tables
    ("**business_partner[^s]*", "business_partners"),
    ("**business_partner_address*", "business_partner_address"),
    ("**customer_company_assignment*", "customer_company_assignment"),
    ("**customer_sales_area_assignment*", "customer_sales_area_assignments"),

    # Plant
    ("**/plant/*part*", "plant"),

    # Products and related
    ("**/products[^/]*/part*", "products"),
    ("**product_description*", "product_description"),
    ("**product_plant*", "product_plants"),
    ("**product_storage*", "product_storage_locations"),

    # Orders
    ("**sales_order_header*", "sales_order_headers"),
    ("**sales_order_item*", "sales_order_items"),
    ("**sales_order_schedule_line*", "sales_order_schedule_lines"),

    # Deliveries
    ("**outbound_delivery_header*", "outbound_delivery_headers"),
    ("**outbound_delivery_item*", "outbound_delivery_items"),

    # Billing / payments / journal
    ("**billing_document_header*", "billing_document_headers"),
    ("**billing_document_item*", "billing_document_items"),
    ("**billing_document_cancellation*", "billing_document_cancellation"),
    ("**payments_accounts_receivable*", "payment_accounts_receivable"),
    ("**journal_entry_items*", "journal_entry_items_accounts_receivable"),
]


async def get_table_columns(conn: asyncpg.Connection, table_name: str) -> dict[str, str]:
    """Return mapping of column_name -> data_type for a PostgreSQL table."""
    rows = await conn.fetch(
        """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = $1
        """,
        table_name,
    )
    return {r["column_name"]: r["data_type"] for r in rows}


async def get_business_partner_ids(conn: asyncpg.Connection) -> set[str]:
    rows = await conn.fetch("SELECT business_partner FROM business_partners")
    return {r["business_partner"] for r in rows}


async def get_sales_order_ids(conn: asyncpg.Connection) -> set[str]:
    rows = await conn.fetch("SELECT sales_order FROM sales_order_headers")
    return {r["sales_order"] for r in rows}


def _coerce_value(col: str, v: str, col_types: dict[str, str]) -> Any:
    """Coerce string v to correct Python type based on PostgreSQL data_type."""
    pg_type = col_types.get(col)

    # Timestamp without time zone -> naive datetime
    if pg_type == "timestamp without time zone":
        dt = _parse_iso_datetime(v)
        if dt is not None:
            return dt.replace(tzinfo=None)
        return datetime.strptime(v[:10], "%Y-%m-%d")

    # Timestamp with time zone -> aware datetime
    if pg_type == "timestamp with time zone":
        dt = _parse_iso_datetime(v)
        if dt is not None:
            return dt
        return datetime.strptime(v[:10], "%Y-%m-%d")

    # Date type
    if pg_type == "date":
        dt = _parse_iso_datetime(v)
        if dt is not None:
            return dt.date()
        return datetime.strptime(v[:10], "%Y-%m-%d").date()

    # Zero-pad doc numbers
    if col in _DOC_PAD_COLS:
        return _pad(v)

    # For numeric/text types, let asyncpg/Postgres cast from string
    return v


def _normalize_record(record: dict, col_types: dict[str, str]) -> dict[str, Any]:
    """Convert a camelCase JSONL record to PostgreSQL-compatible snake_case dict."""
    out: dict[str, Any] = {}

    for key, value in record.items():
        col = _to_snake(key)

        # Skip nested dicts like "creationTime": {...}
        if isinstance(value, dict):
            continue

        if value is None:
            out[col] = None
            continue

        if isinstance(value, bool):
            out[col] = value
            continue

        v = str(value).strip()
        if not v:
            out[col] = None
            continue

        out[col] = _coerce_value(col, v, col_types)

    return out


async def ingest_file(
    conn: asyncpg.Connection,
    jsonl_path: Path,
    table_name: str,
    col_types: dict[str, str],
) -> int:
    rows: list[dict[str, Any]] = []

    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            normalized = _normalize_record(record, col_types)
            filtered = {k: v for k, v in normalized.items() if k in col_types}
            if filtered:
                rows.append(filtered)

    if not rows:
        return 0

    columns = list(rows[0].keys())
    col_list = ", ".join(columns)
    placeholders = ", ".join(f"${i+1}" for i in range(len(columns)))
    sql = (
        f"INSERT INTO {table_name} ({col_list}) "
        f"VALUES ({placeholders}) "
        f"ON CONFLICT DO NOTHING"
    )

    batch = [tuple(r.get(c) for c in columns) for r in rows]
    await conn.executemany(sql, batch)
    return len(batch)


async def main() -> None:
    logger.info("Connecting to PostgreSQL...")
    conn = await asyncpg.connect(settings.postgres_url)
    total_rows = 0

    bp_ids: set[str] | None = None
    so_ids: set[str] | None = None

    try:
        # Preload business partners once (if you later add FK filters)
        bp_ids = await get_business_partner_ids(conn)
        so_ids = await get_sales_order_ids(conn)

        for dir_glob, table_name in TABLE_SOURCES:
            col_types = await get_table_columns(conn, table_name)
            if not col_types:
                logger.warning(
                    "Table not found in schema: %s — run alembic upgrade head first",
                    table_name,
                )
                continue

            # Find relevant JSON/JSONL files
            jsonl_files = list(DATA_DIR.rglob("*.jsonl")) + list(
                DATA_DIR.rglob("*.json")
            )

            if table_name == "payment_accounts_receivable":
                # Explicit: everything under data/Payments/payments_accounts_receivable
                payments_dir = DATA_DIR / "Payments" / "payments_accounts_receivable"
                if payments_dir.exists():
                    relevant = sorted(
                        payments_dir.rglob("*.jsonl")
                    ) + sorted(payments_dir.rglob("*.json"))
                else:
                    relevant = []
            else:
                table_keyword = table_name.replace("_", "")
                relevant = [
                    f
                    for f in jsonl_files
                    if any(
                        table_keyword in part.replace("_", "").replace("-", "")
                        for part in f.parts
                    )
                ]

            if not relevant:
                logger.warning("No JSONL files found for table: %s", table_name)
                continue

            table_count = 0
            for jsonl_path in relevant:
                count = await ingest_file(conn, jsonl_path, table_name, col_types)
                table_count += count

            logger.info("Ingested %d rows → %s", table_count, table_name)
            total_rows += table_count

    finally:
        await conn.close()

    logger.info("=" * 50)
    logger.info("Total rows ingested: %d", total_rows)


if __name__ == "__main__":
    asyncio.run(main())