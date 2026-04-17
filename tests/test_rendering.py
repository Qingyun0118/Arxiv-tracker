import os
import tempfile
import unittest

from arxiv_tracker.email_template import render_email_html
from arxiv_tracker.output import save_markdown
from arxiv_tracker.sitegen import generate_site


def _item_with_score(score):
    return {
        "id": "item-1",
        "source": "arxiv",
        "title": "Test Paper",
        "authors": ["Alice"],
        "published": "2026-01-01T00:00:00+00:00",
        "updated": "2026-01-02T00:00:00+00:00",
        "summary": "A short abstract.",
        "html_url": "https://example.com/abs",
        "pdf_url": "https://example.com/pdf",
        "semantic_score": score,
    }


class RenderingTests(unittest.TestCase):
    def test_markdown_shows_semantic_relevance(self):
        with tempfile.TemporaryDirectory() as out_dir:
            path = save_markdown(
                [_item_with_score(8.321)],
                out_dir,
                summaries_zh={},
                summaries_en={},
                lang="en",
                translations={},
                deep_analyses={},
                analysis_top_n=0,
            )
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()

        self.assertIn("语义相关性分数：高 (8.321)", text)

    def test_email_shows_semantic_relevance(self):
        html = render_email_html(
            [_item_with_score(6.5)],
            translations={},
            summaries_zh={},
            summaries_en={},
            deep_analyses={},
            analysis_top_n=0,
        )
        self.assertIn("语义相关性分数: 中 (6.500)", html)

    def test_site_shows_semantic_relevance(self):
        with tempfile.TemporaryDirectory() as site_dir:
            result = generate_site(
                [_item_with_score(5.2)],
                summaries_zh={},
                summaries_en={},
                translations={},
                site_dir=site_dir,
                site_title="Test",
                deep_analyses={},
                analysis_top_n=0,
            )

            with open(result["index_path"], "r", encoding="utf-8") as f:
                html = f.read()

        self.assertIn("语义相关性分数: 低 (5.200)", html)


if __name__ == "__main__":
    unittest.main()
