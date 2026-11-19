# Generated from: https://github.com/qbittorrent/qBittorrent/blob/9dbd11fc9ad7d31ea348fe2df67b7a9c01215d38/src/searchengine/nova3/nova2.py
# Commit: 9dbd11fc9ad7d31ea348fe2df67b7a9c01215d38
# Date: 2026-10-11 20:46:14 +0800

import abc
from _typeshed import Incomplete
from abc import ABC, abstractmethod
from collections.abc import Iterable

current_path: Incomplete
THREADED: bool
MAX_THREADS: int
Category: Incomplete
EngineModuleName = str

class Engine(ABC, metaclass=abc.ABCMeta):
    name: str
    url: str
    supported_categories: dict[str, str]
    @abstractmethod
    def search(self, query: str, category: str = ...) -> None: ...

engine_dict: dict[EngineModuleName, type[Engine] | None]

def list_engines() -> list[EngineModuleName]: ...
def import_engine(engine_module_name: EngineModuleName) -> type[Engine] | None: ...
def get_capabilities(engines: Iterable[EngineModuleName]) -> str: ...
def run_search(search_params: tuple[type[Engine], str, Category]) -> bool: ...
