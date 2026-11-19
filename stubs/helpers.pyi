# Generated from: https://github.com/qbittorrent/qBittorrent/blob/d494d1b764edc2ca681b84ef582babfee724e110/src/searchengine/nova3/helpers.py
# Commit: d494d1b764edc2ca681b84ef582babfee724e110
# Date: 2026-10-18 19:34:31 +0800

import html
import ssl
from collections.abc import Mapping
from typing import Any

def enable_socks_proxy(enable: bool) -> None: ...
htmlentitydecode = html.unescape

def retrieve_url(url: str, custom_headers: Mapping[str, str] = {}, request_data: Any | None = None, ssl_context: ssl.SSLContext | None = None, unescape_html_entities: bool = True) -> str: ...
def download_file(url: str, referer: str | None = None, ssl_context: ssl.SSLContext | None = None) -> str: ...
