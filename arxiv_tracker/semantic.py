# -*- coding: utf-8 -*-
from __future__ import annotations

import fnmatch
import math
import os
from datetime import datetime
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


def _embed_texts(texts: List[str], emb_cfg: Dict[str, Any]) -> List[List[float]]:
    if not texts:
        return []

    base_url = emb_cfg.get("base_url") or ""
    api_key = emb_cfg.get("api_key") or os.getenv(emb_cfg.get("api_key_env") or "OPENAI_COMPAT_API_KEY", "")
    model = emb_cfg.get("model") or "text-embedding-3-small"
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


def _read_zotero_corpus(semantic_cfg: Dict[str, Any]) -> List[str]:
    if pyzotero is None:
        raise RuntimeError("pyzotero is not installed")

    zotero_cfg = semantic_cfg.get("zotero") or {}
    user_id = zotero_cfg.get("user_id") or os.getenv(zotero_cfg.get("user_id_env") or "ZOTERO_ID", "")
    api_key = zotero_cfg.get("api_key") or os.getenv(zotero_cfg.get("api_key_env") or "ZOTERO_KEY", "")
    include_patterns = zotero_cfg.get("include_path") or []
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

        sorted_items = sorted(items, key=lambda x: x.get("semantic_score", 0.0), reverse=True)
        return sorted_items, scores, None
    except Exception as e:
        return items, {}, f"semantic rerank skipped: {e}"
