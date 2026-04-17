import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from arxiv_tracker.sources import _enrich_scholar_abstracts, _merge_dedup_items, collect_items


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

    def test_collect_items_scholar_prefers_keyword_expression(self):
        cfg = SimpleNamespace(
            categories=["cs.RO"],
            keywords=["robotics", "navigation"],
            keyword_expression='"reinforcement learning" AND "collision avoidance"',
            exclude_keywords=[],
            logic="AND",
            max_results=10,
            sort_by="lastUpdatedDate",
            sort_order="descending",
        )

        env_name = "ARXIV_TRACKER_TEST_SERPAPI_KEY"
        raw_cfg = {
            "sources": {
                "enabled": ["scholar"],
                "priority": ["scholar"],
                "max_candidates": 10,
                "scholar": {
                    "enabled": True,
                    "api_key_env": env_name,
                    "query": "",
                    "max_results": 0,
                },
            }
        }

        with patch.dict(os.environ, {env_name: "dummy-key"}, clear=False):
            items, meta = collect_items(
                cfg,
                raw_cfg,
                since_days=0,
                unique_only=False,
                seen_ids=set(),
                fallback_when_empty=False,
            )

        self.assertEqual(items, [])
        self.assertEqual(
            meta.get("queries", {}).get("scholar"),
            '"reinforcement learning" AND "collision avoidance"',
        )

    def test_scholar_abstract_enrichment_replaces_short_snippet(self):
        items = [
            {
                "id": "scholar:1",
                "source": "scholar",
                "title": "Paper A",
                "summary": "short snippet",
                "doi": "10.1000/test-doi",
            }
        ]
        long_abs = (
            "This work studies safe marine navigation with reinforcement learning under realistic disturbances. "
            "Extensive experiments on multiple benchmarks show robust gains in collision avoidance and route efficiency."
        )
        cfg = {
            "abstract_enrichment": {
                "enabled": True,
                "providers": ["crossref"],
                "min_chars": 120,
                "max_enrich_items": 20,
                "max_workers": 1,
                "cache_path": "",
            }
        }

        with patch("arxiv_tracker.sources._provider_crossref", return_value=long_abs):
            stats, warnings = _enrich_scholar_abstracts(items, cfg)

        self.assertEqual(stats["checked"], 1)
        self.assertEqual(stats["attempted"], 1)
        self.assertEqual(stats["enriched"], 1)
        self.assertEqual(items[0]["summary"], long_abs)
        self.assertTrue(items[0]["summary_enriched"])
        self.assertEqual(items[0]["summary_source"], "crossref")
        self.assertGreater(items[0]["summary_chars"], 120)
        self.assertTrue(any("Scholar abstract enrichment" in w for w in warnings))

    def test_scholar_abstract_enrichment_fallback_to_next_provider(self):
        items = [
            {
                "id": "scholar:2",
                "source": "scholar",
                "title": "Paper B",
                "summary": "short snippet",
            }
        ]
        long_abs = (
            "A two-stage control framework is introduced for underwater robots in cluttered environments. "
            "Comparative evaluations report higher success rates and smoother trajectories."
        )
        cfg = {
            "abstract_enrichment": {
                "enabled": True,
                "providers": ["crossref", "landing_page"],
                "min_chars": 120,
                "max_workers": 1,
                "cache_path": "",
            }
        }

        with patch("arxiv_tracker.sources._provider_crossref", return_value=None), patch(
            "arxiv_tracker.sources._provider_landing_page", return_value=long_abs
        ):
            stats, _ = _enrich_scholar_abstracts(items, cfg)

        self.assertEqual(stats["enriched"], 1)
        self.assertEqual(items[0]["summary_source"], "landing_page")

    def test_scholar_abstract_enrichment_uses_cache(self):
        long_abs = (
            "This paper proposes an adaptive planner for USV navigation with uncertainty-aware policy updates. "
            "Results demonstrate improved safety margins and lower path deviation across challenging scenarios."
        )

        with tempfile.TemporaryDirectory() as td:
            cache_path = os.path.join(td, "scholar_abstract_cache.json")
            cfg = {
                "abstract_enrichment": {
                    "enabled": True,
                    "providers": ["crossref"],
                    "min_chars": 120,
                    "max_workers": 1,
                    "cache_path": cache_path,
                }
            }

            first_items = [
                {
                    "id": "scholar:3",
                    "source": "scholar",
                    "title": "Paper C",
                    "summary": "short snippet",
                    "doi": "10.1000/cache-doi",
                }
            ]
            with patch("arxiv_tracker.sources._provider_crossref", return_value=long_abs):
                first_stats, _ = _enrich_scholar_abstracts(first_items, cfg)
            self.assertEqual(first_stats["enriched"], 1)

            second_items = [
                {
                    "id": "scholar:4",
                    "source": "scholar",
                    "title": "Paper C",
                    "summary": "short snippet",
                    "doi": "10.1000/cache-doi",
                }
            ]
            with patch("arxiv_tracker.sources._provider_crossref", side_effect=AssertionError("should not call provider")):
                second_stats, _ = _enrich_scholar_abstracts(second_items, cfg)

            self.assertEqual(second_stats["cache_hits"], 1)
            self.assertTrue(second_items[0]["summary_source"].startswith("cache:"))
            self.assertEqual(second_items[0]["summary"], long_abs)

    def test_scholar_abstract_enrichment_skips_when_summary_is_complete(self):
        summary = (
            "A complete abstract with enough details on motivation, method and outcomes in real-world conditions. "
            "The evaluation includes ablations and comparisons against strong baselines to support the claims."
        )
        items = [
            {
                "id": "scholar:5",
                "source": "scholar",
                "title": "Paper D",
                "summary": summary,
            }
        ]
        cfg = {
            "abstract_enrichment": {
                "enabled": True,
                "providers": ["crossref"],
                "min_chars": 120,
                "max_workers": 1,
                "cache_path": "",
            }
        }

        with patch("arxiv_tracker.sources._provider_crossref", side_effect=AssertionError("should not be called")):
            stats, _ = _enrich_scholar_abstracts(items, cfg)

        self.assertEqual(stats["checked"], 1)
        self.assertEqual(stats["attempted"], 0)
        self.assertEqual(stats["enriched"], 0)


if __name__ == "__main__":
    unittest.main()
