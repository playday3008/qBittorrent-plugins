# Generated from: https://github.com/qbittorrent/qBittorrent/blob/b95feb648c06fbc720f402fc1e89c952709a0370/src/searchengine/nova3/helpers.py
# Commit: b95feb648c06fbc720f402fc1e89c952709a0370
# Date: 2026-03-15 17:38:12 +0800

import html
import ssl
from collections.abc import Mapping
from typing import Any

def enable_socks_proxy(enable: bool) -> None: ...
htmlentitydecode = html.unescape

def retrieve_url(url: str, custom_headers: Mapping[str, str] = {}, request_data: Any | None = None, ssl_context: ssl.SSLContext | None = None, unescape_html_entities: bool = True) -> str: ...
def download_file(url: str, referer: str | None = None, ssl_context: ssl.SSLContext | None = None) -> str: ...
