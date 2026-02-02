# VERSION: 1.05
# AUTHORS: PlayDay

# MIT License
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

# CHANGELOG:
# 1.00 - Initial release
# 1.01 - Refactored ConfigJson to reference Config class defaults instead of hardcoded values
# 1.02 - Fixed size parsing: now returns bytes (int) instead of string for qBittorrent compatibility
# 1.03 - Added FileHandler for logging to mazepa_to.log file
# 1.04 - Added browser headers (User-Agent, etc.) to fix 403 Forbidden errors; better response handling; use logger.exception() for full tracebacks
# 1.05 - Extracted tests to dedicated test files; code formatting with ruff

# INSTALLATION:
# 1. Install the plugin: https://github.com/qbittorrent/search-plugins/wiki/Install-search-plugins
#
# 2. On first search, a config file (mazepa_to.json) will be created automatically.
#    Edit it with your mazepa.to credentials:
#    {
#        "username": "your_username",
#        "password": "your_password",
#        "cache_login_cookies": true,
#        "log_level": "WARNING"
#    }
#
#    Config file location:
#    - Linux:   ~/.local/share/qBittorrent/nova3/engines/mazepa_to.json
#    - macOS:   ~/Library/Application Support/qBittorrent/nova3/engines/mazepa_to.json
#    - Windows: %LOCALAPPDATA%\qBittorrent\nova3\engines\mazepa_to.json
#
# 3. Optional settings:
#    - cache_login_cookies: true (default) - saves session cookies to avoid re-login
#    - log_level: DEBUG, INFO, WARNING (default), ERROR, CRITICAL
#
# REQUIREMENTS:
# - A valid mazepa.to account (registration required)
# - qBittorrent 4.1.0+ with Search functionality enabled

import gzip
import json
import logging
import os
import re
import sys
import tempfile
import zlib
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import IntEnum
from html.parser import HTMLParser
from http.client import HTTPResponse
from http.cookiejar import LoadError, LWPCookieJar
from pathlib import Path
from typing import Literal, Optional, Self, TypedDict, cast, get_args
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlencode, urlparse
from urllib.request import HTTPCookieProcessor, OpenerDirector, Request, build_opener

from nova2 import Category, Engine  # pyright: ignore[reportMissingModuleSource]
from novaprinter import SearchResults, prettyPrinter  # pyright: ignore[reportMissingModuleSource]

logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
logger = logging.getLogger(__name__)


__all__ = ["mazepa_to"]


class SubForum(TypedDict):
    forum_id: int
    subforums: dict[str, int]


class CategoryEntry(TypedDict):
    category_id: int
    forums: dict[str, SubForum]


# fmt: off
FORUM_MAP: dict[str, CategoryEntry] = {
    "Український контент": {
        "category_id": 4,
        "forums": {
            "": {
                "forum_id": -1,
                "subforums": {
                    "Українські фільми HD, UHD": 37,
                    "Українські фільми SD": 7,
                    "Українські серіали HD, UHD": 38,
                    "Українські серіали SD": 8,
                    "Українські мультфільми HD, UHD": 35,
                    "Українські мультфільми SD": 5,
                    "Українські мультсеріали HD, UHD": 36,
                    "Українські мультсеріали SD": 6,
                    "Українські документальні HD, UHD": 39,
                    "Українські документальні SD": 9,
                },
            },
        },
    },
    "Озвучений контент": {
        "category_id": 5,
        "forums": {
            "": {
                "forum_id": -1,
                "subforums": {
                    "Новинки фільмів UHD, HD": 175,
                    "Фільми UHD": 147,
                    "Фільми HD": 12,
                    "Фільми SD": 13,
                    "Субтитровані фільми": 174,
                    "Серіали UHD": 152,
                    "Серіали HD": 44,
                    "Серіали SD": 14,
                    "Мультфільми UHD": 155,
                    "Мультфільми HD": 41,
                    "Мультфільми SD": 10,
                    "Мультсеріали UHD, HD": 43,
                    "Мультсеріали SD": 11,
                },
            },
            "Аніме": {
                "forum_id": 16,
                "subforums": {
                    "Документальне UHD": 157,
                    "Документальне HD": 42,
                    "Документальне SD": 15,
                },
            },
        },
    },
    "Спорт": {
        "category_id": 6,
        "forums": {
            "": {
                "forum_id": -1,
                "subforums": {
                    "Формула 1 Сезон 2025": 20,
                    "Формула 1 Сезон 2022-2024": 167,
                    "Формула 1 Сезони 2017-2021": 79,
                    "Формула 1 Сезони 2007-2016": 21,
                    "Формула 1 Сезони до 2006": 75,
                },
            },
            "Автоспорт": {
                "forum_id": 77,
                "subforums": {
                    "Чемпіонат та кубок України": 47,
                    "Єврокубки": 46,
                    "Чемпіонат Світу": 48,
                    "Євро 2024": 182,
                    "Чемпіонат Європи": 49,
                    "Закордонні чемпіонати": 53,
                },
            },
            "Бокс, реслінг, бойові мистецтва": {
                "forum_id": 19,
                "subforums": {},
            },
        },
    },
    "Телевізійні передачі": {
        "category_id": 8,
        "forums": {
            "Концерти, відеокліпи": {
                "forum_id": 29,
                "subforums": {},
            },
            "Теле-Шоу": {
                "forum_id": 30,
                "subforums": {},
            },
        },
    },
    "Музика": {
        "category_id": 10,
        "forums": {
            "": {
                "forum_id": -1,
                "subforums": {
                    "Рок": 65,
                    "Поп, Диско": 63,
                    "Фольк, Етно, Народна, Бардівська": 66,
                    "Реп": 64,
                    "Електронна": 67,
                    "Джаз, Блюз": 61,
                    "Класична, Інструментальна": 60,
                    "Невидане": 82,
                },
            },
        },
    },
    "Література": {
        "category_id": 12,
        "forums": {
            "": {
                "forum_id": -1,
                "subforums": {
                    "Українська художня література [до 1991 р.]": 93,
                    "Українська художня література (після 1991 р.)": 92,
                    "Зарубіжна художня література": 91,
                    "Наукова література (гуманітарні дисципліни)": 90,
                    "Наукова література (природничі дисципліни)": 89,
                    "Навчальна та довідкова": 88,
                    "Періодика": 87,
                    "Батькам та малятам": 86,
                    "Графіка (комікси, манґа, BD та інше)": 85,
                },
            },
            "Аудіокниги українською": {
                "forum_id": 84,
                "subforums": {
                    "Українська художня література": 96,
                    "Зарубіжна художня література": 95,
                    "Історія, біографістика, спогади": 94,
                },
            },
        },
    },
    "Програмне забезпечення": {
        "category_id": 13,
        "forums": {
            "Операційні системи": {
                "forum_id": 168,
                "subforums": {},
            },
            "Системні програми": {
                "forum_id": 169,
                "subforums": {},
            },
            "Офіс, текстові редактори": {
                "forum_id": 170,
                "subforums": {},
            },
            "Аудіо, відео обробка": {
                "forum_id": 171,
                "subforums": {},
            },
            "Інше": {
                "forum_id": 173,
                "subforums": {},
            },
            "Ігри": {
                "forum_id": 185,
                "subforums": {},
            },
        },
    },
    "Видалені теми": {
        "category_id": 7,
        "forums": {
            "Архів": {
                "forum_id": 23,
                "subforums": {},
            },
        },
    },
}
# fmt: on


class Payload:
    """Base class for payload data structures."""

    def to_dict(self: Self) -> dict[str, str | list[str]]:
        """Convert dataclass fields to a dictionary suitable for urlencode."""
        result: dict[str, str | list[str]] = {}
        for k, v in vars(self).items():
            if v is None:
                continue
            if isinstance(v, list):
                result[k] = [str(item) for item in cast("list[object]", v)]
            else:
                result[k] = str(v)
        return result


@dataclass
class LoginPayload(Payload):
    """Data structure for login payload."""

    login_username: str = ""
    """Username"""

    login_password: str = ""
    """Password"""

    autologin: Optional[Literal["on"]] = "on"
    """Remember me"""

    redirect: str = "index.php"
    """Redirect URL"""

    login: Literal["Вхід"] = "Вхід"
    """The login action"""


@dataclass
class Config:
    """Configuration schema for the engine."""

    credentials: LoginPayload
    """Login credentials"""

    cache_login_cookies: bool = True
    """Whether to cache login cookies to disk"""

    log_level: str = logging.getLevelName(logger.getEffectiveLevel())
    """Logger level: DEBUG, INFO, WARNING, ERROR, CRITICAL. Default is WARNING."""

    def to_json(self: Self) -> "ConfigJson":
        """Convert Config dataclass to ConfigJson."""
        return ConfigJson(
            username=self.credentials.login_username,
            password=self.credentials.login_password,
            cache_login_cookies=self.cache_login_cookies,
            log_level=self.log_level,
        )


@dataclass
class ConfigJson:
    username: str
    password: str
    cache_login_cookies: Optional[bool] = Config.cache_login_cookies
    log_level: Optional[str] = Config.log_level

    def to_config(self: Self) -> "Config":
        """Convert ConfigJson to Config dataclass."""
        return Config(
            credentials=LoginPayload(login_username=self.username, login_password=self.password),
            cache_login_cookies=self.cache_login_cookies
            if self.cache_login_cookies is not None
            else Config.cache_login_cookies,
            log_level=self.log_level if self.log_level is not None else Config.log_level,
        )


@dataclass
class SearchPayload(Payload):
    """Data structure for search payload."""

    class SortByField(IntEnum):
        """Fields to sort by."""

        Registered = 1
        TopicName = 2
        Section = 3
        Downloaded = 4
        Replies = 5
        Views = 6
        Size = 7
        LastMessage = 8
        LastSeeder = 9
        Seeders = 10
        Leechers = 11
        UploadSpeed = 12
        DownloadSpeed = 13

    class SortOrder(IntEnum):
        """Sort order directions."""

        Ascending = 1
        Descending = 2

    class ReleaseGroup(IntEnum):
        """Release groups."""

        Any = -1
        MazepaVideo = 2
        MazepaFormula1 = 16

    # Search query
    nm: str = ""
    """Search query"""

    pn: Optional[str] = None
    """Author name"""

    allw: Optional[Literal[1]] = None
    """Search all words"""

    # Forum selection
    f: Optional[list[int]] = None
    """Forum IDs"""

    c: Optional[int] = None
    """Category ID"""

    # Sorting options
    o: SortByField = SortByField.Registered
    """Sort by field"""

    s: SortOrder = SortOrder.Descending
    """Sort direction"""

    # Time filter
    tm: int = -1
    """Time period filter (days): -1 = Any time"""

    # Show only filters
    my: Optional[Literal[1]] = None
    """Show only my torrents"""

    a: Optional[Literal[1]] = None
    """Show only active torrents"""

    sd: Optional[Literal[1]] = None
    """Show only with seeder"""

    new: Optional[Literal[1]] = None
    """Show only with new torrents"""

    # Column visibility
    dc: Optional[Literal[1]] = 1
    """Show category column"""

    df: Optional[Literal[1]] = 1
    """Show forum column"""

    da: Optional[Literal[1]] = 1
    """Show author column"""

    ds: Optional[Literal[1]] = 1
    """Show speed column"""

    # Additional filters
    sns: int = -1
    """No seeders filter (days): -1 = Ignore, -2 = Never"""

    srg: ReleaseGroup = ReleaseGroup.Any
    """Release group filter"""

    # My torrents filters
    dlc: Optional[Literal[1]] = None
    """Show my completed"""

    dlw: Optional[Literal[1]] = None
    """Show my planned"""

    dld: Optional[Literal[1]] = None
    """Show my downloaded"""

    dla: Optional[Literal[1]] = None
    """Show my cancelled"""

    # Submit
    submit: Literal[" Пошук "] = " Пошук "
    """Submit button value"""


def size_string_to_bytes(size_str: str) -> int:
    """Convert a human-readable size string to bytes.

    Supports both English (GB, MB, KB, TB, B) and Ukrainian (ГБ, МБ, КБ, ТБ, Б) units.
    Handles non-breaking spaces (\\xa0) and regular spaces.

    Args:
        size_str: Size string like "2.6 GB", "208 MB", "2.6\\xa0GB"

    Returns:
        Size in bytes as integer, or -1 if parsing fails

    """  # noqa: D301
    if not size_str:
        return -1

    # Normalize: replace non-breaking space with regular space and strip
    size_str = size_str.replace("\xa0", " ").strip()

    # Unit multipliers (case-insensitive for English, exact match for Ukrainian)
    units: dict[str, int] = {
        # English units
        "TB": 1024**4,
        "GB": 1024**3,
        "MB": 1024**2,
        "KB": 1024,
        "B": 1,
        # Ukrainian units
        "ТБ": 1024**4,
        "ГБ": 1024**3,
        "МБ": 1024**2,
        "КБ": 1024,
        "Б": 1,
    }

    # Try to extract number and unit
    # Match number (int or float) followed by optional space and unit
    match = re.match(r"^([\d.,]+)\s*([A-Za-zА-Яа-яІіЇїЄє]+)$", size_str)
    if not match:
        logger.debug("Failed to parse size string: %r", size_str)
        return -1

    number_str, unit = match.groups()
    # Handle both comma and dot as decimal separator
    number_str = number_str.replace(",", ".")

    try:
        number = float(number_str)
    except ValueError:
        logger.debug("Failed to parse size number: %r", number_str)
        return -1

    # Find matching unit (case-insensitive for English)
    multiplier = units.get(unit) or units.get(unit.upper())
    if multiplier is None:
        logger.debug("Unknown size unit: %r", unit)
        return -1

    return int(number * multiplier)


class MazepaHTMLParser(HTMLParser):
    """Parser for Mazepa search results HTML using header-based column detection."""

    # Valid keys derived from SearchResults TypedDict
    # Type checkers cannot infer Literal types from TypedDict keys, so we define them manually
    # and validate at class-load time that they match the actual TypedDict
    SearchResultsKeys = Literal["link", "name", "size", "seeds", "leech", "engine_url", "desc_link", "pub_date"]
    assert set(get_args(SearchResultsKeys)) == set(SearchResults.__annotations__.keys()), (  # noqa: S101
        f"SearchResultsKeys out of sync: {set(get_args(SearchResultsKeys))} != {set(SearchResults.__annotations__.keys())}"
    )  # nosec B101

    # Mapping from header text to SearchResults field names
    HEADER_TO_FIELD: dict[str, SearchResultsKeys] = {  # noqa: RUF012
        "Тема": "name",
        "Торрент": "link",
        "Розмір": "size",
        "S": "seeds",
        "L": "leech",
        "Додано": "pub_date",
    }

    @staticmethod
    def _empty_search_result() -> SearchResults:
        """Create an empty SearchResults with default values."""
        return SearchResults(
            {
                "link": "",
                "name": "",
                "size": -1,
                "seeds": -1,
                "leech": -1,
                "engine_url": "",
                "desc_link": "",
                "pub_date": -1,
            },
        )

    def __init__(self) -> None:
        super().__init__()
        self.results: list[SearchResults] = []

        # Pagination: list of next page URLs (relative)
        self.next_page_urls: list[str] = []

        # Column index -> field name mapping (populated from header row)
        self._col_to_field: dict[int, MazepaHTMLParser.SearchResultsKeys] = {}

        # Parsing state
        self._in_header_cell: bool = False
        self._in_data_row: bool = False
        self._header_col_index: int = 0
        self._header_text: str = ""
        self._data_col_index: int = 0
        self._current_field: Optional[MazepaHTMLParser.SearchResultsKeys] = None
        self._current_result: Optional[SearchResults] = None
        self._capture_text: bool = False
        self._current_text: str = ""

        # Pagination parsing state
        self._in_navigation_span: bool = False

        # Track if we're in the actual results table header
        self._in_results_thead: bool = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        attrs_dict = dict(attrs)

        # Detect the actual results table header section
        if tag == "thead":
            class_attr = attrs_dict.get("class") or ""
            if "forumline" in class_attr:
                self._in_results_thead = True
                self._header_col_index = 0  # Reset header counter for actual table

        # Detect navigation span/div for pagination
        if tag in ("span", "div") and attrs_dict.get("class") in ("navigation", "nav"):
            self._in_navigation_span = True

        # Parse pagination links inside navigation
        if tag == "a" and self._in_navigation_span:
            href = attrs_dict.get("href") or ""
            if "tracker.php?" in href and "start=" in href:
                if href not in self.next_page_urls:
                    self.next_page_urls.append(href)

        if tag == "tr":
            class_attr = attrs_dict.get("class") or ""
            if any(c in class_attr for c in ("prow1", "prow2", "row1", "row2", "tCenter")):
                self._in_data_row = True
                self._data_col_index = 0
                self._current_result = MazepaHTMLParser._empty_search_result()

        elif tag == "th" and self._in_results_thead:
            self._in_header_cell = True
            self._header_text = ""

        elif tag == "td" and self._in_data_row and self._current_result:
            self._current_field = self._col_to_field.get(self._data_col_index)
            self._data_col_index += 1

            if self._current_field in ("size", "pub_date"):
                self._capture_text = True
                self._current_text = ""

        elif tag == "a" and self._in_data_row and self._current_result:
            href = attrs_dict.get("href") or ""

            # Download link can be in "link" column or embedded in "size" column (mazepa.to)
            if ("download.php" in href or "dl.php" in href) and not self._current_result["link"]:
                self._current_result["link"] = href

            elif self._current_field == "name":
                # Topic links can be like "t12345" or "viewtopic.php?t=12345" or "topic-xxx-t12345.html"
                if (
                    (href.startswith("t") and len(href) > 1 and href[1:].split("-")[0].split(".")[0].isdigit())
                    or "viewtopic.php" in href
                    or "topic-" in href
                ):
                    self._current_result["desc_link"] = href
                    self._capture_text = True
                    self._current_text = ""

        elif tag == "b" and self._in_data_row:
            if self._current_field in ("seeds", "leech"):
                self._capture_text = True
                self._current_text = ""

        # Also capture seeds/leech from span elements (some TorrentPier themes use this)
        elif tag == "span" and self._in_data_row:
            class_attr = attrs_dict.get("class") or ""
            if "seedmed" in class_attr or "seed" in class_attr:
                self._current_field = "seeds"
                self._capture_text = True
                self._current_text = ""
            elif "leechmed" in class_attr or "leech" in class_attr:
                self._current_field = "leech"
                self._capture_text = True
                self._current_text = ""

    def handle_endtag(self, tag: str) -> None:
        if tag == "thead" and self._in_results_thead:
            self._in_results_thead = False

        elif tag in ("span", "div") and self._in_navigation_span:
            self._in_navigation_span = False

        elif tag == "th" and self._in_header_cell:
            header_text = self._header_text.strip()
            if header_text in self.HEADER_TO_FIELD:
                self._col_to_field[self._header_col_index] = self.HEADER_TO_FIELD[header_text]
            self._header_col_index += 1
            self._in_header_cell = False

        elif tag == "tr":
            if self._in_data_row:
                if self._current_result and self._current_result["link"] and self._current_result["name"]:
                    self.results.append(self._current_result)
                self._in_data_row = False
                self._current_result = None

        elif tag == "td":
            self._current_field = None
            self._capture_text = False

        elif tag == "a" and self._current_field == "name" and self._current_result:
            if self._capture_text and self._current_text:
                self._current_result["name"] = self._current_text.strip()
            self._capture_text = False

        elif (tag == "b" and self._current_result) or (tag == "span" and self._current_result):
            if self._current_field in ("seeds", "leech") and self._capture_text:
                try:
                    self._current_result[self._current_field] = int(self._current_text.strip())
                except ValueError:
                    logger.debug("Failed to parse %s value: %r", self._current_field, self._current_text.strip())
                self._capture_text = False

    def handle_data(self, data: str) -> None:
        if self._in_header_cell:
            self._header_text += data

        if self._capture_text:
            self._current_text += data

        if not self._current_result:
            return

        if self._current_field == "size" and self._current_result["size"] == -1:
            size_text = data.strip()
            if size_text and any(
                unit in size_text for unit in ("TB", "GB", "MB", "KB", "B", "ТБ", "ГБ", "МБ", "КБ", "Б")
            ):
                self._current_result["size"] = size_string_to_bytes(size_text)

        if self._current_field == "pub_date" and self._current_result["pub_date"] == -1:
            date_text = data.strip()
            if date_text and "-" in date_text:
                # Try ISO format first (YYYY-MM-DD)
                try:
                    dt = datetime.strptime(date_text, "%Y-%m-%d")
                    self._current_result["pub_date"] = int(dt.timestamp())
                except ValueError:
                    # Try Ukrainian format (D-Mon-YY) like "7-Гру-25"
                    ua_months = {
                        "Січ": 1,
                        "Лют": 2,
                        "Бер": 3,
                        "Кві": 4,
                        "Тра": 5,
                        "Чер": 6,
                        "Лип": 7,
                        "Сер": 8,
                        "Вер": 9,
                        "Жов": 10,
                        "Лис": 11,
                        "Гру": 12,
                    }
                    try:
                        parts = date_text.split("-")
                        if len(parts) == 3:
                            day = int(parts[0])
                            month = ua_months.get(parts[1], 0)
                            year = int(parts[2])
                            if year < 100:
                                year += 2000  # Convert YY to 20YY
                            if month > 0:
                                dt = datetime(year, month, day)
                                self._current_result["pub_date"] = int(dt.timestamp())
                    except (ValueError, KeyError):
                        logger.debug("Failed to parse pub_date: %r", date_text)


class mazepa_to(Engine):  # noqa: N801
    url: str = "https://mazepa.to/"
    name: str = "Mazepa — торрент-трекер"

    # Shorthand aliases for FORUM_MAP paths
    _U = FORUM_MAP["Український контент"]["forums"]
    _O = FORUM_MAP["Озвучений контент"]["forums"]
    _S = FORUM_MAP["Спорт"]["forums"]
    _M = FORUM_MAP["Музика"]["forums"]
    _L = FORUM_MAP["Література"]["forums"]
    _P = FORUM_MAP["Програмне забезпечення"]["forums"]
    _T = FORUM_MAP["Телевізійні передачі"]["forums"]

    supported_categories: dict[str, str] = {  # noqa: RUF012
        Category.all.name: "-1",
        Category.books.name: ",".join(
            str(x)
            for x in [
                *_L[""]["subforums"].values(),
                _L["Аудіокниги українською"]["forum_id"],
                *_L["Аудіокниги українською"]["subforums"].values(),
            ]
        ),
        Category.games.name: str(_P["Ігри"]["forum_id"]),
        Category.music.name: ",".join(str(x) for x in _M[""]["subforums"].values()),
        Category.software.name: ",".join(
            str(x)
            for x in [
                _P["Операційні системи"]["forum_id"],
                _P["Системні програми"]["forum_id"],
                _P["Офіс, текстові редактори"]["forum_id"],
                _P["Аудіо, відео обробка"]["forum_id"],
                _P["Інше"]["forum_id"],
            ]
        ),
        Category.anime.name: str(_O["Аніме"]["forum_id"]),
        Category.movies.name: ",".join(
            str(x)
            for x in [
                _U[""]["subforums"]["Українські фільми HD, UHD"],
                _U[""]["subforums"]["Українські фільми SD"],
                _U[""]["subforums"]["Українські мультфільми HD, UHD"],
                _U[""]["subforums"]["Українські мультфільми SD"],
                _U[""]["subforums"]["Українські документальні HD, UHD"],
                _U[""]["subforums"]["Українські документальні SD"],
                _O[""]["subforums"]["Новинки фільмів UHD, HD"],
                _O[""]["subforums"]["Фільми UHD"],
                _O[""]["subforums"]["Фільми HD"],
                _O[""]["subforums"]["Фільми SD"],
                _O[""]["subforums"]["Субтитровані фільми"],
                _O[""]["subforums"]["Мультфільми UHD"],
                _O[""]["subforums"]["Мультфільми HD"],
                _O[""]["subforums"]["Мультфільми SD"],
                _O["Аніме"]["subforums"]["Документальне UHD"],
                _O["Аніме"]["subforums"]["Документальне HD"],
                _O["Аніме"]["subforums"]["Документальне SD"],
            ]
        ),
        Category.tv.name: ",".join(
            str(x)
            for x in [
                _U[""]["subforums"]["Українські серіали HD, UHD"],
                _U[""]["subforums"]["Українські серіали SD"],
                _U[""]["subforums"]["Українські мультсеріали HD, UHD"],
                _U[""]["subforums"]["Українські мультсеріали SD"],
                _O[""]["subforums"]["Серіали UHD"],
                _O[""]["subforums"]["Серіали HD"],
                _O[""]["subforums"]["Серіали SD"],
                _O[""]["subforums"]["Мультсеріали UHD, HD"],
                _O[""]["subforums"]["Мультсеріали SD"],
                *_S[""]["subforums"].values(),
                _S["Автоспорт"]["forum_id"],
                *_S["Автоспорт"]["subforums"].values(),
                _S["Бокс, реслінг, бойові мистецтва"]["forum_id"],
                _T["Концерти, відеокліпи"]["forum_id"],
                _T["Теле-Шоу"]["forum_id"],
            ]
        ),
        # Category.pictures.name: "",
    }

    del _U, _O, _S, _M, _L, _P, _T

    login_url: str = f"{url}login.php"
    search_url: str = f"{url}tracker.php"

    def __init__(self: Self) -> None:
        engine_dir = Path(os.path.realpath(__file__)).parent
        self.config_file_path: Path = engine_dir / f"{self.__class__.__name__}.json"
        self.cookies_file_path: Path = engine_dir / f"{self.__class__.__name__}.cookies"
        self.config: Config = self._load_config()
        self.cookie_jar: LWPCookieJar = LWPCookieJar(self.cookies_file_path)
        self.opener: OpenerDirector = build_opener(HTTPCookieProcessor(self.cookie_jar))
        self.opener.addheaders = [
            (
                "User-Agent",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            ),
            (
                "Accept",
                "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            ),
            ("Accept-Language", "uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7"),
            ("Accept-Encoding", "gzip, deflate"),
            ("Connection", "keep-alive"),
            ("Upgrade-Insecure-Requests", "1"),
        ]
        self.logged_in: bool = False

        # Apply configured log level (default: WARNING)
        if self.config.log_level:
            level = getattr(logging, self.config.log_level.upper(), None)
            if isinstance(level, int):
                logger.setLevel(level)

        # Add file handler for logging
        self.log_file_path: Path = engine_dir / f"{self.__class__.__name__}.log"
        file_handler = logging.FileHandler(self.log_file_path, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        file_handler.setLevel(logging.DEBUG)
        logger.addHandler(file_handler)

        if self.config.cache_login_cookies and self.cookies_file_path.exists():
            try:
                self.cookie_jar.load(str(self.cookies_file_path.absolute()), ignore_discard=True, ignore_expires=True)
                logger.info("Loaded %d cached cookies from %s", len(self.cookie_jar), self.cookies_file_path)
            except (LoadError, OSError) as e:
                logger.warning("Failed to load cached cookies from %s: %s", self.cookies_file_path, e)

    def _load_config(self) -> Config:
        """Load configuration from config file.

        Config file format (JSON):
        {
            "username": "your_username",
            "password": "your_password",
            "cache_login_cookies": true,
            "log_level": "WARNING"
        }

        log_level options: DEBUG, INFO, WARNING, ERROR, CRITICAL (default: WARNING)
        """
        defaults = Config(credentials=LoginPayload())

        if not self.config_file_path.exists():
            template: ConfigJson = ConfigJson(  # nosec B106
                username="",
                password="",
            )
            try:
                with self.config_file_path.open("w", encoding="utf-8") as f:
                    json.dump(asdict(template), f, indent=4)
                logger.warning(
                    "Config file created: %s. Fill in 'username' and 'password' fields.",
                    self.config_file_path,
                )
            except OSError:
                logger.exception("Failed to create config file %s", self.config_file_path)
            return defaults

        try:
            with Path(self.config_file_path).open(encoding="utf-8") as f:
                data: ConfigJson = ConfigJson(**json.load(f))

            if not data.username or not data.password:
                logger.warning("Config file missing 'username' or 'password' field")

            # Save config back to propagate any missing fields
            with Path(self.config_file_path).open("w", encoding="utf-8") as f:
                json.dump(asdict(data), f, indent=4)

            logger.debug("Loaded credentials for user: %s", data.username)
            return data.to_config()

        except json.JSONDecodeError:
            logger.exception("Invalid JSON in config file %s", self.config_file_path)
            return defaults
        except OSError:
            logger.exception("Failed to read config file %s", self.config_file_path)
            return defaults

    def _is_session_valid(self) -> bool:
        """Check if current session is authenticated by testing login.php redirect."""
        try:
            response: HTTPResponse = self.opener.open(self.login_url, timeout=10)
            redirect_path = urlparse(response.geturl()).path
        except (URLError, HTTPError, TimeoutError, OSError) as e:
            logger.debug("Session validation failed: %s", e)
            return False
        # If redirected to main page, session is valid
        return redirect_path in ("/", "/index.php")

    def _login(self) -> Literal[True]:
        """Authenticate with Mazepa using stored credentials."""
        if self.logged_in:
            logger.debug("Already logged in, skipping login")
            return True

        # Check if cached cookies are still valid
        if len(self.cookie_jar) > 0:
            logger.debug("Validating %d cached cookies...", len(self.cookie_jar))
            if self._is_session_valid():
                self.logged_in = True
                logger.info("Cached cookies are valid, skipping login")
                return True
            logger.info("Cached cookies expired, performing fresh login")
            self.cookie_jar.clear()

        if not self.config.credentials.login_username or not self.config.credentials.login_password:
            logger.error(
                "Missing credentials: username=%s, password=%s",
                bool(self.config.credentials.login_username),
                bool(self.config.credentials.login_password),
            )
            raise Exception("Username and password must be provided")

        logger.info("Attempting login for user: %s", self.config.credentials.login_username)
        login_data: bytes = urlencode(self.config.credentials.to_dict()).encode("utf-8")

        try:
            request = Request(mazepa_to.login_url, data=login_data)
            request.add_header("Content-Type", "application/x-www-form-urlencoded")
            logger.debug("Sending login request to %s", mazepa_to.login_url)

            response: HTTPResponse = self.opener.open(request, timeout=30)
            redirect_path = urlparse(response.geturl()).path
            logger.debug("Login response redirected to: %s", redirect_path)

            # Check if login was successful by looking for redirect to main page
            if redirect_path in ("/", "/index.php"):
                self.logged_in = True
                logger.info("Login successful for user: %s", self.config.credentials.login_username)

                if self.config.cache_login_cookies:
                    try:
                        self.cookie_jar.save(
                            str(self.cookies_file_path.absolute()),
                            ignore_discard=True,
                            ignore_expires=True,
                        )
                        logger.info("Saved %d cookies to %s", len(self.cookie_jar), self.cookies_file_path)
                    except OSError as e:
                        logger.warning("Failed to save cookies to %s: %s", self.cookies_file_path, e)

                return True
            logger.error(
                "Login failed for user %s: unexpected redirect to %s",
                self.config.credentials.login_username,
                redirect_path,
            )
            raise Exception(f"Login failed: unexpected redirect to {redirect_path}")

        except HTTPError as e:
            logger.exception("Login HTTP error: %s %s", e.code, e.reason)
            raise Exception(f"Login failed with HTTP {e.code}: {e.reason}") from e
        except URLError as e:
            logger.exception("Login URL error: %s", e.reason)
            raise Exception(f"Login failed: {e.reason}") from e
        except TimeoutError:
            logger.exception("Login request timed out after 30s")
            raise Exception("Login request timed out") from None
        except OSError as e:
            logger.exception("Login network error")
            raise Exception(f"Login failed: {e}") from e

    def _parse_and_print_results(self, html_content: str) -> MazepaHTMLParser:
        """Parse HTML content and print results. Returns the parser with pagination info."""
        parser = MazepaHTMLParser()
        parser.feed(html_content)

        for result in parser.results:
            # Ensure full URLs
            if result["link"] and not result["link"].startswith("http"):
                result["link"] = f"{mazepa_to.url}{result['link'].lstrip('/')}"
            result["engine_url"] = mazepa_to.url
            if result["desc_link"] and not result["desc_link"].startswith("http"):
                result["desc_link"] = f"{mazepa_to.url}{result['desc_link'].lstrip('/')}"
            prettyPrinter(result)

        return parser

    def _decompress_response(self, response: HTTPResponse) -> bytes:
        """Read and decompress HTTP response based on Content-Encoding header."""
        data: bytes = response.read()
        match response.getheader("Content-Encoding"):
            case "gzip":
                data = gzip.decompress(data)
            case "deflate":
                data = zlib.decompress(data)
            case _:
                pass
        return data

    def _fetch_page(self, url: str) -> str:
        """Fetch a page and return decoded HTML content."""
        request = Request(url)
        response: HTTPResponse = self.opener.open(request, timeout=30)
        return self._decompress_response(response).decode("utf-8")

    def download_torrent(self: Self, info: str) -> None:
        """Download torrent file and print path for qBittorrent."""
        logger.debug("Downloading torrent from: %s", info)
        self._login()

        try:
            request = Request(info)
            response: HTTPResponse = self.opener.open(request, timeout=30)
            data: bytes = self._decompress_response(response)

            # Write to temp file
            fd, path = tempfile.mkstemp(suffix=".torrent")
            with os.fdopen(fd, "wb") as f:
                f.write(data)

            result = f"{path} {info}"
            logger.info("Downloaded torrent: %s", result)
            print(result)

        except HTTPError as e:
            logger.exception("Download HTTP error: %s %s", e.code, e.reason)
            raise Exception(f"Download failed with HTTP {e.code}: {e.reason}") from e
        except URLError as e:
            logger.exception("Download URL error: %s", e.reason)
            raise Exception(f"Download failed: {e.reason}") from e
        except TimeoutError:
            logger.exception("Download request timed out for: %s", info)
            raise Exception("Download request timed out") from None
        except OSError as e:
            logger.exception("Download error")
            raise Exception(f"Download failed: {e}") from e

    def search(self: Self, query: str, category: str = Category.all.name) -> None:
        """Search for torrents and print results via prettyPrinter."""
        if not query or not query.strip():
            logger.warning("Empty search query provided")
            return

        # nova2.py pre-encodes query with urllib.parse.quote(), so decode it first
        # to avoid double-encoding when we use urlencode() below
        query = unquote(query.strip())

        logger.info("Starting search for: %r in category: %s", query, category)
        self._login()

        # Parse forum IDs from category
        forum_ids: list[int] | None = None
        category_value = self.supported_categories.get(category, "-1")
        if category_value != "-1":
            forum_ids = [int(x) for x in category_value.split(",")]
            logger.debug("Searching in %d forums", len(forum_ids))

        search_payload = SearchPayload(nm=query, f=forum_ids)
        search_data: bytes = urlencode(search_payload.to_dict(), doseq=True).encode("utf-8")

        try:
            # Fetch first page via POST
            request = Request(mazepa_to.search_url, data=search_data)
            logger.debug("Sending search request to %s", mazepa_to.search_url)

            response: HTTPResponse = self.opener.open(request, timeout=30)
            logger.debug("Search response status: %s", response.status)
            html_content: str = self._decompress_response(response).decode("utf-8")
            logger.debug("Received %d bytes of HTML content", len(html_content))

            parser = self._parse_and_print_results(html_content)
            total_results = len(parser.results)
            logger.info("Page 1: found %d results for query: %r", total_results, query.strip())

            # Fetch remaining pages
            fetched_urls: set[str] = set()
            for page_url in parser.next_page_urls:
                if page_url in fetched_urls:
                    continue
                fetched_urls.add(page_url)

                full_url = f"{mazepa_to.url}{page_url.lstrip('/')}"
                logger.debug("Fetching next page: %s", full_url)

                try:
                    page_html = self._fetch_page(full_url)
                    page_parser = self._parse_and_print_results(page_html)
                    total_results += len(page_parser.results)
                    logger.debug("Page fetched: %d results", len(page_parser.results))
                except (HTTPError, URLError, TimeoutError, OSError) as e:
                    logger.warning("Failed to fetch page %s: %s", page_url, e)
                    continue

            logger.info("Search completed, total %d results", total_results)

        except HTTPError as e:
            logger.exception("Search HTTP error: %s %s", e.code, e.reason)
            raise Exception(f"Search failed with HTTP {e.code}: {e.reason}") from e
        except URLError as e:
            logger.exception("Search URL error: %s", e.reason)
            raise Exception(f"Search failed: {e.reason}") from e
        except TimeoutError:
            logger.exception("Search request timed out after 30s for query: %r", query)
            raise Exception("Search request timed out") from None
        except OSError as e:
            logger.exception("Search network error")
            raise Exception(f"Search failed: {e}") from e


# Manual testing entry point (--test is handled at top of file before imports)
if __name__ == "__main__":
    engine = mazepa_to()
    query = sys.argv[1] if len(sys.argv) > 1 else "ASDF"
    logger.info("Running standalone search for: %r", query)
    try:
        engine.search(query)
    except Exception:
        logger.exception("Search failed")
        sys.exit(1)
