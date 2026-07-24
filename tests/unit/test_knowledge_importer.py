from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from app.services.knowledge_importer import KnowledgeImporter


def test_inventory_and_import_text_document(tmp_path: Path):
    archive_path = tmp_path / "coze.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(
            "knowledge/library.txt",
            "图书馆开放时间需要从正式来源核验。",
        )
        archive.writestr("workflow/config.json", json.dumps({"prompt": "x"}))

    importer = KnowledgeImporter(archive_path)
    inventory = importer.inventory()
    by_path = {item.path: item for item in inventory}
    assert by_path["knowledge/library.txt"].importable is True
    assert by_path["workflow/config.json"].importable is False

    output = tmp_path / "output"
    result = importer.import_documents(output)
    imported = [item for item in result if item["status"] == "imported"]
    assert len(imported) == 1
    content = Path(imported[0]["output_path"]).read_text(encoding="utf-8")
    assert "verified: false" in content
    assert "图书馆开放时间" in content


def test_generic_documents_require_explicit_opt_in(tmp_path: Path):
    archive_path = tmp_path / "coze.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("答辩稿.docx", b"not-a-real-docx")
        archive.writestr("knowledge/library.txt", "正式知识候选")

    importer = KnowledgeImporter(archive_path)
    result = importer.import_documents(tmp_path / "safe")
    assert [item["source_path"] for item in result] == [
        "knowledge/library.txt"
    ]


def test_rejects_zip_path_traversal(tmp_path: Path):
    archive_path = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../escape.txt", "bad")

    with pytest.raises(ValueError, match="unsafe zip member"):
        KnowledgeImporter(archive_path).inventory()


def test_saved_knowledge_page_extracts_preview_only(tmp_path: Path):
    archive_path = tmp_path / "coze.zip"
    html = """
    <html><body>
      <script>secretPlatformConfig()</script>
      <div>工作流运行记录</div>
      <h2>预览原始文档</h2>
      <div>图书馆开放时间：7:00-22:30</div>
      <div>1 / 1</div><div>100%</div>
    </body></html>
    """
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("coze/AIGC知识库 - 知识库 - 扣子.html", html)

    importer = KnowledgeImporter(archive_path)
    result = importer.import_documents(tmp_path / "output")
    output_path = Path(result[0]["output_path"])
    content = output_path.read_text(encoding="utf-8")

    assert "图书馆开放时间" in content
    assert "工作流运行记录" not in content
    assert "secretPlatformConfig" not in content
    assert "1 / 1" not in content
