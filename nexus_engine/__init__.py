"""Nexus CPG Forecasting Engine — Demand Profiling (V1) + Economic Profiling (V1.1).

Package layout:
    ingest.py     — load raw CSVs from the sample-data directory
    clean.py      — dedupe / void-exclusion / returns split / CS->EA / daily aggregation
    calendar.py   — valid-day logic (store open, feed outage, ranging)
    classify.py   — ADI/CV2 demand classification, confidence, trend, seasonality
    economics.py  — price/COGS join, GM%, supplier MOQ/coverage days, GMROI
    pipeline.py   — orchestrates the above into the final profile tables
    validate.py   — checks pipeline output against the answer_key/ fixtures
"""
