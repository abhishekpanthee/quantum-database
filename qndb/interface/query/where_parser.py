"""Recursive-descent parser for WHERE / HAVING expressions.

Produces a *condition tree* – nested dicts with a ``"type"`` key:
  comparison | and | or | not | in | between | like | is_null | exists
"""

from typing import Dict, List, Any, Optional, Tuple


class WhereParser:
    """Recursive-descent parser for WHERE / HAVING expressions."""

    def __init__(self, tokens: List[Tuple[str, Any]]):
        self.tokens = list(tokens)
        self.pos = 0

    def parse(self) -> Optional[Dict[str, Any]]:
        if not self.tokens:
            return None
        return self._or_expr()

    # -- helpers -----------------------------------------------------------

    def _peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def _advance(self):
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def _expect(self, ttype: str, value: Any = None):
        tok = self._peek()
        if tok is None:
            raise ValueError(f"Expected ({ttype}, {value}) but reached end")
        if tok[0] != ttype or (value is not None and tok[1] != value):
            raise ValueError(f"Expected ({ttype}, {value}), got {tok}")
        return self._advance()

    # -- grammar rules -----------------------------------------------------

    def _or_expr(self):
        left = self._and_expr()
        while self._peek() == ('KEYWORD', 'OR'):
            self._advance()
            right = self._and_expr()
            left = {"type": "or", "children": [left, right]}
        return left

    def _and_expr(self):
        left = self._not_expr()
        while self._peek() == ('KEYWORD', 'AND'):
            self._advance()
            right = self._not_expr()
            left = {"type": "and", "children": [left, right]}
        return left

    def _not_expr(self):
        if self._peek() == ('KEYWORD', 'NOT'):
            self._advance()
            return {"type": "not", "children": [self._not_expr()]}
        return self._atom()

    def _atom(self):
        tok = self._peek()
        if tok is None:
            raise ValueError("Unexpected end of expression")

        # parenthesised sub-expression
        if tok[0] == 'LPAREN':
            self._advance()
            expr = self._or_expr()
            self._expect('RPAREN')
            return expr

        # EXISTS (subquery)
        if tok == ('KEYWORD', 'EXISTS'):
            self._advance()
            self._expect('LPAREN')
            depth = 1
            while depth > 0 and self.pos < len(self.tokens):
                t = self._advance()
                if t[0] == 'LPAREN':
                    depth += 1
                elif t[0] == 'RPAREN':
                    depth -= 1
            return {"type": "exists", "subquery": True}

        # field-based predicates
        if tok[0] == 'IDENT':
            return self._field_pred(self._qualified_name())

        raise ValueError(f"Unexpected token in WHERE clause: {tok}")

    def _field_pred(self, field_name: str):
        nxt = self._peek()
        if nxt is None:
            return {"type": "comparison", "field": field_name, "operator": "=", "value": True}

        # IS [NOT] NULL
        if nxt == ('KEYWORD', 'IS'):
            self._advance()
            neg = self._peek() == ('KEYWORD', 'NOT')
            if neg:
                self._advance()
            self._expect('KEYWORD', 'NULL')
            return {"type": "is_null", "field": field_name, "negated": neg}

        # optional NOT prefix for IN / BETWEEN / LIKE
        negated = False
        if nxt == ('KEYWORD', 'NOT'):
            self._advance()
            negated = True
            nxt = self._peek()

        # IN (value_list)
        if nxt and nxt == ('KEYWORD', 'IN'):
            self._advance()
            self._expect('LPAREN')
            vals: list = []
            while self._peek() and self._peek()[0] != 'RPAREN':
                vt = self._advance()
                if vt[0] in ('STRING', 'NUMBER', 'IDENT'):
                    vals.append(vt[1])
                # skip COMMA tokens
            self._expect('RPAREN')
            return {"type": "in", "field": field_name, "values": vals, "negated": negated}

        # BETWEEN low AND high
        if nxt and nxt == ('KEYWORD', 'BETWEEN'):
            self._advance()
            low = self._value()
            self._expect('KEYWORD', 'AND')
            high = self._value()
            return {"type": "between", "field": field_name, "low": low, "high": high, "negated": negated}

        # LIKE 'pattern'
        if nxt and nxt == ('KEYWORD', 'LIKE'):
            self._advance()
            vt = self._advance()
            return {"type": "like", "field": field_name, "pattern": vt[1] if vt else '', "negated": negated}

        # If we consumed NOT but the next token is not IN/BETWEEN/LIKE,
        # treat the following comparison as negated.
        if negated:
            return {"type": "not", "children": [self._comparison(field_name)]}

        return self._comparison(field_name)

    def _comparison(self, field_name: str):
        op_tok = self._peek()
        if op_tok and op_tok[0] == 'OP':
            self._advance()
            op = op_tok[1].replace('<>', '!=')
            return {"type": "comparison", "field": field_name, "operator": op, "value": self._value()}
        return {"type": "comparison", "field": field_name, "operator": "=", "value": True}

    def _qualified_name(self) -> str:
        name = str(self._advance()[1])
        while self._peek() and self._peek()[0] == 'DOT':
            self._advance()
            name += '.' + str(self._advance()[1])
        return name

    def _value(self):
        tok = self._peek()
        if tok is None:
            raise ValueError("Expected value")
        if tok[0] in ('STRING', 'NUMBER'):
            self._advance()
            return tok[1]
        if tok[0] == 'IDENT':
            return self._qualified_name()
        # Parenthesised scalar sub-query or value list – kept opaque
        if tok[0] == 'LPAREN':
            self._advance()
            depth = 1
            inner: List[str] = []
            while depth > 0 and self.pos < len(self.tokens):
                t = self._advance()
                if t[0] == 'LPAREN':
                    depth += 1
                elif t[0] == 'RPAREN':
                    depth -= 1
                    if depth == 0:
                        break
                inner.append(str(t[1]))
            return {"subquery": ' '.join(inner)}
        if tok == ('KEYWORD', 'NULL'):
            self._advance()
            return None
        if tok == ('KEYWORD', 'TRUE'):
            self._advance()
            return True
        if tok == ('KEYWORD', 'FALSE'):
            self._advance()
            return False
        raise ValueError(f"Expected value, got {tok}")
