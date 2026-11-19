# Generated from: https://github.com/qbittorrent/qBittorrent/blob/9cc9aeade3b87b659a4ec22b9033fe3878207a06/src/searchengine/nova3/novaprinter.py
# Commit: 9cc9aeade3b87b659a4ec22b9033fe3878207a06
# Date: 2026-10-03 16:35:14 +0800

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
