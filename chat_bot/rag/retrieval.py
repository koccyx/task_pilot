"""Lexical retrieval and rank fusion helpers for RAG search."""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Iterable

from .repository import StoredChunk
from .vector_store import VectorSearchResult


@dataclass(frozen=True)
class LexicalSearchResult:
    """One BM25 search hit."""

    chunk_id: str
    document_id: str
    text: str
    score: float


def bm25_search(
    query: str,
    chunks: list[StoredChunk],
    limit: int,
    k1: float = 1.5,
    b: float = 0.75,
) -> list[LexicalSearchResult]:
    """Rank chunks with BM25."""
    query_terms = _tokenize(query)
    if not query_terms or not chunks:
        return []

    tokenized_chunks = [_tokenize(chunk.text) for chunk in chunks]
    doc_count = len(tokenized_chunks)
    avgdl = sum(len(tokens) for tokens in tokenized_chunks) / doc_count
    doc_frequency: Counter[str] = Counter()
    for tokens in tokenized_chunks:
        doc_frequency.update(set(tokens))

    query_term_counts = Counter(query_terms)
    results: list[LexicalSearchResult] = []
    for chunk, tokens in zip(chunks, tokenized_chunks):
        if not tokens:
            continue
        term_frequency = Counter(tokens)
        score = 0.0
        doc_len = len(tokens)
        for term, query_count in query_term_counts.items():
            tf = term_frequency.get(term, 0)
            if tf == 0:
                continue
            df = doc_frequency[term]
            idf = math.log(1 + (doc_count - df + 0.5) / (df + 0.5))
            denominator = tf + k1 * (1 - b + b * doc_len / avgdl)
            score += query_count * idf * (tf * (k1 + 1) / denominator)
        if score > 0:
            results.append(
                LexicalSearchResult(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    text=chunk.text,
                    score=score,
                )
            )

    results.sort(key=lambda result: result.score, reverse=True)
    return results[:limit]


def reciprocal_rank_fusion(
    dense_results: list[VectorSearchResult],
    lexical_results: list[LexicalSearchResult],
    limit: int,
    k: int = 60,
) -> list[VectorSearchResult]:
    """Fuse dense and lexical ranked lists with RRF."""
    scores: defaultdict[str, float] = defaultdict(float)
    result_by_chunk_id: dict[str, VectorSearchResult] = {}

    for rank, result in enumerate(dense_results, start=1):
        scores[result.chunk_id] += 1.0 / (k + rank)
        result_by_chunk_id[result.chunk_id] = result

    for rank, result in enumerate(lexical_results, start=1):
        scores[result.chunk_id] += 1.0 / (k + rank)
        result_by_chunk_id.setdefault(
            result.chunk_id,
            VectorSearchResult(
                chunk_id=result.chunk_id,
                document_id=result.document_id,
                filename="",
                text=result.text,
                score=result.score,
            ),
        )

    ordered_chunk_ids = sorted(
        scores,
        key=lambda chunk_id: scores[chunk_id],
        reverse=True,
    )
    fused_results = []
    for chunk_id in ordered_chunk_ids[:limit]:
        result = result_by_chunk_id[chunk_id]
        fused_results.append(
            VectorSearchResult(
                chunk_id=result.chunk_id,
                document_id=result.document_id,
                filename=result.filename,
                text=result.text,
                score=scores[chunk_id],
            )
        )
    return fused_results


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[\wа-яА-ЯёЁ]+", text.lower())
