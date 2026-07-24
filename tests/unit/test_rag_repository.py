from __future__ import annotations

from pathlib import Path

import pytest

from app.providers.rag import KnowledgeRepository


@pytest.mark.asyncio
async def test_readme_is_not_indexed_as_campus_knowledge(tmp_path: Path):
    (tmp_path / "README.md").write_text(
        "这里是知识库导入说明，不是校园事实。",
        encoding="utf-8",
    )
    repository = KnowledgeRepository(tmp_path)

    result = await repository.retrieve(["校园事实"])

    assert repository.chunk_count == 0
    assert result == []


@pytest.mark.asyncio
async def test_markdown_document_is_retrievable(tmp_path: Path):
    (tmp_path / "library.md").write_text(
        "图书馆开放时间应以正式通知为准。",
        encoding="utf-8",
    )
    repository = KnowledgeRepository(tmp_path)

    result = await repository.retrieve(["图书馆开放"])

    assert repository.chunk_count == 1
    assert result[0].source_ref == "library.md"


@pytest.mark.asyncio
async def test_front_matter_is_metadata_not_search_content(tmp_path: Path):
    (tmp_path / "imported.md").write_text(
        "---\n"
        'source_path: "知识库/杭电时间知识库.docx"\n'
        "verified: false\n"
        "---\n\n"
        "图书馆每天7:00开放。\n",
        encoding="utf-8",
    )
    repository = KnowledgeRepository(tmp_path)

    result = await repository.retrieve(["图书馆开放"])

    assert repository.chunk_count == 1
    assert result[0].source_ref == "知识库/杭电时间知识库.docx"
    assert result[0].metadata["verified"] is False
    assert "source_path" not in result[0].content


@pytest.mark.asyncio
async def test_long_saved_document_is_split_and_tail_is_retrievable(
    tmp_path: Path,
):
    content = "\n".join(
        [f"第{index}条 普通管理规定。" for index in range(180)]
        + ["第一百八十一条 特殊检索词：考试作弊处理。"]
    )
    (tmp_path / "handbook.md").write_text(content, encoding="utf-8")
    repository = KnowledgeRepository(tmp_path)

    result = await repository.retrieve(["考试作弊处理"])

    assert repository.chunk_count > 1
    assert "考试作弊处理" in result[0].content


@pytest.mark.asyncio
async def test_specific_chinese_phrase_outranks_generic_character_matches(
    tmp_path: Path,
):
    (tmp_path / "handbook.md").write_text(
        "学生参加考试应当遵守学校规定。\n\n"
        "第三章 作弊行为的认定。携带考试相关材料参加考试，"
        "认定为考试作弊。",
        encoding="utf-8",
    )
    repository = KnowledgeRepository(tmp_path)

    result = await repository.retrieve(["考试作弊行为如何认定"], top_k=1)

    assert "作弊行为的认定" in result[0].content


@pytest.mark.asyncio
async def test_enhanced_retrieval_expands_query_and_records_rerank_metadata(
    tmp_path: Path,
):
    official = tmp_path / "official"
    official.mkdir()
    (official / "handbook.md").write_text(
        "---\nverified: true\n---\n\n"
        "学生公寓楼开关门时间为6:20至23:00，晚归应联系值班人员。",
        encoding="utf-8",
    )
    repository = KnowledgeRepository(tmp_path)

    result = await repository.retrieve(["宿舍门禁"], top_k=1)

    assert "公寓楼开关门时间" in result[0].content
    assert result[0].metadata["retrieval"] == "enhanced_lexical_rerank"
    assert result[0].metadata["source_tier"] == 3
    assert result[0].metadata["query_expansion"] is True
