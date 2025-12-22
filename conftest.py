"""Pytest configuration and fixtures for qBittorrent plugin tests.

This module provides mock implementations of qBittorrent's search engine
infrastructure (nova2, novaprinter) that are normally only available when
running within qBittorrent's Python environment.
"""

import sys
from abc import ABC, abstractmethod
from enum import Enum
from typing import TypedDict


class SearchResults(TypedDict):
    """Search result structure expected by qBittorrent."""
    link: str
    name: str
    size: float | int | str
    seeds: int
    leech: int
    engine_url: str
    desc_link: str
    pub_date: int


class Category(Enum):
    """Search categories supported by qBittorrent."""
    all = "all"
    movies = "movies"
    tv = "tv"
    music = "music"
    games = "games"
    anime = "anime"
    software = "software"
    books = "books"


class Engine(ABC):
    """Base class for search engines."""
    name: str
    url: str
    supported_categories: dict[str, str]

    @abstractmethod
    def search(self, query: str, category: str = "all") -> None:
        """Search for torrents."""
        pass


# Create mock novaprinter module
class MockNovaPrinter:
    """Mock novaprinter module."""
    SearchResults = SearchResults

    @staticmethod
    def prettyPrinter(dictionary: SearchResults) -> None:  # noqa: ARG004
        """Print a search result (no-op in tests)."""
        del dictionary  # unused in mock

    @staticmethod
    def anySizeToBytes(size_string: float | int | str) -> int:  # noqa: ARG004
        """Convert size string to bytes."""
        del size_string  # unused in mock
        return 0


# Create mock nova2 module
class MockNova2:
    """Mock nova2 module."""
    Category = Category
    Engine = Engine


# Install mock modules before any imports
nova2_mock = type(sys)("nova2")
nova2_mock.Category = Category  # type: ignore[attr-defined]
nova2_mock.Engine = Engine  # type: ignore[attr-defined]
sys.modules["nova2"] = nova2_mock

novaprinter_mock = type(sys)("novaprinter")
novaprinter_mock.SearchResults = SearchResults  # type: ignore[attr-defined]
novaprinter_mock.prettyPrinter = MockNovaPrinter.prettyPrinter  # type: ignore[attr-defined]
novaprinter_mock.anySizeToBytes = MockNovaPrinter.anySizeToBytes  # type: ignore[attr-defined]
sys.modules["novaprinter"] = novaprinter_mock
