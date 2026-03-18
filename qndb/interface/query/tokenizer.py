"""WHERE / HAVING clause tokenizer."""

from typing import List, Tuple, Any


class WhereTokenizer:
    """Convert a WHERE-clause string into ``(type, value)`` tokens."""

    _KEYWORDS = frozenset([
        'AND', 'OR', 'NOT', 'IN', 'BETWEEN', 'LIKE',
        'IS', 'NULL', 'EXISTS', 'TRUE', 'FALSE',
    ])

    def __init__(self, text: str):
        self.text = text
        self.pos = 0
        self.tokens: List[Tuple[str, Any]] = []
        self._tokenize()

    # -- internal helpers --------------------------------------------------

    def _tokenize(self):
        while self.pos < len(self.text):
            self._skip_ws()
            if self.pos >= len(self.text):
                break
            ch = self.text[self.pos]
            if ch == '(':
                self.tokens.append(('LPAREN', '('));  self.pos += 1
            elif ch == ')':
                self.tokens.append(('RPAREN', ')'));  self.pos += 1
            elif ch == ',':
                self.tokens.append(('COMMA', ','));   self.pos += 1
            elif ch == "'":
                self.tokens.append(('STRING', self._read_string()))
            elif ch in ('=', '!', '<', '>'):
                self.tokens.append(('OP', self._read_op()))
            elif ch == '-' and self.pos + 1 < len(self.text) and self.text[self.pos + 1].isdigit():
                self.tokens.append(('NUMBER', self._read_number()))
            elif ch.isdigit():
                self.tokens.append(('NUMBER', self._read_number()))
            elif ch == '.':
                self.tokens.append(('DOT', '.'));     self.pos += 1
            elif ch.isalpha() or ch == '_':
                word = self._read_word()
                upper = word.upper()
                if upper in self._KEYWORDS:
                    self.tokens.append(('KEYWORD', upper))
                else:
                    self.tokens.append(('IDENT', word))
            else:
                self.pos += 1  # skip unknown characters

    def _skip_ws(self):
        while self.pos < len(self.text) and self.text[self.pos].isspace():
            self.pos += 1

    def _read_string(self) -> str:
        self.pos += 1  # skip opening '
        parts: List[str] = []
        while self.pos < len(self.text):
            if self.text[self.pos] == "'":
                if self.pos + 1 < len(self.text) and self.text[self.pos + 1] == "'":
                    parts.append("'")
                    self.pos += 2
                else:
                    self.pos += 1  # closing '
                    break
            else:
                parts.append(self.text[self.pos])
                self.pos += 1
        return ''.join(parts)

    def _read_op(self) -> str:
        two = self.text[self.pos:self.pos + 2]
        if two in ('!=', '<>', '<=', '>='):
            self.pos += 2
            return two
        ch = self.text[self.pos]
        self.pos += 1
        return ch

    def _read_number(self):
        start = self.pos
        if self.text[self.pos] == '-':
            self.pos += 1
        while self.pos < len(self.text) and (self.text[self.pos].isdigit() or self.text[self.pos] == '.'):
            self.pos += 1
        raw = self.text[start:self.pos]
        return float(raw) if '.' in raw else int(raw)

    def _read_word(self) -> str:
        start = self.pos
        while self.pos < len(self.text) and (self.text[self.pos].isalnum() or self.text[self.pos] == '_'):
            self.pos += 1
        return self.text[start:self.pos]
