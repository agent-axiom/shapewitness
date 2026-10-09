"""Select real JSONL rows that witness observed structural features."""

from .core import Pin, Limits, Result, ShapeWitnessError, Witness, select
from .comparison import compare_reports, read_report
from ._version import __version__

__all__ = ["Pin", "Limits", "Result", "ShapeWitnessError", "Witness", "select", "compare_reports", "read_report"]
