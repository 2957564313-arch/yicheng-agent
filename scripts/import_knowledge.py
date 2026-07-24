from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.config import BASE_DIR
from app.services.knowledge_importer import KnowledgeImporter


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Safely inventory and import knowledge documents from a zip."
    )
    parser.add_argument("--zip", required=True, type=Path)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="import documents after writing the inventory",
    )
    parser.add_argument(
        "--include-documents",
        action="store_true",
        help=(
            "also import supported human-readable documents outside a "
            "knowledge-like folder after manual inventory review"
        ),
    )
    parser.add_argument(
        "--include-unclassified",
        action="store_true",
        help="also import supported unclassified files after manual review",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    importer = KnowledgeImporter(args.zip)
    inventory = importer.inventory()
    inventory_path = (
        BASE_DIR / "docs" / "reference" / "knowledge_inventory.json"
    )
    importer.write_inventory(inventory, inventory_path)
    print(f"inventory: {inventory_path} ({len(inventory)} files)")

    if not args.apply:
        print("dry run only; review inventory before using --apply")
        return
    result = importer.import_documents(
        BASE_DIR / "data" / "knowledge" / "imported",
        include_documents=args.include_documents,
        include_unclassified=args.include_unclassified,
    )
    report_path = (
        BASE_DIR / "docs" / "reference" / "knowledge_import_report.json"
    )
    report_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"report: {report_path}")


if __name__ == "__main__":
    main()
