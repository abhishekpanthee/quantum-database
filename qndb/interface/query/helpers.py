"""Helper utilities for query parsing."""

from typing import Dict, List, Any, Optional, Tuple


def flatten_conditions(tree: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Flatten a condition tree into a backward-compatible list of simple
    ``{field, operator, value}`` dicts.  Only AND-connected comparisons and
    special predicates (IN, BETWEEN, LIKE, IS_NULL) are collected; OR / NOT
    branches are skipped in the flat representation."""
    if tree is None:
        return []
    out: List[Dict[str, Any]] = []

    def _walk(node: Dict):
        ntype = node.get("type")
        if ntype == "comparison":
            out.append({"field": node["field"], "operator": node["operator"], "value": node["value"]})
        elif ntype == "and":
            for child in node.get("children", []):
                _walk(child)
        elif ntype in ("in", "between", "like", "is_null"):
            out.append(node)

    _walk(tree)
    return out


def find_top_level(text: str, keyword: str, start: int = 0) -> int:
    """Return the position of *keyword* in *text* that occurs outside of
    quoted strings and parenthesised groups, respecting word boundaries.
    Returns -1 if not found."""
    upper = text.upper()
    kw_upper = keyword.upper()
    kw_len = len(kw_upper)
    depth = 0
    in_quote = False
    i = start
    while i <= len(upper) - kw_len:
        ch = upper[i]
        if ch == "'":
            if in_quote and i + 1 < len(upper) and upper[i + 1] == "'":
                i += 2
                continue
            in_quote = not in_quote
            i += 1
            continue
        if in_quote:
            i += 1
            continue
        if ch == '(':
            depth += 1
            i += 1
            continue
        if ch == ')':
            depth -= 1
            i += 1
            continue
        if depth == 0 and upper[i:i + kw_len] == kw_upper:
            before_ok = (i == 0 or not upper[i - 1].isalnum())
            after_ok = (i + kw_len >= len(upper) or not upper[i + kw_len].isalnum())
            if before_ok and after_ok:
                return i
        i += 1
    return -1


def extract_between(text: str, start_kw: str, end_keywords: List[str]) -> Tuple[Optional[str], int]:
    """Return the text between *start_kw* and the nearest top-level
    *end_keyword*, as ``(content, end_position)``."""
    begin = find_top_level(text, start_kw)
    if begin == -1:
        return None, -1
    content_start = begin + len(start_kw)
    end = len(text)
    for ekw in end_keywords:
        pos = find_top_level(text, ekw, content_start)
        if pos != -1 and pos < end:
            end = pos
    return text[content_start:end].strip(), end
