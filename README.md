# VeriData DSL

**VeriData** is a declarative Domain-Specific Language (`.vd`) designed for expressing dataset schemas, conditional invariants, statistical outlier checks, and `warn` / `halt` failure policies cleanly and deterministically.

Built for **Syntax Summit** on **Devpost**.

## Quickstart

Requires Python 3.10+ with `pandas` and `numpy` installed (`pip install pandas numpy`).

```bash
python -m veridata.main check examples/orders.vd
python -m veridata.main compile examples/orders.vd -o run_orders_audit.py
python run_orders_audit.py examples/orders_dirty.csv
python -m unittest discover -s tests
