import unittest
from unittest.mock import patch

from arxiv_tracker.semantic import rerank_items_with_zotero


class SemanticRerankTests(unittest.TestCase):
    def test_rerank_disabled_is_noop(self):
        items = [{"id": "a", "title": "A", "summary": "alpha"}]
        ranked, scores, warning = rerank_items_with_zotero(items, {"enabled": False})
        self.assertEqual(ranked, items)
        self.assertEqual(scores, {})
        self.assertIsNone(warning)

    def test_rerank_enabled_with_empty_corpus_warns(self):
        items = [{"id": "a", "title": "A", "summary": "alpha"}]
        with patch("arxiv_tracker.semantic._read_zotero_corpus", return_value=[]):
            ranked, scores, warning = rerank_items_with_zotero(items, {"enabled": True})

        self.assertEqual(ranked, items)
        self.assertEqual(scores, {})
        self.assertIn("zotero corpus is empty", warning or "")

    def test_rerank_scores_and_sorts(self):
        items = [
            {"id": "id-1", "title": "A", "summary": "first"},
            {"id": "id-2", "title": "B", "summary": "second"},
        ]

        with patch("arxiv_tracker.semantic._read_zotero_corpus", return_value=["c1", "c2"]), patch(
            "arxiv_tracker.semantic._embed_texts",
            side_effect=[
                [[1.0, 0.0], [0.1, 0.9]],
                [[1.0, 0.0], [0.0, 1.0]],
            ],
        ):
            ranked, scores, warning = rerank_items_with_zotero(items, {"enabled": True, "embedding": {}})

        self.assertIsNone(warning)
        self.assertEqual(len(scores), 2)
        self.assertIn("semantic_score", ranked[0])
        self.assertGreaterEqual(ranked[0]["semantic_score"], ranked[1]["semantic_score"])
        self.assertEqual(ranked[0]["id"], "id-1")


if __name__ == "__main__":
    unittest.main()
