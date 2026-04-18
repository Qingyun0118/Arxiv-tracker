# -*- coding: utf-8 -*-
from __future__ import annotations

import html
import hashlib
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import quote

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

_ARXIV_URL_ID_PAT = re.compile(r"arxiv\.org/(?:abs|pdf)/([^\s?#]+)", re.IGNORECASE)
_ARXIV_ID_PAT = re.compile(r"\b(?:[a-z\-]+\/\d{7}|\d{4}\.\d{4,5})(?:v\d+)?\b", re.IGNORECASE)
_DOI_PAT = re.compile(r"\b10\.\d{4,9}/[-._;()/:a-z0-9]+\b", re.IGNORECASE)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def _strip_markup(value: str) -> str:
    return _normalize_text(re.sub(r"<[^>]+>", " ", value or ""))


def _extract_doi(text: str) -> Optional[str]:
    m = _DOI_PAT.search(text or "")
    if not m:
        return None
    doi = m.group(0).strip().rstrip(".,;:)]}>\"'")
    return doi.lower() if doi else None


def _extract_arxiv_id(text: str) -> Optional[str]:
    raw_text = text or ""

    m_url = _ARXIV_URL_ID_PAT.search(raw_text)
    if m_url:
        candidate = m_url.group(1).strip().split("/")[-1]
        candidate = candidate.replace(".pdf", "").strip()
        m_id = _ARXIV_ID_PAT.search(candidate)
        if m_id:
            return m_id.group(0)

    m_id = _ARXIV_ID_PAT.search(raw_text)
    if m_id:
        return m_id.group(0)
    return None


def _token_set(value: str) -> Set[str]:
    tokens = re.findall(r"[a-z0-9]+", (value or "").lower())
    return {t for t in tokens if len(t) >= 3}


def _titles_similar(a: str, b: str) -> bool:
    na = _norm_title(a)
    nb = _norm_title(b)
    if not na or not nb:
        return False
    if na == nb:
        return True

    sa = _token_set(a)
    sb = _token_set(b)
    if not sa or not sb:
        return False
    inter = len(sa & sb)
    union = len(sa | sb)
    if union <= 0:
        return False
    return (inter / union) >= 0.60


def _summary_sentence_count(text: str) -> int:
    return len(re.findall(r"[.!?。！？]", text or ""))


def _is_summary_incomplete(summary: str, title: str, min_chars: int) -> bool:
    s = _normalize_text(summary)
    if not s:
        return True
    if _norm_title(s) == _norm_title(title or ""):
        return True
    if len(s) < max(40, int(min_chars or 0)):
        return True
    if s.endswith("...") or s.endswith("…"):
        return True
    if _summary_sentence_count(s) < 2 and len(s) < (max(120, int(min_chars or 0)) + 80):
        return True
    return False


def _decode_openalex_abstract(inverted_index: Any) -> str:
    if not isinstance(inverted_index, dict):
        return ""
    pairs: List[Tuple[int, str]] = []
    for word, positions in inverted_index.items():
        if not isinstance(positions, list):
            continue
        for p in positions:
            try:
                pairs.append((int(p), str(word)))
            except Exception:
                continue
    if not pairs:
        return ""
    pairs.sort(key=lambda x: x[0])
    return _normalize_text(" ".join(w for _, w in pairs))


def _load_summary_cache(path: str) -> Dict[str, Dict[str, str]]:
    if not path:
        return {}
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
                if isinstance(data, dict):
                    return data
    except Exception:
        return {}
    return {}


def _save_summary_cache(path: str, cache: Dict[str, Dict[str, str]]) -> None:
    if not path:
        return
    dir_path = os.path.dirname(path)
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def _build_summary_cache_key(item: Dict[str, Any]) -> str:
    doi = _normalize_text(str(item.get("doi") or "")).lower()
    if doi:
        return f"doi:{doi}"

    arxiv_id = _normalize_text(str(item.get("arxiv_id") or ""))
    if not arxiv_id:
        merged_text = "\n".join(
            [
                str(item.get("title") or ""),
                str(item.get("summary") or ""),
                str(item.get("comments") or ""),
                str(item.get("html_url") or ""),
                str(item.get("pdf_url") or ""),
            ]
        )
        arxiv_id = _extract_arxiv_id(merged_text) or ""
    if arxiv_id:
        return f"arxiv:{arxiv_id.lower()}"

    title_key = _norm_title(str(item.get("title") or ""))
    year = str(item.get("published") or "")[:4]
    if title_key:
        return f"title:{title_key}:{year}"
    return str(item.get("id") or "")


def _read_summary_from_cache(
    cache: Dict[str, Dict[str, str]],
    key: str,
    ttl_days: int,
) -> Optional[Tuple[str, str]]:
    if not key:
        return None
    row = cache.get(key)
    if not isinstance(row, dict):
        return None

    summary = _normalize_text(str(row.get("summary") or ""))
    if not summary:
        return None

    if ttl_days > 0:
        ts = _parse_dt(str(row.get("updated_at") or ""))
        if ts and (datetime.now(timezone.utc) - ts > timedelta(days=ttl_days)):
            return None

    source = _normalize_text(str(row.get("source") or "cache")) or "cache"
    return summary, source


def _find_meta_content(html_text: str, key: str) -> Optional[str]:
    k = re.escape(key)
    patterns = [
        rf'<meta[^>]+(?:name|property)\s*=\s*["\']{k}["\'][^>]*content\s*=\s*["\'](.*?)["\']',
        rf'<meta[^>]+content\s*=\s*["\'](.*?)["\'][^>]*(?:name|property)\s*=\s*["\']{k}["\']',
    ]
    for pat in patterns:
        m = re.search(pat, html_text or "", flags=re.IGNORECASE | re.DOTALL)
        if m:
            value = _normalize_text(m.group(1))
            if value:
                return value
    return None


def _provider_arxiv(item: Dict[str, Any], timeout: int) -> Optional[str]:
    merged_text = "\n".join(
        [
            str(item.get("arxiv_id") or ""),
            str(item.get("html_url") or ""),
            str(item.get("pdf_url") or ""),
            str(item.get("title") or ""),
            str(item.get("comments") or ""),
            str(item.get("summary") or ""),
        ]
    )
    arxiv_id = _extract_arxiv_id(merged_text)
    if not arxiv_id:
        return None
    try:
        xml = fetch_arxiv_feed(
            f"id:{arxiv_id}",
            start=0,
            max_results=1,
            sort_by="submittedDate",
            sort_order="descending",
        )
        parsed = parse_feed(xml) or []
        if not parsed:
            return None
        return _normalize_text(str(parsed[0].get("summary") or "")) or None
    except Exception:
        return None


def _provider_crossref(item: Dict[str, Any], timeout: int) -> Optional[str]:
    merged_text = "\n".join(
        [
            str(item.get("doi") or ""),
            str(item.get("html_url") or ""),
            str(item.get("title") or ""),
            str(item.get("comments") or ""),
            str(item.get("summary") or ""),
        ]
    )
    doi = _extract_doi(merged_text)
    if not doi:
        return None

    url = f"https://api.crossref.org/works/{quote(doi, safe='')}"
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        payload = resp.json() or {}
        message = payload.get("message") or {}
        return _strip_markup(str(message.get("abstract") or "")) or None
    except Exception:
        return None


def _provider_openalex(item: Dict[str, Any], timeout: int) -> Optional[str]:
    merged_text = "\n".join(
        [
            str(item.get("doi") or ""),
            str(item.get("html_url") or ""),
            str(item.get("title") or ""),
            str(item.get("comments") or ""),
            str(item.get("summary") or ""),
        ]
    )
    doi = _extract_doi(merged_text)
    title = _normalize_text(str(item.get("title") or ""))

    try:
        if doi:
            url = f"https://api.openalex.org/works/https://doi.org/{quote(doi, safe='')}"
            resp = requests.get(url, timeout=timeout)
            resp.raise_for_status()
            payload = resp.json() or {}
            abstract = _decode_openalex_abstract(payload.get("abstract_inverted_index"))
            if abstract:
                return abstract

        if title:
            resp = requests.get(
                "https://api.openalex.org/works",
                params={"search": title, "per-page": 3},
                timeout=timeout,
            )
            resp.raise_for_status()
            payload = resp.json() or {}
            for row in payload.get("results") or []:
                cand_title = _normalize_text(str(row.get("display_name") or ""))
                if title and cand_title and not _titles_similar(title, cand_title):
                    continue
                abstract = _decode_openalex_abstract(row.get("abstract_inverted_index"))
                if abstract:
                    return abstract
    except Exception:
        return None
    return None


def _provider_semantic_scholar(item: Dict[str, Any], timeout: int, api_key: str) -> Optional[str]:
    merged_text = "\n".join(
        [
            str(item.get("doi") or ""),
            str(item.get("html_url") or ""),
            str(item.get("title") or ""),
            str(item.get("comments") or ""),
            str(item.get("summary") or ""),
        ]
    )
    doi = _extract_doi(merged_text)
    title = _normalize_text(str(item.get("title") or ""))

    headers = {"Accept": "application/json"}
    if api_key:
        headers["x-api-key"] = api_key

    try:
        if doi:
            resp = requests.get(
                f"https://api.semanticscholar.org/graph/v1/paper/DOI:{quote(doi, safe='')}",
                params={"fields": "title,abstract"},
                headers=headers,
                timeout=timeout,
            )
            if resp.status_code < 400:
                payload = resp.json() or {}
                abstract = _normalize_text(str(payload.get("abstract") or ""))
                if abstract:
                    return abstract

        if title:
            resp = requests.get(
                "https://api.semanticscholar.org/graph/v1/paper/search",
                params={"query": title, "limit": 3, "fields": "title,abstract"},
                headers=headers,
                timeout=timeout,
            )
            if resp.status_code < 400:
                payload = resp.json() or {}
                for row in payload.get("data") or []:
                    cand_title = _normalize_text(str(row.get("title") or ""))
                    if cand_title and not _titles_similar(title, cand_title):
                        continue
                    abstract = _normalize_text(str(row.get("abstract") or ""))
                    if abstract:
                        return abstract
    except Exception:
        return None
    return None


def _provider_landing_page(item: Dict[str, Any], timeout: int) -> Optional[str]:
    url = _normalize_text(str(item.get("html_url") or ""))
    if not url:
        return None
    try:
        resp = requests.get(
            url,
            headers={
                "User-Agent": "arxiv-tracker/0.1 (+https://github.com/colorfulandcjy0806/Arxiv-tracker)",
                "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            },
            timeout=timeout,
            allow_redirects=True,
        )
        resp.raise_for_status()
        text = resp.text or ""

        keys = [
            "citation_abstract",
            "dc.description",
            "description",
            "og:description",
            "twitter:description",
        ]
        for key in keys:
            value = _find_meta_content(text, key)
            if value:
                return value

        m = re.search(r"<section[^>]*abstract[^>]*>(.*?)</section>", text, flags=re.IGNORECASE | re.DOTALL)
        if m:
            value = _strip_markup(m.group(1))
            if value:
                return value

        m2 = re.search(r"<div[^>]*abstract[^>]*>(.*?)</div>", text, flags=re.IGNORECASE | re.DOTALL)
        if m2:
            value = _strip_markup(m2.group(1))
            if value:
                return value
    except Exception:
        return None
    return None


def _resolve_abstract_enrichment_cfg(scholar_cfg: Dict[str, Any]) -> Dict[str, Any]:
    cfg = (scholar_cfg.get("abstract_enrichment") or {}) if isinstance(scholar_cfg, dict) else {}
    providers = cfg.get("providers") or ["arxiv", "crossref", "openalex", "semantic_scholar", "landing_page"]
    if isinstance(providers, str):
        providers = [x.strip() for x in providers.replace(";", ",").split(",") if x.strip()]
    providers = [str(x).strip().lower() for x in providers if str(x).strip()]

    s2_api_key = (
        str(cfg.get("semantic_scholar_api_key") or "").strip()
        or os.getenv(str(cfg.get("semantic_scholar_api_key_env") or "S2_API_KEY"), "").strip()
    )

    if "cache_path" in cfg:
        cache_path = str(cfg.get("cache_path") or "").strip()
    else:
        cache_path = ".state/scholar_abstract_cache.json"

    return {
        "enabled": bool(cfg.get("enabled", False)),
        "min_chars": max(40, int(cfg.get("min_chars", 260))),
        "max_enrich_items": max(0, int(cfg.get("max_enrich_items", 20))),
        "timeout": max(2, int(cfg.get("timeout", 8))),
        "max_workers": max(1, int(cfg.get("max_workers", 4))),
        "providers": providers or ["arxiv", "crossref", "openalex", "semantic_scholar", "landing_page"],
        "cache_path": cache_path,
        "cache_ttl_days": max(0, int(cfg.get("cache_ttl_days", 30))),
        "s2_api_key": s2_api_key,
    }


def _enrich_scholar_abstracts(
    items: List[Dict[str, Any]],
    scholar_cfg: Dict[str, Any],
) -> Tuple[Dict[str, int], List[str]]:
    stats = {"checked": 0, "attempted": 0, "enriched": 0, "cache_hits": 0}
    warnings: List[str] = []

    enrich_cfg = _resolve_abstract_enrichment_cfg(scholar_cfg)
    if not enrich_cfg.get("enabled", False):
        return stats, warnings

    min_chars = int(enrich_cfg.get("min_chars", 260))
    candidates: List[Dict[str, Any]] = []
    for item in items:
        if str(item.get("source") or "").lower() != "scholar":
            continue
        stats["checked"] += 1
        summary = str(item.get("summary") or "")
        title = str(item.get("title") or "")
        if _is_summary_incomplete(summary, title, min_chars):
            candidates.append(item)

    max_enrich_items = int(enrich_cfg.get("max_enrich_items", 20))
    if max_enrich_items > 0:
        candidates = candidates[:max_enrich_items]

    if not candidates:
        return stats, warnings

    stats["attempted"] = len(candidates)

    cache_path = str(enrich_cfg.get("cache_path") or "")
    cache_ttl_days = int(enrich_cfg.get("cache_ttl_days", 30))
    cache = _load_summary_cache(cache_path)
    cache_lock = Lock()
    provider_error_lock = Lock()
    cache_dirty = False

    providers = enrich_cfg.get("providers") or []
    timeout = int(enrich_cfg.get("timeout", 8))
    s2_api_key = str(enrich_cfg.get("s2_api_key") or "")

    def _call_provider(provider: str, item: Dict[str, Any]) -> Optional[str]:
        p = provider.lower().strip()
        if p == "arxiv":
            return _provider_arxiv(item, timeout)
        if p == "crossref":
            return _provider_crossref(item, timeout)
        if p == "openalex":
            return _provider_openalex(item, timeout)
        if p == "semantic_scholar":
            return _provider_semantic_scholar(item, timeout, s2_api_key)
        if p == "landing_page":
            return _provider_landing_page(item, timeout)
        return None

    def _process_one(item: Dict[str, Any]) -> str:
        nonlocal cache_dirty

        key = _build_summary_cache_key(item)
        cached = _read_summary_from_cache(cache, key, cache_ttl_days) if key else None
        if cached:
            summary, source = cached
            item["summary"] = summary
            item["summary_enriched"] = True
            item["summary_source"] = f"cache:{source}"
            item["summary_chars"] = len(summary)
            return "cache"

        title = str(item.get("title") or "")
        quality_min = max(120, min_chars // 2)
        for provider in providers:
            try:
                text = _normalize_text(_call_provider(provider, item) or "")
            except Exception:
                text = ""
                with provider_error_lock:
                    nonlocal_provider_errors["count"] += 1
                continue

            if not text:
                continue
            if _is_summary_incomplete(text, title, quality_min):
                continue

            item["summary"] = text
            item["summary_enriched"] = True
            item["summary_source"] = provider
            item["summary_chars"] = len(text)

            if key:
                with cache_lock:
                    cache[key] = {
                        "summary": text,
                        "source": provider,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                    cache_dirty = True
            return "enriched"

        item["summary_chars"] = len(_normalize_text(str(item.get("summary") or "")))
        return "unchanged"

    nonlocal_provider_errors = {"count": 0}

    workers = min(int(enrich_cfg.get("max_workers", 4)), len(candidates))
    if workers <= 1:
        outcomes = [_process_one(it) for it in candidates]
    else:
        outcomes: List[str] = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_process_one, it) for it in candidates]
            for fut in as_completed(futures):
                try:
                    outcomes.append(fut.result())
                except Exception:
                    outcomes.append("unchanged")

    for status in outcomes:
        if status == "cache":
            stats["cache_hits"] += 1
        elif status == "enriched":
            stats["enriched"] += 1

    if cache_dirty:
        try:
            _save_summary_cache(cache_path, cache)
        except Exception as e:
            warnings.append(f"Scholar abstract cache save failed: {e}")

    if nonlocal_provider_errors["count"] > 0:
        warnings.append(
            f"Scholar abstract enrichment had {nonlocal_provider_errors['count']} provider call failure(s)."
        )

    warnings.append(
        "Scholar abstract enrichment: checked={checked}, attempted={attempted}, "
        "enriched={enriched}, cache_hits={cache_hits}.".format(**stats)
    )
    return stats, warnings


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
    pub_summary = _normalize_text(str(pub_info.get("summary") or ""))

    authors: List[str] = []
    for a in pub_info.get("authors") or []:
        if isinstance(a, dict) and a.get("name"):
            authors.append(str(a.get("name")))

    snippet = _normalize_text(str(raw.get("snippet") or ""))
    summary = _normalize_text(snippet or pub_summary or title)
    if snippet:
        summary_source = "scholar_snippet"
    elif pub_summary:
        summary_source = "scholar_publication_info"
    else:
        summary_source = "scholar_title_fallback"

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

    merged_text = "\n".join([title, summary, pub_summary, link, pdf_url or ""])
    doi = _extract_doi(merged_text)
    arxiv_id = _extract_arxiv_id(merged_text)
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
        "summary_source": summary_source,
        "summary_enriched": False,
        "summary_chars": len(summary),
        "doi": doi,
        "arxiv_id": arxiv_id,
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
) -> Tuple[List[Dict[str, Any]], str, List[str]]:
    warnings: List[str] = []

    query = _build_scholar_query(categories, keywords, scholar_cfg, keyword_expression)
    endpoint = (scholar_cfg.get("endpoint") or "https://serpapi.com/search.json").strip()
    api_key = (scholar_cfg.get("api_key") or os.getenv(scholar_cfg.get("api_key_env") or "SERPAPI_API_KEY", "")).strip()
    if not api_key:
        return [], query, ["SERPAPI key is missing (set sources.scholar.api_key or env SERPAPI_API_KEY)."]

    start_year, end_year = _resolve_year_window(scholar_cfg)

    max_results = int(scholar_cfg.get("max_results", 20))
    if max_results <= 0:
        return [], query, warnings

    per_page = int(scholar_cfg.get("page_size", 20))
    per_page = max(1, min(20, per_page))

    items: List[Dict[str, Any]] = []
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
            warnings.append(f"Scholar request failed: {e}")
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

    if items:
        _, enrich_warnings = _enrich_scholar_abstracts(items, scholar_cfg)
        warnings.extend(enrich_warnings)

    return items, query, warnings


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
        try:
            arxiv_items, arxiv_query = _fetch_arxiv_items(
                cfg,
                arxiv_cfg=arxiv_cfg,
                cutoff=cutoff,
                unique_only=unique_only,
                seen_ids=seen_ids,
                fallback_when_empty=fallback_when_empty,
            )
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else None
            if status != 429:
                raise
            arxiv_items, arxiv_query = [], ""
            meta["warnings"].append(f"arXiv request failed: {e}")
        all_items.extend(arxiv_items)
        meta["queries"]["arxiv"] = arxiv_query
        meta["counts"]["arxiv"] = len(arxiv_items)

    if "scholar" in enabled_sources:
        scholar_cfg = sources_cfg.get("scholar") or {}
        if bool(scholar_cfg.get("enabled", True)):
            scholar_items, scholar_query, scholar_warnings = _fetch_scholar_items(
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
            if scholar_warnings:
                meta["warnings"].extend(scholar_warnings)

    merged = _merge_dedup_items(all_items, max_candidates=max_candidates, source_priority=source_priority)
    meta["counts"]["merged"] = len(merged)
    return merged, meta
