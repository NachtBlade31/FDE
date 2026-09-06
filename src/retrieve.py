"""Retrieval over the CloudServe documentation corpus — A4, FR-06, FR-07.

This component carries the central premise of the whole design. Ines's account of
why the support team does not use her documentation is precise: internal search
"matches on titles and exact terms, and customers do not describe problems in the
words I used for the title. Someone writes *my deployment keeps dying* and my
article is called *resolving container health check failures*. There is no path
between those two phrases in a keyword search."

Semantic retrieval is exactly the path between those two phrases. If it cannot
bridge that gap, assumption AS-01 has failed and the design needs revisiting —
which is why `test_retrieval_bridges_symptom_wording_to_the_article_title` and the
measured hit-rate test exist.

Two design decisions are recorded here.

**Chunking (open decision O-1).** The corpus is 29 articles of 860 to 1,336
characters, ~31.7k characters in total. Each follows the same internal shape:
title, applies-to, symptoms, common causes, numbered resolution steps, notes. The
Dataset Guide warns that "splitting inside a resolution sequence tends to produce
passages that retrieve well but read as incomplete", and a whole article is
already smaller than the chunk size the Setup Guide suggests as a starting point.
Whole-document chunking is therefore the default. `SECTION` is implemented so the
alternative can be measured rather than asserted; see `scripts/compare_chunking.py`.

**Embeddings.** Chroma's built-in embedding function is `all-MiniLM-L6-v2`, the
model the Project Brief specifies, served through onnxruntime. Using it gives us
the required model without `torch` or `sentence-transformers`, which removes about
2.5 GB from a clean-checkout install (decision D-08).
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable, Sequence

from src.config import DEFAULT_RELEVANCE_FLOOR
from src.models import RetrievedPassage

# A query with no alphanumeric content cannot be embedded meaningfully. Returning
# nothing is the correct answer, not an arbitrary nearest neighbour.
_ALNUM = re.compile(r"[^\W_]", re.UNICODE)

# Markdown section headings, used only by the SECTION strategy.
_HEADING = re.compile(r"^#{1,6}\s+.*$", re.MULTILINE)


class ChunkStrategy(str, Enum):
    """How an article is split before embedding."""

    WHOLE = "whole"
    SECTION = "section"


@dataclass(frozen=True)
class Document:
    """One knowledge base article, as supplied."""

    doc_id: str
    title: str
    category: str
    applies_to: str
    content: str
    related_docs: tuple[str, ...] = ()
    last_reviewed_days_ago: int | None = None


@dataclass(frozen=True)
class Chunk:
    """An embedded unit of text that a citation can resolve to.

    `char_start` and `char_end` are offsets into the parent document's content, so
    a citation can be verified against the original article rather than against a
    copy of the text.
    """

    chunk_id: str
    doc_id: str
    title: str
    text: str
    char_start: int
    char_end: int


def _chunk_document(document: Document, strategy: ChunkStrategy) -> list[Chunk]:
    if strategy is ChunkStrategy.WHOLE:
        return [
            Chunk(
                chunk_id=f"{document.doc_id}#0",
                doc_id=document.doc_id,
                title=document.title,
                text=document.content,
                char_start=0,
                char_end=len(document.content),
            )
        ]

    # SECTION: split on markdown headings, keeping each heading with its body so a
    # passage still reads as a unit.
    starts = [m.start() for m in _HEADING.finditer(document.content)]
    if not starts:
        return _chunk_document(document, ChunkStrategy.WHOLE)
    if starts[0] != 0:
        starts.insert(0, 0)
    bounds = list(zip(starts, starts[1:] + [len(document.content)]))

    chunks = []
    for index, (start, end) in enumerate(bounds):
        text = document.content[start:end]
        if not text.strip():
            continue
        chunks.append(
            Chunk(
                chunk_id=f"{document.doc_id}#{index}",
                doc_id=document.doc_id,
                title=document.title,
                text=text,
                char_start=start,
                char_end=end,
            )
        )
    return chunks


class Corpus:
    """The documentation corpus, chunked and indexed by identifier."""

    def __init__(
        self,
        documents: Sequence[Document],
        strategy: ChunkStrategy = ChunkStrategy.WHOLE,
    ) -> None:
        self.documents = list(documents)
        self.strategy = strategy
        self.chunks = [c for d in self.documents for c in _chunk_document(d, strategy)]
        self._by_chunk = {c.chunk_id: c for c in self.chunks}
        self._by_doc = {d.doc_id: d for d in self.documents}

    @classmethod
    def from_records(
        cls, records: Iterable[dict], strategy: ChunkStrategy = ChunkStrategy.WHOLE
    ) -> "Corpus":
        documents = [
            Document(
                doc_id=r["doc_id"],
                title=r.get("title", ""),
                category=r.get("category", ""),
                applies_to=r.get("applies_to", ""),
                content=r.get("content", ""),
                related_docs=tuple(r.get("related_docs", ())),
                last_reviewed_days_ago=r.get("last_reviewed_days_ago"),
            )
            for r in records
        ]
        return cls(documents, strategy)

    @classmethod
    def from_file(
        cls, path: str | Path, strategy: ChunkStrategy = ChunkStrategy.WHOLE
    ) -> "Corpus":
        records = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_records(records, strategy)

    def resolve(self, chunk_id: str) -> Chunk | None:
        """Follow a citation back to the passage it claims to support.

        Returns None for an identifier that is not in the corpus. A6 is checked by
        doing exactly this, so an invented reference must resolve to nothing rather
        than to something plausible.
        """
        return self._by_chunk.get(chunk_id)

    def document(self, doc_id: str) -> Document | None:
        return self._by_doc.get(doc_id)

    def __len__(self) -> int:
        return len(self.chunks)


@dataclass(frozen=True)
class RetrievalResult:
    """What retrieval found, including what it rejected and why.

    "Nothing cleared the floor" and "nothing was close" are different states, and
    only one of them is diagnosable after the fact. Three things need the
    difference:

      - the decision log, whose minimum record carries sources_used with scores;
        an escalation that logs an empty list cannot answer "why did this
        escalate?" at incident review
      - the escalation payload (D3), where "top match DOC-AUTH-002 at 0.38, below
        the 0.40 floor" is actionable for an agent and "no documents" is not
      - calibration, which cannot bin a threshold using only scores that cleared it

    `rejected` is deliberately a separate field. D7 builds citations from
    retrieved chunk ids, so a sub-floor passage reachable from the citation path
    would be a latent A6 violation.
    """

    passages: list[RetrievedPassage]
    rejected: list[RetrievedPassage]
    top_score: float
    floor_applied: float

    @property
    def has_passages(self) -> bool:
        return bool(self.passages)

    @property
    def was_close(self) -> bool:
        """True when something was retrieved but fell short of the floor."""
        return not self.passages and bool(self.rejected)


class Retriever:
    """Semantic search over the corpus, with a relevance floor.

    The floor is what lets retrieval return *nothing*. Build Specification section
    08 names "retrieval that returns something for every query regardless of
    relevance" as a failure, because always returning something hides failure —
    and 143 of the 500 development tickets genuinely have no supporting document.
    """

    DEFAULT_TOP_K = 3

    def __init__(
        self,
        corpus: Corpus,
        relevance_floor: float = DEFAULT_RELEVANCE_FLOOR,
        collection_name: str = "cloudserve-docs",
    ) -> None:
        self.corpus = corpus
        self.relevance_floor = relevance_floor
        self._collection = self._build_index(collection_name)

    def _build_index(self, collection_name: str):
        import chromadb
        from chromadb.utils import embedding_functions

        client = chromadb.EphemeralClient()
        # Chroma shares state across in-process ephemeral clients, so two
        # Retrievers built in one process collide on a fixed name. The suffix
        # keeps each instance independent; the index is rebuilt per instance,
        # which is cheap for a 29-article corpus.
        collection = client.create_collection(
            name=f"{collection_name}-{uuid.uuid4().hex[:8]}",
            # Cosine keeps distances on a bounded, interpretable scale, which is
            # what makes a relevance floor meaningful rather than arbitrary.
            metadata={"hnsw:space": "cosine"},
            embedding_function=embedding_functions.DefaultEmbeddingFunction(),
        )

        chunks = self.corpus.chunks
        collection.add(
            ids=[c.chunk_id for c in chunks],
            documents=[self._embedding_text(c) for c in chunks],
            metadatas=[{"doc_id": c.doc_id} for c in chunks],
        )
        return collection

    @staticmethod
    def _embedding_text(chunk: Chunk) -> str:
        """Prepend the title so it contributes to the match.

        The title carries the vocabulary the technical writer used; the body
        carries the vocabulary the customer is more likely to use. Embedding both
        is what bridges Ines's gap.
        """
        return f"{chunk.title}\n\n{chunk.text}"

    def search(self, query: str, top_k: int | None = None) -> list[RetrievedPassage]:
        """Ranked passages above the relevance floor, or an empty list.

        The ergonomic path. Use `search_detailed` where the rejected candidates
        matter — the decision log, the escalation payload, calibration.
        """
        return self.search_detailed(query, top_k).passages

    def search_detailed(self, query: str, top_k: int | None = None) -> RetrievalResult:
        """Ranked passages, plus what fell below the floor and the floor applied."""
        if not query or not _ALNUM.search(query):
            return RetrievalResult([], [], 0.0, self.relevance_floor)

        k = top_k or self.DEFAULT_TOP_K
        result = self._collection.query(
            query_texts=[query],
            n_results=min(k, len(self.corpus.chunks)),
        )

        ids = result.get("ids", [[]])[0]
        distances = result.get("distances", [[]])[0]

        accepted: list[RetrievedPassage] = []
        rejected: list[RetrievedPassage] = []
        top_score = 0.0

        for chunk_id, distance in zip(ids, distances):
            chunk = self.corpus.resolve(chunk_id)
            if chunk is None:  # pragma: no cover - index and corpus cannot diverge
                continue
            score = max(0.0, min(1.0, 1.0 - float(distance)))
            top_score = max(top_score, score)
            passage = RetrievedPassage(
                doc_id=chunk.doc_id,
                chunk_id=chunk.chunk_id,
                text=chunk.text,
                title=chunk.title,
                score=score,
                char_start=chunk.char_start,
                char_end=chunk.char_end,
            )
            (accepted if score >= self.relevance_floor else rejected).append(passage)

        by_score = lambda p: p.score  # noqa: E731
        return RetrievalResult(
            passages=sorted(accepted, key=by_score, reverse=True),
            rejected=sorted(rejected, key=by_score, reverse=True),
            top_score=top_score,
            floor_applied=self.relevance_floor,
        )
