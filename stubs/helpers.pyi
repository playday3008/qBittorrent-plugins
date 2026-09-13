# Generated from: https://github.com/qbittorrent/qBittorrent/blob/e4b704955ad1717725941356c5ecef78bb65b3fa/src/searchengine/nova3/helpers.py
# Commit: e4b704955ad1717725941356c5ecef78bb65b3fa
# Date: 2026-05-25 15:52:50 +0800

import html
import ssl
from collections.abc import Mapping
from typing import Any

def enable_socks_proxy(enable: bool) -> None: ...
htmlentitydecode = html.unescape

def retrieve_url(url: str, custom_headers: Mapping[str, str] = {}, request_data: Any | None = None, ssl_context: ssl.SSLContext | None = None, unescape_html_entities: bool = True) -> str: ...
def download_file(url: str, referer: str | None = None, ssl_context: ssl.SSLContext | None = None) -> str: ...
