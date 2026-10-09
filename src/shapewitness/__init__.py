"""Select real JSONL rows that witness observed structural features."""

from .core import Limits, Result, ShapeWitnessError, Witness, select
from ._version import __version__

__all__ = ["Limits", "Result", "ShapeWitnessError", "Witness", "select"]
