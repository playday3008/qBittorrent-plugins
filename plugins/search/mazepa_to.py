# VERSION: 1.00
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

# Handle --test flag before any qBittorrent-specific imports
if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        import subprocess  # nosec B404

        # Run pytest from project root so conftest.py provides mock modules
        args = ["pytest", __file__, "-v"] + [a for a in sys.argv[1:] if a != "--test"]
        sys.exit(subprocess.call(args))  # nosec B603

import gzip
import json
import logging
import os
import sys
import tempfile
import zlib
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import IntEnum
from html.parser import HTMLParser
from http.client import HTTPResponse
from http.cookiejar import LoadError, LWPCookieJar
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
            }
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
                "subforums": {}
            },
            "Системні програми": {
                "forum_id": 169,
                "subforums": {}
            },
            "Офіс, текстові редактори": {
                "forum_id": 170,
                "subforums": {}
            },
            "Аудіо, відео обробка": {
                "forum_id": 171,
                "subforums": {}
            },
            "Інше": {
                "forum_id": 173,
                "subforums": {}
            },
            "Ігри": {
                "forum_id": 185,
                "subforums": {}
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


class Payload:
    """Base class for payload data structures"""
    def to_dict(self: Self) -> dict[str, str | list[str]]:
        """Convert dataclass fields to a dictionary suitable for urlencode"""
        result: dict[str, str | list[str]] = {}
        for k, v in vars(self).items():
            if v is None:
                continue
            if isinstance(v, list):
                result[k] = [str(item) for item in cast(list[object], v)]
            else:
                result[k] = str(v)
        return result


@dataclass
class LoginPayload(Payload):
    """Data structure for login payload"""

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
    """Configuration schema for the engine"""

    credentials: LoginPayload
    """Login credentials"""

    cache_login_cookies: bool = True
    """Whether to cache login cookies to disk"""

    log_level: str = logging.getLevelName(logger.getEffectiveLevel())
    """Logger level: DEBUG, INFO, WARNING, ERROR, CRITICAL. Default is WARNING."""

    def to_json(self: Self) -> 'ConfigJson':
        """Convert Config dataclass to ConfigJson"""
        return ConfigJson(
            username=self.credentials.login_username,
            password=self.credentials.login_password,
            cache_login_cookies=self.cache_login_cookies,
            log_level=self.log_level
        )


@dataclass
class ConfigJson:
    username: str
    password: str
    cache_login_cookies: Optional[bool] = True
    log_level: Optional[str] = None

    def to_config(self: Self) -> 'Config':
        """Convert ConfigJson to Config dataclass"""
        return Config(
            credentials=LoginPayload(
                login_username=self.username,
                login_password=self.password
            ),
            cache_login_cookies=self.cache_login_cookies if self.cache_login_cookies is not None else True,
            log_level=self.log_level if self.log_level is not None else logging.getLevelName(logger.getEffectiveLevel())
        )


@dataclass
class SearchPayload(Payload):
    """Data structure for search payload"""

    class SortByField(IntEnum):
        """Fields to sort by"""
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
        """Sort order directions"""
        Ascending = 1
        Descending = 2

    class ReleaseGroup(IntEnum):
        """Release groups"""
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


class MazepaHTMLParser(HTMLParser):
    """Parser for Mazepa search results HTML using header-based column detection"""

    # Valid keys derived from SearchResults TypedDict
    # Type checkers cannot infer Literal types from TypedDict keys, so we define them manually
    # and validate at class-load time that they match the actual TypedDict
    SearchResultsKeys = Literal["link", "name", "size", "seeds", "leech", "engine_url", "desc_link", "pub_date"]
    assert set(get_args(SearchResultsKeys)) == set(SearchResults.__annotations__.keys()), \
        f"SearchResultsKeys out of sync: {set(get_args(SearchResultsKeys))} != {set(SearchResults.__annotations__.keys())}"  # nosec B101

    # Mapping from header text to SearchResults field names
    HEADER_TO_FIELD: dict[str, SearchResultsKeys] = {
        "Тема": "name",
        "Торрент": "link",
        "Розмір": "size",
        "S": "seeds",
        "L": "leech",
        "Додано": "pub_date",
    }

    @staticmethod
    def _empty_search_result() -> SearchResults:
        """Create an empty SearchResults with default values"""
        return SearchResults(
            {
                "link": "",
                "name": "",
                "size": "",
                "seeds": -1,
                "leech": -1,
                "engine_url": "",
                "desc_link": "",
                "pub_date": -1,
            }
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
                if href.startswith("t") and len(href) > 1 and href[1:].split("-")[0].split(".")[0].isdigit():
                    self._current_result["desc_link"] = href
                    self._capture_text = True
                    self._current_text = ""
                elif "viewtopic.php" in href or "topic-" in href:
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
                if (
                    self._current_result
                    and self._current_result["link"]
                    and self._current_result["name"]
                ):
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

        elif tag == "b" and self._current_result:
            if self._current_field in ("seeds", "leech") and self._capture_text:
                try:
                    self._current_result[self._current_field] = int(self._current_text.strip())
                except ValueError:
                    logger.debug("Failed to parse %s value: %r", self._current_field, self._current_text.strip())
                self._capture_text = False

        elif tag == "span" and self._current_result:
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

        if self._current_field == "size" and not self._current_result["size"]:
            size_text = data.strip()
            if size_text and any(
                unit in size_text for unit in ("GB", "MB", "KB", "TB", "B", "ГБ", "МБ", "КБ", "ТБ", "Б")
            ):
                self._current_result["size"] = size_text

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
                        "Січ": 1, "Лют": 2, "Бер": 3, "Кві": 4, "Тра": 5, "Чер": 6,
                        "Лип": 7, "Сер": 8, "Вер": 9, "Жов": 10, "Лис": 11, "Гру": 12
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


class mazepa_to(Engine):
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

    supported_categories: dict[str, str] = {
        Category.all.name: "-1",
        Category.books.name: ','.join(str(x) for x in [
            *_L[""]["subforums"].values(),
            _L["Аудіокниги українською"]["forum_id"],
            *_L["Аудіокниги українською"]["subforums"].values(),
        ]),
        Category.games.name: str(_P["Ігри"]["forum_id"]),
        Category.music.name: ','.join(str(x) for x in _M[""]["subforums"].values()),
        Category.software.name: ','.join(str(x) for x in [
            _P["Операційні системи"]["forum_id"],
            _P["Системні програми"]["forum_id"],
            _P["Офіс, текстові редактори"]["forum_id"],
            _P["Аудіо, відео обробка"]["forum_id"],
            _P["Інше"]["forum_id"],
        ]),
        Category.anime.name: str(_O["Аніме"]["forum_id"]),
        Category.movies.name: ','.join(str(x) for x in [
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
        ]),
        Category.tv.name: ','.join(str(x) for x in [
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
        ]),
        #Category.pictures.name: "",
    }

    del _U, _O, _S, _M, _L, _P, _T

    login_url: str = f"{url}login.php"
    search_url: str = f"{url}tracker.php"

    def __init__(self: Self) -> None:
        engine_dir = os.path.dirname(os.path.realpath(__file__))
        self.config_file_path: str = os.path.join(engine_dir, f"{self.__class__.__name__}.json")
        self.cookies_file_path: str = os.path.join(engine_dir, f"{self.__class__.__name__}.cookies")
        self.config: Config = self._load_config()
        self.cookie_jar: LWPCookieJar = LWPCookieJar(self.cookies_file_path)
        self.opener: OpenerDirector = build_opener(HTTPCookieProcessor(self.cookie_jar))
        self.logged_in: bool = False

        # Apply configured log level (default: WARNING)
        if self.config.log_level:
            level = getattr(logging, self.config.log_level.upper(), None)
            if isinstance(level, int):
                logger.setLevel(level)

        if self.config.cache_login_cookies and os.path.exists(self.cookies_file_path):
            try:
                self.cookie_jar.load(
                    self.cookies_file_path,
                    ignore_discard=True,
                    ignore_expires=True
                )
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

        if not os.path.exists(self.config_file_path):
            template: ConfigJson = ConfigJson(  # nosec B106
                username="",
                password="",
            )
            try:
                with open(self.config_file_path, "w", encoding="utf-8") as f:
                    json.dump(asdict(template), f, indent=4)
                logger.warning(
                    "Config file created: %s. Fill in 'username' and 'password' fields.",
                    self.config_file_path
                )
            except OSError as e:
                logger.error("Failed to create config file %s: %s", self.config_file_path, e)
            return defaults

        try:
            with open(self.config_file_path, "r", encoding="utf-8") as f:
                data: ConfigJson = ConfigJson(**json.load(f))

            if not data.username or not data.password:
                logger.warning("Config file missing 'username' or 'password' field")

            # Save config back to propagate any missing fields
            with open(self.config_file_path, "w", encoding="utf-8") as f:
                json.dump(asdict(data), f, indent=4)

            logger.debug("Loaded credentials for user: %s", data.username)
            return data.to_config()

        except json.JSONDecodeError as e:
            logger.error("Invalid JSON in config file %s: %s", self.config_file_path, e)
            return defaults
        except OSError as e:
            logger.error("Failed to read config file %s: %s", self.config_file_path, e)
            return defaults

    def _is_session_valid(self) -> bool:
        """Check if current session is authenticated by testing login.php redirect."""
        try:
            response: HTTPResponse = self.opener.open(self.login_url, timeout=10)
            redirect_path = urlparse(response.geturl()).path
            # If redirected to main page, session is valid
            return redirect_path in ("/", "/index.php")
        except (URLError, HTTPError, TimeoutError, OSError) as e:
            logger.debug("Session validation failed: %s", e)
            return False

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
            else:
                logger.info("Cached cookies expired, performing fresh login")
                self.cookie_jar.clear()

        if not self.config.credentials.login_username or not self.config.credentials.login_password:
            logger.error("Missing credentials: username=%s, password=%s",
                         bool(self.config.credentials.login_username), bool(self.config.credentials.login_password))
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
                            self.cookies_file_path,
                            ignore_discard=True,
                            ignore_expires=True
                        )
                        logger.info("Saved %d cookies to %s", len(self.cookie_jar), self.cookies_file_path)
                    except OSError as e:
                        logger.warning("Failed to save cookies to %s: %s", self.cookies_file_path, e)

                return True
            else:
                logger.error("Login failed for user %s: unexpected redirect to %s",
                             self.config.credentials.login_username, redirect_path)
                raise Exception(f"Login failed: unexpected redirect to {redirect_path}")

        except HTTPError as e:
            logger.error("Login HTTP error: %s %s", e.code, e.reason)
            raise Exception(f"Login failed with HTTP {e.code}: {e.reason}") from e
        except URLError as e:
            logger.error("Login URL error: %s", e.reason)
            raise Exception(f"Login failed: {e.reason}") from e
        except TimeoutError:
            logger.error("Login request timed out after 30s")
            raise Exception("Login request timed out") from None
        except OSError as e:
            logger.error("Login network error: %s", e)
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

    def _fetch_page(self, url: str) -> str:
        """Fetch a page and return decoded HTML content."""
        request = Request(url)
        response: HTTPResponse = self.opener.open(request, timeout=30)
        return response.read().decode("utf-8")

    def download_torrent(self: Self, info: str) -> None:
        """Download torrent file and print path for qBittorrent."""
        logger.debug("Downloading torrent from: %s", info)
        self._login()

        try:
            request = Request(info)
            response: HTTPResponse = self.opener.open(request, timeout=30)
            data: bytes = response.read()

            # Handle compressed response
            match response.getheader('Content-Encoding'):
                case 'gzip':
                    data = gzip.decompress(data)
                case 'deflate':
                    data = zlib.decompress(data)
                case _:
                    pass

            # Write to temp file
            fd, path = tempfile.mkstemp(suffix=".torrent")
            with os.fdopen(fd, "wb") as f:
                f.write(data)

            result = f"{path} {info}"
            logger.info("Downloaded torrent: %s", result)
            print(result)

        except HTTPError as e:
            logger.error("Download HTTP error: %s %s", e.code, e.reason)
            raise Exception(f"Download failed with HTTP {e.code}: {e.reason}") from e
        except URLError as e:
            logger.error("Download URL error: %s", e.reason)
            raise Exception(f"Download failed: {e.reason}") from e
        except TimeoutError:
            logger.error("Download request timed out for: %s", info)
            raise Exception("Download request timed out") from None
        except OSError as e:
            logger.error("Download error: %s", e)
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
        search_data: bytes = urlencode(search_payload.to_dict(), doseq=True).encode(
            "utf-8"
        )

        try:
            # Fetch first page via POST
            request = Request(mazepa_to.search_url, data=search_data)
            logger.debug("Sending search request to %s", mazepa_to.search_url)

            response: HTTPResponse = self.opener.open(request, timeout=30)
            logger.debug("Search response status: %s", response.status)
            html_content: str = response.read().decode("utf-8")
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
            logger.error("Search HTTP error: %s %s", e.code, e.reason)
            raise Exception(f"Search failed with HTTP {e.code}: {e.reason}") from e
        except URLError as e:
            logger.error("Search URL error: %s", e.reason)
            raise Exception(f"Search failed: {e.reason}") from e
        except TimeoutError:
            logger.error("Search request timed out after 30s for query: %r", query)
            raise Exception("Search request timed out") from None
        except OSError as e:
            logger.error("Search network error: %s", e)
            raise Exception(f"Search failed: {e}") from e


# Manual testing entry point (--test is handled at top of file before imports)
if __name__ == "__main__":
    engine = mazepa_to()
    query = sys.argv[1] if len(sys.argv) > 1 else "ASDF"
    logger.info("Running standalone search for: %r", query)
    try:
        engine.search(query)
    except Exception as e:
        logger.error("Search failed: %s", e)
        sys.exit(1)


# =============================================================================
# INLINE TESTS (run with: pytest mazepa_to.py -v)
# Only loaded when running under pytest to avoid bloating production imports
# =============================================================================

if "pytest" in sys.modules:
    from typing import Generator
    from unittest.mock import MagicMock, mock_open, patch

    import pytest

    def _noop_init(_: object) -> None:
        """No-op initializer for mocking __init__ methods."""
        pass

    # -------------------------------------------------------------------------
    # Test Fixtures
    # -------------------------------------------------------------------------

    @pytest.fixture
    def sample_html_single_result() -> str:
        """Sample HTML with a single search result."""
        return """
        <table>
            <thead class="forumline">
            <tr>
                <th>Тема</th>
                <th>Торрент</th>
                <th>Розмір</th>
                <th>S</th>
                <th>L</th>
                <th>Додано</th>
            </tr>
            </thead>
            <tr class="prow1">
                <td><a href="t12345">Test Torrent Name</a></td>
                <td><a href="download.php?id=12345">Download</a></td>
                <td>1.5 GB</td>
                <td><b>10</b></td>
                <td><b>5</b></td>
                <td>2024-01-15</td>
            </tr>
        </table>
        """

    @pytest.fixture
    def sample_html_multiple_results() -> str:
        """Sample HTML with multiple search results."""
        return """
        <table>
            <thead class="forumline">
            <tr>
                <th>Тема</th>
                <th>Торрент</th>
                <th>Розмір</th>
                <th>S</th>
                <th>L</th>
                <th>Додано</th>
            </tr>
            </thead>
            <tr class="prow1">
                <td><a href="t111">First Torrent</a></td>
                <td><a href="download.php?id=111">Download</a></td>
                <td>500 MB</td>
                <td><b>20</b></td>
                <td><b>3</b></td>
                <td>2024-02-20</td>
            </tr>
            <tr class="prow2">
                <td><a href="t222">Second Torrent</a></td>
                <td><a href="download.php?id=222">Download</a></td>
                <td>2.3 GB</td>
                <td><b>50</b></td>
                <td><b>10</b></td>
                <td>2024-03-10</td>
            </tr>
            <tr class="prow1">
                <td><a href="t333">Third Torrent</a></td>
                <td><a href="download.php?id=333">Download</a></td>
                <td>750 KB</td>
                <td><b>5</b></td>
                <td><b>1</b></td>
                <td>2024-01-05</td>
            </tr>
        </table>
        """

    @pytest.fixture
    def sample_html_with_pagination() -> str:
        """Sample HTML with pagination links."""
        return """
        <span class="navigation">
            <a href="tracker.php?nm=test&start=0">1</a>
            <a href="tracker.php?nm=test&start=50">2</a>
            <a href="tracker.php?nm=test&start=100">3</a>
        </span>
        <table>
            <thead class="forumline">
            <tr>
                <th>Тема</th>
                <th>Торрент</th>
                <th>Розмір</th>
                <th>S</th>
                <th>L</th>
                <th>Додано</th>
            </tr>
            </thead>
            <tr class="prow1">
                <td><a href="t12345">Paginated Result</a></td>
                <td><a href="download.php?id=12345">Download</a></td>
                <td>1 GB</td>
                <td><b>15</b></td>
                <td><b>2</b></td>
                <td>2024-06-01</td>
            </tr>
        </table>
        """

    @pytest.fixture
    def sample_config_dict() -> ConfigJson:
        """Sample configuration dictionary."""
        return ConfigJson(
            username="testuser",
            password="testpass",  # nosec B106
            cache_login_cookies=True)

    @pytest.fixture
    def temp_dir() -> Generator[str, None, None]:
        """Create a temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    # -------------------------------------------------------------------------
    # Tests for Payload Classes
    # -------------------------------------------------------------------------

    class TestPayload:
        """Tests for payload classes."""

        def test_to_dict_with_strings(self) -> None:
            payload = LoginPayload(login_username="user", login_password="pass")  # nosec B106
            result = payload.to_dict()
            assert result["login_username"] == "user"  # nosec B101
            assert result["login_password"] == "pass"  # nosec B101

        def test_to_dict_excludes_none(self) -> None:
            payload = SearchPayload(nm="test", pn=None)
            result = payload.to_dict()
            assert "pn" not in result  # nosec B101

        def test_to_dict_converts_list(self) -> None:
            payload = SearchPayload(nm="test", f=[1, 2, 3])
            result = payload.to_dict()
            assert result["f"] == ["1", "2", "3"]  # nosec B101

        def test_to_dict_converts_enum(self) -> None:
            payload = SearchPayload(nm="test", o=SearchPayload.SortByField.Seeders)
            result = payload.to_dict()
            assert result["o"] == "10"  # nosec B101

    class TestLoginPayload:
        """Tests for LoginPayload dataclass."""

        def test_default_values(self) -> None:
            payload = LoginPayload()
            assert payload.login_username == ""  # nosec B101
            assert payload.login_password == ""  # nosec B101, B105
            assert payload.autologin == "on"  # nosec B101
            assert payload.login == "Вхід"  # nosec B101

        def test_custom_values(self) -> None:
            payload = LoginPayload(login_username="myuser", login_password="mypass", autologin=None)  # nosec B106
            assert payload.login_username == "myuser"  # nosec B101
            assert payload.autologin is None  # nosec B101

    class TestConfig:
        """Tests for Config dataclass."""

        def test_default_cache_login_cookies(self) -> None:
            config = Config(credentials=LoginPayload())
            assert config.cache_login_cookies is True  # nosec B101

        def test_to_json_conversion(self) -> None:
            config = Config(credentials=LoginPayload(login_username="user", login_password="pass"), cache_login_cookies=False)  # nosec B106
            json_config = config.to_json()
            assert json_config.username == "user"  # nosec B101
            assert json_config.cache_login_cookies is False  # nosec B101

    class TestConfigJson:
        """Tests for ConfigJson dataclass."""

        def test_to_config_conversion(self) -> None:
            json_config = ConfigJson(username="testuser", password="testpass", cache_login_cookies=False)  # nosec B106
            config = json_config.to_config()
            assert config.credentials.login_username == "testuser"  # nosec B101
            assert config.cache_login_cookies is False  # nosec B101

        def test_to_config_default_cache(self) -> None:
            json_config = ConfigJson(username="user", password="pass", cache_login_cookies=None)  # nosec B106
            config = json_config.to_config()
            assert config.cache_login_cookies is True  # nosec B101

    class TestSearchPayload:
        """Tests for SearchPayload dataclass."""

        def test_sort_by_field_enum_values(self) -> None:
            assert SearchPayload.SortByField.Registered.value == 1  # nosec B101
            assert SearchPayload.SortByField.Seeders.value == 10  # nosec B101

        def test_sort_order_enum_values(self) -> None:
            assert SearchPayload.SortOrder.Ascending.value == 1  # nosec B101
            assert SearchPayload.SortOrder.Descending.value == 2  # nosec B101

        def test_default_values(self) -> None:
            payload = SearchPayload()
            assert payload.nm == ""  # nosec B101
            assert payload.o == SearchPayload.SortByField.Registered  # nosec B101
            assert payload.s == SearchPayload.SortOrder.Descending  # nosec B101

        def test_to_dict_with_forum_ids(self) -> None:
            payload = SearchPayload(nm="test query", f=[16, 32, 44])
            result = payload.to_dict()
            assert result["f"] == ["16", "32", "44"]  # nosec B101

    # -------------------------------------------------------------------------
    # Tests for MazepaHTMLParser
    # -------------------------------------------------------------------------

    class TestMazepaHTMLParser:
        """Tests for MazepaHTMLParser class."""

        def test_parse_single_result(self, sample_html_single_result: str) -> None:
            parser = MazepaHTMLParser()
            parser.feed(sample_html_single_result)
            assert len(parser.results) == 1  # nosec B101
            result = parser.results[0]
            assert result["name"] == "Test Torrent Name"  # nosec B101
            assert result["link"] == "download.php?id=12345"  # nosec B101
            assert result["size"] == "1.5 GB"  # nosec B101
            assert result["seeds"] == 10  # nosec B101
            assert result["leech"] == 5  # nosec B101

        def test_parse_multiple_results(self, sample_html_multiple_results: str) -> None:
            parser = MazepaHTMLParser()
            parser.feed(sample_html_multiple_results)
            assert len(parser.results) == 3  # nosec B101
            assert parser.results[0]["name"] == "First Torrent"  # nosec B101
            assert parser.results[2]["name"] == "Third Torrent"  # nosec B101

        def test_parse_pub_date(self, sample_html_single_result: str) -> None:
            parser = MazepaHTMLParser()
            parser.feed(sample_html_single_result)
            expected_timestamp = int(datetime.strptime("2024-01-15", "%Y-%m-%d").timestamp())
            assert parser.results[0]["pub_date"] == expected_timestamp  # nosec B101

        def test_empty_search_result_defaults(self) -> None:
            result = MazepaHTMLParser._empty_search_result()  # pyright: ignore[reportPrivateUsage]
            assert result["link"] == ""  # nosec B101
            assert result["seeds"] == -1  # nosec B101
            assert result["pub_date"] == -1  # nosec B101

        def test_header_to_field_mapping(self) -> None:
            assert MazepaHTMLParser.HEADER_TO_FIELD["Тема"] == "name"  # nosec B101
            assert MazepaHTMLParser.HEADER_TO_FIELD["S"] == "seeds"  # nosec B101

        def test_parse_missing_link_skips_result(self) -> None:
            html = """
            <table>
                <thead class="forumline">
                <tr><th>Тема</th><th>Торрент</th><th>Розмір</th><th>S</th><th>L</th><th>Додано</th></tr>
                </thead>
                <tr class="prow1">
                    <td><a href="t1">Test</a></td>
                    <td>No link</td>
                    <td>100 MB</td>
                    <td><b>5</b></td>
                    <td><b>2</b></td>
                    <td>2024-01-01</td>
                </tr>
            </table>
            """
            parser = MazepaHTMLParser()
            parser.feed(html)
            assert len(parser.results) == 0  # nosec B101

        def test_parse_empty_html(self) -> None:
            parser = MazepaHTMLParser()
            parser.feed("")
            assert len(parser.results) == 0  # nosec B101

        def test_parse_pagination_links(self, sample_html_with_pagination: str) -> None:
            parser = MazepaHTMLParser()
            parser.feed(sample_html_with_pagination)
            assert len(parser.next_page_urls) == 3  # nosec B101
            assert "tracker.php?nm=test&start=50" in parser.next_page_urls  # nosec B101

        def test_parse_various_sizes(self) -> None:
            html = """
            <table>
                <thead class="forumline">
                <tr><th>Тема</th><th>Торрент</th><th>Розмір</th><th>S</th><th>L</th><th>Додано</th></tr>
                </thead>
                <tr class="prow1">
                    <td><a href="t1">Test</a></td>
                    <td><a href="download.php?id=1">DL</a></td>
                    <td>{size}</td>
                    <td><b>1</b></td>
                    <td><b>1</b></td>
                    <td>2024-01-01</td>
                </tr>
            </table>
            """
            for size in ["500 MB", "2.3 GB", "750 KB", "1 TB"]:
                parser = MazepaHTMLParser()
                parser.feed(html.format(size=size))
                assert parser.results[0]["size"] == size  # nosec B101

        def test_parse_ukrainian_size_units(self) -> None:
            """Test parsing of Ukrainian size units (ГБ, МБ, etc.)."""
            html = """
            <table>
                <thead class="forumline">
                <tr><th>Тема</th><th>Торрент</th><th>Розмір</th><th>S</th><th>L</th><th>Додано</th></tr>
                </thead>
                <tr class="prow1">
                    <td><a href="t1">Test</a></td>
                    <td><a href="download.php?id=1">DL</a></td>
                    <td>{size}</td>
                    <td><b>1</b></td>
                    <td><b>1</b></td>
                    <td>2024-01-01</td>
                </tr>
            </table>
            """
            for size in ["500 МБ", "2.3 ГБ", "750 КБ", "1 ТБ"]:
                parser = MazepaHTMLParser()
                parser.feed(html.format(size=size))
                assert parser.results[0]["size"] == size  # nosec B101

        def test_parse_invalid_seeds_leech(self) -> None:
            html = """
            <table>
                <thead class="forumline">
                <tr><th>Тема</th><th>Торрент</th><th>Розмір</th><th>S</th><th>L</th><th>Додано</th></tr>
                </thead>
                <tr class="prow1">
                    <td><a href="t1">Test</a></td>
                    <td><a href="download.php?id=1">DL</a></td>
                    <td>100 MB</td>
                    <td><b>invalid</b></td>
                    <td><b>bad</b></td>
                    <td>2024-01-01</td>
                </tr>
            </table>
            """
            parser = MazepaHTMLParser()
            parser.feed(html)
            assert parser.results[0]["seeds"] == -1  # nosec B101
            assert parser.results[0]["leech"] == -1  # nosec B101

        def test_pagination_deduplication(self) -> None:
            html = """
            <span class="navigation">
                <a href="tracker.php?nm=test&start=50">2</a>
                <a href="tracker.php?nm=test&start=50">2</a>
            </span>
            """
            parser = MazepaHTMLParser()
            parser.feed(html)
            assert parser.next_page_urls.count("tracker.php?nm=test&start=50") == 1  # nosec B101

        def test_column_reordering(self) -> None:
            html = """
            <table>
                <thead class="forumline">
                <tr><th>Розмір</th><th>Тема</th><th>S</th><th>Торрент</th><th>L</th><th>Додано</th></tr>
                </thead>
                <tr class="prow1">
                    <td>500 MB</td>
                    <td><a href="t1">Reordered</a></td>
                    <td><b>15</b></td>
                    <td><a href="download.php?id=1">DL</a></td>
                    <td><b>3</b></td>
                    <td>2024-05-01</td>
                </tr>
            </table>
            """
            parser = MazepaHTMLParser()
            parser.feed(html)
            assert parser.results[0]["name"] == "Reordered"  # nosec B101
            assert parser.results[0]["size"] == "500 MB"  # nosec B101
            assert parser.results[0]["seeds"] == 15  # nosec B101

        def test_parse_ukrainian_date_format(self) -> None:
            """Test parsing of Ukrainian date format (D-Mon-YY)."""
            html = """
            <table>
                <thead class="forumline">
                <tr><th>Тема</th><th>Торрент</th><th>Розмір</th><th>S</th><th>L</th><th>Додано</th></tr>
                </thead>
                <tr class="prow1">
                    <td><a href="t1">Test</a></td>
                    <td><a href="download.php?id=1">DL</a></td>
                    <td>100 MB</td>
                    <td><b>5</b></td>
                    <td><b>2</b></td>
                    <td>7-Гру-25</td>
                </tr>
            </table>
            """
            parser = MazepaHTMLParser()
            parser.feed(html)
            expected_timestamp = int(datetime(2025, 12, 7).timestamp())
            assert parser.results[0]["pub_date"] == expected_timestamp  # nosec B101

        def test_parse_all_ukrainian_months(self) -> None:
            """Test parsing all Ukrainian month abbreviations."""
            ua_months = [
                ("Січ", 1), ("Лют", 2), ("Бер", 3), ("Кві", 4),
                ("Тра", 5), ("Чер", 6), ("Лип", 7), ("Сер", 8),
                ("Вер", 9), ("Жов", 10), ("Лис", 11), ("Гру", 12)
            ]
            html_template = """
            <table>
                <thead class="forumline">
                <tr><th>Тема</th><th>Торрент</th><th>Розмір</th><th>S</th><th>L</th><th>Додано</th></tr>
                </thead>
                <tr class="prow1">
                    <td><a href="t1">Test</a></td>
                    <td><a href="download.php?id=1">DL</a></td>
                    <td>100 MB</td>
                    <td><b>5</b></td>
                    <td><b>2</b></td>
                    <td>15-{month}-24</td>
                </tr>
            </table>
            """
            for month_name, month_num in ua_months:
                parser = MazepaHTMLParser()
                parser.feed(html_template.format(month=month_name))
                expected_timestamp = int(datetime(2024, month_num, 15).timestamp())
                assert parser.results[0]["pub_date"] == expected_timestamp, f"Failed for {month_name}"  # nosec B101

        def test_parse_dl_php_link(self) -> None:
            """Test parsing dl.php download links (alternative to download.php)."""
            html = """
            <table>
                <thead class="forumline">
                <tr><th>Тема</th><th>Торрент</th><th>Розмір</th><th>S</th><th>L</th><th>Додано</th></tr>
                </thead>
                <tr class="prow1">
                    <td><a href="t1">Test</a></td>
                    <td><a href="dl.php?id=12345">DL</a></td>
                    <td>100 MB</td>
                    <td><b>5</b></td>
                    <td><b>2</b></td>
                    <td>2024-01-01</td>
                </tr>
            </table>
            """
            parser = MazepaHTMLParser()
            parser.feed(html)
            assert parser.results[0]["link"] == "dl.php?id=12345"  # nosec B101

        def test_parse_viewtopic_link(self) -> None:
            """Test parsing viewtopic.php style description links."""
            html = """
            <table>
                <thead class="forumline">
                <tr><th>Тема</th><th>Торрент</th><th>Розмір</th><th>S</th><th>L</th><th>Додано</th></tr>
                </thead>
                <tr class="prow1">
                    <td><a href="viewtopic.php?t=12345">Test Topic</a></td>
                    <td><a href="download.php?id=1">DL</a></td>
                    <td>100 MB</td>
                    <td><b>5</b></td>
                    <td><b>2</b></td>
                    <td>2024-01-01</td>
                </tr>
            </table>
            """
            parser = MazepaHTMLParser()
            parser.feed(html)
            assert parser.results[0]["desc_link"] == "viewtopic.php?t=12345"  # nosec B101
            assert parser.results[0]["name"] == "Test Topic"  # nosec B101

        def test_parse_topic_html_link(self) -> None:
            """Test parsing topic-xxx-t12345.html style links."""
            html = """
            <table>
                <thead class="forumline">
                <tr><th>Тема</th><th>Торрент</th><th>Розмір</th><th>S</th><th>L</th><th>Додано</th></tr>
                </thead>
                <tr class="prow1">
                    <td><a href="topic-some-name-t12345.html">Topic HTML</a></td>
                    <td><a href="download.php?id=1">DL</a></td>
                    <td>100 MB</td>
                    <td><b>5</b></td>
                    <td><b>2</b></td>
                    <td>2024-01-01</td>
                </tr>
            </table>
            """
            parser = MazepaHTMLParser()
            parser.feed(html)
            assert parser.results[0]["desc_link"] == "topic-some-name-t12345.html"  # nosec B101

        def test_parse_span_seeds_leech(self) -> None:
            """Test parsing seeds/leech from span elements with seedmed/leechmed classes."""
            html = """
            <table>
                <thead class="forumline">
                <tr><th>Тема</th><th>Торрент</th><th>Розмір</th><th>S</th><th>L</th><th>Додано</th></tr>
                </thead>
                <tr class="prow1">
                    <td><a href="t1">Test</a></td>
                    <td><a href="download.php?id=1">DL</a></td>
                    <td>100 MB</td>
                    <td><span class="seedmed">25</span></td>
                    <td><span class="leechmed">8</span></td>
                    <td>2024-01-01</td>
                </tr>
            </table>
            """
            parser = MazepaHTMLParser()
            parser.feed(html)
            assert parser.results[0]["seeds"] == 25  # nosec B101
            assert parser.results[0]["leech"] == 8  # nosec B101

        def test_parse_tCenter_row_class(self) -> None:
            """Test parsing rows with tCenter class."""
            html = """
            <table>
                <thead class="forumline">
                <tr><th>Тема</th><th>Торрент</th><th>Розмір</th><th>S</th><th>L</th><th>Додано</th></tr>
                </thead>
                <tr class="tCenter">
                    <td><a href="t1">Center Row</a></td>
                    <td><a href="download.php?id=1">DL</a></td>
                    <td>100 MB</td>
                    <td><b>5</b></td>
                    <td><b>2</b></td>
                    <td>2024-01-01</td>
                </tr>
            </table>
            """
            parser = MazepaHTMLParser()
            parser.feed(html)
            assert len(parser.results) == 1  # nosec B101
            assert parser.results[0]["name"] == "Center Row"  # nosec B101

        def test_parse_row1_row2_classes(self) -> None:
            """Test parsing rows with row1/row2 classes (alternative to prow1/prow2)."""
            html = """
            <table>
                <thead class="forumline">
                <tr><th>Тема</th><th>Торрент</th><th>Розмір</th><th>S</th><th>L</th><th>Додано</th></tr>
                </thead>
                <tr class="row1">
                    <td><a href="t1">Row1 Test</a></td>
                    <td><a href="download.php?id=1">DL</a></td>
                    <td>100 MB</td>
                    <td><b>5</b></td>
                    <td><b>2</b></td>
                    <td>2024-01-01</td>
                </tr>
                <tr class="row2">
                    <td><a href="t2">Row2 Test</a></td>
                    <td><a href="download.php?id=2">DL</a></td>
                    <td>200 MB</td>
                    <td><b>10</b></td>
                    <td><b>3</b></td>
                    <td>2024-01-02</td>
                </tr>
            </table>
            """
            parser = MazepaHTMLParser()
            parser.feed(html)
            assert len(parser.results) == 2  # nosec B101
            assert parser.results[0]["name"] == "Row1 Test"  # nosec B101
            assert parser.results[1]["name"] == "Row2 Test"  # nosec B101

        def test_parse_div_navigation(self) -> None:
            """Test parsing pagination from div.nav element."""
            html = """
            <div class="nav">
                <a href="tracker.php?nm=test&start=50">2</a>
                <a href="tracker.php?nm=test&start=100">3</a>
            </div>
            """
            parser = MazepaHTMLParser()
            parser.feed(html)
            assert len(parser.next_page_urls) == 2  # nosec B101

    # -------------------------------------------------------------------------
    # Tests for FORUM_MAP
    # -------------------------------------------------------------------------

    class TestForumMap:
        """Tests for FORUM_MAP constant."""

        def test_forum_map_categories_exist(self) -> None:
            expected = ["Український контент", "Озвучений контент", "Спорт", "Музика", "Література"]
            for cat in expected:
                assert cat in FORUM_MAP  # nosec B101

        def test_category_entry_structure(self) -> None:
            for entry in FORUM_MAP.values():
                assert "category_id" in entry  # nosec B101
                assert "forums" in entry  # nosec B101
                assert isinstance(entry["category_id"], int)  # nosec B101

        def test_specific_forum_ids(self) -> None:
            sport = FORUM_MAP["Спорт"]["forums"]
            assert sport["Автоспорт"]["forum_id"] == 77  # nosec B101
            assert sport["Бокс, реслінг, бойові мистецтва"]["forum_id"] == 19  # nosec B101

        def test_subforum_exists(self) -> None:
            music = FORUM_MAP["Музика"]["forums"]
            assert "Рок" in music[""]["subforums"]  # nosec B101
            assert music[""]["subforums"]["Рок"] == 65  # nosec B101

    # -------------------------------------------------------------------------
    # Tests for mazepa_to Engine
    # -------------------------------------------------------------------------

    class TestMazepaToEngine:
        """Tests for mazepa_to engine class."""

        def test_class_attributes(self) -> None:
            assert mazepa_to.url == "https://mazepa.to/"  # nosec B101
            assert mazepa_to.name == "Mazepa — торрент-трекер"  # nosec B101
            assert mazepa_to.login_url == "https://mazepa.to/login.php"  # nosec B101

        def test_supported_categories(self) -> None:
            cats = mazepa_to.supported_categories
            assert Category.all.name in cats  # nosec B101
            assert Category.movies.name in cats  # nosec B101
            assert cats[Category.all.name] == "-1"  # nosec B101

        def test_is_session_valid_success(self) -> None:
            with patch.object(mazepa_to, '__init__', _noop_init):
                engine = mazepa_to()
                engine.opener = MagicMock(spec=OpenerDirector)
                engine.login_url = "https://mazepa.to/login.php"
                mock_response = MagicMock()
                mock_response.geturl.return_value = "https://mazepa.to/"
                engine.opener.open.return_value = mock_response
                assert engine._is_session_valid() is True  # pyright: ignore[reportPrivateUsage]  # nosec B101

        def test_is_session_valid_failure(self) -> None:
            with patch.object(mazepa_to, '__init__', _noop_init):
                engine = mazepa_to()
                engine.opener = MagicMock(spec=OpenerDirector)
                engine.login_url = "https://mazepa.to/login.php"
                mock_response = MagicMock()
                mock_response.geturl.return_value = "https://mazepa.to/login.php"
                engine.opener.open.return_value = mock_response
                assert engine._is_session_valid() is False  # pyright: ignore[reportPrivateUsage]  # nosec B101

        def test_login_already_logged_in(self) -> None:
            with patch.object(mazepa_to, '__init__', _noop_init):
                engine = mazepa_to()
                engine.logged_in = True
                assert engine._login() is True  # pyright: ignore[reportPrivateUsage]  # nosec B101

        def test_login_missing_credentials(self) -> None:
            with patch.object(mazepa_to, '__init__', _noop_init):
                engine = mazepa_to()
                engine.logged_in = False
                engine.cookie_jar = MagicMock()
                engine.cookie_jar.__len__ = MagicMock(return_value=0)
                engine.config = Config(credentials=LoginPayload())
                with pytest.raises(Exception, match="Username and password must be provided"):
                    engine._login()  # pyright: ignore[reportPrivateUsage]

        def test_login_success(self) -> None:
            with patch.object(mazepa_to, '__init__', _noop_init):
                engine = mazepa_to()
                engine.logged_in = False
                engine.cookie_jar = MagicMock()
                engine.cookie_jar.__len__ = MagicMock(return_value=0)
                engine.opener = MagicMock(spec=OpenerDirector)
                engine.config = Config(credentials=LoginPayload(login_username="user", login_password="pass"), cache_login_cookies=False)  # nosec B106
                engine.cookies_file_path = "/tmp/cookies"  # nosec B108
                mock_response = MagicMock()
                mock_response.geturl.return_value = "https://mazepa.to/"
                engine.opener.open.return_value = mock_response
                assert engine._login() is True  # pyright: ignore[reportPrivateUsage]  # nosec B101
                assert engine.logged_in is True  # nosec B101

        def test_search_empty_query(self) -> None:
            with patch.object(mazepa_to, '__init__', _noop_init):
                engine = mazepa_to()
                engine.logged_in = True
                engine.supported_categories = mazepa_to.supported_categories
                engine.search("")  # Should not raise

        def test_search_success(self, sample_html_single_result: str) -> None:
            with patch.object(mazepa_to, '__init__', _noop_init):
                engine = mazepa_to()
                engine.logged_in = True
                engine.opener = MagicMock(spec=OpenerDirector)
                engine.supported_categories = mazepa_to.supported_categories
                mock_response = MagicMock()
                mock_response.status = 200
                mock_response.read.return_value = sample_html_single_result.encode("utf-8")
                engine.opener.open.return_value = mock_response
                with patch.object(engine, '_login', return_value=True):
                    with patch('mazepa_to.prettyPrinter') as mock_printer:
                        engine.search("test query")
                mock_printer.assert_called_once()
                assert mock_printer.call_args[0][0]["name"] == "Test Torrent Name"  # nosec B101

        def test_download_torrent_success(self) -> None:
            with patch.object(mazepa_to, '__init__', _noop_init):
                engine = mazepa_to()
                engine.logged_in = True
                engine.opener = MagicMock(spec=OpenerDirector)
                mock_response = MagicMock()
                mock_response.read.return_value = b"d8:announce...e"
                engine.opener.open.return_value = mock_response
                with patch.object(engine, '_login', return_value=True):
                    with patch('builtins.print') as mock_print:
                        with patch('tempfile.mkstemp', return_value=(1, "/tmp/test.torrent")):  # nosec B108
                            with patch('os.fdopen', mock_open()):
                                engine.download_torrent("https://mazepa.to/download.php?id=123")
                assert "/tmp/test.torrent" in mock_print.call_args[0][0]  # nosec B101 B108

        def test_is_session_valid_network_error(self) -> None:
            with patch.object(mazepa_to, '__init__', _noop_init):
                engine = mazepa_to()
                engine.opener = MagicMock(spec=OpenerDirector)
                engine.login_url = "https://mazepa.to/login.php"
                engine.opener.open.side_effect = URLError("Network error")
                assert engine._is_session_valid() is False  # pyright: ignore[reportPrivateUsage]  # nosec B101

        def test_is_session_valid_index_php_redirect(self) -> None:
            """Test that /index.php redirect is considered valid session."""
            with patch.object(mazepa_to, '__init__', _noop_init):
                engine = mazepa_to()
                engine.opener = MagicMock(spec=OpenerDirector)
                engine.login_url = "https://mazepa.to/login.php"
                mock_response = MagicMock()
                mock_response.geturl.return_value = "https://mazepa.to/index.php"
                engine.opener.open.return_value = mock_response
                assert engine._is_session_valid() is True  # pyright: ignore[reportPrivateUsage]  # nosec B101

        def test_login_http_error(self) -> None:
            with patch.object(mazepa_to, '__init__', _noop_init):
                engine = mazepa_to()
                engine.logged_in = False
                engine.cookie_jar = MagicMock()
                engine.cookie_jar.__len__ = MagicMock(return_value=0)
                engine.opener = MagicMock(spec=OpenerDirector)
                engine.config = Config(credentials=LoginPayload(login_username="user", login_password="pass"))  # nosec B106
                engine.opener.open.side_effect = HTTPError("url", 403, "Forbidden", {}, None)  # type: ignore[arg-type]
                with pytest.raises(Exception, match="Login failed with HTTP 403"):
                    engine._login()  # pyright: ignore[reportPrivateUsage]

        def test_login_index_php_redirect_success(self) -> None:
            """Test that login redirecting to /index.php is considered successful."""
            with patch.object(mazepa_to, '__init__', _noop_init):
                engine = mazepa_to()
                engine.logged_in = False
                engine.cookie_jar = MagicMock()
                engine.cookie_jar.__len__ = MagicMock(return_value=0)
                engine.opener = MagicMock(spec=OpenerDirector)
                engine.config = Config(credentials=LoginPayload(login_username="user", login_password="pass"), cache_login_cookies=False)  # nosec B106
                engine.cookies_file_path = "/tmp/cookies"  # nosec B108
                mock_response = MagicMock()
                mock_response.geturl.return_value = "https://mazepa.to/index.php"
                engine.opener.open.return_value = mock_response
                assert engine._login() is True  # pyright: ignore[reportPrivateUsage]  # nosec B101
                assert engine.logged_in is True  # nosec B101

        def test_search_http_error(self) -> None:
            with patch.object(mazepa_to, '__init__', _noop_init):
                engine = mazepa_to()
                engine.logged_in = True
                engine.opener = MagicMock(spec=OpenerDirector)
                engine.supported_categories = mazepa_to.supported_categories
                engine.opener.open.side_effect = HTTPError("url", 500, "Error", {}, None)  # type: ignore[arg-type]
                with patch.object(engine, '_login', return_value=True):
                    with pytest.raises(Exception, match="Search failed with HTTP 500"):
                        engine.search("test")

        def test_download_torrent_gzip(self) -> None:
            from io import BytesIO
            with patch.object(mazepa_to, '__init__', _noop_init):
                engine = mazepa_to()
                engine.logged_in = True
                engine.opener = MagicMock(spec=OpenerDirector)
                original_data = b"d8:announce...e"
                buf = BytesIO()
                with gzip.GzipFile(fileobj=buf, mode='wb') as gz:
                    gz.write(original_data)
                mock_response = MagicMock()
                mock_response.read.return_value = buf.getvalue()
                mock_response.getheader.return_value = 'gzip'
                engine.opener.open.return_value = mock_response
                with patch.object(engine, '_login', return_value=True):
                    with patch('builtins.print'):
                        with patch('tempfile.mkstemp', return_value=(1, "/tmp/test.torrent")):  # nosec B108
                            with patch('os.fdopen', mock_open()) as mock_file:
                                engine.download_torrent("https://mazepa.to/download.php?id=123")
                mock_file().write.assert_called_once_with(original_data)

        def test_download_torrent_deflate(self) -> None:
            with patch.object(mazepa_to, '__init__', _noop_init):
                engine = mazepa_to()
                engine.logged_in = True
                engine.opener = MagicMock(spec=OpenerDirector)
                original_data = b"d8:announce...e"
                mock_response = MagicMock()
                mock_response.read.return_value = zlib.compress(original_data)
                mock_response.getheader.return_value = 'deflate'
                engine.opener.open.return_value = mock_response
                with patch.object(engine, '_login', return_value=True):
                    with patch('builtins.print'):
                        with patch('tempfile.mkstemp', return_value=(1, "/tmp/test.torrent")):  # nosec B108
                            with patch('os.fdopen', mock_open()) as mock_file:
                                engine.download_torrent("https://mazepa.to/download.php?id=123")
                mock_file().write.assert_called_once_with(original_data)

        def test_fetch_page(self) -> None:
            with patch.object(mazepa_to, '__init__', _noop_init):
                engine = mazepa_to()
                engine.opener = MagicMock(spec=OpenerDirector)
                mock_response = MagicMock()
                mock_response.read.return_value = b"<html>Test</html>"
                engine.opener.open.return_value = mock_response
                assert engine._fetch_page("https://mazepa.to/test") == "<html>Test</html>"  # pyright: ignore[reportPrivateUsage]  # nosec B101

    # -------------------------------------------------------------------------
    # Integration Tests
    # -------------------------------------------------------------------------

    class TestIntegration:
        """Integration tests combining multiple components."""

        def test_full_search_flow(self, sample_html_single_result: str) -> None:
            with patch.object(mazepa_to, '__init__', _noop_init):
                engine = mazepa_to()
                engine.logged_in = False
                engine.cookie_jar = MagicMock()
                engine.cookie_jar.__len__ = MagicMock(return_value=0)
                engine.opener = MagicMock(spec=OpenerDirector)
                engine.config = Config(credentials=LoginPayload(login_username="user", login_password="pass"), cache_login_cookies=False)  # nosec B106
                engine.cookies_file_path = "/tmp/cookies"  # nosec B108
                engine.supported_categories = mazepa_to.supported_categories
                login_response = MagicMock()
                login_response.geturl.return_value = "https://mazepa.to/"
                search_response = MagicMock()
                search_response.status = 200
                search_response.read.return_value = sample_html_single_result.encode("utf-8")
                engine.opener.open.side_effect = [login_response, search_response]
                with patch('mazepa_to.prettyPrinter') as mock_printer:
                    engine.search("test query")
                assert engine.logged_in is True  # nosec B101
                assert mock_printer.call_args[0][0]["name"] == "Test Torrent Name"  # nosec B101

        def test_config_round_trip(self) -> None:
            from dataclasses import asdict
            original = Config(credentials=LoginPayload(login_username="testuser", login_password="testpass"), cache_login_cookies=False)  # nosec B106
            json_config = original.to_json()
            json_str = json.dumps(asdict(json_config))
            parsed = ConfigJson(**json.loads(json_str))
            restored = parsed.to_config()
            assert restored.credentials.login_username == original.credentials.login_username  # nosec B101
            assert restored.cache_login_cookies == original.cache_login_cookies  # nosec B101

        def test_search_payload_encoding(self) -> None:
            from urllib.parse import urlencode
            payload = SearchPayload(nm="test query", f=[16, 32], o=SearchPayload.SortByField.Seeders)
            encoded = urlencode(payload.to_dict(), doseq=True)
            assert "f=16" in encoded  # nosec B101
            assert "f=32" in encoded  # nosec B101
            assert "o=10" in encoded  # nosec B101
