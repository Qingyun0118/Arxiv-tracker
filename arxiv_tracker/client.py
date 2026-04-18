# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import time
import random
import requests
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Dict, Optional

# 首选 HTTPS，失败时回退到 HTTP（某些网络下 HTTPS 易读超）
ARXIV_HTTPS = "https://export.arxiv.org/api/query"
ARXIV_HTTP  = "http://export.arxiv.org/api/query"

# 可通过环境变量调整（Windows PowerShell 示例见下）
DEFAULT_TIMEOUT = float(os.getenv("ARXIV_TIMEOUT", "45"))      # 单次请求超时（秒）
MAX_ATTEMPTS    = int(os.getenv("ARXIV_MAX_ATTEMPTS", "6"))    # 尝试次数
BASE_PAUSE      = float(os.getenv("ARXIV_PAUSE", "1.5"))       # 基础退避（秒）
MAX_SLEEP       = float(os.getenv("ARXIV_MAX_SLEEP", "20"))    # 退避上限（秒）
RETRY_AFTER_JITTER_FACTOR = 0.1
MAX_JITTER_SECONDS = 0.5

RETRYABLE_STATUS = {429, 500, 502, 503, 504}

HEADERS = {
    # 写一个正常 UA，arXiv 官方建议标注用途；邮箱可去掉
    "User-Agent": os.getenv("ARXIV_UA", "arxiv-tracker/0.1 (+https://github.com/colorfulandcjy0806/Arxiv-tracker)"),
    "Accept": "application/atom+xml,application/xml;q=0.9,*/*;q=0.8",
}

_session = requests.Session()


def _retry_after_delay(resp: Optional[requests.Response]) -> Optional[float]:
    if resp is None:
        return None
    raw = (resp.headers or {}).get("Retry-After")
    if not raw:
        return None

    s = str(raw).strip()
    if not s:
        return None

    if s.isdigit():
        return max(0.0, float(s))

    try:
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (dt - datetime.now(timezone.utc)).total_seconds())
    except Exception:
        return None


def _sleep_backoff(attempt: int, resp: Optional[requests.Response] = None) -> None:
    """
    指数退避 + 抖动。第 1 次失败等待 ~BASE_PAUSE，
    之后 2^n 递增，并加 0~0.5 随机抖动，封顶 MAX_SLEEP。
    """
    retry_after = _retry_after_delay(resp)
    if retry_after is not None:
        jitter = random.uniform(0, min(MAX_JITTER_SECONDS, retry_after * RETRY_AFTER_JITTER_FACTOR)) if retry_after > 0 else 0.0
        delay = min(retry_after + jitter, MAX_SLEEP)
    else:
        delay = min(BASE_PAUSE * (2 ** (attempt - 1)) + random.uniform(0, MAX_JITTER_SECONDS), MAX_SLEEP)
    time.sleep(delay)


def _do_get(base_url: str, params: Dict[str, str], timeout: Optional[float] = None) -> requests.Response:
    """
    带重试的 GET：对超时/连接错误/部分 5xx&429 做重试。
    """
    timeout = timeout or DEFAULT_TIMEOUT
    last_err: Optional[Exception] = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        retry_resp: Optional[requests.Response] = None
        try:
            resp = _session.get(base_url, params=params, headers=HEADERS, timeout=timeout)
            # 主动对可重试状态码抛出异常，以走重试逻辑
            if resp.status_code in RETRYABLE_STATUS:
                raise requests.exceptions.HTTPError(f"HTTP {resp.status_code}", response=resp)
            return resp  # 成功
        except (requests.exceptions.Timeout,
                requests.exceptions.ReadTimeout,
                requests.exceptions.ConnectionError) as e:
            last_err = e
        except requests.exceptions.HTTPError as e:
            last_err = e
            # 仅对可重试状态码重试；其他直接退出循环
            st = getattr(e.response, "status_code", None)
            if st not in RETRYABLE_STATUS:
                break
            retry_resp = e.response

        # 还有机会就退避后继续
        if attempt < MAX_ATTEMPTS:
            _sleep_backoff(attempt, retry_resp)

    # 全部失败
    if last_err:
        raise last_err
    raise RuntimeError("Unknown arXiv request error.")


def fetch_arxiv_feed(query: str,
                     start: int = 0,
                     max_results: int = 10,
                     sort_by: str = "submittedDate",
                     sort_order: str = "descending") -> str:
    """
    拉取 arXiv Atom Feed。先 HTTPS，失败则 HTTP 回退。
    """
    params = {
        "search_query": query,
        "start": str(start),
        "max_results": str(max_results),
        "sortBy": sort_by,
        "sortOrder": sort_order,
    }

    last_err: Optional[Exception] = None
    for base in (ARXIV_HTTPS, ARXIV_HTTP):
        try:
            r = _do_get(base, params, timeout=DEFAULT_TIMEOUT)
            r.raise_for_status()
            return r.text
        except Exception as e:
            last_err = e
            # 换下一个 base 继续
            continue

    # 两个 base 都失败
    assert last_err is not None
    raise last_err
