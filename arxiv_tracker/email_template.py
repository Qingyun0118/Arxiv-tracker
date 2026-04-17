# -*- coding: utf-8 -*-
import html
from typing import Dict, List, Any, Optional

try:
    from markdown import markdown as _md
except Exception:
    _md = None

def _esc(x: Optional[str]) -> str:
    return html.escape(x or "", quote=True)

def _md2html(md: str) -> str:
    if not md: return ""
    if _md:
        return _md(md, extensions=["extra", "sane_lists", "tables"])
    return "<pre style='white-space:pre-wrap'>" + _esc(md) + "</pre>"

def _strip_redundant_links(md: str) -> str:
    out = []
    for line in (md or "").splitlines():
        if line.strip().lower().startswith("- **links**"):
            continue
        out.append(line)
    return "\n".join(out)

def _join_links(it: Dict[str, Any]) -> str:
    parts = []
    if it.get("html_url"):
        parts.append(f'<a href="{_esc(it["html_url"])}">Abs</a>')
    if it.get("pdf_url"):
        parts.append(f'<a href="{_esc(it["pdf_url"])}">PDF</a>')
    if it.get("code_urls"):
        a = [f'<a href="{_esc(u)}">Code{i+1}</a>' for i,u in enumerate(it["code_urls"][:3])]
        parts.append(" · ".join(a))
    if it.get("project_urls"):
        a = [f'<a href="{_esc(u)}">Project{i+1}</a>' for i,u in enumerate(it["project_urls"][:2])]
        parts.append(" · ".join(a))
    return " · ".join(parts)

CSS = """
.container{font-family:ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial;color:#0f172a}
.card{border:1px solid #e5e7eb;border-radius:14px;padding:14px;margin:12px 0;background:#fff}
.title{font-weight:700;font-size:16px;margin:0 0 6px 0}
.meta{color:#667085;font-size:13px;margin:2px 0}
.links a{color:#2563eb;text-decoration:none;margin-right:10px}
.grid{display:grid;grid-template-columns:1fr;gap:10px}
@media (min-width: 860px){.grid-2{grid-template-columns:1fr 1fr}}
.section{border:1px solid #eef2f7;border-radius:10px;padding:8px 10px;background:#f8fafc}
.section h4{margin:4px 0 6px 0;font-size:14px}
"""

def _render_card(it: Dict[str, Any],
                 t_zh: Optional[Dict[str, str]] = None,
                 sum_zh: Optional[Dict[str, str]] = None,
                 sum_en: Optional[Dict[str, str]] = None,
                 deep: Optional[Dict[str, str]] = None) -> str:
    title = it.get("title") or ""
    title_link = it.get("html_url") or "#"
    authors = ", ".join(it.get("authors", []))
    venue = it.get("venue_inferred") or (it.get("journal_ref") or "")
    pub = it.get("published") or "—"
    upd = it.get("updated") or "—"
    src = (it.get("source") or "arxiv").upper()
    comments = it.get("comments") or ""
    summary = it.get("summary") or ""

    zh_title = (t_zh or {}).get("title_zh")
    zh_sum   = (t_zh or {}).get("summary_zh") or "【翻译失败】该论文中文摘要暂不可用"

    # 新双语总结
    digest_en = (sum_en or {}).get("digest_en") or (sum_zh or {}).get("digest_en") or ""
    digest_zh = (sum_zh or {}).get("digest_zh") or (sum_en or {}).get("digest_zh") or ""

    out = [f'<div class="card">']
    out.append(f'<div class="title"><a href="{_esc(title_link)}">{_esc(title)}</a></div>')
    out.append(f'<div class="meta">Source: {_esc(src)}</div>')
    out.append(f'<div class="meta">Authors: {_esc(authors)}</div>')
    if venue: out.append(f'<div class="meta">Venue: {_esc(venue)}</div>')
    out.append(f'<div class="meta">First: {_esc(pub)} · Latest: {_esc(upd)}</div>')
    if comments: out.append(f'<div class="meta">Comments: {_esc(comments)}</div>')

    links = _join_links(it)
    if links: out.append(f'<div class="links" style="margin:8px 0">{links}</div>')

    if summary:
        out.append('<div class="section"><h4>Abstract</h4><div style="white-space:pre-wrap">'
                   + _esc(summary) + '</div></div>')
    zh_parts = []
    if zh_title:
        zh_parts.append(f"<p><b>标题：</b>{_esc(zh_title)}</p>")
    zh_parts.append("<div style='white-space:pre-wrap'>" + _esc(zh_sum) + "</div>")
    out.append('<div class="section"><h4>中文标题/摘要</h4>' + "".join(zh_parts) + '</div>')

    # ✅ 仅 Summary / 总结（英文→中文）
    if digest_en or digest_zh:
        inner = ""
        if digest_en:
            inner += "<div style='white-space:pre-wrap'>" + _esc(digest_en) + "</div>"
        if digest_zh:
            inner += "<div style='white-space:pre-wrap;margin-top:8px'>" + _esc(digest_zh) + "</div>"
        out.append('<div class="section"><h4>Summary / 总结</h4>'+ inner +'</div>')

    if deep:
        mapping = [
            ("method", "方法"),
            ("innovation", "创新点"),
            ("results", "实验结果"),
            ("limitations", "局限性"),
            ("practical_value", "应用价值"),
        ]
        deep_lines = []
        for key, label in mapping:
            val = (deep.get(key) or "").strip()
            if val:
                deep_lines.append(f"<p><b>{_esc(label)}：</b>{_esc(val)}</p>")
        if deep_lines:
            out.append('<div class="section"><h4>Top-N 深度分析</h4>' + "".join(deep_lines) + '</div>')

    out.append('</div>')
    return "\n".join(out)


def render_email_html(
    items: List[Dict[str, Any]],
    lang: str = "both",
    translations: Optional[Dict[str, Dict[str, str]]] = None,
    summaries_zh: Optional[Dict[str, Dict[str, str]]] = None,
    summaries_en: Optional[Dict[str, Dict[str, str]]] = None,
    deep_analyses: Optional[Dict[str, Dict[str, str]]] = None,
    analysis_top_n: int = 0,
    detail: str = "full",
    max_items: int = 50,
    title: str = "arXiv Daily Digest",
) -> str:
    translations = translations or {}
    summaries_zh = summaries_zh or {}
    summaries_en = summaries_en or {}
    deep_analyses = deep_analyses or {}

    head = f"""
    <meta charset="utf-8">
    <div class="container">
      <h2 style="margin:8px 0 12px 0;">{_esc(title)}</h2>
      <style>{CSS}</style>
    """

    if not items:
        return head + "<p>No results.</p></div>"

    body = [head]
    for i, it in enumerate(items[:max_items], 1):
        sid = it.get("id") or ""
        deep = deep_analyses.get(sid) if (analysis_top_n > 0 and i <= analysis_top_n) else None
        body.append(_render_card(it, translations.get(sid), summaries_zh.get(sid), summaries_en.get(sid), deep=deep))
    body.append("</div>")
    return "\n".join(body)
