# Generated from: https://github.com/qbittorrent/qBittorrent/blob/e4b704955ad1717725941356c5ecef78bb65b3fa/src/searchengine/nova3/novaprinter.py
# Commit: e4b704955ad1717725941356c5ecef78bb65b3fa
# Date: 2026-05-25 15:52:50 +0800

from typing import NotRequired
from typing_extensions import TypedDict

class SearchResults(TypedDict):
    link: str
    name: str
    size: float | int | str
    seeds: int
    leech: int
    engine_url: str
    desc_link: NotRequired[str]
    pub_date: NotRequired[int]

def prettyPrinter(dictionary: SearchResults) -> None: ...
def anySizeToBytes(size_string: float | int | str) -> int: ...
