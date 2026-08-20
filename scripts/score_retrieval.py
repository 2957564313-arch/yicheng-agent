"""Score knowledge retrieval on the labelled cases.

The acceptance test only asks whether the markers appear somewhere in the top
three chunks.  That passes even when the right chunk ranks third, which is the
difference between an answer the model quotes and one it has to dig for.  This
reports rank-sensitive numbers so a ranking change can be judged instead of
guessed at.

    uv run python -m scripts.score_retrieval
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.providers.rag import KnowledgeRepository

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = PROJECT_ROOT / "tests" / "fixtures" / "knowledge_retrieval_cases.json"
KNOWLEDGE_DIRECTORY = PROJECT_ROOT / "data" / "knowledge"


def _first_hit_rank(facts, markers: list[str]) -> int | None:
    """1-based rank of the first chunk carrying every expected marker."""
    for rank, fact in enumerate(facts, start=1):
        if all(marker in fact.content for marker in markers):
            return rank
    return None


async def main() -> int:
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    repository = KnowledgeRepository(KNOWLEDGE_DIRECTORY)

    hits_at_1 = 0
    hits_at_3 = 0
    combined_at_3 = 0
    reciprocal_rank = 0.0
    misses: list[str] = []
    demotions: list[str] = []

    for case in cases:
        facts = await repository.retrieve(
            [case["query"]],
            purpose="qa",
            top_k=3,
        )
        markers = case["expected_markers"]
        rank = _first_hit_rank(facts, markers)
        evidence = "\n".join(fact.content for fact in facts)
        if all(marker in evidence for marker in markers):
            combined_at_3 += 1
        if rank == 1:
            hits_at_1 += 1
        if rank is not None:
            hits_at_3 += 1
            reciprocal_rank += 1 / rank
            if rank > 1:
                demotions.append(f"  rank {rank}: {case['query']}")
        else:
            misses.append(f"  {case['query']} -> {markers}")

    total = len(cases)
    print(f"cases              {total}")
    print(f"recall@1           {hits_at_1}/{total}  ({hits_at_1 / total:.1%})")
    print(f"recall@3           {hits_at_3}/{total}  ({hits_at_3 / total:.1%})")
    print(f"markers in top 3   {combined_at_3}/{total}")
    print(f"MRR                {reciprocal_rank / total:.3f}")
    if demotions:
        print("\nfound but not first:")
        print("\n".join(demotions))
    if misses:
        print("\nnot found in top 3:")
        print("\n".join(misses))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
