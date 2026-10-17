"""
Strategies package for web acquisition.
"""
from engine.acquisition.web.strategies.base import BaseExtractionStrategy, StrategyResult
from engine.acquisition.web.strategies.direct_document import DirectDocumentStrategy
from engine.acquisition.web.strategies.static_dom import StaticDomStrategy
from engine.acquisition.web.strategies.reader_container import ReaderContainerStrategy
from engine.acquisition.web.strategies.lazy_images import LazyImagesStrategy
from engine.acquisition.web.strategies.embedded_json import EmbeddedJsonStrategy
from engine.acquisition.web.strategies.api_manifest import ApiManifestStrategy
from engine.acquisition.web.strategies.rendered_dom import RenderedDomStrategy
from engine.acquisition.web.strategies.browser_network import BrowserNetworkStrategy
from engine.acquisition.web.strategies.resource_timing import ResourceTimingStrategy
from engine.acquisition.web.strategies.rendered_capture import RenderedCaptureStrategy

__all__ = [
    "BaseExtractionStrategy",
    "StrategyResult",
    "DirectDocumentStrategy",
    "StaticDomStrategy",
    "ReaderContainerStrategy",
    "LazyImagesStrategy",
    "EmbeddedJsonStrategy",
    "ApiManifestStrategy",
    "RenderedDomStrategy",
    "BrowserNetworkStrategy",
    "ResourceTimingStrategy",
    "RenderedCaptureStrategy",
]
