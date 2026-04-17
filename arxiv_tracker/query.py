# arxiv_tracker/query.py
import re
from typing import List, Optional, Tuple

FIELDS = ("ti", "abs", "co")  # 标题/摘要/评论（会议常在 comments）

def _quote(term: str) -> str:
    # 有空格或连字符时加引号，避免被拆词
    t = term.strip()
    if re.search(r'[\s-]', t):
        return f'"{t}"'
    return t

def _field_or(fields: List[str], term: str) -> str:
    q = _quote(term)
    return "(" + " OR ".join(f"{f}:{q}" for f in fields) + ")"

def _expand_variants(kw: str) -> List[str]:
    """为一个关键词生成若干变体：连字符/空格、大小写不敏感"""
    k = kw.strip()
    out = {k}
    if " " in k:
        out.add(k.replace(" ", "-"))
    if "-" in k:
        out.add(k.replace("-", " "))
    return sorted(out, key=len, reverse=True)  # 优先长短语

def _kw_group(kw: str) -> str:
    """
    为一个逻辑关键词构造一个子查询：
    - 先尝试短语精确（含连字符/空格变体）
    - 若包含 'open vocabulary' 与 'segmentation'，再加一个“拆词 AND”备选
    """
    variants = _expand_variants(kw)
    parts = []

    # 1) 短语匹配（多个变体，ti/abs/co）
    for v in variants:
        parts.append(_field_or(FIELDS, v))

    # 2) 针对 open-vocabulary segmentation 的拆词 AND（覆盖更多写法）
    low = kw.lower()
    if ("open vocabulary" in low or "open-vocabulary" in low) and "segmentation" in low:
        ov_terms = ["open vocabulary", "open-vocabulary", "open-vocabulary segmentation", "open vocabulary segmentation"]
        seg_terms = ["segmentation", "image segmentation"]
        ov_or = "(" + " OR ".join(_field_or(FIELDS, t) for t in ov_terms) + ")"
        seg_or = "(" + " OR ".join(_field_or(FIELDS, t) for t in seg_terms) + ")"
        parts.append(f"({ov_or} AND {seg_or})")

    return "(" + " OR ".join(parts) + ")"


_BOOLEAN_TOKENS = re.compile(r"\(|\)|\bAND\b|\bOR\b", flags=re.IGNORECASE)


def _tokenize_keyword_expression(expr: str) -> List[Tuple[str, str]]:
    tokens: List[Tuple[str, str]] = []
    pos = 0
    for m in _BOOLEAN_TOKENS.finditer(expr or ""):
        if m.start() > pos:
            chunk = (expr[pos:m.start()] or "").strip()
            if chunk:
                tokens.append(("TERM", chunk))
        token = m.group(0)
        if token == "(":
            tokens.append(("LPAREN", token))
        elif token == ")":
            tokens.append(("RPAREN", token))
        else:
            tokens.append((token.upper(), token.upper()))
        pos = m.end()

    tail = (expr[pos:] if expr else "").strip()
    if tail:
        tokens.append(("TERM", tail))
    return tokens


class _KeywordExprParser:
    def __init__(self, tokens: List[Tuple[str, str]]):
        self.tokens = tokens
        self.idx = 0

    def _peek(self) -> Optional[Tuple[str, str]]:
        if self.idx >= len(self.tokens):
            return None
        return self.tokens[self.idx]

    def _take(self) -> Optional[Tuple[str, str]]:
        tok = self._peek()
        if tok is not None:
            self.idx += 1
        return tok

    def _accept(self, kind: str) -> bool:
        tok = self._peek()
        if tok and tok[0] == kind:
            self.idx += 1
            return True
        return False

    def parse(self):
        if not self.tokens:
            raise ValueError("keyword_expression is empty")
        node = self._parse_or()
        if self._peek() is not None:
            raise ValueError(f"unexpected token: {self._peek()[1]}")
        return node

    def _parse_or(self):
        node = self._parse_and()
        while self._accept("OR"):
            rhs = self._parse_and()
            node = ("OR", node, rhs)
        return node

    def _parse_and(self):
        node = self._parse_primary()
        while self._accept("AND"):
            rhs = self._parse_primary()
            node = ("AND", node, rhs)
        return node

    def _parse_primary(self):
        tok = self._peek()
        if tok is None:
            raise ValueError("unexpected end of expression")

        if tok[0] == "LPAREN":
            self._take()
            inner = self._parse_or()
            if not self._accept("RPAREN"):
                raise ValueError("missing closing ')' in keyword_expression")
            return inner

        if tok[0] == "TERM":
            self._take()
            term = (tok[1] or "").strip()
            if not term:
                raise ValueError("empty term in keyword_expression")
            return ("TERM", term)

        raise ValueError(f"unexpected token: {tok[1]}")


def _compile_keyword_ast(node) -> str:
    kind = node[0]
    if kind == "TERM":
        return _kw_group(node[1])
    if kind in ("AND", "OR"):
        left = _compile_keyword_ast(node[1])
        right = _compile_keyword_ast(node[2])
        return f"({left} {kind} {right})"
    raise ValueError(f"unsupported AST node: {kind}")


def _build_keyword_query(keys: List[str], keyword_expression: str) -> str:
    expr = (keyword_expression or "").strip()
    if expr:
        tokens = _tokenize_keyword_expression(expr)
        parser = _KeywordExprParser(tokens)
        ast = parser.parse()
        return _compile_keyword_ast(ast)

    if keys:
        return "(" + " OR ".join(_kw_group(k) for k in keys) + ")"
    return ""


def build_search_query(
    categories: List[str],
    keywords: List[str],
    exclude_keywords: List[str] = None,
    logic: str = "AND",
    keyword_expression: str = "",
) -> str:
    """
    生成 arXiv API 的 search_query 字符串。
    - categories: ["cs.CV","cs.LG"] -> (cat:cs.CV OR cat:cs.LG)
    - keywords:   每个 kw 变成一个 _kw_group，关键词之间用 OR 连接
    - keyword_expression: 严格布尔表达式（支持括号/AND/OR），优先于 keywords
    - 组间逻辑：cat_group (AND/OR) kw_group
    - 结构: (正面查询) AND NOT (负面查询)
    """
    cats = [c.strip() for c in (categories or []) if c and c.strip()]
    keys = [k.strip() for k in (keywords or []) if k and k.strip()]
    excs = [e.strip() for e in (exclude_keywords or []) if e and e.strip()] 
    
    cat_q = ""
    key_q = ""
    exc_q = "" 

    if cats:
        cat_q = "(" + " OR ".join(f"cat:{c}" for c in cats) + ")"
    key_q = _build_keyword_query(keys, keyword_expression)
        
    if excs:
        # 复用 _kw_group 逻辑，也可以只做简单匹配。这里复用逻辑以支持变体。
        # 意思为: NOT ( ("LLM"在标题/摘要) OR ("Large Language Model"在标题/摘要) )
        exc_q = " AND NOT (" + " OR ".join(_kw_group(e) for e in excs) + ")"
        
    # 构建正面查询部分
    positive_q = ""
    if cat_q and key_q:
        op = "AND" if (logic or "AND").upper() == "AND" else "OR"
        positive_q = f"({cat_q} {op} {key_q})"
    elif cat_q:
        positive_q = cat_q
    elif key_q:
        positive_q = key_q
    else:
        positive_q = "all:*"

    # 最终拼接
    return positive_q + exc_q
