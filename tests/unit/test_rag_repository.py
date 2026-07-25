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
    assert result[0].metadata["retrieval"] == "scoped_lexical_rerank"
    assert result[0].metadata["source_tier"] == 3
    assert result[0].metadata["query_expansion"] is True


@pytest.mark.asyncio
async def test_planning_scope_excludes_unrelated_policy_documents(
    tmp_path: Path,
):
    curated = tmp_path / "curated"
    official = tmp_path / "official"
    curated.mkdir()
    official.mkdir()
    (curated / "campus_time.md").write_text(
        "---\nverified: true\nknowledge_type: operations\n---\n\n"
        "东操场场地全天开放，阳光长跑计入时段到21:00。",
        encoding="utf-8",
    )
    (official / "student_handbook.md").write_text(
        "---\nverified: true\nknowledge_type: policy\n---\n\n"
        "体育活动奖用于奖励坚持体育锻炼的学生。",
        encoding="utf-8",
    )
    repository = KnowledgeRepository(tmp_path)

    result = await repository.retrieve(
        ["东操场跑步"],
        purpose="planning",
        top_k=3,
    )

    assert result
    assert all(item.metadata["knowledge_type"] != "policy" for item in result)
    assert "阳光长跑计入时段" in result[0].content


@pytest.mark.asyncio
async def test_markdown_headings_keep_operational_rules_focused(
    tmp_path: Path,
):
    curated = tmp_path / "curated"
    curated.mkdir()
    (curated / "rules.md").write_text(
        "---\nverified: true\nknowledge_type: operations\n---\n\n"
        "# 校园规则\n\n"
        "## 上课时间\n\n第1节08:05开始。\n\n"
        "## 阳光长跑\n\n东操场07:00—21:00可计入阳光长跑。",
        encoding="utf-8",
    )
    repository = KnowledgeRepository(tmp_path)

    result = await repository.retrieve(["东操场跑步"], top_k=1)

    assert "阳光长跑" in result[0].content
    assert "第1节" not in result[0].content
