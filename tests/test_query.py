import unittest

from arxiv_tracker.query import build_search_query


class QueryBuilderTests(unittest.TestCase):
    def test_legacy_keywords_mode_still_works(self):
        query = build_search_query(
            categories=["cs.AI"],
            keywords=["open vocabulary segmentation", "vision language model"],
            exclude_keywords=["Large Language Model"],
            logic="AND",
        )
        self.assertIn("cat:cs.AI", query)
        self.assertIn("AND NOT", query)
        self.assertIn("open vocabulary segmentation", query)

    def test_keyword_expression_with_parentheses(self):
        query = build_search_query(
            categories=["cs.RO"],
            keywords=[],
            logic="AND",
            keyword_expression="(open vocabulary segmentation OR vision language grounding) AND (reinforcement learning OR MARL)",
        )
        self.assertIn("cat:cs.RO", query)
        self.assertIn("AND", query)
        self.assertIn("open vocabulary segmentation", query)
        self.assertIn("vision language grounding", query)
        self.assertIn("reinforcement learning", query)
        self.assertIn("MARL", query)

    def test_invalid_keyword_expression_raises(self):
        with self.assertRaises(ValueError):
            build_search_query(
                categories=[],
                keywords=[],
                keyword_expression="(open vocabulary OR) AND reinforcement learning",
            )


if __name__ == "__main__":
    unittest.main()
