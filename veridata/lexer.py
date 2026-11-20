from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class TokenType(Enum):
    DATASET = auto()
    FROM = auto()
    SCHEMA = auto()
    ENUM = auto()
    RULES = auto()
    EXPECT = auto()
    ASSERT = auto()
    WHERE = auto()
    ELSE = auto()
    WARN = auto()
    HALT = auto()
    ON_FAILURE = auto()
    EXPORT = auto()
    SUMMARY = auto()
    AND = auto()
    OR = auto()
    TRUE = auto()
    FALSE = auto()

    IDENT = auto()
    NUMBER = auto()
    PERCENT = auto()
    STRING = auto()

    LBRACE = auto()
    RBRACE = auto()
    LBRACKET = auto()
    RBRACKET = auto()
    LPAREN = auto()
    RPAREN = auto()
    COLON = auto()
    COMMA = auto()
    EQ = auto()
    NEQ = auto()
    GTE = auto()
    LTE = auto()
    GT = auto()
    LT = auto()

    EOF = auto()


KEYWORDS: dict[str, TokenType] = {
    "dataset": TokenType.DATASET,
    "from": TokenType.FROM,
    "schema": TokenType.SCHEMA,
    "enum": TokenType.ENUM,
    "rules": TokenType.RULES,
    "expect": TokenType.EXPECT,
    "assert": TokenType.ASSERT,
    "where": TokenType.WHERE,
    "else": TokenType.ELSE,
    "warn": TokenType.WARN,
    "halt": TokenType.HALT,
    "on_failure": TokenType.ON_FAILURE,
    "export": TokenType.EXPORT,
    "summary": TokenType.SUMMARY,
    "and": TokenType.AND,
    "or": TokenType.OR,
    "true": TokenType.TRUE,
    "false": TokenType.FALSE,
}


@dataclass
class Token:
    type: TokenType
    value: str
    line: int
    col: int


class LexError(Exception):
    def __init__(self, message: str, line: int, col: int) -> None:
        super().__init__(f"LexError at {line}:{col}: {message}")
        self.line = line
        self.col = col


class Lexer:
    def __init__(self, source: str) -> None:
        self.source = source
        self.pos = 0
        self.line = 1
        self.col = 1

    def _peek(self, offset: int = 0) -> str:
        idx = self.pos + offset
        return self.source[idx] if idx < len(self.source) else "\0"

    def _advance(self) -> str:
        ch = self._peek()
        self.pos += 1
        if ch == "\n":
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return ch

    def _skip_whitespace_and_comments(self) -> None:
        while self.pos < len(self.source):
            ch = self._peek()
            if ch.isspace():
                self._advance()
            elif ch == "/" and self._peek(1) == "/":
                while self._peek() not in ("\n", "\0"):
                    self._advance()
            else:
                break

    def _read_string(self) -> Token:
        start_line, start_col = self.line, self.col
        self._advance()
        chars: list[str] = []
        while self._peek() not in ('"', "\0"):
            ch = self._advance()
            if ch == "\\" and self._peek() != "\0":
                esc = self._advance()
                escape_map = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}
                chars.append(escape_map.get(esc, esc))
            else:
                chars.append(ch)
        if self._peek() != '"':
            raise LexError("Unterminated string literal", start_line, start_col)
        self._advance()
        return Token(TokenType.STRING, "".join(chars), start_line, start_col)

    def _read_number_or_percent(self) -> Token:
        start_line, start_col = self.line, self.col
        chars: list[str] = []
        seen_dot = False
        while self._peek().isdigit() or (self._peek() == "." and not seen_dot and self._peek(1).isdigit()):
            if self._peek() == ".":
                seen_dot = True
            chars.append(self._advance())
        if self._peek() == "%":
            self._advance()
            return Token(TokenType.PERCENT, "".join(chars), start_line, start_col)
        return Token(TokenType.NUMBER, "".join(chars), start_line, start_col)

    def _read_ident_or_keyword(self) -> Token:
        start_line, start_col = self.line, self.col
        chars: list[str] = []
        while self._peek().isalnum() or self._peek() == "_":
            chars.append(self._advance())
        ident = "".join(chars)
        tok_type = KEYWORDS.get(ident, TokenType.IDENT)
        return Token(tok_type, ident, start_line, start_col)

    def tokenize(self) -> list[Token]:
        tokens: list[Token] = []
        while True:
            self._skip_whitespace_and_comments()
            line, col = self.line, self.col
            ch = self._peek()

            if ch == "\0":
                tokens.append(Token(TokenType.EOF, "", line, col))
                return tokens

            if ch == '"':
                tokens.append(self._read_string())
            elif ch.isdigit():
                tokens.append(self._read_number_or_percent())
            elif ch.isalpha() or ch == "_":
                tokens.append(self._read_ident_or_keyword())
            else:
                two_char = ch + self._peek(1)
                two_map = {
                    "==": TokenType.EQ,
                    "!=": TokenType.NEQ,
                    ">=": TokenType.GTE,
                    "<=": TokenType.LTE,
                }
                if two_char in two_map:
                    self._advance()
                    self._advance()
                    tokens.append(Token(two_map[two_char], two_char, line, col))
                    continue

                one_map = {
                    "{": TokenType.LBRACE,
                    "}": TokenType.RBRACE,
                    "[": TokenType.LBRACKET,
                    "]": TokenType.RBRACKET,
                    "(": TokenType.LPAREN,
                    ")": TokenType.RPAREN,
                    ":": TokenType.COLON,
                    ",": TokenType.COMMA,
                    ">": TokenType.GT,
                    "<": TokenType.LT,
                }
                if ch in one_map:
                    self._advance()
                    tokens.append(Token(one_map[ch], ch, line, col))
                else:
                    raise LexError(f"Unexpected character {ch!r}", line, col)
