"""Final reranking helpers for RAG search results."""

from __future__ import annotations

import re
from collections import Counter
from typing import Protocol

from .vector_store import VectorSearchResult


class SearchReranker(Protocol):
    """Rerank already retrieved RAG candidates."""

    def rerank(
        self,
        query: str,
        results: list[VectorSearchResult],
        limit: int,
    ) -> list[VectorSearchResult]:
        """Return final ordered RAG results."""


class NoopReranker:
    """Keep retrieval order unchanged."""

    def rerank(
        self,
        query: str,
        results: list[VectorSearchResult],
        limit: int,
    ) -> list[VectorSearchResult]:
        _ = query
        return results[:limit]


class LexicalReranker:
    """Rerank candidates with lightweight query-text lexical matching."""

    def rerank(
        self,
        query: str,
        results: list[VectorSearchResult],
        limit: int,
    ) -> list[VectorSearchResult]:
        query_terms = _tokenize(query)
        if not query_terms or not results:
            return results[:limit]

        scored_results = []
        total_results = len(results)
        for rank, result in enumerate(results, start=1):
            rerank_score = self._score(
                query=query,
                query_terms=query_terms,
                text=result.text,
                rank=rank,
                total_results=total_results,
            )
            scored_results.append((rerank_score, result))

        scored_results.sort(key=lambda item: item[0], reverse=True)
        return [
            VectorSearchResult(
                chunk_id=result.chunk_id,
                document_id=result.document_id,
                filename=result.filename,
                text=result.text,
                score=score,
            )
            for score, result in scored_results[:limit]
        ]

    @staticmethod
    def _score(
        query: str,
        query_terms: list[str],
        text: str,
        rank: int,
        total_results: int,
    ) -> float:
        text_terms = _tokenize(text)
        if not text_terms:
            return 0.0

        unique_query_terms = set(query_terms)
        text_term_counts = Counter(text_terms)
        matched_terms = [
            term for term in unique_query_terms if text_term_counts.get(term, 0) > 0
        ]
        coverage = len(matched_terms) / len(unique_query_terms)
        density = sum(text_term_counts[term] for term in query_terms) / len(text_terms)
        exact_phrase_bonus = 0.2 if query.lower().strip() in text.lower() else 0.0
        retrieval_order_bonus = (total_results - rank + 1) / max(total_results, 1) * 0.05
        return coverage + density + exact_phrase_bonus + retrieval_order_bonus


def build_reranker(provider: str, enabled: bool) -> SearchReranker:
    """Build a configured RAG reranker."""
    if not enabled:
        return NoopReranker()
    normalized_provider = provider.lower().strip()
    if normalized_provider == "lexical":
        return LexicalReranker()
    if normalized_provider in {"none", "noop"}:
        return NoopReranker()
    raise ValueError(f"Unsupported RAG reranker provider: {provider}")


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[\wа-яА-ЯёЁ]+", text.lower())
