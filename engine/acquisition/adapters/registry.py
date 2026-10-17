from pathlib import Path
from typing import Any
from engine.acquisition.adapters.base import BaseSourceAdapter
from engine.acquisition.adapters.local_folder import LocalFolderAdapter
from engine.acquisition.adapters.zip_archive import ZipArchiveAdapter
from engine.acquisition.adapters.generic_web import GenericAuthorizedWebAdapter

class AdapterRegistry:
    def __init__(self):
        self._adapters: list[BaseSourceAdapter] = []

    def register(self, adapter: BaseSourceAdapter) -> None:
        self._adapters.append(adapter)

    def get_adapter_for(self, source: str | Path | dict) -> BaseSourceAdapter:
        for adapter in self._adapters:
            if adapter.can_handle(source):
                return adapter
        raise ValueError(f"No suitable source adapter found for source: {source}")

    def get_adapter_by_id(self, adapter_id: str) -> BaseSourceAdapter:
        for adapter in self._adapters:
            if adapter.adapter_id == adapter_id:
                return adapter
        raise KeyError(f"Adapter not found: {adapter_id}")

    def list_adapters(self) -> list[dict[str, str]]:
        return [
            {"id": a.adapter_id, "name": a.display_name}
            for a in self._adapters
        ]

def get_default_registry() -> AdapterRegistry:
    registry = AdapterRegistry()
    registry.register(LocalFolderAdapter())
    registry.register(ZipArchiveAdapter())
    registry.register(GenericAuthorizedWebAdapter())
    return registry
