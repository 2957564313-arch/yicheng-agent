from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from math import log
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
    "请假": (
        "销假",
        "请假手续",
        "学生管理",
        "最长请假时间不能超过四周",
    ),
    "注册": (
        "暂缓注册",
        "未按期注册",
        "每天按6节课计",
        "学籍",
    ),
    "旷课": ("考勤", "课程考核资格", "三分之一", "迟到", "早退"),
    "迟到": ("早退", "旷课", "0.5学时", "考勤"),
    "早退": ("迟到", "旷课", "0.5学时", "考勤"),
    "申诉": (
        "书面申诉",
        "学生申诉处理委员会",
        "处分决定书",
        "10日",
    ),
    "休学": (
        "一学期或者一学年",
        "累计不得超过两年",
        "休学期间",
        "复学",
    ),
    "复学": (
        "休学期满",
        "开学两周内",
        "复学申请",
        "教务处",
    ),
    "修业年限": (
        "创业休学",
        "四年制本科生",
        "最长修业年限为8年",
    ),
    "转专业": (
        "普通类转专业",
        "实际在校学期",
        "超过四学期",
        "不得申请",
    ),
    "奖学金": ("评奖评优", "奖助学金", "综合测评"),
}

QUERY_NORMALIZATIONS = {
    "什么时候": "时间",
    "修业几年": "修业年限",
    "能读几年": "修业年限",
    "几点开门": "开放时间",
    "几点开放": "开放时间",
    "几点关门": "关闭时间",
    "几点闭馆": "关闭时间",
    "关门": "关闭",
    "开门": "开放",
    "怎么办": "如何处理",
    "菜鸟": "菜鸟驿站",
    "寝室": "宿舍",
}

OPERATIONAL_TERMS = (
    "开放",
    "营业",
    "时间",
    "几点",
    "门禁",
    "熄灯",
    "热水",
    "快递",
    "驿站",
    "图书馆",
    "操场",
    "田径场",
    "跑步",
    "阳光长跑",
    "体育馆",
    "餐厅",
    "食堂",
    "校医院",
    "节次",
    "课表",
    "上课",
    "拥堵",
)

POLICY_TERMS = (
    "处分",
    "作弊",
    "违纪",
    "奖学金",
    "请假",
    "旷课",
    "考勤",
    "迟到",
    "早退",
    "申诉",
    "休学",
    "复学",
    "注册",
    "修业年限",
    "学籍",
    "转专业",
    "评奖",
    "综合测评",
)


@dataclass(frozen=True, slots=True)
class _KnowledgeChunk:
    id: str
    content: str
    tokens: Counter[str]
    source_ref: str
    verified: bool
    source_tier: int
    knowledge_type: str
    title: str | None
    page: int | None


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


def _normalized_query(text: str) -> str:
    value = text.strip()
    for source, target in QUERY_NORMALIZATIONS.items():
        value = value.replace(source, target)
    value = re.sub(
        r"(?:最长)?(?:可以|能)?(?:读|修业)\s*几年",
        "修业年限",
        value,
    )
    return value


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
    heading_sections = [
        section.strip()
        for section in re.split(r"(?m)(?=^#{1,4}\s+)", content)
        if section.strip()
    ]
    if len(heading_sections) > 1:
        chunks: list[str] = []
        for section in heading_sections:
            if len(section) <= max_chars:
                chunks.append(section)
            else:
                chunks.extend(_content_chunks_without_headings(section, max_chars))
        return chunks
    return _content_chunks_without_headings(content, max_chars)


def _pdf_page_chunks(content: str, max_chars: int = 1600) -> list[str]:
    """Keep each extracted PDF page independently citable.

    A chapter title is carried forward only as retrieval context. The page
    marker remains in every chunk so the final answer can cite the actual
    evidence page instead of the first page of a multi-page chunk.
    """
    page_pattern = re.compile(
        r"(?m)(?=^\s*-\s*\d{1,3}\s*-\s*$)"
    )
    pages = [
        part.strip()
        for part in page_pattern.split(content)
        if part.strip()
    ]
    if not re.search(r"(?m)^\s*-\s*\d{1,3}\s*-\s*$", content):
        return _content_chunks(content, max_chars)
    chunks: list[str] = []
    active_title: str | None = None
    for page in pages:
        marker_match = re.match(
            r"^\s*(-\s*\d{1,3}\s*-)\s*",
            page,
        )
        page_marker = marker_match.group(1) if marker_match else ""
        page_body = (
            page[marker_match.end() :].strip()
            if marker_match
            else page
        )
        page_sections = [
            section.strip()
            for section in re.split(
                r"(?m)(?=^第[一二三四五六七八九十百]+章\s*)",
                page_body,
            )
            if section.strip()
        ] or [page_body]
        for section in page_sections:
            inferred = _infer_chunk_title(section)
            if inferred:
                active_title = inferred
            contextual_parts = [page_marker] if page_marker else []
            if active_title and active_title not in section[:180]:
                contextual_parts.append(f"## {active_title}")
            contextual_parts.append(section)
            chunks.extend(
                _content_chunks_without_headings(
                    "\n\n".join(contextual_parts),
                    max_chars,
                )
            )
    return chunks


def _chunk_context(content: str) -> tuple[str | None, int | None]:
    """Keep human-readable section and PDF page evidence for each chunk."""
    headings = re.findall(
        r"(?m)^#{1,4}\s+(.+?)\s*$",
        content,
    )
    pages = re.findall(
        r"(?m)^\s*-\s*(\d{1,3})\s*-\s*$",
        content,
    )
    title = headings[-1].strip() if headings else _infer_chunk_title(content)
    page = int(pages[0]) if pages else None
    return title, page


def _infer_chunk_title(content: str) -> str | None:
    candidates = [
        re.sub(r"^#{1,4}\s+", "", line.strip(" -"))
        for line in content.splitlines()
        if line.strip(" -")
    ]
    patterns = (
        r"^第[一二三四五六七八九十百]+章\s*\S+",
        r"^第[一二三四五六七八九十百]+节\s*\S+",
        r"^.{2,45}(?:办法|规定|细则|条例|守则)$",
    )
    for pattern in patterns:
        matches = [
            line
            for line in candidates
            if len(line) <= 55 and re.match(pattern, line)
        ]
        if matches:
            return matches[-1]
    return None


def _normalize_pdf_layout(content: str) -> str:
    """Repair visual PDF line wraps without destroying article boundaries."""
    lines = content.replace("\r", "\n").splitlines()
    paragraphs: list[str] = []
    current = ""

    def flush() -> None:
        nonlocal current
        if current.strip():
            paragraphs.append(current.strip())
        current = ""

    boundary_patterns = (
        r"^#{1,4}\s+",
        r"^-\s*\d{1,3}\s*-$",
        r"^第[一二三四五六七八九十百零〇0-9]+[章节条款]\s*",
        r"^[（(][一二三四五六七八九十0-9]+[）)]",
        r"^[一二三四五六七八九十]+[、.]",
    )
    for raw_line in lines:
        line = re.sub(r"[ \t]+", " ", raw_line).strip()
        if not line:
            flush()
            continue
        is_boundary = any(
            re.match(pattern, line) for pattern in boundary_patterns
        )
        if is_boundary:
            flush()
            current = line
            if re.match(
                r"^#{1,4}\s+|^-\s*\d{1,3}\s*-$"
                r"|^第[一二三四五六七八九十百]+章\s*",
                line,
            ):
                flush()
            continue
        if not current:
            current = line
        elif (
            re.search(r"[A-Za-z0-9]$", current)
            and re.match(r"^[A-Za-z0-9]", line)
        ):
            current += " " + line
        else:
            current += line
    flush()
    return "\n\n".join(paragraphs)


def _content_chunks_without_headings(
    content: str,
    max_chars: int,
) -> list[str]:
    """Split prose while keeping Markdown sections as independent evidence."""
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
            # Keep one short source line as overlap. PDF extraction often
            # wraps a single sentence across two visual lines, and without
            # overlap a rule such as “累计不｜得超过两年” is split between
            # chunks and cannot be quoted completely.
            overlap = (
                [current[-1]]
                if current and len(current[-1]) <= min(400, max_chars // 2)
                else []
            )
            current = overlap
            current_chars = len(overlap[0]) if overlap else 0
            separator_chars = 2 if current else 0
        current.append(unit)
        current_chars += separator_chars + len(unit)
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def _focused_evidence_excerpt(
    content: str,
    *,
    terms: list[str],
    max_chars: int = 1200,
) -> str:
    """Keep the part of a long chunk that actually matched the query.

    A plain ``content[:max_chars]`` can silently cut off a rule located near
    the end of a PDF-derived chunk.  Rank candidate windows by the matching
    query and expansion terms they contain, then return the densest window.
    """
    if len(content) <= max_chars:
        return content
    matches: list[tuple[int, int]] = []
    for term in dict.fromkeys(value.strip() for value in terms):
        if len(term) < 2:
            continue
        start = 0
        while True:
            position = content.find(term, start)
            if position < 0:
                break
            # Long, explicit expansion phrases carry substantially more
            # meaning than repeated two-character words such as “休学”.
            matches.append((position, min(len(term) ** 3, 1000)))
            start = position + max(1, len(term))
    if not matches:
        return content[:max_chars]

    best_start = 0
    best_score = -1
    for position, _ in matches:
        candidate_start = min(
            max(0, position - max_chars // 2),
            len(content) - max_chars,
        )
        candidate_end = candidate_start + max_chars
        score = sum(
            weight
            for match_position, weight in matches
            if candidate_start <= match_position < candidate_end
        )
        if score > best_score or (
            score == best_score and candidate_start > best_start
        ):
            best_start = candidate_start
            best_score = score

    if best_start:
        previous_newline = content.rfind("\n", 0, best_start)
        if previous_newline >= 0:
            best_start = previous_newline + 1
    best_end = min(len(content), best_start + max_chars)
    return content[best_start:best_end]


def _infer_knowledge_type(
    *,
    path: Path,
    content: str,
    metadata: dict[str, str],
) -> str:
    declared = metadata.get("knowledge_type", "").strip().lower()
    if declared in {"operations", "policy", "calendar", "general"}:
        return declared
    name = path.stem
    if any(term in name for term in ("学生手册", "制度", "办法", "条例")):
        return "policy"
    if any(
        term in name
        for term in ("时间", "开放", "服务", "地点", "课表", "作息")
    ):
        return "operations"
    operation_hits = sum(term in content for term in OPERATIONAL_TERMS)
    policy_hits = sum(term in content for term in POLICY_TERMS)
    if operation_hits >= 3 and operation_hits > policy_hits:
        return "operations"
    if policy_hits >= 2 and policy_hits > operation_hits:
        return "policy"
    return "general"


class KnowledgeRepository:
    """可审计的两阶段增强检索。

    第一阶段使用查询扩展与加权中文词片召回；第二阶段依据精确短语、
    已核验状态和来源层级重排，并做相似段落去重。整个过程无需外部
    向量服务，适合比赛现场离线运行，也能明确追溯到原始文档。
    """

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self._chunks: list[_KnowledgeChunk] = []
        self._document_frequency: Counter[str] = Counter()
        if directory.exists():
            for path in sorted(directory.glob("**/*.md")):
                if path.name.lower() == "readme.md":
                    continue
                content, metadata = _split_front_matter(
                    path.read_text(encoding="utf-8").strip()
                )
                if (
                    str(metadata.get("source_path", "")).lower().endswith(
                        ".pdf"
                    )
                    or str(metadata.get("document_pages", "")).isdigit()
                ):
                    content = _normalize_pdf_layout(content)
                verified = metadata.get("verified", "false").lower() == "true"
                source_ref = metadata.get(
                    "source_path",
                    str(path.relative_to(directory)),
                )
                relative_parts = path.relative_to(directory).parts
                source_tier = (
                    4
                    if "curated" in relative_parts
                    else (3 if "official" in relative_parts else 1)
                )
                knowledge_type = _infer_knowledge_type(
                    path=path,
                    content=content,
                    metadata=metadata,
                )
                is_pdf_source = (
                    str(metadata.get("source_path", "")).lower().endswith(
                        ".pdf"
                    )
                    or str(metadata.get("document_pages", "")).isdigit()
                )
                source_chunks = (
                    _pdf_page_chunks(content)
                    if is_pdf_source
                    else _content_chunks(content)
                )
                for index, chunk in enumerate(source_chunks):
                    chunk_id = f"{path.stem}:{index}"
                    title, page = _chunk_context(chunk)
                    self._chunks.append(
                        _KnowledgeChunk(
                            id=chunk_id,
                            content=chunk,
                            tokens=_tokens(chunk),
                            source_ref=source_ref,
                            verified=verified,
                            source_tier=source_tier,
                            knowledge_type=knowledge_type,
                            title=title,
                            page=page,
                        )
                    )
        for chunk in self._chunks:
            self._document_frequency.update(set(chunk.tokens))

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)

    async def retrieve(
        self,
        queries: list[str],
        *,
        top_k: int = 3,
        purpose: str = "auto",
    ) -> list[RetrievedFact]:
        expanded_queries = self._expand_queries(queries)
        allowed_types = self._allowed_types(
            purpose=purpose,
            queries=queries,
        )
        query_tokens = Counter()
        for query in expanded_queries:
            query_tokens.update(_tokens(query))

        ranked: list[tuple[float, _KnowledgeChunk]] = []
        for chunk in self._chunks:
            if (
                allowed_types is not None
                and chunk.knowledge_type not in allowed_types
            ):
                continue
            lexical_score = sum(
                _token_weight(token)
                * min(count, chunk.tokens.get(token, 0))
                * self._inverse_document_frequency(token)
                for token, count in query_tokens.items()
            )
            exact_bonus = sum(
                18
                for query in queries
                if (
                    len(query.strip()) >= 3
                    and query.strip() in chunk.content
                )
            )
            expansion_bonus = sum(
                6
                for query in expanded_queries[len(queries) :]
                if len(query) >= 2 and query in chunk.content
            )
            answer_value_bonus = sum(
                90
                for query in expanded_queries[len(queries) :]
                if (
                    query in chunk.content
                    and re.search(
                        r"(?:\d+(?:\.\d+)?|[一二三四五六七八九十百]+)"
                        r"(?:日|天|年|周|学期|节|学时)",
                        query,
                    )
                )
            )
            title_bonus = self._title_bonus(
                queries=queries,
                expanded_queries=expanded_queries,
                title=chunk.title,
            )
            coverage_bonus = self._coverage_bonus(
                expanded_queries=expanded_queries,
                content=chunk.content,
                title=chunk.title,
            )
            phrase_density_bonus = min(
                30,
                round(
                    lexical_score
                    * 260
                    / max(len(chunk.content), 260)
                ),
            )
            authority_bonus = (
                chunk.source_tier * 8
                + (12 if chunk.verified else 0)
            )
            score = (
                lexical_score
                + exact_bonus
                + expansion_bonus
                + answer_value_bonus
                + title_bonus
                + coverage_bonus
                + phrase_density_bonus
                + authority_bonus
            )
            if lexical_score > 0:
                ranked.append((score, chunk))
        ranked.sort(key=lambda item: (-item[0], item[1].id))

        selected: list[tuple[int, _KnowledgeChunk]] = []
        relative_floor = ranked[0][0] * 0.3 if ranked else 0
        for candidate in ranked[: max(top_k * 10, 30)]:
            if candidate[0] < relative_floor:
                continue
            if any(
                self._content_similarity(
                    candidate[1].content,
                    current[1].content,
                )
                >= 0.82
                for current in selected
            ):
                continue
            selected.append(candidate)
            if len(selected) >= top_k:
                break

        return [
            RetrievedFact(
                id=chunk.id,
                content=_focused_evidence_excerpt(
                    chunk.content,
                    terms=expanded_queries,
                ),
                priority=round(
                    chunk.source_tier * 10
                    + (15 if chunk.verified else 0)
                    + min(score, 50)
                ),
                source=DataSource.RAG,
                source_ref=chunk.source_ref,
                verified_at=None,
                metadata={
                    "retrieval": "scoped_lexical_rerank",
                    "verified": chunk.verified,
                    "source_tier": chunk.source_tier,
                    "retrieval_score": score,
                    "query_expansion": True,
                    "knowledge_type": chunk.knowledge_type,
                    "purpose": purpose,
                    "title": chunk.title,
                    "page": chunk.page,
                    "matched_terms": self._matched_terms(
                        expanded_queries,
                        chunk,
                    ),
                },
            )
            for score, chunk in selected
        ]

    @staticmethod
    def _allowed_types(
        *,
        purpose: str,
        queries: list[str],
    ) -> set[str] | None:
        if purpose == "planning":
            return {"operations", "calendar", "general"}
        query = " ".join(queries)
        operation_hits = sum(term in query for term in OPERATIONAL_TERMS)
        policy_hits = sum(term in query for term in POLICY_TERMS)
        if operation_hits and operation_hits >= policy_hits:
            return {"operations", "calendar", "general"}
        if policy_hits:
            return {"policy", "general"}
        return None

    @staticmethod
    def _expand_queries(queries: list[str]) -> list[str]:
        expanded = list(
            dict.fromkeys(
                value
                for query in queries
                if query.strip()
                for value in (query.strip(), _normalized_query(query))
                if value
            )
        )
        for query in list(expanded):
            for keyword, related in QUERY_EXPANSIONS.items():
                if keyword in query:
                    expanded.extend(
                        value for value in related if value not in expanded
                    )
        return expanded

    def _inverse_document_frequency(self, token: str) -> float:
        frequency = self._document_frequency.get(token, 0)
        return 1 + log((len(self._chunks) + 1) / (frequency + 1))

    @staticmethod
    def _title_bonus(
        *,
        queries: list[str],
        expanded_queries: list[str],
        title: str | None,
    ) -> int:
        if not title:
            return 0
        normalized_title = re.sub(r"\s+", "", title)
        direct = max(
            (
                len(query.replace(" ", ""))
                for query in queries
                if query.strip() and query.replace(" ", "") in normalized_title
            ),
            default=0,
        )
        related = sum(
            1
            for term in expanded_queries
            if len(term) >= 2 and term.replace(" ", "") in normalized_title
        )
        return min(35, direct * 4 + related * 6)

    @staticmethod
    def _coverage_bonus(
        *,
        expanded_queries: list[str],
        content: str,
        title: str | None,
    ) -> int:
        haystack = f"{title or ''}\n{content}"
        meaningful = [
            term
            for term in dict.fromkeys(expanded_queries)
            if len(term.strip()) >= 2
        ]
        if not meaningful:
            return 0
        hits = sum(term in haystack for term in meaningful)
        return round(24 * hits / len(meaningful))

    @staticmethod
    def _matched_terms(
        expanded_queries: list[str],
        chunk: _KnowledgeChunk,
    ) -> list[str]:
        haystack = f"{chunk.title or ''}\n{chunk.content}"
        return [
            term
            for term in dict.fromkeys(expanded_queries)
            if len(term) >= 2 and term in haystack
        ][:12]

    @staticmethod
    def _content_similarity(left: str, right: str) -> float:
        left_tokens = set(_tokens(left))
        right_tokens = set(_tokens(right))
        if not left_tokens or not right_tokens:
            return 0
        return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
