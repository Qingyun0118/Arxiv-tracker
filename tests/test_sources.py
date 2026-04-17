import os
import unittest
from types import SimpleNamespace

from arxiv_tracker.sources import _merge_dedup_items, collect_items


class SourceCollectionTests(unittest.TestCase):
    def test_merge_dedup_prefers_source_priority(self):
        items = [
            {
                "id": "scholar:1",
                "source": "scholar",
                "title": "A Great Paper",
                "published": "2025-01-01T00:00:00+00:00",
                "updated": "2025-01-01T00:00:00+00:00",
                "summary": "short",
                "authors": ["A"],
                "pdf_url": None,
            },
            {
                "id": "arxiv:1",
                "source": "arxiv",
                "title": "A Great Paper",
                "published": "2025-01-01T00:00:00+00:00",
                "updated": "2025-01-02T00:00:00+00:00",
                "summary": "longer summary",
                "authors": ["A", "B"],
                "pdf_url": "https://arxiv.org/pdf/1.pdf",
            },
        ]

        merged = _merge_dedup_items(items, max_candidates=10, source_priority=["arxiv", "scholar"])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["source"], "arxiv")

    def test_collect_items_warns_when_scholar_key_missing(self):
        cfg = SimpleNamespace(
            categories=["cs.AI"],
            keywords=["robotics"],
            keyword_expression="",
            exclude_keywords=[],
            logic="AND",
            max_results=10,
            sort_by="lastUpdatedDate",
            sort_order="descending",
        )

        env_name = "ARXIV_TRACKER_TEST_SERPAPI_KEY"
        os.environ.pop(env_name, None)

        raw_cfg = {
            "sources": {
                "enabled": ["scholar"],
                "priority": ["scholar"],
                "max_candidates": 10,
                "scholar": {
                    "enabled": True,
                    "api_key_env": env_name,
                    "query": "robotics reinforcement learning",
                    "max_results": 5,
                },
            }
        }

        items, meta = collect_items(
            cfg,
            raw_cfg,
            since_days=0,
            unique_only=False,
            seen_ids=set(),
            fallback_when_empty=False,
        )

        self.assertEqual(items, [])
        self.assertTrue(meta.get("warnings"))
        self.assertIn("SERPAPI key is missing", meta["warnings"][0])


if __name__ == "__main__":
    unittest.main()
