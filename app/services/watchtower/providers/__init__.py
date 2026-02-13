"""
Watchtower data providers.
Each provider fetches data from a specific source (FDA RSS, etc.).
"""
from .base import WatchtowerProvider, WatchItem
from .fda_recalls import FDARecallsProvider
from .fda_warning_letters import FDAWarningLettersProvider
from .fda_shortages import FDAShortagesProvider

__all__ = [
    "WatchtowerProvider", 
    "WatchItem", 
    "FDARecallsProvider",
    "FDAWarningLettersProvider",
    "FDAShortagesProvider"
]
