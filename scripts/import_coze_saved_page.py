from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from app.services.knowledge_importer import (
    _coze_knowledge_document,
    _html_text,
)


def import_saved_page(source: Path, output: Path) -> dict[str, object]:
    plain_text = _html_text(source.read_bytes())
    document = _coze_knowledge_document(plain_text)
    if not document:
        raise ValueError("saved page does not contain a Coze document preview")

    page_match = re.search(r"(\d+)\s*/\s*(\d+)", plain_text)
    total_pages = int(page_match.group(2)) if page_match else None
    visible_markers = [
        int(value)
        for value in re.findall(r"\n(\d{1,3}) -\n", document)
    ]
    visible_page_max = max(visible_markers) if visible_markers else None
    is_partial = bool(
        total_pages
        and visible_page_max
        and visible_page_max < total_pages
    )

    front_matter = (
        "---\n"
        f"source_path: {json.dumps(str(source), ensure_ascii=False)}\n"
        f"imported_at: {datetime.now(UTC).isoformat()}\n"
        "verified: false\n"
        f"document_total_pages: {total_pages or 'unknown'}\n"
        f"visible_page_max: {visible_page_max or 'unknown'}\n"
        f"completeness: {'partial_saved_page_snapshot' if is_partial else 'unknown'}\n"
        "---\n\n"
    )
    warning = (
        "# 2025年学生手册（扣子保存页面文本）\n\n"
        f"> 页面标注共{total_pages or '未知'}页；当前HTML实际包含至"
        f"第{visible_page_max or '未知'}页。"
        "该内容用于检索演示，正式结论需以学校发布的完整原始PDF为准。\n\n"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        front_matter + warning + document + "\n",
        encoding="utf-8",
    )
    return {
        "source": str(source),
        "output": str(output),
        "characters": len(document),
        "total_pages": total_pages,
        "visible_page_max": visible_page_max,
        "partial": is_partial,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            import_saved_page(args.source, args.output),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
