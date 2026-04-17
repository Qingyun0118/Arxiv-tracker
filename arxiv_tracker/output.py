# -*- coding: utf-8 -*-
import os, json, datetime
from typing import List, Dict, Any, Optional

def _ensure_dir(p: str):
    os.makedirs(p, exist_ok=True)

def save_json(items: List[Dict[str, Any]], out_dir: str) -> str:
    _ensure_dir(out_dir)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(out_dir, f"arxiv_{ts}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    return path

def _render_lang_block(lang_label: str, it: Dict[str, Any],
                       summ: Optional[Dict[str, str]],
                       trans: Optional[Dict[str, str]],
                       deep: Optional[Dict[str, str]] = None):
    lines = []
    lines.append(f"### [{lang_label}]")
    # 中文段落强制展示，翻译失败时输出占位标记
    if lang_label == "中文":
        t_title = (trans or {}).get("title_zh")
        t_sum = (trans or {}).get("summary_zh") or "【翻译失败】该论文中文摘要暂不可用"
        lines.append("**中文翻译**")
        if t_title:
            lines.append(f"- 标题：{t_title}")
        lines.append(f"- 摘要：{t_sum}")
        lines.append("")
    if summ and summ.get("tldr"):
        lines.append("> **TL;DR**: " + summ["tldr"])
        lines.append("")
    if summ and summ.get("full_md"):
        lines.append(summ["full_md"])
        lines.append("")
    if deep:
        lines.append("**Top-N 深度分析**")
        mapping = [
            ("method", "方法"),
            ("innovation", "创新点"),
            ("results", "实验结果"),
            ("limitations", "局限性"),
            ("practical_value", "应用价值"),
        ]
        for key, label in mapping:
            val = (deep.get(key) or "").strip()
            if val:
                lines.append(f"- {label}：{val}")
        lines.append("")
    return lines

def save_markdown(items: List[Dict[str, Any]], out_dir: str,
                  summaries_zh: Dict[str, Dict[str, str]] = None,
                  summaries_en: Dict[str, Dict[str, str]] = None,
                  lang: str = "both",
                  translations: Dict[str, Dict[str, str]] = None,
                  deep_analyses: Dict[str, Dict[str, str]] = None,
                  analysis_top_n: int = 0) -> str:
    _ensure_dir(out_dir)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(out_dir, f"arxiv_{ts}.md")
    lines = ["# arXiv 检索结果 / Results", ""]
    deep_analyses = deep_analyses or {}
    for i, it in enumerate(items, 1):
        au = ", ".join(it.get("authors", []))
        title = it.get("title", "")
        venue = it.get("venue_inferred") or (it.get("journal_ref") or "")
        pub = it.get("published", "")
        upd = it.get("updated", "")
        src = it.get("source") or "arxiv"
        lines.append(f"## {i}. {title}")
        lines.append(f"- Source：{src}")
        lines.append(f"- Authors：{au}")
        if venue:
            lines.append(f"- Venue：{venue}")
        if it.get("comments"):
            lines.append(f"- Comments：{it['comments']}")
        lines.append(f"- First：{pub or '—'}；Latest：{upd or '—'}")
        if it.get("html_url"):
            lines.append(f"- Abs：{it['html_url']}")
        if it.get("pdf_url"):
            lines.append(f"- PDF：{it['pdf_url']}")
        if it.get("code_urls"):
            lines.append(f"- Code：{', '.join(it['code_urls'])}")
        if it.get("project_urls"):
            lines.append(f"- Project：{', '.join(it['project_urls'])}")

        sid = it.get("id") or ""
        trans = translations.get(sid) if translations else None
        deep = deep_analyses.get(sid) if (analysis_top_n > 0 and i <= analysis_top_n) else None
        if lang in ("zh", "both"):
            lines.extend(_render_lang_block("中文", it, (summaries_zh or {}).get(sid), trans, deep=deep))
        if lang in ("en", "both"):
            lines.extend(_render_lang_block("English", it, (summaries_en or {}).get(sid), None, deep=None))
        lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path
