"""
FOLD - Fractal Optimized Layered Data

Store any file inside a video and get it back byte-for-byte.
"""

__version__ = "2.0.0"

from .core.encoder import store
from .core.decoder import retrieve, retrieve_file

__all__ = ["store", "retrieve", "retrieve_file"]
