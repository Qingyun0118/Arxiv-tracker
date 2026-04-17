import unittest
from unittest.mock import Mock, patch

from arxiv_tracker.semantic import _embed_texts, rerank_items_with_zotero


class SemanticRerankTests(unittest.TestCase):
    def test_embed_texts_resolves_env(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"data": [{"embedding": [0.12, 0.34]}]}

        with patch.dict(
            "os.environ",
            {
                "SEMANTIC_EMBED_BASE_URL": "https://api.deepseek.com",
                "SEMANTIC_EMBED_MODEL": "text-embedding-3-small",
                "SEMANTIC_EMBED_API_KEY": "sk-semantic",
            },
            clear=False,
        ), patch("arxiv_tracker.semantic.requests.post", return_value=response) as post:
            vecs = _embed_texts(
                ["abc"],
                {
                    "base_url_env": "SEMANTIC_EMBED_BASE_URL",
                    "model_env": "SEMANTIC_EMBED_MODEL",
                    "api_key_env": "SEMANTIC_EMBED_API_KEY",
                    "batch_size": 64,
                    "timeout": 45,
                },
            )

        self.assertEqual(vecs, [[0.12, 0.34]])
        self.assertEqual(post.call_args.args[0], "https://api.deepseek.com/v1/embeddings")
        self.assertEqual(post.call_args.kwargs["json"]["model"], "text-embedding-3-small")
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer sk-semantic")

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

    def test_rerank_requires_include_path_by_default(self):
        items = [{"id": "a", "title": "A", "summary": "alpha"}]
        ranked, scores, warning = rerank_items_with_zotero(
            items,
            {
                "enabled": True,
                "zotero": {"require_include_path": True, "include_path": []},
            },
        )

        self.assertEqual(ranked, items)
        self.assertEqual(scores, {})
        self.assertIn("include_path is required", warning or "")

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
