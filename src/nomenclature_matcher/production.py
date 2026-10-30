from __future__ import annotations

import logging
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path

from .bm25_store import BM25Store
from .application.matching import match_products
from .application.competitor_resolver import CompetitorResolver
from .application.ports import (
    CollectionReadinessPort,
    MatcherPort,
    RequestHistoryPort,
    ResourceScopePort,
)
from .documents import load_products_from_csv
from .embeddings import OpenAIEmbedder
from .hybrid_retriever import HybridRetriever
from .infrastructure.postgres_history import PostgresRequestHistory
from .infrastructure.competitor_catalog_registry import CatalogRegistry
from .infrastructure.competitor_knowledge_store import CompetitorKnowledgeStore
from .infrastructure.telemetry_adapter import ObservabilityTelemetry
from .matcher import NomenclatureMatcher
from .observability import (
    ObservedEmbedder,
    ObservedQdrantStore,
    ObservedQueryInterpreter,
    ObservedReranker,
)
from .qdrant_store import QdrantStore
from .query_interpreter import DeepSeekQueryInterpreter
from .reranker import DeepSeekReranker
from .settings import Settings
from .web_search_mcp import MCPWebSearchLookup

logger = logging.getLogger(__name__)


@dataclass
class ProductionRuntime:
    settings: Settings
    matcher: MatcherPort
    qdrant_store: CollectionReadinessPort
    history: RequestHistoryPort
    resources: ResourceScopePort = field(default_factory=ExitStack, repr=False)

    def ready(self) -> bool:
        if not self.history.ping():
            return False
        try:
            return self.qdrant_store.collection_exists(
                self.settings.qdrant_collection_alias
            )
        except Exception:
            return False

    def close(self) -> None:
        self.resources.close()


def _validate_runtime_settings(settings: Settings) -> None:
    missing = []
    if not settings.openai_api_key:
        missing.append("OPENAI_API_KEY")
    if not settings.deepseek_api_key:
        missing.append("DEEPSEEK_API_KEY")
    if not settings.database_url.strip():
        missing.append("DATABASE_URL")
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    auth_token = settings.api_auth_token.get_secret_value()
    if settings.app_env.strip().lower() in {"production", "prod"}:
        if len(auth_token) < 32:
            raise RuntimeError(
                "API_AUTH_TOKEN must contain at least 32 characters in production"
            )

    csv_path = Path(settings.product_csv_path)
    if not csv_path.is_file():
        raise RuntimeError(f"Product catalog CSV not found: {csv_path}")


def _warm_web_search(matcher: NomenclatureMatcher) -> bool:
    lookup = getattr(matcher, "competitor_lookup", None)
    warmup = getattr(lookup, "warmup", None)
    if not callable(warmup):
        return True
    try:
        warmup()
    except Exception:
        logger.exception(
            "Web search MCP warmup failed; starting API with web enrichment temporarily bypassed"
        )
        return False
    logger.info("Web search MCP warmup completed")
    return True


def build_production_runtime(settings: Settings | None = None) -> ProductionRuntime:
    settings = settings or Settings()
    logging.basicConfig(
        level=getattr(logging, str(settings.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    resources = ExitStack()
    try:
        _validate_runtime_settings(settings)
        products = load_products_from_csv(settings.product_csv_path)

        base_embedder = OpenAIEmbedder(settings)
        resources.callback(base_embedder.client.close)
        embedder = ObservedEmbedder(base_embedder, settings)

        base_qdrant_store = QdrantStore(settings)
        resources.callback(base_qdrant_store.client.close)
        qdrant_store = ObservedQdrantStore(base_qdrant_store, settings)

        if not qdrant_store.collection_exists(settings.qdrant_collection_alias):
            raise RuntimeError(
                "Qdrant collection "
                f"{settings.qdrant_collection_alias!r} is not available. "
                "Restore the champion snapshot or rebuild the index before starting the API."
            )

        base_interpreter = DeepSeekQueryInterpreter(settings)
        resources.callback(base_interpreter.client.close)
        query_interpreter = ObservedQueryInterpreter(base_interpreter, settings)

        base_reranker = DeepSeekReranker(settings)
        resources.callback(base_reranker.client.close)
        reranker = ObservedReranker(base_reranker, settings)
        telemetry = ObservabilityTelemetry()

        competitor_lookup = (
            MCPWebSearchLookup(settings) if settings.web_search_enabled else None
        )
        competitor_resolver = None
        if settings.competitor_resolver_enabled:
            competitor_resolver = CompetitorResolver(
                store=CompetitorKnowledgeStore(settings.competitor_kb_path),
                registry=CatalogRegistry(settings.competitor_catalog_registry_path),
            )

        matcher = NomenclatureMatcher(
            embedder,
            qdrant_store,
            settings,
            reranker=reranker,
            hybrid_retriever=HybridRetriever(
                embedder,
                qdrant_store,
                BM25Store(products),
                settings,
            ),
            query_interpreter=query_interpreter,
            competitor_lookup=competitor_lookup,
            competitor_resolver=competitor_resolver,
            telemetry=telemetry,
        )
        lookup = getattr(matcher, "competitor_lookup", None)
        close_lookup = getattr(lookup, "close", None)
        if callable(close_lookup):
            resources.callback(close_lookup)
        _warm_web_search(matcher)

        history = PostgresRequestHistory(settings)
        history.open()
        resources.callback(history.close)
    except BaseException:
        try:
            resources.close()
        except Exception:
            logger.exception("Failed to close resources after runtime startup failure")
        raise

    logger.info(
        "Production runtime ready: products=%s qdrant_collection=%s",
        len(products),
        settings.qdrant_collection_alias,
    )
    return ProductionRuntime(
        settings=settings,
        matcher=matcher,
        qdrant_store=qdrant_store,
        history=history,
        resources=resources.pop_all(),
    )
