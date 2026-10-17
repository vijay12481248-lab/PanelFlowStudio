from engine.acquisition.adapters.base import BaseSourceAdapter
from engine.acquisition.adapters.local_folder import LocalFolderAdapter
from engine.acquisition.adapters.zip_archive import ZipArchiveAdapter
from engine.acquisition.adapters.generic_web import GenericAuthorizedWebAdapter
from engine.acquisition.adapters.registry import AdapterRegistry, get_default_registry

__all__ = [
    "BaseSourceAdapter",
    "LocalFolderAdapter",
    "ZipArchiveAdapter",
    "GenericAuthorizedWebAdapter",
    "AdapterRegistry",
    "get_default_registry",
]
