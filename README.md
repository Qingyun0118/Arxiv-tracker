# Arxiv-tracker · arXiv 每日论文追踪器

[![Stars](https://img.shields.io/github/stars/colorfulandcjy0806/Arxiv-tracker?style=flat-square)](https://github.com/colorfulandcjy0806/Arxiv-tracker/stargazers)
[![CI](https://img.shields.io/github/actions/workflow/status/colorfulandcjy0806/Arxiv-tracker/digest.yml?label=Arxiv%20Digest&style=flat-square)](../../actions)
[![Pages](https://img.shields.io/badge/GitHub%20Pages-online-2ea44f?style=flat-square)](https://colorfulandcjy0806.github.io/Arxiv-tracker/)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776ab?style=flat-square&logo=python)
![Last Commit](https://img.shields.io/github/last-commit/colorfulandcjy0806/Arxiv-tracker?style=flat-square)
![Open Issues](https://img.shields.io/github/issues/colorfulandcjy0806/Arxiv-tracker?style=flat-square)
[![License: MIT](https://img.shields.io/badge/License-MIT-black.svg?style=flat-square)](./LICENSE)

> **如果你喜欢本项目，欢迎点亮一个 ⭐ Star 获取最新进展！**  

**简体中文 | [English](./README_EN.md)**

---

## 😮 项目亮点（Highlights）

- 🔎 **多学科多主题检索**：支持 `cs.CV / cs.LG / cs.AI / cs.CL` 等分类，自由组合关键词；`logic: AND/OR` 控制“分类集合”与“关键词集合”的布尔关系
- 🧩 **严格布尔关键词表达式**：支持 `keyword_expression`（括号 + `AND/OR`），用于精细控制检索条件
- 🧠 **LLM 双语总结**：**英文一段 + 中文一段** 或两阶段摘要（TL;DR + Method Card + Discussion）
- 🔗 **自动提取链接**：Abs / PDF / 代码仓库 / 项目页
- 📨 **邮件推送**：QQ SMTP（465/SSL 或 587/STARTTLS），支持多收件人
- 🌐 **网页发布（GitHub Pages）**：自动生成美观 HTML，历史归档与折叠/展开
- ♻️ **去重 + 新鲜度**：仅推送“近 N 天 & 未发送过”的论文；支持**成功后再写入**的幂等防重
- 📦 **OpenAI-Compatible LLM**：**DeepSeek / SiliconFlow 等统一配置**（一个 `base_url` + 一个 `api_key` 即可）
- 🔁 **自动分页抓取**：避免每次只拿同一批前 N 条导致结果“用尽”

**网页效果如下图：**  
<img src="images/html.png" alt="Preview" width="720">

**邮件效果如下图：**  
<img src="images/email.png" alt="Preview" width="720">

---

## 📰 News
- **2025-12-12**：支持通过关键词排除不想要的文献。
- **2025-09-15**：新增代码链接补全，先从 comments/summary/arXiv 页面 抓取 GitHub/Code 链接；若仍缺失，可选扫描 PDF 首页尝试识别链接，缓解 “github code 显示不全” 问题。
- **2025-08-25**
  - 新增 **Freshness + 去重持久化**（且仅在**成功输出**后写入 `seen.json`）。
  - 新增 **OpenAI-Compatible LLM**：除 DeepSeek 外，已验证可直连 **SiliconFlow** 免费/付费模型（示例：`Qwen/Qwen3-8B`）。
  - 修复“**可能重复发邮件**”的问题；补充 Actions **并发防重**与“**手动触发选择是否发信**”。
  - 新增 **自动分页抓取**，避免总是命中同一批条目。
- **2025-08-22**：完成初版（检索 → 摘要/翻译 → 邮件/网页）。
---

## 🧭 仓库结构

```
arxiv_tracker/        # 核心逻辑（客户端、解析、摘要、站点、邮件等）
docs/                 # GitHub Pages 站点输出（自动生成）
outputs/              # 每次运行保存的 JSON/MD（自动生成）
.state/               # 去重状态（seen.json，建议随仓库提交）
.github/workflows/    # digest.yml 定时任务（每日 21:00 北京时间）
config.yaml           # 检索/摘要/邮件/站点/去重 配置
requirements.txt      # 运行依赖
```

---

## 🚀 快速开始（Fork & 部署）

### 1) Fork 本仓库

点击右上角 **Fork**，得到你自己的副本。

### 2) 配置 Secrets 与 Variables

> Settings → **Secrets and variables** → **Actions**

> 为避免个人信息泄露，邮箱、API Key、账号信息等请放在 **Secrets**。
> 检索关键词这类非敏感参数建议放在 **Variables**，便于在线调参。

**Secrets（机密）**

- `OPENAI_COMPAT_API_KEY`：任意 OpenAI 兼容平台的 API Key（如 **DeepSeek**、**SiliconFlow**）  
- `OPENAI_COMPAT_BASE_URL`：LLM 服务 Base URL（如 `https://api.deepseek.com` 或 `https://api.siliconflow.cn`）
- `OPENAI_COMPAT_MODEL`：LLM 模型名（如 `deepseek-chat`、`Qwen/Qwen2.5-7B-Instruct`）
- `SEMANTIC_EMBED_BASE_URL`：语义重排 Embedding 服务 Base URL（启用 `semantic.enabled` 时使用）
- `SEMANTIC_EMBED_MODEL`：语义重排 Embedding 模型名（启用 `semantic.enabled` 时使用）
- `SEMANTIC_EMBED_API_KEY`：语义重排 Embedding API Key（启用 `semantic.enabled` 时使用）
- `EMAIL_TO`：收件人（多个用 `,` 或 `;` 分隔，比如 `a@qq.com,b@xx.com`）
- `EMAIL_SENDER`：发件人邮箱（通常与 SMTP 用户一致，比如 `xxx@qq.com`）
- `SMTP_USER`：SMTP 用户名（通常 = 发件人邮箱，比如 `xxx@qq.com`）
- `SMTP_PASS`：QQ 邮箱 **SMTP 授权码**（非登录密码）
- `SERPAPI_API_KEY`：Google Scholar 检索 API Key（若启用 `sources.scholar`）
- `ZOTERO_ID`：Zotero 用户 ID（若启用语义重排）
- `ZOTERO_KEY`：Zotero API Key（若启用语义重排）

**Variables（非敏感，建议用于检索调参）**

- `TRACKER_CATEGORIES`：arXiv 领域分类（逗号/分号/斜杠/换行分隔，例如 `cs.CV,cs.LG,cs.AI`）
- `TRACKER_KEYWORDS`：关键词列表（逗号/分号/换行分隔）
- `TRACKER_KEYWORD_EXPRESSION`：严格布尔表达式（支持括号 + `AND/OR`，优先于 `TRACKER_KEYWORDS`）

> 启用语义重排时，请在 `config.yaml` 里填写 `semantic.zotero.include_path`（只重排指定收藏夹路径）。

### 3) 启用 GitHub Pages

Settings → **Pages**：Source 选 **Deploy from a branch**；Branch 选 `main`，Folder 选 `/docs`。

### 4) 配置并运行工作流（支持手动触发是否发信，仓库已经写好，这步可以省略，直接运行就行）

`.github/workflows/digest.yml` 示例（节选）：

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
    - cron: "0 13 * * *"  # 每天 13:00 UTC = 北京时间 21:00

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
          # 下面三项在启用 semantic.enabled 时需要
          SEMANTIC_EMBED_BASE_URL: ${{ secrets.SEMANTIC_EMBED_BASE_URL }}
          SEMANTIC_EMBED_MODEL:    ${{ secrets.SEMANTIC_EMBED_MODEL }}
          SEMANTIC_EMBED_API_KEY:  ${{ secrets.SEMANTIC_EMBED_API_KEY }}
          # 下面三项按功能开关启用
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

**配置流程如下：**  
<img src="images/guide.png" alt="Preview" width="720">


> **要点**：`file_pattern` 里包含 `.state/**`，这样去重状态会随运行持久化到仓库，防止重复推送。

---

## ⚙️ 配置说明（`config.yaml`）

> 下面示例演示最常用的字段。完整示例请参考仓库中的 `config.yaml`。

```yaml
# === 检索 ===
categories: ["cs.CV", "cs.LG", "cs.AI"]
# [可选] 通过环境变量注入分类（优先级：CLI > 环境变量 > 配置）
categories_env: "TRACKER_CATEGORIES"
keywords:
  - "open vocabulary segmentation"
  - "vision-language grounding"
# [可选] 严格布尔表达式，优先于 keywords（支持括号 + AND/OR）
keyword_expression: "(open vocabulary segmentation OR vision-language grounding) AND (reinforcement learning OR MARL)"
# [可选] 通过环境变量注入关键词（优先级：CLI > 环境变量 > 配置）
keywords_env: "TRACKER_KEYWORDS"
keyword_expression_env: "TRACKER_KEYWORD_EXPRESSION"
# [新增] 排除包含以下词汇的论文
exclude_keywords:
  - "Large Language Model"
  - "Generative AI"
logic: "AND"                 # 左：分类集合 (OR)；右：关键词集合 (OR)；二者再 AND/OR
max_results: 100             # 每页抓取上限（内部支持自动分页累计）
sort_by: "lastUpdatedDate"   # 或 submittedDate
sort_order: "descending"

# === 多源检索（arXiv + Scholar）===
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

# === 输出语言 ===
lang: "both"                 # zh / en / both

# === 摘要生成 ===
summary:
  mode: "llm"                # none / heuristic / llm
  scope: "both"              # tldr / full / both

# === LLM（OpenAI-Compatible，DeepSeek / SiliconFlow 均可） ===
llm:
  # 推荐：用环境变量注入，不在仓库中写死
  base_url: ""
  model: ""
  base_url_env: "OPENAI_COMPAT_BASE_URL"
  model_env: "OPENAI_COMPAT_MODEL"
  # 若你只在本地测试，也可直接写死：
  # base_url: "https://api.deepseek.com"
  # model: "deepseek-chat"
  api_key_env: "OPENAI_COMPAT_API_KEY"     # 统一密钥环境变量
  system_prompt_en: |
    You are a senior paper-reading assistant...
  system_prompt_zh: |
    你是资深论文阅读助手...

# === 可选：题目/摘要中文翻译 ===
translate:
  enabled: true
  lang: "zh"
  fields: ["title", "summary"]

# === 邮件发送（QQ 邮箱示例） ===
email:
  enabled: true
  subject: "[arXiv] Daily Digest"
  smtp_server: "smtp.qq.com"
  smtp_port: 465
  tls: "ssl"                 # auto / ssl / starttls
  debug: false
  detail: "full"             # simple / full
  max_items: 10
  attach_md: true
  attach_pdf: false

# === 站点（GitHub Pages） ===
site:
  enabled: true
  dir: "docs"
  title: "arXiv 论文速递"
  keep_runs: 1024
  theme: "light"
  accent: "#2563eb"

# === 新鲜度 & 去重（成功后落盘） ===
freshness:
  since_days: 3               # 近 N 天（若偶尔为空，可暂时改 2~3）
  unique_only: true           # 开启跨天去重
  state_path: ".state/seen.json"
  fallback_when_empty: false  # 当当天无新增时是否回退展示最近 top 若干

# === Zotero 语义重排（建议限定路径，避免全库噪声） ===
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
    # BaseURL / model / api key 全部走 Secrets 环境变量注入
    base_url: ""
    model: ""
    base_url_env: "SEMANTIC_EMBED_BASE_URL"
    model_env: "SEMANTIC_EMBED_MODEL"
    api_key_env: "SEMANTIC_EMBED_API_KEY"
    batch_size: 64
    timeout: 45
```

> **搜索逻辑**：默认 `categories` 内 OR、`keywords` 内 OR，再由 `logic` 连接。若配置 `keyword_expression`，会启用严格布尔解析（括号 + `AND/OR`），并优先覆盖 `keywords`。
>
> **语义重排行为**：当 `semantic.enabled=true` 且 `require_include_path=true` 时，若 `include_path` 为空，会自动跳过语义重排并在日志给出告警。

---

## 🛠️ 本地运行（macOS/Linux）

```bash
python -m venv .venv && source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

export OPENAI_COMPAT_API_KEY="你的密钥"
export TRACKER_CATEGORIES="cs.CV,cs.LG,cs.AI"
export TRACKER_KEYWORDS="open vocabulary segmentation,vision-language grounding"
# 若设置表达式，将优先于 TRACKER_KEYWORDS
export TRACKER_KEYWORD_EXPRESSION="(open vocabulary segmentation OR vision-language grounding) AND reinforcement learning"
export OPENAI_COMPAT_BASE_URL="https://api.siliconflow.cn"
export OPENAI_COMPAT_MODEL="Qwen/Qwen2.5-7B-Instruct"
# 若启用语义重排（semantic.enabled=true），再注入以下三个变量
export SEMANTIC_EMBED_BASE_URL="https://api.siliconflow.cn"
export SEMANTIC_EMBED_MODEL="BAAI/bge-m3"
export SEMANTIC_EMBED_API_KEY="你的Embedding密钥"
# 若启用 Scholar/Zotero 功能，再注入以下变量
export SERPAPI_API_KEY="你的SerpApi密钥"
export ZOTERO_ID="你的Zotero用户ID"
export ZOTERO_KEY="你的Zotero API Key"
export EMAIL_TO="your@qq.com"
export EMAIL_SENDER="your@qq.com"
export SMTP_USER="your@qq.com"
export SMTP_PASS="你的QQ SMTP授权码"

python -m arxiv_tracker.cli run --config config.yaml --site-dir docs --verbose
```

### Windows（PowerShell）

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt

$Env:OPENAI_COMPAT_API_KEY = "你的密钥"
$Env:TRACKER_CATEGORIES = "cs.CV,cs.LG,cs.AI"
$Env:TRACKER_KEYWORDS = "open vocabulary segmentation,vision-language grounding"
# 若设置表达式，将优先于 TRACKER_KEYWORDS
$Env:TRACKER_KEYWORD_EXPRESSION = "(open vocabulary segmentation OR vision-language grounding) AND reinforcement learning"
$Env:OPENAI_COMPAT_BASE_URL = "https://api.siliconflow.cn"
$Env:OPENAI_COMPAT_MODEL = "Qwen/Qwen2.5-7B-Instruct"
# 若启用语义重排（semantic.enabled=true），再注入以下三个变量
$Env:SEMANTIC_EMBED_BASE_URL = "https://api.siliconflow.cn"
$Env:SEMANTIC_EMBED_MODEL = "BAAI/bge-m3"
$Env:SEMANTIC_EMBED_API_KEY = "你的Embedding密钥"
# 若启用 Scholar/Zotero 功能，再注入以下变量
$Env:SERPAPI_API_KEY = "你的SerpApi密钥"
$Env:ZOTERO_ID = "你的Zotero用户ID"
$Env:ZOTERO_KEY = "你的Zotero API Key"
$Env:EMAIL_TO     = "your@qq.com"
$Env:EMAIL_SENDER = "your@qq.com"
$Env:SMTP_USER    = "your@qq.com"
$Env:SMTP_PASS    = "你的QQ SMTP授权码"

python -m arxiv_tracker.cli run --config config.yaml --site-dir docs --verbose
```

---

## ❓ 常见问题（FAQ）

- **检索结果总是相同/逐渐变少？**  
  已启用**自动分页** + **新鲜度过滤** + **成功后落盘去重**。若当天为空，可将 `since_days` 临时改为 2~3 并观察；或检查关键词是否过窄。
- **401 Unauthorized（SiliconFlow/DeepSeek）**  
  请确保 `OPENAI_COMPAT_API_KEY` 填写的是真实可用的 API Key；SiliconFlow 的 Bearer 直接放 Key 即可。
- **ReadTimeout（arXiv API）**  
  可能是网络波动，可重试；或稍后再试。
- **邮件没收到？**  
  检查 Actions 日志“Show email env (masked)”是否注入完整；QQ 开启 SMTP 并使用**授权码**；必要时切换 465/SSL 与 587/STARTTLS。

---

## 🗺️ 待办清单
- [x] 解决每天检索到的文献都一样的问题
- [x] 每次会发送2封邮件的bug
- [x] 代码链接补全（缺失时抓取 PDF 首页作为兜底）
- [x] 支持更多LLM，下一步考虑硅基流动的API
- [x] 支持排除特定关键词（如过滤 LLM 泛滥的论文）
- [ ] 更多站点主题（暗色、跟随系统） 
- [ ] 自定义卡片字段开关与顺序 

## ✨ Star History

[![Star History](https://api.star-history.com/svg?repos=colorfulandcjy0806/Arxiv-tracker&type=Date)](https://star-history.com/#colorfulandcjy0806/Arxiv-tracker&Date)

---

## 🤝 Community contributors

<a href="https://github.com/colorfulandcjy0806/Arxiv-tracker/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=colorfulandcjy0806/Arxiv-tracker" alt="Contributors" width="720"/>
</a>

## 🔒 License

本项目基于 **MIT 协议** 开源，详见 [LICENSE](./LICENSE)。
