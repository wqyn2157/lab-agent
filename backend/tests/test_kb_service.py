import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app.services import kb_service
from app.services.text_splitter import split_text


class MemoryCollection:
    def __init__(self):
        self.rows = {}
        self.upsert_calls = 0

    def get(self, include):
        return {
            "ids": list(self.rows),
            "documents": [row[0] for row in self.rows.values()],
        }

    def upsert(self, ids, documents, metadatas):
        self.upsert_calls += 1
        self.rows.update(zip(ids, zip(documents, metadatas)))

    def delete(self, ids):
        for key in ids:
            self.rows.pop(key, None)


class KnowledgeBaseTests(unittest.TestCase):
    def test_search_formats_sources_filters_and_limits_chunks(self):
        collection = Mock()
        collection.count.return_value = 4
        collection.query.return_value = {
            "documents": [["second", "best", "filtered", "third"]],
            "metadatas": [[
                {"source": "rules.md", "chunk_index": 0},
                {"source": "rules.md", "chunk_index": 2},
                {"source": "other.md", "chunk_index": 1},
                {"source": "other.md", "chunk_index": 0},
            ]],
            "distances": [[0.8, 0.1, 1.5, 0.9]],
        }
        with patch.object(kb_service, "get_collection", return_value=collection), patch("builtins.print"):
            result = kb_service.search("question")
        self.assertEqual(result, "[rules.md · 片段 3]\nbest\n\n[rules.md · 片段 1]\nsecond")
        collection.query.assert_called_once_with(query_texts=["question"], n_results=4)

    def test_search_handles_empty_library_and_no_matching_chunks(self):
        collection = Mock()
        collection.count.return_value = 0
        with patch.object(kb_service, "get_collection", return_value=collection):
            self.assertEqual(kb_service.search("question"), "")
        collection.query.assert_not_called()
        collection.count.return_value = 1
        collection.query.return_value = {
            "documents": [["irrelevant"]],
            "metadatas": [[{"source": "other.md", "chunk_index": 0}]],
            "distances": [[2.0]],
        }
        with patch.object(kb_service, "get_collection", return_value=collection), patch("builtins.print"):
            self.assertEqual(kb_service.search("question"), "")

    def test_splitter_boundaries(self):
        self.assertEqual(split_text(" \n\t "), [])
        self.assertEqual(split_text("  abc  "), ["abc"])
        self.assertEqual(split_text("abcde", 5, 2), ["abcde"])
        self.assertEqual(split_text("abcdefghij", 5, 0), ["abcde", "fghij"])
        self.assertEqual(split_text("abcdefghij", 5, 2), ["abcde", "defgh", "ghij"])
        for size, overlap in [(0, 0), (-1, 0), (5, -1), (5, 5)]:
            with self.subTest(size=size, overlap=overlap):
                with self.assertRaises(ValueError):
                    split_text("abc", size, overlap)

    def test_chunk_sync_lifecycle(self):
        collection = MemoryCollection()
        collection.rows["rules"] = ("legacy whole document", {"source": "rules.md"})
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            path = directory / "rules.md"
            text = "".join(chr(0x4E00 + i) for i in range(1200))
            path.write_text(text, encoding="utf-8-sig")
            with patch.object(kb_service, "KB_DIR", directory), patch.object(
                kb_service, "_collection", collection
            ):
                kb_service.get_collection()
                expected = {
                    f"rules::chunk::{i}": (chunk, {"source": "rules.md", "chunk_index": i})
                    for i, chunk in enumerate(split_text(text))
                }
                self.assertEqual(collection.rows, expected)
                chunks = [row[0] for row in collection.rows.values()]
                self.assertEqual([len(chunk) for chunk in chunks], [500, 500, 360])
                self.assertEqual(chunks[0] + "".join(chunk[80:] for chunk in chunks[1:]), text)

                kb_service.get_collection()
                self.assertEqual(collection.upsert_calls, 1)

                path.write_text(text[:-1] + "X", encoding="utf-8")
                with patch.object(collection, "upsert", wraps=collection.upsert) as upsert:
                    kb_service.get_collection()
                    self.assertEqual(upsert.call_args.kwargs["ids"], ["rules::chunk::2"])

                path.write_text(text[:100], encoding="utf-8")
                kb_service.get_collection()
                self.assertEqual(set(collection.rows), {"rules::chunk::0"})
                self.assertEqual(collection.rows["rules::chunk::0"][0], text[:100])

                path = path.rename(directory / "renamed.md")
                kb_service.get_collection()
                self.assertEqual(set(collection.rows), {"renamed::chunk::0"})
                self.assertEqual(collection.rows["renamed::chunk::0"][1]["source"], "renamed.md")

                path.write_text(" \n ", encoding="utf-8")
                kb_service.get_collection()
                self.assertEqual(collection.rows, {})

                path.write_text("restored", encoding="utf-8")
                kb_service.get_collection()
                path.unlink()
                kb_service.get_collection()
                self.assertEqual(collection.rows, {})

    def test_failed_upsert_preserves_old_records(self):
        collection = MemoryCollection()
        collection.rows["rules"] = ("legacy", {"source": "rules.md"})
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "rules.md").write_text("new content", encoding="utf-8")
            with patch.object(kb_service, "KB_DIR", directory), patch.object(
                kb_service, "_collection", collection
            ), patch.object(collection, "upsert", side_effect=RuntimeError("write failed")):
                with self.assertRaisesRegex(RuntimeError, "write failed"):
                    kb_service.get_collection()
                self.assertEqual(collection.rows, {"rules": ("legacy", {"source": "rules.md"})})


if __name__ == "__main__":
    unittest.main()
