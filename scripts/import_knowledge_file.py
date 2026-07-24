from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from pypdf import PdfReader

from app.services.knowledge_importer import CONVERTERS


def import_file(
    source: Path,
    output: Path,
    *,
    verified: bool,
) -> dict[str, object]:
    raw = source.read_bytes()
    extension = source.suffix.lower()
    converter = CONVERTERS.get(extension)
    if converter is None:
        raise ValueError(f"unsupported knowledge file: {extension}")
    content = converter(raw).strip()
    if not content:
        raise ValueError("knowledge file contains no extractable text")

    pages = len(PdfReader(source).pages) if extension == ".pdf" else None
    digest = hashlib.sha256(raw).hexdigest()
    front_matter = (
        "---\n"
        f"source_path: {json.dumps(source.name, ensure_ascii=False)}\n"
        f"source_sha256: {json.dumps(digest)}\n"
        f"imported_at: {datetime.now(UTC).isoformat()}\n"
        f"verified: {'true' if verified else 'false'}\n"
        f"document_pages: {pages or 'unknown'}\n"
        "completeness: complete_source_document\n"
        "---\n\n"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(front_matter + content + "\n", encoding="utf-8")
    return {
        "source": str(source),
        "output": str(output),
        "characters": len(content),
        "pages": pages,
        "sha256": digest,
        "verified": verified,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--verified", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            import_file(
                args.source,
                args.output,
                verified=args.verified,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
