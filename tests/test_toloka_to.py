"""Tests for toloka_to search engine plugin."""

# ruff: noqa: D102, N802, S101, S105, S106, S108, SLF001, SIM117, PLR2004

import gzip
import json
import sys
import tempfile
import zlib
from collections.abc import Generator
from dataclasses import asdict
from datetime import datetime
from http.client import HTTPResponse
from http.cookiejar import LWPCookieJar
from io import BytesIO
from pathlib import Path
from unittest.mock import mock_open, patch
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import OpenerDirector

import pytest

# Add plugins directory to path for imports
sys.path.insert(0, "plugins/search")

from nova2 import Category  # pyright: ignore[reportMissingModuleSource]

from plugins.search.toloka_to import (
    FORUM_MAP,
    Config,
    ConfigJson,
    LoginPayload,
    SearchPayload,
    TolokaHTMLParser,
    size_string_to_bytes,
    toloka_to,
)
from tests.mock_utils import mock, when


def _noop_init(self: object) -> None:
    """No-op initializer for mocking __init__ methods."""


# -------------------------------------------------------------------------
# Test Fixtures
# -------------------------------------------------------------------------


@pytest.fixture
def sample_html_single_result() -> str:
    """Sample HTML with a single search result."""
    return """
    <table>
        <tr>
            <th>Назва</th>
            <th>Посил</th>
            <th>Розмір</th>
            <th>S</th>
            <th>L</th>
            <th>Додано</th>
        </tr>
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
        <tr>
            <th>Назва</th>
            <th>Посил</th>
            <th>Розмір</th>
            <th>S</th>
            <th>L</th>
            <th>Додано</th>
        </tr>
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
        <tr>
            <th>Назва</th>
            <th>Посил</th>
            <th>Розмір</th>
            <th>S</th>
            <th>L</th>
            <th>Додано</th>
        </tr>
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
        cache_login_cookies=True,
    )


@pytest.fixture
def temp_dir() -> Generator[str, None, None]:
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


# -------------------------------------------------------------------------
# Tests for Payload Classes
# -------------------------------------------------------------------------


class TestSizeStringToBytes:
    """Tests for size_string_to_bytes function."""

    def test_english_units(self) -> None:
        assert size_string_to_bytes("500 MB") == (500 * 1024**2)  # nosec B101
        assert size_string_to_bytes("2.3 GB") == int(2.3 * 1024**3)  # nosec B101
        assert size_string_to_bytes("750 KB") == (750 * 1024)  # nosec B101
        assert size_string_to_bytes("1 TB") == (1 * 1024**4)  # nosec B101
        assert size_string_to_bytes("1024 B") == 1024  # nosec B101

    def test_ukrainian_units(self) -> None:
        assert size_string_to_bytes("500 МБ") == (500 * 1024**2)  # nosec B101
        assert size_string_to_bytes("2.3 ГБ") == int(2.3 * 1024**3)  # nosec B101
        assert size_string_to_bytes("750 КБ") == (750 * 1024)  # nosec B101
        assert size_string_to_bytes("1 ТБ") == (1 * 1024**4)  # nosec B101
        assert size_string_to_bytes("1024 Б") == 1024  # nosec B101

    def test_non_breaking_space(self) -> None:
        """Test handling of non-breaking space (\\xa0) from HTML &nbsp;."""  # noqa: D301
        assert size_string_to_bytes("2.6\xa0GB") == int(2.6 * 1024**3)  # nosec B101
        assert size_string_to_bytes("208\xa0MB") == (208 * 1024**2)  # nosec B101

    def test_no_space(self) -> None:
        """Test sizes without space between number and unit."""
        assert size_string_to_bytes("500MB") == (500 * 1024**2)  # nosec B101
        assert size_string_to_bytes("2.3GB") == int(2.3 * 1024**3)  # nosec B101

    def test_comma_decimal_separator(self) -> None:
        """Test handling of comma as decimal separator (European format)."""
        assert size_string_to_bytes("2,3 GB") == int(2.3 * 1024**3)  # nosec B101
        assert size_string_to_bytes("1,5 MB") == int(1.5 * 1024**2)  # nosec B101

    def test_case_insensitive_english(self) -> None:
        """Test case-insensitive matching for English units."""
        assert size_string_to_bytes("500 mb") == (500 * 1024**2)  # nosec B101
        assert size_string_to_bytes("2.3 gb") == int(2.3 * 1024**3)  # nosec B101
        assert size_string_to_bytes("750 Kb") == (750 * 1024)  # nosec B101

    def test_invalid_input(self) -> None:
        """Test that invalid inputs return -1."""
        assert size_string_to_bytes("") == -1  # nosec B101
        assert size_string_to_bytes("invalid") == -1  # nosec B101
        assert size_string_to_bytes("500") == -1  # nosec B101  # no unit
        assert size_string_to_bytes("GB 500") == -1  # nosec B101  # wrong order


class TestPayload:
    """Tests for payload classes."""

    def test_to_dict_with_strings(self) -> None:
        payload = LoginPayload(username="user", password="pass")  # nosec B106
        result = payload.to_dict()
        assert result["username"] == "user"  # nosec B101
        assert result["password"] == "pass"  # nosec B101

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
        assert payload.username == ""  # nosec B101
        assert payload.password == ""  # nosec B101, B105
        assert payload.autologin == "on"  # nosec B101
        assert payload.ssl == "on"  # nosec B101
        assert payload.login == "Вхід"  # nosec B101

    def test_custom_values(self) -> None:
        payload = LoginPayload(username="myuser", password="mypass", autologin=None, ssl=None)  # nosec B106
        assert payload.username == "myuser"  # nosec B101
        assert payload.autologin is None  # nosec B101


class TestConfig:
    """Tests for Config dataclass."""

    def test_default_cache_login_cookies(self) -> None:
        config = Config(credentials=LoginPayload())
        assert config.cache_login_cookies is True  # nosec B101

    def test_to_json_conversion(self) -> None:
        config = Config(credentials=LoginPayload(username="user", password="pass"), cache_login_cookies=False)  # nosec B106
        json_config = config.to_json()
        assert json_config.username == "user"  # nosec B101
        assert json_config.cache_login_cookies is False  # nosec B101


class TestConfigJson:
    """Tests for ConfigJson dataclass."""

    def test_to_config_conversion(self) -> None:
        json_config = ConfigJson(username="testuser", password="testpass", cache_login_cookies=False)  # nosec B106
        config = json_config.to_config()
        assert config.credentials.username == "testuser"  # nosec B101
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

    def test_release_status_enum_values(self) -> None:
        assert SearchPayload.ReleaseStatus.Any.value == -1  # nosec B101
        assert SearchPayload.ReleaseStatus.Gold.value == 1  # nosec B101

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
# Tests for TolokaHTMLParser
# -------------------------------------------------------------------------


class TestTolokaHTMLParser:
    """Tests for TolokaHTMLParser class."""

    def test_parse_single_result(self, sample_html_single_result: str) -> None:
        parser = TolokaHTMLParser()
        parser.feed(sample_html_single_result)
        assert len(parser.results) == 1  # nosec B101
        result = parser.results[0]
        assert result["name"] == "Test Torrent Name"  # nosec B101
        assert result["link"] == "download.php?id=12345"  # nosec B101
        assert result["size"] == int(1.5 * 1024**3)  # 1.5 GB in bytes  # nosec B101
        assert result["seeds"] == 10  # nosec B101
        assert result["leech"] == 5  # nosec B101

    def test_parse_multiple_results(self, sample_html_multiple_results: str) -> None:
        parser = TolokaHTMLParser()
        parser.feed(sample_html_multiple_results)
        assert len(parser.results) == 3  # nosec B101
        assert parser.results[0]["name"] == "First Torrent"  # nosec B101
        assert parser.results[2]["name"] == "Third Torrent"  # nosec B101

    def test_parse_pagination_links(self, sample_html_with_pagination: str) -> None:
        parser = TolokaHTMLParser()
        parser.feed(sample_html_with_pagination)
        assert len(parser.next_page_urls) == 3  # nosec B101
        assert "tracker.php?nm=test&start=50" in parser.next_page_urls  # nosec B101

    def test_parse_pub_date(self, sample_html_single_result: str) -> None:
        parser = TolokaHTMLParser()
        parser.feed(sample_html_single_result)
        expected_timestamp = int(datetime.strptime("2024-01-15", "%Y-%m-%d").timestamp())
        assert parser.results[0]["pub_date"] == expected_timestamp  # nosec B101

    def test_parse_various_sizes(self) -> None:
        html = """
        <table>
            <tr><th>Назва</th><th>Посил</th><th>Розмір</th><th>S</th><th>L</th><th>Додано</th></tr>
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
        # Size string -> expected bytes
        size_tests = [
            ("500 MB", (500 * 1024**2)),
            ("2.3 GB", int(2.3 * 1024**3)),
            ("750 KB", (750 * 1024)),
            ("1 TB", (1 * 1024**4)),
        ]
        for size_str, expected_bytes in size_tests:
            parser = TolokaHTMLParser()
            parser.feed(html.format(size=size_str))
            assert parser.results[0]["size"] == expected_bytes  # nosec B101

    def test_empty_search_result_defaults(self) -> None:
        result = TolokaHTMLParser._empty_search_result()  # pyright: ignore[reportPrivateUsage]
        assert result["link"] == ""  # nosec B101
        assert result["size"] == -1  # nosec B101
        assert result["seeds"] == -1  # nosec B101
        assert result["pub_date"] == -1  # nosec B101

    def test_header_to_field_mapping(self) -> None:
        assert TolokaHTMLParser.HEADER_TO_FIELD["Назва"] == "name"  # nosec B101
        assert TolokaHTMLParser.HEADER_TO_FIELD["S"] == "seeds"  # nosec B101

    def test_parse_missing_link_skips_result(self) -> None:
        html = """
        <table>
            <tr><th>Назва</th><th>Посил</th><th>Розмір</th><th>S</th><th>L</th><th>Додано</th></tr>
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
        parser = TolokaHTMLParser()
        parser.feed(html)
        assert len(parser.results) == 0  # nosec B101

    def test_parse_invalid_seeds_leech(self) -> None:
        html = """
        <table>
            <tr><th>Назва</th><th>Посил</th><th>Розмір</th><th>S</th><th>L</th><th>Додано</th></tr>
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
        parser = TolokaHTMLParser()
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
        parser = TolokaHTMLParser()
        parser.feed(html)
        assert parser.next_page_urls.count("tracker.php?nm=test&start=50") == 1  # nosec B101

    def test_parse_empty_html(self) -> None:
        parser = TolokaHTMLParser()
        parser.feed("")
        assert len(parser.results) == 0  # nosec B101

    def test_column_reordering(self) -> None:
        html = """
        <table>
            <tr><th>Розмір</th><th>Назва</th><th>S</th><th>Посил</th><th>L</th><th>Додано</th></tr>
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
        parser = TolokaHTMLParser()
        parser.feed(html)
        assert parser.results[0]["name"] == "Reordered"  # nosec B101
        assert parser.results[0]["size"] == (500 * 1024**2)  # 500 MB in bytes  # nosec B101
        assert parser.results[0]["seeds"] == 15  # nosec B101


# -------------------------------------------------------------------------
# Tests for FORUM_MAP
# -------------------------------------------------------------------------


class TestForumMap:
    """Tests for FORUM_MAP constant."""

    def test_forum_map_categories_exist(self) -> None:
        expected = ["Фільми українською", "Українська музика", "Література українською", "Ігри українською"]
        for cat in expected:
            assert cat in FORUM_MAP  # nosec B101

    def test_category_entry_structure(self) -> None:
        for entry in FORUM_MAP.values():
            assert "category_id" in entry  # nosec B101
            assert "forums" in entry  # nosec B101
            assert isinstance(entry["category_id"], int)  # nosec B101

    def test_specific_forum_ids(self) -> None:
        films = FORUM_MAP["Фільми українською"]["forums"]
        assert films["Українське кіно"]["forum_id"] == 117  # nosec B101
        assert films["Українське озвучення"]["subforums"]["Фільми"] == 16  # nosec B101

    def test_all_forum_ids_unique(self) -> None:
        forum_ids: list[int] = []
        for cat_entry in FORUM_MAP.values():
            for forum in cat_entry["forums"].values():
                forum_ids.append(forum["forum_id"])
                forum_ids.extend(forum["subforums"].values())
        assert len(forum_ids) == len(set(forum_ids))  # nosec B101


# -------------------------------------------------------------------------
# Tests for toloka_to Engine
# -------------------------------------------------------------------------


class TestTolokaToEngine:
    """Tests for toloka_to engine class."""

    def test_class_attributes(self) -> None:
        assert toloka_to.url == "https://toloka.to/"  # nosec B101
        assert toloka_to.name == "Гуртом — торрент-толока"  # nosec B101
        assert toloka_to.login_url == "https://toloka.to/login.php"  # nosec B101

    def test_supported_categories(self) -> None:
        cats = toloka_to.supported_categories
        assert Category.all.name in cats  # nosec B101
        assert Category.movies.name in cats  # nosec B101
        assert cats[Category.all.name] == "-1"  # nosec B101

    def test_is_session_valid_success(self) -> None:
        with patch.object(toloka_to, "__init__", _noop_init):
            engine = toloka_to()
            engine.opener = mock(OpenerDirector)
            engine.login_url = "https://toloka.to/login.php"
            response = mock(HTTPResponse)
            when(response.geturl).returns("https://toloka.to/")
            when(engine.opener.open).returns(response)
            assert engine._is_session_valid() is True  # pyright: ignore[reportPrivateUsage]  # nosec B101

    def test_is_session_valid_failure(self) -> None:
        with patch.object(toloka_to, "__init__", _noop_init):
            engine = toloka_to()
            engine.opener = mock(OpenerDirector)
            engine.login_url = "https://toloka.to/login.php"
            response = mock(HTTPResponse)
            when(response.geturl).returns("https://toloka.to/login.php")
            when(engine.opener.open).returns(response)
            assert engine._is_session_valid() is False  # pyright: ignore[reportPrivateUsage]  # nosec B101

    def test_is_session_valid_network_error(self) -> None:
        with patch.object(toloka_to, "__init__", _noop_init):
            engine = toloka_to()
            engine.opener = mock(OpenerDirector)
            engine.login_url = "https://toloka.to/login.php"
            when(engine.opener.open).raises(URLError("Network error"))
            assert engine._is_session_valid() is False  # pyright: ignore[reportPrivateUsage]  # nosec B101

    def test_login_already_logged_in(self) -> None:
        with patch.object(toloka_to, "__init__", _noop_init):
            engine = toloka_to()
            engine.logged_in = True
            assert engine._login() is True  # pyright: ignore[reportPrivateUsage]  # nosec B101

    def test_login_missing_credentials(self) -> None:
        with patch.object(toloka_to, "__init__", _noop_init):
            engine = toloka_to()
            engine.logged_in = False
            engine.cookie_jar = mock(LWPCookieJar)
            when(engine.cookie_jar.__len__).returns(0)
            engine.config = Config(credentials=LoginPayload())
            with pytest.raises(Exception, match="Username and password must be provided"):
                engine._login()  # pyright: ignore[reportPrivateUsage]

    def test_login_success(self) -> None:
        with patch.object(toloka_to, "__init__", _noop_init):
            engine = toloka_to()
            engine.logged_in = False
            engine.cookie_jar = mock(LWPCookieJar)
            when(engine.cookie_jar.__len__).returns(0)
            engine.opener = mock(OpenerDirector)
            engine.config = Config(
                credentials=LoginPayload(username="user", password="pass"),  # nosec B106
                cache_login_cookies=False,
            )
            engine.cookies_file_path = Path("/tmp/cookies")  # nosec B108
            response = mock(HTTPResponse)
            when(response.geturl).returns("https://toloka.to/")
            when(engine.opener.open).returns(response)
            assert engine._login() is True  # pyright: ignore[reportPrivateUsage]  # nosec B101
            assert engine.logged_in is True  # nosec B101

    def test_login_http_error(self) -> None:
        with patch.object(toloka_to, "__init__", _noop_init):
            engine = toloka_to()
            engine.logged_in = False
            engine.cookie_jar = mock(LWPCookieJar)
            when(engine.cookie_jar.__len__).returns(0)
            engine.opener = mock(OpenerDirector)
            engine.config = Config(credentials=LoginPayload(username="user", password="pass"))  # nosec B106
            when(engine.opener.open).raises(HTTPError("url", 403, "Forbidden", {}, None))  # type: ignore[arg-type]
            with pytest.raises(Exception, match="Login failed with HTTP 403"):
                engine._login()  # pyright: ignore[reportPrivateUsage]

    def test_search_empty_query(self) -> None:
        with patch.object(toloka_to, "__init__", _noop_init):
            engine = toloka_to()
            engine.logged_in = True
            engine.supported_categories = toloka_to.supported_categories
            engine.search("")  # Should not raise

    def test_search_success(self, sample_html_single_result: str) -> None:
        with patch.object(toloka_to, "__init__", _noop_init):
            engine = toloka_to()
            engine.logged_in = True
            engine.opener = mock(OpenerDirector)
            engine.supported_categories = toloka_to.supported_categories
            response = mock(HTTPResponse)
            response.status = 200
            when(response.read).returns(sample_html_single_result.encode("utf-8"))
            when(engine.opener.open).returns(response)
            with patch.object(engine, "_login", return_value=True):
                with patch("plugins.search.toloka_to.prettyPrinter") as mock_printer:
                    engine.search("test query")
            mock_printer.assert_called_once()
            assert mock_printer.call_args[0][0]["name"] == "Test Torrent Name"  # nosec B101

    def test_search_http_error(self) -> None:
        with patch.object(toloka_to, "__init__", _noop_init):
            engine = toloka_to()
            engine.logged_in = True
            engine.opener = mock(OpenerDirector)
            engine.supported_categories = toloka_to.supported_categories
            when(engine.opener.open).raises(HTTPError("url", 500, "Error", {}, None))  # type: ignore[arg-type]
            with patch.object(engine, "_login", return_value=True):
                with pytest.raises(Exception, match="Search failed with HTTP 500"):
                    engine.search("test")

    def test_download_torrent_success(self) -> None:
        with patch.object(toloka_to, "__init__", _noop_init):
            engine = toloka_to()
            engine.logged_in = True
            engine.opener = mock(OpenerDirector)
            response = mock(HTTPResponse)
            when(response.read).returns(b"d8:announce...e")
            when(engine.opener.open).returns(response)
            with patch.object(engine, "_login", return_value=True):
                with patch("builtins.print") as mock_print:
                    with patch("tempfile.mkstemp", return_value=(1, "/tmp/test.torrent")):  # nosec B108
                        with patch("os.fdopen", mock_open()):
                            engine.download_torrent("https://toloka.to/download.php?id=123")
            assert "/tmp/test.torrent" in mock_print.call_args[0][0]  # nosec B101 B108

    def test_download_torrent_gzip(self) -> None:
        with patch.object(toloka_to, "__init__", _noop_init):
            engine = toloka_to()
            engine.logged_in = True
            engine.opener = mock(OpenerDirector)
            original_data = b"d8:announce...e"
            buf = BytesIO()
            with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
                gz.write(original_data)
            response = mock(HTTPResponse)
            when(response.read).returns(buf.getvalue())
            when(response.getheader).returns("gzip")
            when(engine.opener.open).returns(response)
            with patch.object(engine, "_login", return_value=True):
                with patch("builtins.print"):
                    with patch("tempfile.mkstemp", return_value=(1, "/tmp/test.torrent")):  # nosec B108
                        with patch("os.fdopen", mock_open()) as mock_file:
                            engine.download_torrent("https://toloka.to/download.php?id=123")
            mock_file().write.assert_called_once_with(original_data)

    def test_download_torrent_deflate(self) -> None:
        with patch.object(toloka_to, "__init__", _noop_init):
            engine = toloka_to()
            engine.logged_in = True
            engine.opener = mock(OpenerDirector)
            original_data = b"d8:announce...e"
            response = mock(HTTPResponse)
            when(response.read).returns(zlib.compress(original_data))
            when(response.getheader).returns("deflate")
            when(engine.opener.open).returns(response)
            with patch.object(engine, "_login", return_value=True):
                with patch("builtins.print"):
                    with patch("tempfile.mkstemp", return_value=(1, "/tmp/test.torrent")):  # nosec B108
                        with patch("os.fdopen", mock_open()) as mock_file:
                            engine.download_torrent("https://toloka.to/download.php?id=123")
            mock_file().write.assert_called_once_with(original_data)

    def test_fetch_page(self) -> None:
        with patch.object(toloka_to, "__init__", _noop_init):
            engine = toloka_to()
            engine.opener = mock(OpenerDirector)
            response = mock(HTTPResponse)
            when(response.read).returns(b"<html>Test</html>")
            when(engine.opener.open).returns(response)
            assert engine._fetch_page("https://toloka.to/test") == "<html>Test</html>"  # pyright: ignore[reportPrivateUsage]  # nosec B101


# -------------------------------------------------------------------------
# Integration Tests
# -------------------------------------------------------------------------


class TestIntegration:
    """Integration tests combining multiple components."""

    def test_full_search_flow(self, sample_html_single_result: str) -> None:
        with patch.object(toloka_to, "__init__", _noop_init):
            engine = toloka_to()
            engine.logged_in = False
            engine.cookie_jar = mock(LWPCookieJar)
            when(engine.cookie_jar.__len__).returns(0)
            engine.opener = mock(OpenerDirector)
            engine.config = Config(
                credentials=LoginPayload(username="user", password="pass"),  # nosec B106
                cache_login_cookies=False,
            )
            engine.cookies_file_path = Path("/tmp/cookies")  # nosec B108
            engine.supported_categories = toloka_to.supported_categories
            login_response = mock(HTTPResponse)
            when(login_response.geturl).returns("https://toloka.to/")
            search_response = mock(HTTPResponse)
            search_response.status = 200
            when(search_response.read).returns(sample_html_single_result.encode("utf-8"))
            when(engine.opener.open).returns(login_response, search_response)
            with patch("plugins.search.toloka_to.prettyPrinter") as mock_printer:
                engine.search("test query")
            assert engine.logged_in is True  # nosec B101
            assert mock_printer.call_args[0][0]["name"] == "Test Torrent Name"  # nosec B101

    def test_config_round_trip(self) -> None:
        original = Config(credentials=LoginPayload(username="testuser", password="testpass"), cache_login_cookies=False)  # nosec B106
        json_config = original.to_json()
        json_str = json.dumps(asdict(json_config))
        parsed = ConfigJson(**json.loads(json_str))
        restored = parsed.to_config()
        assert restored.credentials.username == original.credentials.username  # nosec B101
        assert restored.cache_login_cookies == original.cache_login_cookies  # nosec B101

    def test_search_payload_encoding(self) -> None:
        payload = SearchPayload(nm="test query", f=[16, 32], o=SearchPayload.SortByField.Seeders)
        encoded = urlencode(payload.to_dict(), doseq=True)
        assert "f=16" in encoded  # nosec B101
        assert "f=32" in encoded  # nosec B101
        assert "o=10" in encoded  # nosec B101
