"""
Quantum data encoding package.

This module provides implementations for various quantum data encoding schemes,
including amplitude encoding for continuous data, basis encoding for discrete data,
and a quantum RAM implementation.
"""

from .amplitude_encoder import AmplitudeEncoder
from .basis_encoder import BasisEncoder
from .qram import QRAM

__all__ = ['AmplitudeEncoder', 'BasisEncoder', 'QRAM']