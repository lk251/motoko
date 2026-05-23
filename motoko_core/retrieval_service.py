"""Live retrieval service boundary for Motoko."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


RETRIEVAL_SERVICE_SCHEMA = "retrieval-service-v1"


@dataclass(frozen=True)
class RetrievalServiceResult:
    text: str
    sources: list[dict] = field(default_factory=list)
    diagnostics: dict = field(default_factory=dict)


class RetrievalService:
    """Callback-backed service for live hybrid retrieval orchestration.

    The root facade still owns the concrete stores and model calls. This
    boundary makes that ownership explicit while giving tests a narrow place
    to exercise query-to-context behavior with fake callbacks.
    """

    def __init__(
        self,
        *,
        load_index: Callable,
        retrieve_index_query: Callable,
        render_index_overview: Callable,
        load_topic: Callable,
        retrieve_topic: Callable,
        load_dossier: Callable,
        retrieve_dossier: Callable,
        render_context_items: Callable,
    ) -> None:
        self.load_index = load_index
        self.retrieve_index_query = retrieve_index_query
        self.render_index_overview = render_index_overview
        self.load_topic = load_topic
        self.retrieve_topic = retrieve_topic
        self.load_dossier = load_dossier
        self.retrieve_dossier = retrieve_dossier
        self.render_context_items = render_context_items

    def retrieve_index(self, index: dict, query: str) -> RetrievalServiceResult:
        text, sources = self.retrieve_index_query(index, query)
        return RetrievalServiceResult(
            text=text,
            sources=list(sources),
            diagnostics={"schema": RETRIEVAL_SERVICE_SCHEMA, "kind": "index", "source_count": len(sources)},
        )

    def render_attached_context(self, items: list[dict], query: str) -> RetrievalServiceResult:
        text, sources = self.render_context_items(
            items,
            query,
            load_index=self.load_index,
            render_index_query=self.retrieve_index_query,
            render_index_overview=self.render_index_overview,
            load_topic=self.load_topic,
            render_topic=self.retrieve_topic,
            load_dossier=self.load_dossier,
            render_dossier=self.retrieve_dossier,
        )
        return RetrievalServiceResult(
            text=text,
            sources=list(sources),
            diagnostics={
                "schema": RETRIEVAL_SERVICE_SCHEMA,
                "kind": "attached-context",
                "item_count": len(items),
                "source_count": len(sources),
            },
        )
