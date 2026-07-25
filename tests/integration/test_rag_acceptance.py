from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.providers.rag import KnowledgeRepository


PROJECT_ROOT = Path(__file__).parents[2]
KNOWLEDGE_DIRECTORY = PROJECT_ROOT / "data" / "knowledge"
CASES_PATH = PROJECT_ROOT / "tests" / "fixtures" / "knowledge_retrieval_cases.json"
CASES = json.loads(CASES_PATH.read_text(encoding="utf-8"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    CASES,
    ids=[
        f"{index + 1:02d}-{case['category']}-{case['query']}"
        for index, case in enumerate(CASES)
    ],
)
async def test_verified_knowledge_retrieval_acceptance(case: dict):
    """The real competition knowledge base must survive retrieval changes."""
    repository = KnowledgeRepository(KNOWLEDGE_DIRECTORY)

    facts = await repository.retrieve(
        [case["query"]],
        purpose="qa",
        top_k=3,
    )

    assert facts, case["query"]
    combined_evidence = "\n".join(item.content for item in facts)
    for marker in case["expected_markers"]:
        assert marker in combined_evidence, (
            f"query={case['query']!r}; marker={marker!r}; "
            f"evidence={combined_evidence!r}"
        )
    assert facts[0].metadata["knowledge_type"] == case["expected_type"]
    assert facts[0].metadata["verified"] is True
    assert facts[0].metadata["source_tier"] >= 3

    expected_pages = case.get("expected_pages")
    expected_page = case.get("expected_page")
    if expected_page is not None or expected_pages is not None:
        matching_facts = [
            fact
            for fact in facts
            if all(
                marker in fact.content
                for marker in case["expected_markers"]
            )
        ]
        assert matching_facts, case["query"]
        allowed_pages = expected_pages or [expected_page]
        assert matching_facts[0].metadata["page"] in allowed_pages
        assert matching_facts[0].metadata["title"]
