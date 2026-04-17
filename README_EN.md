# Arxiv-tracker · Daily arXiv Paper Tracker

[![Stars](https://img.shields.io/github/stars/colorfulandcjy0806/Arxiv-tracker?style=flat-square)](https://github.com/colorfulandcjy0806/Arxiv-tracker/stargazers)
[![CI](https://img.shields.io/github/actions/workflow/status/colorfulandcjy0806/Arxiv-tracker/digest.yml?label=Arxiv%20Digest&style=flat-square)](../../actions)
[![Pages](https://img.shields.io/badge/GitHub%20Pages-online-2ea44f?style=flat-square)](https://colorfulandcjy0806.github.io/Arxiv-tracker/)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776ab?style=flat-square&logo=python)
![Last Commit](https://img.shields.io/github/last-commit/colorfulandcjy0806/Arxiv-tracker?style=flat-square)
![Open Issues](https://img.shields.io/github/issues/colorfulandcjy0806/Arxiv-tracker?style=flat-square)
[![License: MIT](https://img.shields.io/badge/License-MIT-black.svg?style=flat-square)](./LICENSE)

> **If you like this project, please give it a ⭐ star for the latest updates!**  

**[简体中文](./README.md) | English**

---

## 😮 Highlights

- 🔎 **Multi-field, multi-topic search**: categories like `cs.CV / cs.LG / cs.AI / cs.CL`; free-form keywords; `logic: AND/OR` controls the relation between the *category-set* and the *keyword-set*
- 🧩 **Strict boolean keyword expression**: supports `keyword_expression` with parentheses + `AND/OR` for fine-grained query control
- 🧠 **Bilingual LLM summaries**: one English + one Chinese paragraph, or **two-stage** (TL;DR + Method Card + Discussion)
- 🔗 **Auto links**: abstract / PDF / code repo / project page
- 📨 **Email delivery**: QQ SMTP (465/SSL or 587/STARTTLS), multi-recipient
- 🌐 **Web page (GitHub Pages)**: nice HTML site with archive & collapse/expand
- ♻️ **Freshness + Dedup**: only push papers that are *fresh* and *not sent before*; write `seen.json` **after successful output** to keep idempotency
- 📦 **OpenAI-Compatible LLM**: **DeepSeek / SiliconFlow** supported via the same config (one `base_url` + one `api_key`)
- 🔁 **Auto pagination**: avoid always taking the same first N results

**Preview (web):**  
<img src="images/html.png" alt="Preview" width="720">

**Preview (email):**  
<img src="images/email.png" alt="Preview" width="720">

---

## 📰 News

- **2025-12-12**: Support the exclusion of unwanted literature through keywords.
- **2025-09-15**: Add code link completion. First, crawl the GitHub/Code link from the comments/summary/arXiv page; If it is still missing, you can scan the PDF homepage to try to identify the link and alleviate the problem of "incomplete display of GitHub code".
- **2025-08-25**
  - Added **Freshness + persistent dedup** (write to `seen.json` only after a successful output).
  - Added **OpenAI-Compatible LLM**: besides DeepSeek, now works with **SiliconFlow** (e.g., `Qwen/Qwen3-8B`).
  - Fixed a bug that **could send duplicate emails**; added Actions **concurrency guard** and a **manual-send toggle**.
  - Introduced **auto pagination** to avoid reusing the same batch.
- **2025-08-22**: First public release (search → summarize/translate → email/web).
---

## 🧭 Repository Layout

```
arxiv_tracker/        # Core logic (client, parser, summarizer, site, mailer)
docs/                 # GitHub Pages output (auto-generated)
outputs/              # Per-run JSON/MD (auto-generated)
.state/               # Dedup state (seen.json, recommend committing it)
.github/workflows/    # digest.yml (daily 21:00 Beijing time)
config.yaml           # Search / summary / email / site / dedup config
requirements.txt      # Dependencies
```

---

## 🚀 Quick Start (Fork & Deploy)

### 1) Fork

Click **Fork** on the top-right.

### 2) Configure Secrets and Variables

> Settings → **Secrets and variables** → **Actions**

> To reduce privacy leakage risk, keep email/API keys/account data in **Secrets**.
> Put non-sensitive query knobs (keywords/expression) in **Variables** for easier tuning.

**Secrets**

- `OPENAI_COMPAT_API_KEY`: API key for any OpenAI-compatible provider (e.g., **DeepSeek**, **SiliconFlow**)
- `OPENAI_COMPAT_BASE_URL`: LLM service base URL (e.g., `https://api.deepseek.com` or `https://api.siliconflow.cn`)
- `OPENAI_COMPAT_MODEL`: LLM model name (e.g., `deepseek-chat`, `Qwen/Qwen2.5-7B-Instruct`)
- `SEMANTIC_EMBED_BASE_URL`: Base URL of embedding service for semantic reranking (used when `semantic.enabled=true`)
- `SEMANTIC_EMBED_MODEL`: Embedding model name for semantic reranking (used when `semantic.enabled=true`)
- `SEMANTIC_EMBED_API_KEY`: Embedding API key for semantic reranking (used when `semantic.enabled=true`)
- `EMAIL_TO`: Recipients (comma/semicolon separated)
- `EMAIL_SENDER`: Sender email (usually equals SMTP user)
- `SMTP_USER`: SMTP username (usually the same as sender)
- `SMTP_PASS`: QQ **SMTP App Password** (not your login password)
- `SERPAPI_API_KEY`: Google Scholar API key (if `sources.scholar` is enabled)
- `ZOTERO_ID`: Zotero user ID (if semantic reranking is enabled)
- `ZOTERO_KEY`: Zotero API key (if semantic reranking is enabled)

**Variables (non-sensitive, recommended for query tuning)**

- `TRACKER_CATEGORIES`: arXiv category list (comma/semicolon/slash/newline separated, e.g. `cs.CV,cs.LG,cs.AI`)
- `TRACKER_KEYWORDS`: keyword list (comma/semicolon/newline separated)
- `TRACKER_KEYWORD_EXPRESSION`: strict boolean expression (parentheses + `AND/OR`, takes precedence over `TRACKER_KEYWORDS`)

> When semantic reranking is enabled, set `semantic.zotero.include_path` in `config.yaml` to limit corpus scope.

### 3) Enable GitHub Pages

Settings → **Pages** → Source: **Deploy from a branch**; Branch `main`, Folder `/docs`.

### 4) Workflow (Support manual triggering of whether to send a message. The code has already written it, so this step can be omitted and run directly)

Example `digest.yml` (excerpt):

```yaml
name: arxiv-digest

on:
  workflow_dispatch:
    inputs:
      send_email:
        description: "Send email for manual run?"
        required: false
        default: "true"
        type: choice
        options: ["false", "true"]
  schedule:
    - cron: "0 13 * * *"  # 13:00 UTC = 21:00 Beijing

concurrency:
  group: arxiv-digest
  cancel-in-progress: true

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with: { python-version: "3.10" }

      - name: Install deps
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Compute Pages URL
        id: site
        run: |
          REPO="${GITHUB_REPOSITORY}"
          OWNER="${REPO%%/*}"
          NAME="${REPO#*/}"
          echo "url=https://${OWNER}.github.io/${NAME}/" >> $GITHUB_OUTPUT

      - name: Run tracker (schedule-only email unless forced)
        env:
          TRACKER_CATEGORIES: ${{ vars.TRACKER_CATEGORIES }}
          TRACKER_KEYWORDS: ${{ vars.TRACKER_KEYWORDS }}
          TRACKER_KEYWORD_EXPRESSION: ${{ vars.TRACKER_KEYWORD_EXPRESSION }}
          OPENAI_COMPAT_BASE_URL: ${{ secrets.OPENAI_COMPAT_BASE_URL }}
          OPENAI_COMPAT_MODEL:    ${{ secrets.OPENAI_COMPAT_MODEL }}
          OPENAI_COMPAT_API_KEY: ${{ secrets.OPENAI_COMPAT_API_KEY }}
          # Required when semantic.enabled=true
          SEMANTIC_EMBED_BASE_URL: ${{ secrets.SEMANTIC_EMBED_BASE_URL }}
          SEMANTIC_EMBED_MODEL:    ${{ secrets.SEMANTIC_EMBED_MODEL }}
          SEMANTIC_EMBED_API_KEY:  ${{ secrets.SEMANTIC_EMBED_API_KEY }}
          # Optional, depending on enabled features
          SERPAPI_API_KEY: ${{ secrets.SERPAPI_API_KEY }}
          ZOTERO_ID:       ${{ secrets.ZOTERO_ID }}
          ZOTERO_KEY:      ${{ secrets.ZOTERO_KEY }}
          EMAIL_TO:     ${{ secrets.EMAIL_TO }}
          EMAIL_SENDER: ${{ secrets.EMAIL_SENDER }}
          SMTP_USER:    ${{ secrets.SMTP_USER }}
          SMTP_PASS:    ${{ secrets.SMTP_PASS }}
        run: |
          set -e
          EXTRA="--no-email"
          if { [ "${{ github.event_name }}" = "schedule" ] && [ "${{ github.run_attempt }}" = "1" ]; } || \
             { [ "${{ github.event_name }}" = "workflow_dispatch" ] && [ "${{ inputs.send_email }}" = "true" ]; }; then
            EXTRA=""
          fi
          python -m arxiv_tracker.cli run \
            --config config.yaml \
            --site-dir docs \
            --site-url "${{ steps.site.outputs.url }}" \
            $EXTRA \
            --verbose

      - name: Commit outputs
        uses: stefanzweifel/git-auto-commit-action@v5
        with:
          commit_message: "chore: update digest & site"
          file_pattern: |
            docs/**
            outputs/**
            .state/**
```

**Configuration process is as follows:**

<img src="images/guide.png" alt="Preview" width="720">

> **Note**: include `.state/**` in `file_pattern` to persist dedup state across runs.

---

## ⚙️ Configuration (`config.yaml`)

```yaml
# === Search ===
categories: ["cs.CV", "cs.LG", "cs.AI"]
# [Optional] inject categories from environment (priority: CLI > env > config)
categories_env: "TRACKER_CATEGORIES"
keywords:
  - "open vocabulary segmentation"
  - "vision-language grounding"
# [Optional] strict boolean expression, takes precedence over keywords
keyword_expression: "(open vocabulary segmentation OR vision-language grounding) AND (reinforcement learning OR MARL)"
# [Optional] inject keywords from environment (priority: CLI > env > config)
keywords_env: "TRACKER_KEYWORDS"
keyword_expression_env: "TRACKER_KEYWORD_EXPRESSION"
# [New] Exclude papers containing these terms
exclude_keywords:
  - "Large Language Model"
  - "Generative AI"
logic: "AND"                 # categories (OR) combined with keywords (OR) by AND/OR
max_results: 100             # per-page cap; the runner auto-paginates internally
sort_by: "lastUpdatedDate"   # or submittedDate
sort_order: "descending"

# === Multi-source retrieval (arXiv + Scholar) ===
sources:
  enabled: ["arxiv", "scholar"]
  priority: ["arxiv", "scholar"]
  max_candidates: 50
  scholar:
    enabled: true
    endpoint: "https://serpapi.com/search.json"
    api_key_env: "SERPAPI_API_KEY"
    max_results: 30
    page_size: 20
    abstract_enrichment:
      enabled: true
      min_chars: 260
      max_enrich_items: 20
      timeout: 8
      max_workers: 4
      providers: ["arxiv", "crossref", "openalex", "semantic_scholar", "landing_page"]
      cache_path: ".state/scholar_abstract_cache.json"
      cache_ttl_days: 30
      semantic_scholar_api_key_env: "S2_API_KEY"

# === Output language ===
lang: "both"                 # zh / en / both

# === Summaries ===
summary:
  mode: "llm"                # none / heuristic / llm
  scope: "both"              # tldr / full / both

# === LLM (OpenAI-Compatible: DeepSeek / SiliconFlow) ===
llm:
  # Recommended: inject via environment variables (avoid hardcoding in repo)
  base_url: ""
  model: ""
  base_url_env: "OPENAI_COMPAT_BASE_URL"
  model_env: "OPENAI_COMPAT_MODEL"
  # For local-only tests, you can still hardcode:
  # base_url: "https://api.deepseek.com"
  # model: "deepseek-chat"
  api_key_env: "OPENAI_COMPAT_API_KEY"
  system_prompt_en: |
    You are a senior paper-reading assistant...
  system_prompt_zh: |
    你是资深论文阅读助手...

# === Optional: CN translation for title/abstract ===
translate:
  enabled: true
  lang: "zh"
  fields: ["title", "summary"]

# === Email (QQ SMTP example) ===
email:
  enabled: true
  subject: "[arXiv] Daily Digest"
  smtp_server: "smtp.qq.com"
  smtp_port: 465
  tls: "ssl"                 # auto / ssl / starttls
  debug: false
  detail: "full"
  max_items: 10
  attach_md: true
  attach_pdf: false

# === Site (GitHub Pages) ===
site:
  enabled: true
  dir: "docs"
  title: "arXiv Daily"
  keep_runs: 1024
  theme: "light"
  accent: "#2563eb"

# === Freshness & Dedup (write after success) ===
freshness:
  since_days: 3
  unique_only: true
  state_path: ".state/seen.json"
  fallback_when_empty: false

# === Zotero semantic reranking (scope-limited to reduce noise) ===
semantic:
  enabled: true
  zotero:
    user_id_env: "ZOTERO_ID"
    api_key_env: "ZOTERO_KEY"
    require_include_path: true
    include_path:
      - "2026/rl-auv/**"
      - "2026/multi-agent/**"
    max_corpus: 300
  embedding:
    # Base URL / model / api key are injected from Secrets env vars
    base_url: ""
    model: ""
    base_url_env: "SEMANTIC_EMBED_BASE_URL"
    model_env: "SEMANTIC_EMBED_MODEL"
    api_key_env: "SEMANTIC_EMBED_API_KEY"
    batch_size: 64
    timeout: 45
```

> **Query semantics**: by default, `categories` are OR-ed, `keywords` are OR-ed, then connected by `logic`. If `keyword_expression` is provided, strict boolean parsing (parentheses + `AND/OR`) is applied and takes precedence over `keywords`.
>
> **Semantic rerank behavior**: when `semantic.enabled=true` and `require_include_path=true`, an empty `include_path` will skip reranking with a warning in logs.

---

## 🛠️ Run Locally (macOS/Linux)

```bash
python -m venv .venv && source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

export OPENAI_COMPAT_API_KEY="your_api_key"
export TRACKER_CATEGORIES="cs.CV,cs.LG,cs.AI"
export TRACKER_KEYWORDS="open vocabulary segmentation,vision-language grounding"
# If set, expression takes precedence over TRACKER_KEYWORDS
export TRACKER_KEYWORD_EXPRESSION="(open vocabulary segmentation OR vision-language grounding) AND reinforcement learning"
export OPENAI_COMPAT_BASE_URL="https://api.siliconflow.cn"
export OPENAI_COMPAT_MODEL="Qwen/Qwen2.5-7B-Instruct"
# Required only when semantic.enabled=true
export SEMANTIC_EMBED_BASE_URL="https://api.siliconflow.cn"
export SEMANTIC_EMBED_MODEL="BAAI/bge-m3"
export SEMANTIC_EMBED_API_KEY="your_embedding_api_key"
# Optional, depending on enabled features
export SERPAPI_API_KEY="your_serpapi_key"
export ZOTERO_ID="your_zotero_user_id"
export ZOTERO_KEY="your_zotero_api_key"
export EMAIL_TO="your@qq.com"
export EMAIL_SENDER="your@qq.com"
export SMTP_USER="your@qq.com"
export SMTP_PASS="your_qq_smtp_app_password"

python -m arxiv_tracker.cli run --config config.yaml --site-dir docs --verbose
```

### Windows (PowerShell)

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt

$Env:OPENAI_COMPAT_API_KEY = "your_api_key"
$Env:TRACKER_CATEGORIES = "cs.CV,cs.LG,cs.AI"
$Env:TRACKER_KEYWORDS = "open vocabulary segmentation,vision-language grounding"
# If set, expression takes precedence over TRACKER_KEYWORDS
$Env:TRACKER_KEYWORD_EXPRESSION = "(open vocabulary segmentation OR vision-language grounding) AND reinforcement learning"
$Env:OPENAI_COMPAT_BASE_URL = "https://api.siliconflow.cn"
$Env:OPENAI_COMPAT_MODEL = "Qwen/Qwen2.5-7B-Instruct"
# Required only when semantic.enabled=true
$Env:SEMANTIC_EMBED_BASE_URL = "https://api.siliconflow.cn"
$Env:SEMANTIC_EMBED_MODEL = "BAAI/bge-m3"
$Env:SEMANTIC_EMBED_API_KEY = "your_embedding_api_key"
# Optional, depending on enabled features
$Env:SERPAPI_API_KEY = "your_serpapi_key"
$Env:ZOTERO_ID = "your_zotero_user_id"
$Env:ZOTERO_KEY = "your_zotero_api_key"
$Env:EMAIL_TO     = "your@qq.com"
$Env:EMAIL_SENDER = "your@qq.com"
$Env:SMTP_USER    = "your@qq.com"
$Env:SMTP_PASS    = "your_qq_smtp_app_password"

python -m arxiv_tracker.cli run --config config.yaml --site-dir docs --verbose
```

---

## ❓ FAQ

- **Results look stale / empty?**  
  Auto pagination + freshness filter + post-success dedup are enabled. If a day is empty, try temporarily increasing `since_days` to 2–3; also check if your keywords are too narrow.
- **401 Unauthorized (SiliconFlow/DeepSeek)**  
  Ensure `OPENAI_COMPAT_API_KEY` is a valid key for the provider you configured.
- **ReadTimeout (arXiv API)**  
  Likely network hiccups; just retry later.
- **No email received**  
  Check “Show email env (masked)” in Actions logs; ensure QQ SMTP app password is used and TLS/port matches your settings.
  
---

##  🗺️  To-do list

- [x] Solve the problem of retrieving the same literature every day
- [x] Bug of sending 2 emails each time
- [x] Support more LLMs, next step to consider silicon-based flow APIs
- [x] Code link completion (when missing, grab the PDF homepage as a backup)
- [x] Logic to exclude specific keywords (e.g., filtering out "LLM" noise).
- [ ] More site themes (dark color, following system)
- [ ] Custom card field switch and order

## ✨ Star History

[![Star History](https://api.star-history.com/svg?repos=colorfulandcjy0806/Arxiv-tracker&type=Date)](https://star-history.com/#colorfulandcjy0806/Arxiv-tracker&Date)

---

## 🤝 Community contributors

<a href="https://github.com/colorfulandcjy0806/Arxiv-tracker/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=colorfulandcjy0806/Arxiv-tracker" alt="Contributors" width="720"/>
</a>

## 🔒 License

MIT — see [LICENSE](./LICENSE).
