# Generated from: https://github.com/qbittorrent/qBittorrent/blob/becfd19e348028bd572056b755f5232976e30146/src/searchengine/nova3/helpers.py
# Commit: becfd19e348028bd572056b755f5232976e30146
# Date: 2025-08-31 22:10:30 +0800

import html
import ssl
from collections.abc import Mapping
from typing import Any

def enable_socks_proxy(enable: bool) -> None: ...
htmlentitydecode = html.unescape

def retrieve_url(url: str, custom_headers: Mapping[str, str] = {}, request_data: Any | None = None, ssl_context: ssl.SSLContext | None = None, unescape_html_entities: bool = True) -> str: ...
def download_file(url: str, referer: str | None = None, ssl_context: ssl.SSLContext | None = None) -> str: ...
