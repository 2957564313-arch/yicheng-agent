from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from app.schemas.common import DataSource
from app.schemas.context import RetrievedFact


QUERY_EXPANSIONS = {
    "门禁": ("宿舍", "公寓楼", "开关门", "熄灯"),
    "宿舍": ("公寓楼", "门禁", "熄灯"),
    "快递": ("驿站", "取件", "顺丰", "京东", "菜鸟"),
    "跑步": ("阳光长跑", "操场", "田径场", "体育锻炼"),
    "课程": ("上课时间", "节次", "作息"),
    "上课": ("课程", "节次", "作息"),
    "图书馆": ("开放时间", "自习", "阅览室"),
    "吃饭": ("餐厅", "食堂", "就餐"),
    "处分": ("违纪", "纪律处分", "学生管理"),
    "作弊": ("考试违纪", "考试纪律", "处分"),
    "请假": ("销假", "请假手续", "学生管理"),
    "奖学金": ("评奖评优", "奖助学金", "综合测评"),
}


def _tokens(text: str) -> Counter[str]:
    english = re.findall(r"[a-zA-Z0-9_]+", text.lower())
    chinese = [
        char
        for char in text
        if "\u4e00" <= char <= "\u9fff"
    ]
    bigrams = [
        chinese[index] + chinese[index + 1]
        for index in range(len(chinese) - 1)
    ]
    trigrams = [
        chinese[index] + chinese[index + 1] + chinese[index + 2]
        for index in range(len(chinese) - 2)
    ]
    return Counter([*english, *chinese, *bigrams, *trigrams])


def _token_weight(token: str) -> int:
    if all("\u4e00" <= char <= "\u9fff" for char in token):
        return {1: 0, 2: 3}.get(len(token), 5)
    return 3


def _split_front_matter(content: str) -> tuple[str, dict[str, str]]:
    if not content.startswith("---\n"):
        return content, {}
    end = content.find("\n---\n", 4)
    if end < 0:
        return content, {}
    metadata = {}
    for line in content[4:end].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"')
    return content[end + 5 :].lstrip(), metadata


def _split_long_unit(unit: str, max_chars: int) -> list[str]:
    """Split long paragraphs without requiring a document-specific parser."""
    lines = [line.strip() for line in unit.splitlines() if line.strip()]
    if len(lines) <= 1:
        lines = [
            part.strip()
            for part in re.split(r"(?<=[。！？；.!?])", unit)
            if part.strip()
        ]
    pieces: list[str] = []
    for line in lines:
        if len(line) <= max_chars:
            pieces.append(line)
            continue
        pieces.extend(
            line[start : start + max_chars]
            for start in range(0, len(line), max_chars)
        )
    return pieces


def _content_chunks(content: str, max_chars: int = 1600) -> list[str]:
    """Build bounded chunks so saved long documents remain searchable."""
    raw_units = [
        part.strip()
        for part in re.split(r"\n\s*\n", content)
        if part.strip()
    ]
    units: list[str] = []
    for unit in raw_units:
        if len(unit) <= max_chars:
            units.append(unit)
        else:
            units.extend(_split_long_unit(unit, max_chars))

    chunks: list[str] = []
    current: list[str] = []
    current_chars = 0
    for unit in units:
        separator_chars = 2 if current else 0
        if current and current_chars + separator_chars + len(unit) > max_chars:
            chunks.append("\n\n".join(current))
            current = []
            current_chars = 0
            separator_chars = 0
        current.append(unit)
        current_chars += separator_chars + len(unit)
    if current:
        chunks.append("\n\n".join(current))
    return chunks


class KnowledgeRepository:
    """可审计的两阶段增强检索。

    第一阶段使用查询扩展与加权中文词片召回；第二阶段依据精确短语、
    已核验状态和来源层级重排，并做相似段落去重。整个过程无需外部
    向量服务，适合比赛现场离线运行，也能明确追溯到原始文档。
    """

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self._chunks: list[
            tuple[str, str, Counter[str], str, bool, int]
        ] = []
        if directory.exists():
            for path in sorted(directory.glob("**/*.md")):
                if path.name.lower() == "readme.md":
                    continue
                content, metadata = _split_front_matter(
                    path.read_text(encoding="utf-8").strip()
                )
                verified = metadata.get("verified", "false").lower() == "true"
                source_ref = metadata.get(
                    "source_path",
                    str(path.relative_to(directory)),
                )
                relative_parts = path.relative_to(directory).parts
                source_tier = (
                    3
                    if "official" in relative_parts
                    else (2 if "curated" in relative_parts else 1)
                )
                for index, chunk in enumerate(_content_chunks(content)):
                    chunk_id = f"{path.stem}:{index}"
                    self._chunks.append(
                        (
                            chunk_id,
                            chunk,
                            _tokens(chunk),
                            source_ref,
                            verified,
                            source_tier,
                        )
                    )

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)

    async def retrieve(
        self,
        queries: list[str],
        *,
        top_k: int = 3,
    ) -> list[RetrievedFact]:
        expanded_queries = self._expand_queries(queries)
        query_tokens = Counter()
        for query in expanded_queries:
            query_tokens.update(_tokens(query))

        ranked: list[tuple[int, str, str, str, bool, int]] = []
        for (
            chunk_id,
            content,
            chunk_tokens,
            source_ref,
            verified,
            source_tier,
        ) in self._chunks:
            lexical_score = sum(
                _token_weight(token)
                * min(count, chunk_tokens.get(token, 0))
                for token, count in query_tokens.items()
            )
            exact_bonus = sum(
                18
                for query in queries
                if len(query.strip()) >= 3 and query.strip() in content
            )
            expansion_bonus = sum(
                6
                for query in expanded_queries[len(queries) :]
                if len(query) >= 2 and query in content
            )
            authority_bonus = source_tier * 8 + (12 if verified else 0)
            score = (
                lexical_score
                + exact_bonus
                + expansion_bonus
                + authority_bonus
            )
            if lexical_score > 0:
                ranked.append(
                    (
                        score,
                        chunk_id,
                        content,
                        source_ref,
                        verified,
                        source_tier,
                    )
                )
        ranked.sort(key=lambda item: (-item[0], item[1]))

        selected: list[tuple[int, str, str, str, bool, int]] = []
        for candidate in ranked[: max(top_k * 8, 20)]:
            if any(
                self._content_similarity(candidate[2], current[2]) >= 0.82
                for current in selected
            ):
                continue
            selected.append(candidate)
            if len(selected) >= top_k:
                break

        return [
            RetrievedFact(
                id=chunk_id,
                content=content[:1200],
                priority=source_tier * 10 + (15 if verified else 0) + min(
                    score,
                    50,
                ),
                source=DataSource.RAG,
                source_ref=source_ref,
                verified_at=None,
                metadata={
                    "retrieval": "enhanced_lexical_rerank",
                    "verified": verified,
                    "source_tier": source_tier,
                    "retrieval_score": score,
                    "query_expansion": True,
                },
            )
            for (
                score,
                chunk_id,
                content,
                source_ref,
                verified,
                source_tier,
            ) in selected
        ]

    @staticmethod
    def _expand_queries(queries: list[str]) -> list[str]:
        expanded = list(dict.fromkeys(query.strip() for query in queries if query.strip()))
        for query in list(expanded):
            for keyword, related in QUERY_EXPANSIONS.items():
                if keyword in query:
                    expanded.extend(
                        value for value in related if value not in expanded
                    )
        return expanded

    @staticmethod
    def _content_similarity(left: str, right: str) -> float:
        left_tokens = set(_tokens(left))
        right_tokens = set(_tokens(right))
        if not left_tokens or not right_tokens:
            return 0
        return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
