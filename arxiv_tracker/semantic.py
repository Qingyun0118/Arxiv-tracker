# -*- coding: utf-8 -*-
from __future__ import annotations

import fnmatch
import math
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests

try:
    from pyzotero import zotero as pyzotero
except Exception:
    pyzotero = None


def _normalize_embeddings_endpoint(base_url: str) -> str:
    base = (base_url or "").rstrip("/")
    if not base:
        raise ValueError("embedding base_url is empty")
    if base.endswith("/embeddings"):
        return base
    if base.endswith("/v1"):
        return base + "/embeddings"
    return base + "/v1/embeddings"


def _dot(v1: List[float], v2: List[float]) -> float:
    return sum(a * b for a, b in zip(v1, v2))


def _norm(v: List[float]) -> float:
    return math.sqrt(sum(x * x for x in v))


def _cosine(v1: List[float], v2: List[float]) -> float:
    n1 = _norm(v1)
    n2 = _norm(v2)
    if n1 <= 1e-12 or n2 <= 1e-12:
        return 0.0
    return _dot(v1, v2) / (n1 * n2)


def _resolve_env_preferred(cfg: Dict[str, Any], value_key: str, env_key: str) -> str:
    env_name = str(cfg.get(env_key) or "").strip()
    if env_name:
        env_value = os.getenv(env_name, "").strip()
        if env_value:
            return env_value
    return str(cfg.get(value_key) or "").strip()


def _embed_texts(texts: List[str], emb_cfg: Dict[str, Any]) -> List[List[float]]:
    if not texts:
        return []

    base_url = _resolve_env_preferred(emb_cfg, "base_url", "base_url_env")

    api_key = str(emb_cfg.get("api_key") or "").strip()
    if not api_key:
        api_key_env = str(emb_cfg.get("api_key_env") or "OPENAI_COMPAT_API_KEY").strip()
        api_key = os.getenv(api_key_env, "").strip()

    model = _resolve_env_preferred(emb_cfg, "model", "model_env") or "text-embedding-3-small"
    batch_size = int(emb_cfg.get("batch_size", 64))
    timeout = int(emb_cfg.get("timeout", 45))

    if not api_key:
        raise RuntimeError("embedding api key is missing")

    endpoint = _normalize_embeddings_endpoint(base_url)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    vectors: List[List[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        payload = {
            "model": model,
            "input": batch,
        }
        resp = requests.post(endpoint, json=payload, headers=headers, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        vecs = [x.get("embedding") for x in (data.get("data") or [])]
        if len(vecs) != len(batch):
            raise RuntimeError("embedding response size mismatch")
        vectors.extend(vecs)
    return vectors


def _safe_date(value: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return datetime(1970, 1, 1)


def _parse_item_datetime(item: Dict[str, Any]) -> datetime:
    for key in ("updated", "published"):
        raw = str(item.get(key) or "").strip()
        if not raw:
            continue
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            continue
    return datetime(1970, 1, 1, tzinfo=timezone.utc)


def _compute_freshness_scores(items: List[Dict[str, Any]]) -> List[float]:
    if not items:
        return []

    stamps = [_parse_item_datetime(it).timestamp() for it in items]
    lo = min(stamps)
    hi = max(stamps)

    if hi - lo <= 1e-12:
        return [10.0 for _ in items]

    scores: List[float] = []
    for ts in stamps:
        # Normalize by recency: latest=10, oldest=0.
        scores.append(((ts - lo) / (hi - lo)) * 10.0)
    return scores


def _resolve_rank_weights(semantic_cfg: Dict[str, Any]) -> Tuple[float, float]:
    ranking_cfg = (semantic_cfg or {}).get("ranking") or {}

    try:
        time_weight = float(ranking_cfg.get("time_weight", 0.6))
    except Exception:
        time_weight = 0.6

    try:
        semantic_weight = float(ranking_cfg.get("semantic_weight", 0.4))
    except Exception:
        semantic_weight = 0.4

    time_weight = max(0.0, time_weight)
    semantic_weight = max(0.0, semantic_weight)

    total = time_weight + semantic_weight
    if total <= 1e-12:
        return 0.6, 0.4
    return time_weight / total, semantic_weight / total


def _normalize_include_patterns(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = value.replace(";", ",").split(",")
        return [p.strip() for p in parts if p.strip()]
    if isinstance(value, (list, tuple, set)):
        out: List[str] = []
        for item in value:
            s = str(item).strip()
            if s:
                out.append(s)
        return out
    s = str(value).strip()
    return [s] if s else []


def _read_zotero_corpus(semantic_cfg: Dict[str, Any]) -> List[str]:
    zotero_cfg = semantic_cfg.get("zotero") or {}
    include_patterns = _normalize_include_patterns(zotero_cfg.get("include_path"))
    require_include_path = bool(zotero_cfg.get("require_include_path", True))
    if require_include_path and not include_patterns:
        raise RuntimeError(
            "zotero include_path is required when semantic.enabled=true "
            "(set semantic.zotero.include_path, e.g. ['2026/rl/**'])."
        )

    if pyzotero is None:
        raise RuntimeError("pyzotero is not installed")

    user_id = zotero_cfg.get("user_id") or os.getenv(zotero_cfg.get("user_id_env") or "ZOTERO_ID", "")
    api_key = zotero_cfg.get("api_key") or os.getenv(zotero_cfg.get("api_key_env") or "ZOTERO_KEY", "")
    max_corpus = int(zotero_cfg.get("max_corpus", 300))

    if not user_id or not api_key:
        raise RuntimeError("zotero credentials are missing")

    client = pyzotero.Zotero(user_id, "user", api_key)
    collections = client.everything(client.collections())
    col_map = {c["key"]: c for c in collections}

    def get_collection_path(col_key: str) -> str:
        item = col_map.get(col_key)
        if not item:
            return ""
        parent = item["data"].get("parentCollection")
        name = item["data"].get("name") or ""
        if parent:
            return (get_collection_path(parent) + "/" + name).strip("/")
        return name

    corpus_items = client.everything(client.items(itemType="conferencePaper || journalArticle || preprint"))
    rows: List[Tuple[datetime, str]] = []

    for it in corpus_items:
        data = it.get("data") or {}
        abstract = (data.get("abstractNote") or "").strip()
        if not abstract:
            continue

        paths = [get_collection_path(x) for x in data.get("collections") or []]
        if include_patterns:
            hit = False
            for p in paths:
                if any(fnmatch.fnmatch(p, pat) for pat in include_patterns):
                    hit = True
                    break
            if not hit:
                continue

        added = _safe_date(data.get("dateAdded") or "")
        rows.append((added, abstract))

    rows.sort(key=lambda x: x[0], reverse=True)
    return [r[1] for r in rows[:max_corpus]]


def rerank_items_with_zotero(
    items: List[Dict[str, Any]],
    semantic_cfg: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], Dict[str, float], Optional[str]]:
    if not items:
        return items, {}, None
    if not (semantic_cfg or {}).get("enabled", False):
        return items, {}, None

    try:
        corpus = _read_zotero_corpus(semantic_cfg)
        if not corpus:
            return items, {}, "zotero corpus is empty"

        emb_cfg = semantic_cfg.get("embedding") or {}
        candidate_texts = [((it.get("summary") or "").strip() or (it.get("title") or "").strip()) for it in items]
        candidate_vecs = _embed_texts(candidate_texts, emb_cfg)
        corpus_vecs = _embed_texts(corpus, emb_cfg)

        scores: Dict[str, float] = {}
        for item, vec in zip(items, candidate_vecs):
            sims = [_cosine(vec, cvec) for cvec in corpus_vecs]
            best = max(sims) if sims else 0.0
            score = (best + 1.0) * 5.0
            sid = item.get("id") or ""
            if sid:
                scores[sid] = score
            item["semantic_score"] = score

        freshness_scores = _compute_freshness_scores(items)
        time_weight, semantic_weight = _resolve_rank_weights(semantic_cfg)

        for item, freshness_score in zip(items, freshness_scores):
            semantic_score = float(item.get("semantic_score") or 0.0)
            rank_score = (time_weight * freshness_score) + (semantic_weight * semantic_score)
            item["freshness_score"] = freshness_score
            item["rank_score"] = rank_score

        sorted_items = sorted(
            items,
            key=lambda x: (
                x.get("rank_score", 0.0),
                x.get("freshness_score", 0.0),
                x.get("semantic_score", 0.0),
            ),
            reverse=True,
        )
        return sorted_items, scores, None
    except Exception as e:
        return items, {}, f"semantic rerank skipped: {e}"
