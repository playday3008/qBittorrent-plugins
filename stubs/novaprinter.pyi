# Generated from: https://github.com/qbittorrent/qBittorrent/blob/8fc5d0914d15e735ca33553304435dc618b173b6/src/searchengine/nova3/novaprinter.py
# Commit: 8fc5d0914d15e735ca33553304435dc618b173b6
# Date: 2025-04-20 16:47:45 +0800

from typing_extensions import TypedDict

class SearchResults(TypedDict):
    link: str
    name: str
    size: float | int | str
    seeds: int
    leech: int
    engine_url: str
    desc_link: str
    pub_date: int

def prettyPrinter(dictionary: SearchResults) -> None: ...
def anySizeToBytes(size_string: float | int | str) -> int: ...
