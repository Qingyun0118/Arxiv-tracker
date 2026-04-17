# -*- coding: utf-8 -*-
import json
import os
import re
from typing import Any, Dict, List, Optional

import requests
import yaml


def _json_loose(s: str) -> Dict[str, Any]:
    """宽松 JSON 解析：尽力从文本中抽出首个 {...} 为 JSON。"""
    m = re.search(r"\{[\s\S]*\}", s)
    if not m:
        return {}
    raw = m.group(0)
    try:
        return json.loads(raw)
    except Exception:
        t = re.sub(r",\s*([}\]])", r"\1", raw)
        try:
            return json.loads(t)
        except Exception:
            return {}


def _loose_json_load(s: str) -> Dict[str, Any]:
    """兼容旧名，等价 _json_loose。"""
    return _json_loose(s)


def _render_template(text: str, variables: Optional[Dict[str, Any]] = None) -> str:
    out = text or ""
    for k, v in (variables or {}).items():
        out = out.replace("{{" + str(k) + "}}", "" if v is None else str(v))
    return out


def load_prompt_bundle(
    path: str,
    *,
    fallback_system: str = "",
    fallback_user_template: str = "",
) -> Dict[str, str]:
    """
    从 yaml/json 加载提示词模板。
    文件格式示例：
      system: |
        ...
      user_template: |
        ...
    """
    data: Dict[str, Any] = {}
    try:
        if path and os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                if path.lower().endswith((".yaml", ".yml")):
                    data = yaml.safe_load(f) or {}
                else:
                    data = json.load(f) or {}
    except Exception:
        data = {}

    return {
        "system": str(data.get("system") or fallback_system or ""),
        "user_template": str(data.get("user_template") or fallback_user_template or ""),
    }


def _normalize_chat_endpoint(base_url: str) -> str:
    """
    允许三种写法：
      1) https://api.xxx.com
      2) https://api.xxx.com/v1
      3) https://api.xxx.com/v1/chat/completions
    统一规范到完整终点：.../v1/chat/completions
    """
    if not base_url:
        raise ValueError("llm.base_url is empty")
    base = base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return base + "/chat/completions"
    return base + "/v1/chat/completions"


def _chat_completions_request(
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: List[Dict[str, str]],
    temperature: float = 0.2,
    max_tokens: int = 1024,
    timeout: int = 30,
) -> str:
    """统一的 OpenAI 兼容 Chat Completions 请求（requests 直连）。"""
    url = _normalize_chat_endpoint(base_url)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"]
    except Exception:
        return data.get("choices", [{}])[0].get("text", "")


def call_llm_bilingual_summary(
    item: Dict[str, Any],
    *,
    base_url: str,
    model: str,
    api_key: str,
    system_prompt_zh: str = "",
    system_prompt_en: str = "",
) -> Dict[str, str]:
    """输出两段摘要：digest_en / digest_zh。"""
    title = item.get("title") or ""
    summary = item.get("summary") or ""
    comments = item.get("comments") or ""
    venue = item.get("venue_inferred") or (item.get("journal_ref") or "")

    sys_prompt = system_prompt_en or system_prompt_zh or "You are a precise academic assistant. Summarize papers concisely."
    user_payload = {
        "title": title,
        "abstract": summary,
        "venue_or_comments": (venue or comments or ""),
    }
    messages = [
        {"role": "system", "content": sys_prompt},
        {
            "role": "user",
            "content": (
                "Given the paper metadata below, write TWO concise one-paragraph digests:\n"
                "1) English paragraph first.\n"
                "2) Then a Simplified Chinese paragraph.\n"
                "- Each paragraph must briefly cover: motivation, method, and main experimental results.\n"
                "- Do not include links, bullet lists, markdown, or headings. Plain sentences only.\n"
                '- Return STRICT JSON: {\"digest_en\": \"...\", \"digest_zh\": \"...\"}\n\n'
                f"DATA:\n{json.dumps(user_payload, ensure_ascii=False)}"
            ),
        },
    ]
    text = _chat_completions_request(
        base_url=base_url,
        api_key=api_key,
        model=model,
        messages=messages,
        temperature=0.2,
        max_tokens=600,
    )
    data = _json_loose(text)
    return {
        "digest_en": (data.get("digest_en") or "").strip(),
        "digest_zh": (data.get("digest_zh") or "").strip(),
    }


def build_llm_prompt(item: Dict[str, Any], lang: str = "zh", scope: str = "both"):
    title = item.get("title") or ""
    authors = ", ".join(item.get("authors") or [])
    venue = item.get("venue_inferred") or (item.get("journal_ref") or "")
    comments = item.get("comments") or ""
    summary = item.get("summary") or ""
    links = {
        "html": item.get("html_url"),
        "pdf": item.get("pdf_url"),
        "code": item.get("code_urls") or [],
        "project": item.get("project_urls") or [],
        "other": item.get("other_urls") or [],
    }
    meta = {
        "title": title,
        "authors": authors,
        "venue": venue,
        "comments": comments,
        "summary": summary,
        "links": links,
    }
    ask_lang = "中文" if lang == "zh" else "English"
    user_prompt = f"""
请阅读以下论文元信息(JSON)，用{ask_lang}输出“两阶段摘要”：
1) TL;DR（1~2 句，先总后分，避免口号）
2) **Method Card**：任务/动机、核心方法、关键设计、数据与指标、主要结果与结论、局限与未来工作、保留链接（PDF/代码/项目页）
3) **Discussion Questions**：3~5 个高质量问题（可用于组会讨论）
请保留所有给定链接，不要臆造。scope="{scope}" 表示输出范围（tldr/full/both）。

JSON:
{json.dumps(meta, ensure_ascii=False, indent=2)}
""".strip()
    return user_prompt


def call_llm_two_stage(
    item: Dict[str, Any],
    lang: str,
    scope: str,
    base_url: str,
    model: str,
    api_key: str,
    system_prompt: str = "",
    user_template: str = "",
    template_vars: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """两阶段摘要接口（支持可配置 user_template）。"""
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    if user_template:
        user_content = _render_template(
            user_template,
            {
                "title": item.get("title") or "",
                "summary": item.get("summary") or "",
                "comments": item.get("comments") or "",
                "authors": ", ".join(item.get("authors") or []),
                "scope": scope,
                "lang": lang,
                **(template_vars or {}),
            },
        )
    else:
        user_content = build_llm_prompt(item, lang=lang, scope=scope)

    messages.append({"role": "user", "content": user_content})
    text = _chat_completions_request(
        base_url=base_url,
        api_key=api_key,
        model=model,
        messages=messages,
        temperature=0.2,
        max_tokens=900,
    ).strip()

    tldr, full_md = "", ""
    if "TL;DR" in text or "TLDR" in text or "Tl;dr" in text:
        parts = text.splitlines()
        tldr_lines, rest_lines, in_tldr = [], [], False
        for ln in parts:
            if "TL;DR" in ln or "TLDR" in ln or "Tl;dr" in ln:
                in_tldr = True
                t = ln.replace("TL;DR", "").replace("TLDR", "").replace("Tl;dr", "")
                tldr_lines.append(t.strip(" :："))
            elif in_tldr and (ln.strip().startswith("**Method") or ln.strip().lower().startswith("**discussion")):
                in_tldr = False
                rest_lines.append(ln)
            elif in_tldr:
                tldr_lines.append(ln)
            else:
                rest_lines.append(ln)
        tldr = " ".join([s.strip() for s in tldr_lines if s.strip()])
        full_md = "\n".join(rest_lines).strip()
    else:
        full_md = text
    return {"tldr": tldr, "full_md": full_md}


def call_llm_translate(
    item: Dict[str, Any],
    target_lang: str,
    base_url: str,
    model: str,
    api_key: str,
    system_prompt: str = "",
    user_template: str = "",
    template_vars: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """标题/摘要中文翻译（支持可配置 user_template）。"""
    title = item.get("title") or ""
    summary = item.get("summary") or ""
    comments = item.get("comments") or ""
    want_comments = bool(comments.strip())
    schema_keys = ["title_zh", "summary_zh"] + (["comments_zh"] if want_comments else [])

    sys_prompt = system_prompt or "You are a precise academic translator. Translate to Simplified Chinese concisely and faithfully; keep technical terms."
    if user_template:
        inst = _render_template(
            user_template,
            {
                "target_lang": target_lang,
                "title": title,
                "summary": summary,
                "comments": comments,
                "source": item.get("source") or "arxiv",
                "schema_keys": json.dumps(schema_keys, ensure_ascii=False),
                **(template_vars or {}),
            },
        )
    else:
        inst = f"""
Translate the following fields into Simplified Chinese.
Return ONLY compact JSON with keys {schema_keys} (omit keys you can't translate).
Do not add commentary.

DATA:
{json.dumps({"title": title, "summary": summary, "comments": comments}, ensure_ascii=False, indent=2)}
""".strip()

    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": inst},
    ]
    text = _chat_completions_request(
        base_url=base_url,
        api_key=api_key,
        model=model,
        messages=messages,
        temperature=0.0,
        max_tokens=700,
    ).strip()

    data = _loose_json_load(text)
    out: Dict[str, str] = {}
    if isinstance(data, dict):
        if "title_zh" in data and isinstance(data["title_zh"], str):
            out["title_zh"] = data["title_zh"].strip()
        if "summary_zh" in data and isinstance(data["summary_zh"], str):
            out["summary_zh"] = data["summary_zh"].strip()
        if "comments_zh" in data and isinstance(data["comments_zh"], str):
            out["comments_zh"] = data["comments_zh"].strip()
    return out


def call_llm_deep_analysis(
    item: Dict[str, Any],
    *,
    base_url: str,
    model: str,
    api_key: str,
    system_prompt: str = "",
    user_template: str = "",
    template_vars: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """Top-N 深度分析：输出 method/innovation/results/limitations/practical_value。"""
    title = item.get("title") or ""
    summary = item.get("summary") or ""
    comments = item.get("comments") or ""
    source = item.get("source") or "arxiv"

    sys_prompt = system_prompt or "You are a rigorous scientific reviewer. Provide concise and evidence-grounded analysis."
    if user_template:
        inst = _render_template(
            user_template,
            {
                "title": title,
                "summary": summary,
                "comments": comments,
                "source": source,
                **(template_vars or {}),
            },
        )
    else:
        inst = f"""
Please analyze the paper information below and output STRICT JSON with 5 fields:
- method
- innovation
- results
- limitations
- practical_value

Do not fabricate unavailable evidence; if missing, state that abstract lacks enough details.

DATA:
{json.dumps({"title": title, "summary": summary, "comments": comments, "source": source}, ensure_ascii=False, indent=2)}
""".strip()

    text = _chat_completions_request(
        base_url=base_url,
        api_key=api_key,
        model=model,
        messages=[
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": inst},
        ],
        temperature=0.2,
        max_tokens=900,
    ).strip()

    data = _json_loose(text)
    out = {
        "method": "",
        "innovation": "",
        "results": "",
        "limitations": "",
        "practical_value": "",
    }
    if isinstance(data, dict):
        for k in out:
            v = data.get(k)
            if isinstance(v, str):
                out[k] = v.strip()
    return out
