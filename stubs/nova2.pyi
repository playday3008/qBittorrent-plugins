# Generated from: https://github.com/qbittorrent/qBittorrent/blob/8e4d88bf59e3c3c5e21ba03502b37a6048de1659/src/searchengine/nova3/nova2.py
# Commit: 8e4d88bf59e3c3c5e21ba03502b37a6048de1659
# Date: 2026-05-18 22:12:03 +0800

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
