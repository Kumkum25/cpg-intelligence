"""All configurable paths/dates live here, read from environment variables
with sensible defaults — nothing in the app hardcodes a file path.
"""
from __future__ import annotations

import os

import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_DATA_DIR = os.environ.get("NEXUS_DATA_DIR", os.path.join(BASE_DIR, "nexus_cpg_sample_data_v1"))
UPLOAD_DIR = os.environ.get("NEXUS_UPLOAD_DIR", os.path.join(BASE_DIR, "uploaded_data"))
OUTPUT_DIR = os.environ.get("NEXUS_OUTPUT_DIR", os.path.join(BASE_DIR, "output"))
DEFAULT_ASOF = pd.Timestamp(os.environ.get("NEXUS_ASOF", "2026-11-20"))

REQUIRED_RAW_FILES = [
    "pos_sales_transactions.csv", "product_master.csv", "location_master.csv",
    "ranging.csv", "store_calendar_feed_log.csv", "inventory_daily.csv",
    "sku_economics.csv", "supplier_constraints.csv", "inventory_valuation_weekly.csv",
]

REQUIRED_COLUMNS = {
    "pos_sales_transactions.csv": [
        "tenant_id", "source_system", "ingest_batch_id", "store_id", "transaction_id", "line_no",
        "txn_datetime", "sku_code", "qty", "uom", "unit_price", "line_amount", "txn_type",
        "line_status", "orig_transaction_id",
    ],
    "product_master.csv": ["sku_code", "gtin", "description", "brand", "category", "base_uom", "eaches_per_case", "launch_date", "delist_date"],
    "location_master.csv": ["store_id", "store_name", "state", "zip", "channel", "timezone", "open_date"],
    "ranging.csv": ["store_id", "sku_code", "ranged_from", "ranged_to"],
    "store_calendar_feed_log.csv": ["store_id", "date", "store_open", "pos_feed_received", "feed_complete"],
    "inventory_daily.csv": ["store_id", "sku_code", "inventory_date", "on_hand_eod_ea", "oos_eod_flag"],
    "sku_economics.csv": ["channel_id", "sku_code", "effective_from", "effective_to", "net_price_per_ea", "cogs_per_ea"],
    "supplier_constraints.csv": ["sku_code", "supplier_id", "ship_to_location_id", "effective_from", "effective_to", "moq_qty", "moq_uom", "eaches_per_uom", "unit_purchase_cost_per_ea", "lead_time_days", "shelf_life_days"],
    "inventory_valuation_weekly.csv": ["store_id", "sku_code", "inventory_date", "on_hand_ea", "inventory_value_at_cost", "snapshot_status"],
}
