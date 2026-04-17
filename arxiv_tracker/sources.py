# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

import requests

from .client import fetch_arxiv_feed
from .extractors import extract_urls, extract_venue_info
from .parser import parse_feed
from .query import build_search_query


_CATEGORY_HINTS = {
    "cs.RO": "robotics autonomous systems",
    "cs.AI": "artificial intelligence",
    "cs.LG": "machine learning",
    "cs.CV": "computer vision",
    "cs.CL": "natural language processing",
}


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def _year_to_iso(year: Optional[int]) -> Optional[str]:
    if not year:
        return None
    return f"{year:04d}-01-01T00:00:00+00:00"


def _extract_year(text: str) -> Optional[int]:
    m = re.search(r"\b(19|20)\d{2}\b", text or "")
    if not m:
        return None
    try:
        return int(m.group(0))
    except Exception:
        return None


def _norm_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def _meta_score(item: Dict[str, Any]) -> int:
    score = 0
    if item.get("pdf_url"):
        score += 2
    if item.get("authors"):
        score += 1
    if item.get("summary"):
        score += min(len(item.get("summary") or "") // 120, 3)
    return score


def _sort_key(item: Dict[str, Any]) -> Tuple[datetime, int]:
    dt = _parse_dt(item.get("updated")) or _parse_dt(item.get("published"))
    if dt is None:
        dt = datetime(1970, 1, 1, tzinfo=timezone.utc)
    return dt, _meta_score(item)


def _build_scholar_query(
    categories: List[str],
    keywords: List[str],
    scholar_cfg: Dict[str, Any],
    keyword_expression: str = "",
) -> str:
    query = (scholar_cfg.get("query") or "").strip()
    if query:
        return query

    expr = (keyword_expression or "").strip()
    if expr:
        return expr

    kw = [k.strip() for k in (keywords or []) if k and k.strip()]
    parts: List[str] = []
    if kw:
        quoted = [f'"{x}"' if " " in x else x for x in kw]
        parts.append("(" + " OR ".join(quoted) + ")" if len(quoted) > 1 else quoted[0])

    cat_hints = []
    for c in categories or []:
        cat_hints.append(_CATEGORY_HINTS.get(c.strip(), c.strip()))
    cat_hints = [x for x in cat_hints if x]
    if cat_hints:
        parts.append("(" + " OR ".join(cat_hints) + ")")

    suffix = (scholar_cfg.get("query_suffix") or "").strip()
    if suffix:
        parts.append(suffix)

    if not parts:
        return "latest research"
    return " ".join(parts)


def _resolve_year_window(scholar_cfg: Dict[str, Any]) -> Tuple[Optional[int], Optional[int]]:
    now_year = datetime.now(timezone.utc).year
    tf_cfg = (scholar_cfg.get("timeframe") or {})
    mode = str(tf_cfg.get("mode") or "last_2_years").lower()

    if mode == "this_year":
        return now_year, now_year
    if mode in ("last_2_years", "recent_2y", "two_years"):
        return now_year - 1, now_year
    if mode == "custom":
        start = tf_cfg.get("start_year")
        end = tf_cfg.get("end_year")
        try:
            start_year = int(start) if start is not None else None
            end_year = int(end) if end is not None else None
            return start_year, end_year
        except Exception:
            return None, None
    return None, None


def _normalize_scholar_item(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    title = (raw.get("title") or "").strip()
    if not title:
        return None

    link = (raw.get("link") or "").strip()
    result_id = (raw.get("result_id") or "").strip()
    if not result_id:
        result_id = hashlib.sha1((link or title).encode("utf-8")).hexdigest()[:16]

    pub_info = raw.get("publication_info") or {}
    pub_summary = pub_info.get("summary") or ""

    authors: List[str] = []
    for a in pub_info.get("authors") or []:
        if isinstance(a, dict) and a.get("name"):
            authors.append(str(a.get("name")))

    snippet = (raw.get("snippet") or "").strip()
    summary = snippet or pub_summary or title

    year = _extract_year(pub_summary) or _extract_year(snippet)
    published_iso = _year_to_iso(year)

    pdf_url = None
    for res in raw.get("resources") or []:
        if not isinstance(res, dict):
            continue
        file_fmt = str(res.get("file_format") or "").lower()
        if file_fmt == "pdf":
            pdf_url = (res.get("link") or res.get("serpapi_link") or "").strip() or None
            if pdf_url:
                break

    merged_text = "\n".join([title, summary, pub_summary, link])
    url_info = extract_urls(merged_text)
    code_urls = url_info.get("code_urls", [])
    project_urls = url_info.get("project_urls", [])
    all_urls = url_info.get("all_urls", [])
    other_urls = [u for u in all_urls if u not in set(code_urls + project_urls)]

    item = {
        "id": f"scholar:{result_id}",
        "source": "scholar",
        "title": title,
        "authors": authors,
        "primary_category": None,
        "categories": [],
        "published": published_iso,
        "updated": published_iso,
        "comments": pub_summary,
        "journal_ref": pub_summary,
        "venue_inferred": extract_venue_info(pub_summary) or "",
        "summary": summary,
        "html_url": link or None,
        "pdf_url": pdf_url,
        "code_urls": code_urls,
        "project_urls": project_urls,
        "other_urls": other_urls,
    }
    return item


def _fetch_arxiv_items(
    cfg: Any,
    *,
    arxiv_cfg: Dict[str, Any],
    cutoff: Optional[datetime],
    unique_only: bool,
    seen_ids: Set[str],
    fallback_when_empty: bool,
) -> Tuple[List[Dict[str, Any]], str]:
    query = (arxiv_cfg.get("query") or "").strip()
    if not query:
        query = build_search_query(
            cfg.categories,
            cfg.keywords,
            cfg.exclude_keywords,
            cfg.logic,
            getattr(cfg, "keyword_expression", ""),
        )

    want_new = int(arxiv_cfg.get("max_results", cfg.max_results or 50))
    page_size = int(arxiv_cfg.get("page_size", min(200, max(25, want_new))))
    max_pages = int(arxiv_cfg.get("max_pages", 20))

    collected: List[Dict[str, Any]] = []
    reached_cutoff = False
    start = 0

    for _ in range(max_pages):
        xml = fetch_arxiv_feed(query, start=start, max_results=page_size, sort_by=cfg.sort_by, sort_order=cfg.sort_order)
        page_items = parse_feed(xml) or []
        if not page_items:
            break

        for it in page_items:
            it.setdefault("source", "arxiv")
            dt = _parse_dt(it.get("updated")) or _parse_dt(it.get("published"))
            if cutoff and dt and dt < cutoff:
                reached_cutoff = True
                break

            pid = it.get("id")
            if unique_only and pid and pid in seen_ids:
                continue

            collected.append(it)
            if len(collected) >= want_new:
                break

        if len(collected) >= want_new or reached_cutoff:
            break
        if len(page_items) < page_size:
            break
        start += page_size

    if not collected and fallback_when_empty:
        xml = fetch_arxiv_feed(query, start=0, max_results=want_new, sort_by=cfg.sort_by, sort_order=cfg.sort_order)
        collected = parse_feed(xml) or []
        for it in collected:
            it.setdefault("source", "arxiv")

    return collected, query


def _fetch_scholar_items(
    categories: List[str],
    keywords: List[str],
    keyword_expression: str,
    *,
    scholar_cfg: Dict[str, Any],
    cutoff: Optional[datetime],
    unique_only: bool,
    seen_ids: Set[str],
) -> Tuple[List[Dict[str, Any]], str, Optional[str]]:
    endpoint = (scholar_cfg.get("endpoint") or "https://serpapi.com/search.json").strip()
    api_key = (scholar_cfg.get("api_key") or os.getenv(scholar_cfg.get("api_key_env") or "SERPAPI_API_KEY", "")).strip()
    if not api_key:
        return [], "", "SERPAPI key is missing (set sources.scholar.api_key or env SERPAPI_API_KEY)."

    query = _build_scholar_query(categories, keywords, scholar_cfg, keyword_expression)
    start_year, end_year = _resolve_year_window(scholar_cfg)

    max_results = int(scholar_cfg.get("max_results", 20))
    if max_results <= 0:
        return [], query, None

    per_page = int(scholar_cfg.get("page_size", 20))
    per_page = max(1, min(20, per_page))

    items: List[Dict[str, Any]] = []
    error_msg = None

    for start in range(0, max_results, per_page):
        params: Dict[str, Any] = {
            "engine": "google_scholar",
            "q": query,
            "api_key": api_key,
            "start": start,
            "num": min(per_page, max_results - start),
        }
        if start_year:
            params["as_ylo"] = start_year
        if end_year:
            params["as_yhi"] = end_year

        try:
            resp = requests.get(endpoint, params=params, timeout=20)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as e:
            error_msg = f"Scholar request failed: {e}"
            break

        organic = payload.get("organic_results") or []
        if not organic:
            break

        for raw in organic:
            item = _normalize_scholar_item(raw)
            if not item:
                continue

            item_id = item.get("id")
            if unique_only and item_id and item_id in seen_ids:
                continue

            dt = _parse_dt(item.get("updated")) or _parse_dt(item.get("published"))
            if cutoff and dt and dt < cutoff:
                continue

            items.append(item)

        if len(organic) < params["num"]:
            break

    return items, query, error_msg


def _merge_dedup_items(items: List[Dict[str, Any]], max_candidates: int, source_priority: List[str]) -> List[Dict[str, Any]]:
    source_rank = {s.lower(): i for i, s in enumerate(source_priority)}

    def dedup_key(it: Dict[str, Any]) -> str:
        t = _norm_title(it.get("title") or "")
        y = (it.get("published") or "")[:4]
        if t:
            return f"{t}:{y}"
        return it.get("id") or hashlib.sha1(str(it).encode("utf-8")).hexdigest()

    def is_better(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
        sa = source_rank.get((a.get("source") or "").lower(), 999)
        sb = source_rank.get((b.get("source") or "").lower(), 999)
        if sa != sb:
            return sa < sb
        if _sort_key(a) != _sort_key(b):
            return _sort_key(a) > _sort_key(b)
        return _meta_score(a) > _meta_score(b)

    chosen: Dict[str, Dict[str, Any]] = {}
    for item in items:
        key = dedup_key(item)
        prev = chosen.get(key)
        if prev is None or is_better(item, prev):
            chosen[key] = item

    merged = list(chosen.values())
    merged.sort(key=_sort_key, reverse=True)
    return merged[:max_candidates]


def collect_items(
    cfg: Any,
    raw_cfg: Dict[str, Any],
    *,
    since_days: int,
    unique_only: bool,
    seen_ids: Set[str],
    fallback_when_empty: bool,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    sources_cfg = raw_cfg.get("sources") or {}
    enabled_sources = [str(x).strip().lower() for x in (sources_cfg.get("enabled") or ["arxiv"]) if str(x).strip()]
    source_priority = [str(x).strip().lower() for x in (sources_cfg.get("priority") or enabled_sources)]
    max_candidates = int(sources_cfg.get("max_candidates", cfg.max_results or 50))

    cutoff = datetime.now(timezone.utc) - timedelta(days=since_days) if since_days > 0 else None

    all_items: List[Dict[str, Any]] = []
    meta: Dict[str, Any] = {
        "queries": {},
        "counts": {},
        "warnings": [],
    }

    if "arxiv" in enabled_sources:
        arxiv_cfg = sources_cfg.get("arxiv") or {}
        arxiv_items, arxiv_query = _fetch_arxiv_items(
            cfg,
            arxiv_cfg=arxiv_cfg,
            cutoff=cutoff,
            unique_only=unique_only,
            seen_ids=seen_ids,
            fallback_when_empty=fallback_when_empty,
        )
        all_items.extend(arxiv_items)
        meta["queries"]["arxiv"] = arxiv_query
        meta["counts"]["arxiv"] = len(arxiv_items)

    if "scholar" in enabled_sources:
        scholar_cfg = sources_cfg.get("scholar") or {}
        if bool(scholar_cfg.get("enabled", True)):
            scholar_items, scholar_query, err = _fetch_scholar_items(
                cfg.categories,
                cfg.keywords,
                getattr(cfg, "keyword_expression", ""),
                scholar_cfg=scholar_cfg,
                cutoff=cutoff,
                unique_only=unique_only,
                seen_ids=seen_ids,
            )
            all_items.extend(scholar_items)
            meta["queries"]["scholar"] = scholar_query
            meta["counts"]["scholar"] = len(scholar_items)
            if err:
                meta["warnings"].append(err)

    merged = _merge_dedup_items(all_items, max_candidates=max_candidates, source_priority=source_priority)
    meta["counts"]["merged"] = len(merged)
    return merged, meta
