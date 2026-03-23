"""GraphIQ — Schema Registry: static entity + alias definitions.

This is the ONLY file that hand-maintains entity/field data.
Everything else (prompt builder, query builder, guardrails) reads
from SchemaRegistry which loads from this module.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

FieldType = Literal["str", "int", "decimal", "date", "bool"]
JoinType = Literal["inner", "left"]


@dataclass
class FieldDef:
    """Metadata for a single database column."""

    name: str
    type: FieldType
    filterable: bool = True
    sortable: bool = True
    aggregatable: bool = False
    aliases: list[str] = field(default_factory=list)


@dataclass
class EntityDef:
    """Metadata for a single database table / O2C entity."""

    table_name: str
    primary_key: list[str]
    aliases: list[str]
    fields: dict[str, FieldDef]
    neo4j_label: str | None = None  # Set only for graph nodes


@dataclass
class JoinEdge:
    """A single legal join between two tables."""

    from_table: str
    from_column: str
    to_table: str
    to_column: str
    join_type: JoinType
    preferred: bool = False

    # For composite join keys (e.g. sales_order_items → schedule_lines)
    from_columns: list[str] | None = None
    to_columns: list[str] | None = None


# ─────────────────────────────────────────────────────────────────────────────
# ENTITY CATALOG — 19 SAP O2C entities
# ─────────────────────────────────────────────────────────────────────────────

ENTITY_CATALOG: dict[str, EntityDef] = {
    # ── 1. Sales Order Headers ───────────────────────────────────────────────
    "sales_order_headers": EntityDef(
        table_name="sales_order_headers",
        primary_key=["sales_order"],
        neo4j_label="SalesOrder",
        aliases=["order", "sales_order", "sales_order_header", "so"],
        fields={
            "sales_order": FieldDef(
                "sales_order",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["order_number", "sales_order_number", "order_id", "so_number"],
            ),
            "sales_order_type": FieldDef(
                "sales_order_type",
                "str",
                filterable=True,
                sortable=False,
                aggregatable=False,
                aliases=["order_type", "so_type"],
            ),
            "sold_to_party": FieldDef(
                "sold_to_party",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["customer_id", "sold_to", "customer_number_so"],
            ),
            "creation_date": FieldDef(
                "creation_date",
                "date",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["order_date", "created_date", "so_date"],
            ),
            "total_net_amount": FieldDef(
                "total_net_amount",
                "decimal",
                filterable=True,
                sortable=True,
                aggregatable=True,
                aliases=["order_amount", "order_total", "net_amount_so", "so_amount"],
            ),
            "transaction_currency": FieldDef(
                "transaction_currency",
                "str",
                filterable=True,
                sortable=False,
                aggregatable=False,
                aliases=["currency", "so_currency"],
            ),
            "sales_organization": FieldDef(
                "sales_organization",
                "str",
                filterable=True,
                sortable=False,
                aggregatable=False,
                aliases=["sales_org"],
            ),
            "distribution_channel": FieldDef(
                "distribution_channel",
                "str",
                filterable=True,
                sortable=False,
                aggregatable=False,
                aliases=["dist_channel"],
            ),
            "created_by_user": FieldDef(
                "created_by_user",
                "str",
                filterable=True,
                sortable=False,
                aggregatable=False,
                aliases=["created_by", "so_creator"],
            ),
            "updated_at": FieldDef(
                "updated_at",
                "date",
                filterable=False,
                sortable=True,
                aggregatable=False,
            ),
        },
    ),

    # ── 2. Sales Order Items ─────────────────────────────────────────────────
    "sales_order_items": EntityDef(
        table_name="sales_order_items",
        primary_key=["sales_order", "sales_order_item"],
        aliases=["order_item", "sales_order_item", "so_item"],
        fields={
            "sales_order": FieldDef(
                "sales_order",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["order_number"],
            ),
            "sales_order_item": FieldDef(
                "sales_order_item",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["item_number", "so_item_number"],
            ),
            "material": FieldDef(
                "material",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["product_id", "material_number", "sku", "product"],
            ),
            "requested_quantity": FieldDef(
                "requested_quantity",
                "decimal",
                filterable=True,
                sortable=True,
                aggregatable=True,
                aliases=["quantity", "ordered_qty", "req_qty"],
            ),
            "net_amount": FieldDef(
                "net_amount",
                "decimal",
                filterable=True,
                sortable=True,
                aggregatable=True,
                aliases=["item_amount", "line_amount", "net_amount_soi"],
            ),
            "transaction_currency": FieldDef(
                "transaction_currency",
                "str",
                filterable=True,
                sortable=False,
                aggregatable=False,
                aliases=["currency"],
            ),
            "delivery_status": FieldDef(
                "delivery_status",
                "str",
                filterable=True,
                sortable=False,
                aggregatable=False,
                aliases=["item_delivery_status"],
            ),
            "updated_at": FieldDef(
                "updated_at",
                "date",
                filterable=False,
                sortable=True,
                aggregatable=False,
            ),
        },
    ),

    # ── 3. Sales Order Schedule Lines ────────────────────────────────────────
    "sales_order_schedule_lines": EntityDef(
        table_name="sales_order_schedule_lines",
        primary_key=["sales_order", "sales_order_item", "schedule_line"],
        aliases=["schedule_line", "so_schedule", "delivery_schedule"],
        fields={
            "sales_order": FieldDef(
                "sales_order",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
            ),
            "sales_order_item": FieldDef(
                "sales_order_item",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
            ),
            "schedule_line": FieldDef(
                "schedule_line",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
            ),
            "confd_order_qty": FieldDef(
                "confd_order_qty",
                "decimal",
                filterable=True,
                sortable=True,
                aggregatable=True,
                aliases=["confirmed_qty", "schedule_qty"],
            ),
            "scheduled_delivery_date": FieldDef(
                "scheduled_delivery_date",
                "date",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["schedule_date", "delivery_schedule_date"],
            ),
            "updated_at": FieldDef(
                "updated_at",
                "date",
                filterable=False,
                sortable=True,
                aggregatable=False,
            ),
        },
    ),

    # ── 4. Outbound Delivery Headers ─────────────────────────────────────────
    "outbound_delivery_headers": EntityDef(
        table_name="outbound_delivery_headers",
        primary_key=["delivery_document"],
        neo4j_label="Delivery",
        aliases=["delivery", "outbound_delivery", "delivery_header", "shipment"],
        fields={
            "delivery_document": FieldDef(
                "delivery_document",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["delivery_number", "delivery_id", "delivery_doc"],
            ),
            "creation_date": FieldDef(
                "creation_date",
                "date",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["delivery_date", "shipped_date"],
            ),
            "goods_movement_status": FieldDef(
                "goods_movement_status",
                "str",
                filterable=True,
                sortable=False,
                aggregatable=False,
                aliases=["delivery_status", "shipment_status", "movement_status"],
            ),
            "shipping_point": FieldDef(
                "shipping_point",
                "str",
                filterable=True,
                sortable=False,
                aggregatable=False,
                aliases=["ship_point"],
            ),
            "sold_to_party": FieldDef(
                "sold_to_party",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["customer_id_delivery"],
            ),
            "updated_at": FieldDef(
                "updated_at",
                "date",
                filterable=False,
                sortable=True,
                aggregatable=False,
            ),
        },
    ),

    # ── 5. Outbound Delivery Items ───────────────────────────────────────────
    "outbound_delivery_items": EntityDef(
        table_name="outbound_delivery_items",
        primary_key=["delivery_document", "delivery_document_item"],
        aliases=["delivery_item", "outbound_delivery_item"],
        fields={
            "delivery_document": FieldDef(
                "delivery_document",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["delivery_number"],
            ),
            "delivery_document_item": FieldDef(
                "delivery_document_item",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["delivery_item_number"],
            ),
            "material": FieldDef(
                "material",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["product_id", "material_number", "product"],
            ),
            "reference_sd_document": FieldDef(
                "reference_sd_document",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["sales_order_ref", "reference_order"],
            ),
            "actual_delivery_qty": FieldDef(
                "actual_delivery_qty",
                "decimal",
                filterable=True,
                sortable=True,
                aggregatable=True,
                aliases=["delivered_qty", "actual_qty"],
            ),
            "updated_at": FieldDef(
                "updated_at",
                "date",
                filterable=False,
                sortable=True,
                aggregatable=False,
            ),
        },
    ),

    # ── 6. Billing Document Headers ──────────────────────────────────────────
    "billing_document_headers": EntityDef(
        table_name="billing_document_headers",
        primary_key=["billing_document"],
        neo4j_label="Invoice",
        aliases=["billing", "invoice", "billing_header", "bill"],
        fields={
            "billing_document": FieldDef(
                "billing_document",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["billing_number", "invoice_number", "billing_id"],
            ),
            "billing_document_type": FieldDef(
                "billing_document_type",
                "str",
                filterable=True,
                sortable=False,
                aggregatable=False,
                aliases=["invoice_type", "billing_type"],
            ),
            "billing_document_date": FieldDef(
                "billing_document_date",
                "date",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["billing_date", "invoice_date"],
            ),
            "sold_to_party": FieldDef(
                "sold_to_party",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["customer_id_billing"],
            ),
            "total_net_amount": FieldDef(
                "total_net_amount",
                "decimal",
                filterable=True,
                sortable=True,
                aggregatable=True,
                aliases=["invoice_amount", "billing_total"],
            ),
            "transaction_currency": FieldDef(
                "transaction_currency",
                "str",
                filterable=True,
                sortable=False,
                aggregatable=False,
                aliases=["billing_currency"],
            ),
            "accounting_document": FieldDef(
                "accounting_document",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["accounting_doc", "fi_document"],
            ),
            "updated_at": FieldDef(
                "updated_at",
                "date",
                filterable=False,
                sortable=True,
                aggregatable=False,
            ),
        },
    ),

    # ── 7. Billing Document Items ────────────────────────────────────────────
    "billing_document_items": EntityDef(
        table_name="billing_document_items",
        primary_key=["billing_document", "billing_document_item"],
        aliases=["billing_item", "invoice_item", "billing_line"],
        fields={
            "billing_document": FieldDef(
                "billing_document",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["billing_number"],
            ),
            "billing_document_item": FieldDef(
                "billing_document_item",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["billing_item_number"],
            ),
            "material": FieldDef(
                "material",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["product_id", "product_number", "product"],
            ),
            "billing_quantity": FieldDef(
                "billing_quantity",
                "decimal",
                filterable=True,
                sortable=True,
                aggregatable=True,
                aliases=["billed_qty", "invoice_qty"],
            ),
            "net_amount": FieldDef(
                "net_amount",
                "decimal",
                filterable=True,
                sortable=True,
                aggregatable=True,
                aliases=["billing_amount", "line_billing_amount", "item_billing_amount"],
            ),
            "transaction_currency": FieldDef(
                "transaction_currency",
                "str",
                filterable=True,
                sortable=False,
                aggregatable=False,
                aliases=["billing_item_currency"],
            ),
            "reference_sd_document": FieldDef(
                "reference_sd_document",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["sales_order_ref"],
            ),
            "updated_at": FieldDef(
                "updated_at",
                "date",
                filterable=False,
                sortable=True,
                aggregatable=False,
            ),
        },
    ),

    # ── 8. Billing Document Cancellation ─────────────────────────────────────
    "billing_document_cancellation": EntityDef(
        table_name="billing_document_cancellation",
        primary_key=["billing_document"],
        aliases=["billing_cancellation", "cancelled_billing", "invoice_cancellation"],
        fields={
            "billing_document": FieldDef(
                "billing_document",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["billing_number"],
            ),
            "cancelled_billing_document": FieldDef(
                "cancelled_billing_document",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["cancelled_invoice", "original_billing"],
            ),
            "cancellation_date": FieldDef(
                "cancellation_date",
                "date",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["cancel_date"],
            ),
            "updated_at": FieldDef(
                "updated_at",
                "date",
                filterable=False,
                sortable=True,
                aggregatable=False,
            ),
        },
    ),

    # ── 9. Journal Entry Items / Accounts Receivable ─────────────────────────
    "journal_entry_items_accounts_receivable": EntityDef(
        table_name="journal_entry_items_accounts_receivable",
        primary_key=["accounting_document", "fiscal_year", "accounting_document_item"],
        neo4j_label="JournalEntry",
        aliases=["journal_entry", "journal", "accounting_entry", "ar_entry", "je"],
        fields={
            "accounting_document": FieldDef(
                "accounting_document",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["accounting_doc", "fi_document"],
            ),
            "fiscal_year": FieldDef(
                "fiscal_year",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["fiscal_year_je"],
            ),
            "accounting_document_item": FieldDef(
                "accounting_document_item",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
            ),
            "posting_date": FieldDef(
                "posting_date",
                "date",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["journal_date", "je_posting_date"],
            ),
            "amount_in_document_currency": FieldDef(
                "amount_in_document_currency",
                "decimal",
                filterable=True,
                sortable=True,
                aggregatable=True,
                aliases=["journal_amount", "je_amount"],
            ),
            "currency": FieldDef(
                "currency",
                "str",
                filterable=True,
                sortable=False,
                aggregatable=False,
                aliases=["je_currency"],
            ),
            "clearing_accounting_document": FieldDef(
                "clearing_accounting_document",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["clearing_doc", "payment_clearing_doc"],
            ),
            "updated_at": FieldDef(
                "updated_at",
                "date",
                filterable=False,
                sortable=True,
                aggregatable=False,
            ),
        },
    ),

    # ── 10. Payment Accounts Receivable ──────────────────────────────────────
    "payment_accounts_receivable": EntityDef(
        table_name="payment_accounts_receivable",
        primary_key=["accounting_document", "fiscal_year"],
        neo4j_label="Payment",
        aliases=["payment", "ar_payment", "receipt"],
        fields={
            "accounting_document": FieldDef(
                "accounting_document",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["payment_doc", "payment_document"],
            ),
            "fiscal_year": FieldDef(
                "fiscal_year",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["payment_fiscal_year"],
            ),
            "posting_date": FieldDef(
                "posting_date",
                "date",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["payment_date", "payment_posting_date"],
            ),
            "amount_in_transaction_currency": FieldDef(
                "amount_in_transaction_currency",
                "decimal",
                filterable=True,
                sortable=True,
                aggregatable=True,
                aliases=["payment_amount", "paid_amount"],
            ),
            "transaction_currency": FieldDef(
                "transaction_currency",
                "str",
                filterable=True,
                sortable=False,
                aggregatable=False,
                aliases=["payment_currency"],
            ),
            "customer": FieldDef(
                "customer",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["paying_customer"],
            ),
            "updated_at": FieldDef(
                "updated_at",
                "date",
                filterable=False,
                sortable=True,
                aggregatable=False,
            ),
        },
    ),

    # ── 11. Business Partners ────────────────────────────────────────────────
    "business_partners": EntityDef(
        table_name="business_partners",
        primary_key=["business_partner"],
        neo4j_label="Customer",
        aliases=["customer", "business_partner", "bp", "client", "buyer"],
        fields={
            "business_partner": FieldDef(
                "business_partner",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["bp_id", "partner_id"],
            ),
            "customer": FieldDef(
                "customer",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["customer_number", "customer_id"],
            ),
            "business_partner_full_name": FieldDef(
                "business_partner_full_name",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["customer_name", "company_name", "bp_name"],
            ),
            "business_partner_category": FieldDef(
                "business_partner_category",
                "str",
                filterable=True,
                sortable=False,
                aggregatable=False,
                aliases=["customer_category", "partner_type"],
            ),
            "is_blocked": FieldDef(
                "is_blocked",
                "bool",
                filterable=True,
                sortable=False,
                aggregatable=False,
                aliases=["blocked", "customer_blocked"],
            ),
            "country": FieldDef(
                "country",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["customer_country"],
            ),
            "updated_at": FieldDef(
                "updated_at",
                "date",
                filterable=False,
                sortable=True,
                aggregatable=False,
            ),
        },
    ),

    # ── 12. Business Partner Address ─────────────────────────────────────────
    "business_partner_address": EntityDef(
        table_name="business_partner_address",
        primary_key=["business_partner"],
        aliases=["customer_address", "bp_address", "partner_address"],
        fields={
            "business_partner": FieldDef(
                "business_partner",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
            ),
            "city": FieldDef(
                "city",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["customer_city"],
            ),
            "country": FieldDef(
                "country",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["customer_country_addr"],
            ),
            "postal_code": FieldDef(
                "postal_code",
                "str",
                filterable=True,
                sortable=False,
                aggregatable=False,
            ),
            "street": FieldDef(
                "street",
                "str",
                filterable=True,
                sortable=False,
                aggregatable=False,
                aliases=["address_street"],
            ),
            "updated_at": FieldDef(
                "updated_at",
                "date",
                filterable=False,
                sortable=True,
                aggregatable=False,
            ),
        },
    ),

    # ── 13. Customer Company Assignment ──────────────────────────────────────
    "customer_company_assignment": EntityDef(
        table_name="customer_company_assignment",
        primary_key=["customer", "company_code"],
        aliases=["company_assignment", "customer_company"],
        fields={
            "customer": FieldDef(
                "customer",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["customer_number"],
            ),
            "company_code": FieldDef(
                "company_code",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["company"],
            ),
            "reconciliation_account": FieldDef(
                "reconciliation_account",
                "str",
                filterable=True,
                sortable=False,
                aggregatable=False,
            ),
            "updated_at": FieldDef(
                "updated_at",
                "date",
                filterable=False,
                sortable=True,
                aggregatable=False,
            ),
        },
    ),

    # ── 14. Customer Sales Area Assignments ──────────────────────────────────
    "customer_sales_area_assignments": EntityDef(
        table_name="customer_sales_area_assignments",
        primary_key=["customer", "sales_organization", "distribution_channel", "division"],
        aliases=["sales_area_assignment", "customer_sales_area"],
        fields={
            "customer": FieldDef(
                "customer",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
            ),
            "sales_organization": FieldDef(
                "sales_organization",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["sales_org"],
            ),
            "distribution_channel": FieldDef(
                "distribution_channel",
                "str",
                filterable=True,
                sortable=False,
                aggregatable=False,
            ),
            "division": FieldDef(
                "division",
                "str",
                filterable=True,
                sortable=False,
                aggregatable=False,
            ),
            "updated_at": FieldDef(
                "updated_at",
                "date",
                filterable=False,
                sortable=True,
                aggregatable=False,
            ),
        },
    ),

    # ── 15. Products ─────────────────────────────────────────────────────────
    "products": EntityDef(
        table_name="products",
        primary_key=["product"],
        neo4j_label="Product",
        aliases=["product", "material", "sku", "item"],
        fields={
            "product": FieldDef(
                "product",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["product_id", "material_number", "product_code"],
            ),
            "product_type": FieldDef(
                "product_type",
                "str",
                filterable=True,
                sortable=False,
                aggregatable=False,
                aliases=["material_type"],
            ),
            "product_group": FieldDef(
                "product_group",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["product_category", "material_group"],
            ),
            "base_unit": FieldDef(
                "base_unit",
                "str",
                filterable=True,
                sortable=False,
                aggregatable=False,
                aliases=["unit_of_measure", "base_uom"],
            ),
            "gross_weight": FieldDef(
                "gross_weight",
                "decimal",
                filterable=True,
                sortable=True,
                aggregatable=True,
                aliases=["weight"],
            ),
            "net_weight": FieldDef(
                "net_weight",
                "decimal",
                filterable=True,
                sortable=True,
                aggregatable=True,
            ),
            "updated_at": FieldDef(
                "updated_at",
                "date",
                filterable=False,
                sortable=True,
                aggregatable=False,
            ),
        },
    ),

    # ── 16. Product Description ───────────────────────────────────────────────
    "product_description": EntityDef(
        table_name="product_description",
        primary_key=["product", "language"],
        aliases=["product_name", "material_description"],
        fields={
            "product": FieldDef(
                "product",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
            ),
            "language": FieldDef(
                "language",
                "str",
                filterable=True,
                sortable=False,
                aggregatable=False,
            ),
            "product_description": FieldDef(
                "product_description",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["product_name", "material_description", "product_desc"],
            ),
            "updated_at": FieldDef(
                "updated_at",
                "date",
                filterable=False,
                sortable=True,
                aggregatable=False,
            ),
        },
    ),

    # ── 17. Product Plants ────────────────────────────────────────────────────
    "product_plants": EntityDef(
        table_name="product_plants",
        primary_key=["product", "plant"],
        aliases=["material_plant", "product_plant"],
        fields={
            "product": FieldDef(
                "product",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
            ),
            "plant": FieldDef(
                "plant",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["plant_code"],
            ),
            "updated_at": FieldDef(
                "updated_at",
                "date",
                filterable=False,
                sortable=True,
                aggregatable=False,
            ),
        },
    ),

    # ── 18. Product Storage Locations ─────────────────────────────────────────
    "product_storage_locations": EntityDef(
        table_name="product_storage_locations",
        primary_key=["product", "plant", "storage_location"],
        aliases=["storage_location", "product_storage"],
        fields={
            "product": FieldDef(
                "product",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
            ),
            "plant": FieldDef(
                "plant",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
            ),
            "storage_location": FieldDef(
                "storage_location",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["warehouse_location"],
            ),
            "updated_at": FieldDef(
                "updated_at",
                "date",
                filterable=False,
                sortable=True,
                aggregatable=False,
            ),
        },
    ),

    # ── 19. Plant ─────────────────────────────────────────────────────────────
    "plant": EntityDef(
        table_name="plant",
        primary_key=["plant"],
        neo4j_label="Plant",
        aliases=["plant", "factory", "warehouse", "distribution_center"],
        fields={
            "plant": FieldDef(
                "plant",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["plant_code", "plant_id"],
            ),
            "plant_name": FieldDef(
                "plant_name",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["factory_name", "plant_description"],
            ),
            "sales_organization": FieldDef(
                "sales_organization",
                "str",
                filterable=True,
                sortable=True,
                aggregatable=False,
                aliases=["plant_sales_org"],
            ),
            "updated_at": FieldDef(
                "updated_at",
                "date",
                filterable=False,
                sortable=True,
                aggregatable=False,
            ),
        },
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# JOIN PATH GRAPH
# ─────────────────────────────────────────────────────────────────────────────

JOIN_EDGES: list[JoinEdge] = [
    # ── Hard FK (header ↔ items) ─────────────────────────────────────────────
    JoinEdge(
        "sales_order_headers",
        "sales_order",
        "sales_order_items",
        "sales_order",
        "inner",
        preferred=True,
    ),
    JoinEdge(
        "sales_order_items",
        "sales_order",
        "sales_order_schedule_lines",
        "sales_order",
        "inner",
    ),
    JoinEdge(
        "outbound_delivery_headers",
        "delivery_document",
        "outbound_delivery_items",
        "delivery_document",
        "inner",
        preferred=True,
    ),
    JoinEdge(
        "billing_document_headers",
        "billing_document",
        "billing_document_items",
        "billing_document",
        "inner",
        preferred=True,
    ),
    JoinEdge("products", "product", "product_description", "product", "inner"),
    JoinEdge("products", "product", "product_plants", "product", "inner"),
    JoinEdge("products", "product", "product_storage_locations", "product", "inner"),
    JoinEdge("product_plants", "plant", "plant", "plant", "inner"),

    # ── Soft lookup (cross-document, SAP allows orphans) ─────────────────────
    JoinEdge(
        "billing_document_items",
        "reference_sd_document",
        "sales_order_headers",
        "sales_order",
        "left",
    ),
    JoinEdge(
        "outbound_delivery_items",
        "reference_sd_document",
        "sales_order_items",
        "sales_order",
        "left",
    ),
    JoinEdge(
        "billing_document_headers",
        "sold_to_party",
        "business_partners",
        "customer",
        "left",
        preferred=True,
    ),
    JoinEdge(
        "billing_document_headers",
        "accounting_document",
        "journal_entry_items_accounts_receivable",
        "accounting_document",
        "left",
    ),
    JoinEdge(
        "sales_order_headers",
        "sold_to_party",
        "business_partners",
        "customer",
        "left",
        preferred=True,
    ),
    JoinEdge(
        "journal_entry_items_accounts_receivable",
        "clearing_accounting_document",
        "payment_accounts_receivable",
        "accounting_document",
        "left",
    ),
    JoinEdge(
        "payment_accounts_receivable",
        "customer",
        "business_partners",
        "customer",
        "left",
    ),
    JoinEdge(
        "business_partners",
        "business_partner",
        "business_partner_address",
        "business_partner",
        "left",
    ),
    JoinEdge(
        "business_partners",
        "customer",
        "customer_company_assignment",
        "customer",
        "left",
    ),
    JoinEdge(
        "business_partners",
        "customer",
        "customer_sales_area_assignments",
        "customer",
        "left",
    ),
    JoinEdge(
        "billing_document_headers",
        "billing_document",
        "billing_document_cancellation",
        "cancelled_billing_document",
        "left",
    ),
    JoinEdge("sales_order_items", "material", "products", "product", "left"),
    JoinEdge("billing_document_items", "material", "products", "product", "left"),
]

# ─────────────────────────────────────────────────────────────────────────────
# ALIAS → (table, column) flat lookup  (built at import time)
# ─────────────────────────────────────────────────────────────────────────────

# Entity-level aliases:  alias_str → table_name
ENTITY_ALIAS_MAP: dict[str, str] = {}
for _entity_name, _ent in ENTITY_CATALOG.items():
    ENTITY_ALIAS_MAP[_ent.table_name.lower()] = _entity_name
    for _alias in _ent.aliases:
        ENTITY_ALIAS_MAP[_alias.lower()] = _entity_name

# Field-level aliases:  alias_str → (table_name, column_name)
FIELD_ALIAS_MAP: dict[str, tuple[str, str]] = {}
for _entity_name, _ent in ENTITY_CATALOG.items():
    for _col_name, _fdef in _ent.fields.items():
        FIELD_ALIAS_MAP[_col_name.lower()] = (_entity_name, _col_name)
        for _alias in _fdef.aliases:
            FIELD_ALIAS_MAP[_alias.lower()] = (_entity_name, _col_name)

