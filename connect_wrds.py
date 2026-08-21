"""Minimal WRDS connectivity check. Run: .venv/bin/python connect_wrds.py"""

import wrds

conn = wrds.Connection(wrds_username="cbruce1")
print(conn.raw_sql("SELECT 1 AS ok"))
conn.close()
print("connection OK")
