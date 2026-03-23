"""GraphIQ — Alembic migration: create all 19 O2C tables + audit schema.

Run: alembic upgrade head
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Audit schema ──────────────────────────────────────────────────────────
    op.execute("CREATE SCHEMA IF NOT EXISTS audit")
    op.create_table(
        "request_logs",
        sa.Column("request_id", sa.String(36), primary_key=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_question", sa.Text, nullable=False),
        sa.Column("llm_provider_used", sa.String(50)),
        sa.Column("intent_raw_json", sa.Text),
        sa.Column("intent_validated", sa.Text),
        sa.Column("corrections_applied", sa.Text),
        sa.Column("guardrail_result", sa.String(20)),
        sa.Column("guardrail_detail", sa.Text),
        sa.Column("query_generated", sa.Text),
        sa.Column("query_params", sa.Text),
        sa.Column("store_used", sa.String(10)),
        sa.Column("query_ms", sa.Integer),
        sa.Column("result_row_count", sa.Integer),
        sa.Column("result_truncated", sa.Boolean),
        sa.Column("prose_answer", sa.Text),
        sa.Column("total_latency_ms", sa.Integer),
        sa.Column("error_type", sa.String(50)),
        sa.Column("error_detail", sa.Text),
        schema="audit",
    )
    op.create_index("idx_audit_timestamp", "request_logs", ["timestamp"], schema="audit")

    # ── Helper: add updated_at column ─────────────────────────────────────────
    def _updated_at() -> sa.Column:
        return sa.Column("updated_at", sa.DateTime(timezone=True),
                         server_default=sa.text("NOW()"), nullable=False)

    # ── 1. sales_order_headers ────────────────────────────────────────────────
    op.create_table(
        "sales_order_headers",
        sa.Column("sales_order", sa.String(10), primary_key=True),
        sa.Column("sales_order_type", sa.String(10)),
        sa.Column("sold_to_party", sa.String(10)),
        sa.Column("creation_date", sa.Date),
        sa.Column("total_net_amount", sa.Numeric(18, 2)),
        sa.Column("transaction_currency", sa.String(5)),
        sa.Column("sales_organization", sa.String(10)),
        sa.Column("distribution_channel", sa.String(5)),
        sa.Column("created_by_user", sa.String(50)),
        _updated_at(),
    )
    op.create_index("idx_soh_sold_party_date", "sales_order_headers", ["sold_to_party", "creation_date"])
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at() RETURNS TRIGGER AS $$
        BEGIN NEW.updated_at = NOW(); RETURN NEW; END; $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trg_soh_updated BEFORE UPDATE ON sales_order_headers
        FOR EACH ROW EXECUTE FUNCTION update_updated_at()
    """)

    # ── 2. sales_order_items ──────────────────────────────────────────────────
    op.create_table(
        "sales_order_items",
        sa.Column("sales_order", sa.String(10), nullable=False),
        sa.Column("sales_order_item", sa.String(10), nullable=False),
        sa.Column("material", sa.String(40)),
        sa.Column("requested_quantity", sa.Numeric(13, 3)),
        sa.Column("net_amount", sa.Numeric(18, 2)),
        sa.Column("transaction_currency", sa.String(5)),
        sa.Column("delivery_status", sa.String(5)),
        _updated_at(),
        sa.PrimaryKeyConstraint("sales_order", "sales_order_item"),
        sa.ForeignKeyConstraint(["sales_order"], ["sales_order_headers.sales_order"]),
    )
    op.create_index("idx_soi_material_amount", "sales_order_items", ["material", "net_amount"])

    # ── 3. sales_order_schedule_lines ─────────────────────────────────────────
    op.create_table(
        "sales_order_schedule_lines",
        sa.Column("sales_order", sa.String(10), nullable=False),
        sa.Column("sales_order_item", sa.String(10), nullable=False),
        sa.Column("schedule_line", sa.String(10), nullable=False),
        sa.Column("confd_order_qty", sa.Numeric(13, 3)),
        sa.Column("scheduled_delivery_date", sa.Date),
        _updated_at(),
        sa.PrimaryKeyConstraint("sales_order", "sales_order_item", "schedule_line"),
        sa.ForeignKeyConstraint(
            ["sales_order", "sales_order_item"],
            ["sales_order_items.sales_order", "sales_order_items.sales_order_item"],
        ),
    )

    # ── 4. outbound_delivery_headers ──────────────────────────────────────────
    op.create_table(
        "outbound_delivery_headers",
        sa.Column("delivery_document", sa.String(10), primary_key=True),
        sa.Column("creation_date", sa.Date),
        sa.Column("goods_movement_status", sa.String(5)),
        sa.Column("shipping_point", sa.String(10)),
        sa.Column("sold_to_party", sa.String(10)),
        _updated_at(),
    )

    # ── 5. outbound_delivery_items ────────────────────────────────────────────
    op.create_table(
        "outbound_delivery_items",
        sa.Column("delivery_document", sa.String(10), nullable=False),
        sa.Column("delivery_document_item", sa.String(10), nullable=False),
        sa.Column("material", sa.String(40)),
        sa.Column("reference_sd_document", sa.String(10)),
        sa.Column("actual_delivery_qty", sa.Numeric(13, 3)),
        _updated_at(),
        sa.PrimaryKeyConstraint("delivery_document", "delivery_document_item"),
        sa.ForeignKeyConstraint(["delivery_document"], ["outbound_delivery_headers.delivery_document"]),
    )
    op.create_index("idx_odi_ref_sd", "outbound_delivery_items", ["reference_sd_document"])

    # ── 6. billing_document_headers ───────────────────────────────────────────
    op.create_table(
        "billing_document_headers",
        sa.Column("billing_document", sa.String(10), primary_key=True),
        sa.Column("billing_document_type", sa.String(10)),
        sa.Column("billing_document_date", sa.Date),
        sa.Column("sold_to_party", sa.String(10)),
        sa.Column("total_net_amount", sa.Numeric(18, 2)),
        sa.Column("transaction_currency", sa.String(5)),
        sa.Column("accounting_document", sa.String(10)),
        _updated_at(),
    )
    op.create_index("idx_bdh_sold_party_date", "billing_document_headers", ["sold_to_party", "billing_document_date"])
    op.create_index("idx_bdh_accounting", "billing_document_headers", ["accounting_document"])

    # ── 7. billing_document_items ─────────────────────────────────────────────
    op.create_table(
        "billing_document_items",
        sa.Column("billing_document", sa.String(10), nullable=False),
        sa.Column("billing_document_item", sa.String(10), nullable=False),
        sa.Column("material", sa.String(40)),
        sa.Column("billing_quantity", sa.Numeric(13, 3)),
        sa.Column("net_amount", sa.Numeric(18, 2)),
        sa.Column("transaction_currency", sa.String(5)),
        sa.Column("reference_sd_document", sa.String(10)),
        _updated_at(),
        sa.PrimaryKeyConstraint("billing_document", "billing_document_item"),
        sa.ForeignKeyConstraint(["billing_document"], ["billing_document_headers.billing_document"]),
    )
    op.create_index("idx_bdi_material_amount", "billing_document_items", ["material", "net_amount"])
    op.create_index("idx_bdi_ref_sd", "billing_document_items", ["reference_sd_document"])

    # ── 8. billing_document_cancellation ──────────────────────────────────────
    op.create_table(
        "billing_document_cancellation",
        sa.Column("billing_document", sa.String(10), primary_key=True),
        sa.Column("cancelled_billing_document", sa.String(10)),
        sa.Column("cancellation_date", sa.Date),
        _updated_at(),
    )

    # ── 9. journal_entry_items_accounts_receivable ────────────────────────────
    op.create_table(
        "journal_entry_items_accounts_receivable",
        sa.Column("accounting_document", sa.String(10), nullable=False),
        sa.Column("fiscal_year", sa.String(4), nullable=False),
        sa.Column("accounting_document_item", sa.String(10), nullable=False),
        sa.Column("posting_date", sa.Date),
        sa.Column("amount_in_document_currency", sa.Numeric(18, 2)),
        sa.Column("currency", sa.String(5)),
        sa.Column("clearing_accounting_document", sa.String(10)),
        _updated_at(),
        sa.PrimaryKeyConstraint("accounting_document", "fiscal_year", "accounting_document_item"),
    )
    op.create_index("idx_jeiar_clearing", "journal_entry_items_accounts_receivable", ["clearing_accounting_document"])

    # ── 10. payment_accounts_receivable ───────────────────────────────────────
    op.create_table(
        "payment_accounts_receivable",
        sa.Column("accounting_document", sa.String(10), nullable=False),
        sa.Column("fiscal_year", sa.String(4), nullable=False),
        sa.Column("posting_date", sa.Date),
        sa.Column("amount_in_transaction_currency", sa.Numeric(18, 2)),
        sa.Column("transaction_currency", sa.String(5)),
        sa.Column("customer", sa.String(10)),
        _updated_at(),
        sa.PrimaryKeyConstraint("accounting_document", "fiscal_year"),
    )

    # ── 11. business_partners ─────────────────────────────────────────────────
    op.create_table(
        "business_partners",
        sa.Column("business_partner", sa.String(10), primary_key=True),
        sa.Column("customer", sa.String(10)),
        sa.Column("business_partner_full_name", sa.String(100)),
        sa.Column("business_partner_category", sa.String(5)),
        sa.Column("is_blocked", sa.Boolean, server_default="false"),
        sa.Column("country", sa.String(5)),
        _updated_at(),
    )

    # ── 12. business_partner_address ─────────────────────────────────────────
    op.create_table(
        "business_partner_address",
        sa.Column("business_partner", sa.String(10), primary_key=True),
        sa.Column("city", sa.String(100)),
        sa.Column("country", sa.String(5)),
        sa.Column("postal_code", sa.String(20)),
        sa.Column("street", sa.String(200)),
        _updated_at(),
    )

    # ── 13. customer_company_assignment ───────────────────────────────────────
    op.create_table(
        "customer_company_assignment",
        sa.Column("customer", sa.String(10), nullable=False),
        sa.Column("company_code", sa.String(10), nullable=False),
        sa.Column("reconciliation_account", sa.String(10)),
        _updated_at(),
        sa.PrimaryKeyConstraint("customer", "company_code"),
    )

    # ── 14. customer_sales_area_assignments ───────────────────────────────────
    op.create_table(
        "customer_sales_area_assignments",
        sa.Column("customer", sa.String(10), nullable=False),
        sa.Column("sales_organization", sa.String(10), nullable=False),
        sa.Column("distribution_channel", sa.String(5), nullable=False),
        sa.Column("division", sa.String(5), nullable=False),
        _updated_at(),
        sa.PrimaryKeyConstraint("customer", "sales_organization", "distribution_channel", "division"),
    )

    # ── 15. products ──────────────────────────────────────────────────────────
    op.create_table(
        "products",
        sa.Column("product", sa.String(40), primary_key=True),
        sa.Column("product_type", sa.String(10)),
        sa.Column("product_group", sa.String(20)),
        sa.Column("base_unit", sa.String(5)),
        sa.Column("gross_weight", sa.Numeric(13, 3)),
        sa.Column("net_weight", sa.Numeric(13, 3)),
        _updated_at(),
    )

    # ── 16. product_description ───────────────────────────────────────────────
    op.create_table(
        "product_description",
        sa.Column("product", sa.String(40), nullable=False),
        sa.Column("language", sa.String(5), nullable=False, server_default="EN"),
        sa.Column("product_description", sa.String(200)),
        _updated_at(),
        sa.PrimaryKeyConstraint("product", "language"),
        sa.ForeignKeyConstraint(["product"], ["products.product"]),
    )

    # ── 17. product_plants ────────────────────────────────────────────────────
    op.create_table(
        "product_plants",
        sa.Column("product", sa.String(40), nullable=False),
        sa.Column("plant", sa.String(10), nullable=False),
        _updated_at(),
        sa.PrimaryKeyConstraint("product", "plant"),
        sa.ForeignKeyConstraint(["product"], ["products.product"]),
    )

    # ── 18. product_storage_locations ─────────────────────────────────────────
    op.create_table(
        "product_storage_locations",
        sa.Column("product", sa.String(40), nullable=False),
        sa.Column("plant", sa.String(10), nullable=False),
        sa.Column("storage_location", sa.String(10), nullable=False),
        _updated_at(),
        sa.PrimaryKeyConstraint("product", "plant", "storage_location"),
        sa.ForeignKeyConstraint(["product"], ["products.product"]),
    )

    # ── 19. plant ─────────────────────────────────────────────────────────────
    op.create_table(
        "plant",
        sa.Column("plant", sa.String(10), primary_key=True),
        sa.Column("plant_name", sa.String(100)),
        sa.Column("sales_organization", sa.String(10)),
        _updated_at(),
    )


def downgrade() -> None:
    tables = [
        "sales_order_schedule_lines", "sales_order_items", "sales_order_headers",
        "outbound_delivery_items", "outbound_delivery_headers",
        "billing_document_items", "billing_document_headers", "billing_document_cancellation",
        "journal_entry_items_accounts_receivable", "payment_accounts_receivable",
        "business_partner_address", "customer_company_assignment",
        "customer_sales_area_assignments", "business_partners",
        "product_description", "product_plants", "product_storage_locations",
        "products", "plant",
    ]
    for t in tables:
        op.drop_table(t)
    op.drop_table("request_logs", schema="audit")
    op.execute("DROP SCHEMA IF EXISTS audit")
