"""Shared cross-project package: domain types, audit writer, DQ helpers, LLM seam.

The ONLY code shared between TerraSignal and LedgerLens. Projects never import
from each other; cross-pollination goes through here or doesn't happen.
"""
