from __future__ import annotations

from typing import Any

from .ast_nodes import (
    BinaryExpr,
    ConstraintSpec,
    DatasetDecl,
    Expr,
    FieldDecl,
    FuncCallExpr,
    IdentExpr,
    LiteralExpr,
    OnFailureBlock,
    RulesBlock,
    RuleStmt,
    SchemaBlock,
    SourceSpan,
)
from .lexer import Token, TokenType


class ParseError(Exception):
    def __init__(self, message: str, token: Token) -> None:
        super().__init__(f"ParseError at {token.line}:{token.col}: {message} (got {token.type.name} {token.value!r})")
        self.token = token


class Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.pos = 0

    def _current(self) -> Token:
        return self.tokens[self.pos]

    def _peek(self, offset: int = 1) -> Token:
        idx = self.pos + offset
        return self.tokens[idx] if idx < len(self.tokens) else self.tokens[-1]

    def _match(self, *types: TokenType) -> Token | None:
        # sourcery skip: class-extract-method
        if self._current().type in types:
            tok = self._current()
            self.pos += 1
            return tok
        return None

    def _expect(self, tok_type: TokenType, message: str = "") -> Token:
        tok = self._current()
        if tok.type == tok_type:
            self.pos += 1
            return tok
        raise ParseError(message or f"Expected {tok_type.name}", tok)

    def _span(self, tok: Token) -> SourceSpan:
        return SourceSpan(tok.line, tok.col)

    def parse(self) -> DatasetDecl:
        kw = self._expect(TokenType.DATASET, "Expected 'dataset' declaration")
        name_tok = self._expect(TokenType.STRING, "Expected dataset name string")
        self._expect(TokenType.FROM, "Expected 'from' after dataset name")
        src_tok = self._expect(TokenType.STRING, "Expected source file path string")
        self._expect(TokenType.LBRACE, "Expected '{' to open dataset block")

        schema: SchemaBlock | None = None
        rules: RulesBlock | None = None
        on_failure: OnFailureBlock | None = None

        while self._current().type != TokenType.RBRACE:
            tok = self._current()
            if tok.type == TokenType.SCHEMA:
                schema = self._parse_schema_block()
            elif tok.type == TokenType.RULES:
                rules = self._parse_rules_block()
            elif tok.type == TokenType.ON_FAILURE:
                on_failure = self._parse_on_failure_block()
            else:
                raise ParseError("Unknown dataset section", tok)

        self._expect(TokenType.RBRACE, "Expected '}' to close dataset block")
        self._expect(TokenType.EOF, "Unexpected trailing tokens")

        return DatasetDecl(
            name=name_tok.value,
            source_path=src_tok.value,
            schema=schema,
            rules=rules,
            on_failure=on_failure,
            span=self._span(kw),
        )

    def _parse_schema_block(self) -> SchemaBlock:
        kw = self._expect(TokenType.SCHEMA)
        self._expect(TokenType.LBRACE)
        fields: list[FieldDecl] = []
        while self._current().type != TokenType.RBRACE:
            fields.append(self._parse_field_decl())
        self._expect(TokenType.RBRACE)
        return SchemaBlock(fields=fields, span=self._span(kw))

    def _parse_field_decl(self) -> FieldDecl:
        name_tok = self._expect(TokenType.IDENT, "Expected field name")
        self._expect(TokenType.COLON, "Expected ':' after field name")

        enum_values: list[str] = []
        if self._match(TokenType.ENUM):
            field_type = "enum"
            self._expect(TokenType.LPAREN, "Expected '(' for enum values")
            while True:
                val_tok = self._expect(TokenType.STRING, "Expected string enum option")
                enum_values.append(val_tok.value)
                if not self._match(TokenType.COMMA):
                    break
            self._expect(TokenType.RPAREN, "Expected ')' after enum values")
        else:
            type_tok = self._expect(TokenType.IDENT, "Expected field type")
            field_type = type_tok.value

        constraints: list[ConstraintSpec] = []
        if self._match(TokenType.LBRACKET):
            while True:
                c_tok = self._expect(TokenType.IDENT, "Expected constraint name")
                c_val: Any = True
                if self._match(TokenType.COLON):
                    c_val = self._parse_constraint_value()
                constraints.append(ConstraintSpec(name=c_tok.value, value=c_val, span=self._span(c_tok)))
                if not self._match(TokenType.COMMA):
                    break
            self._expect(TokenType.RBRACKET, "Expected ']' after constraints")

        return FieldDecl(
            name=name_tok.value,
            field_type=field_type,
            enum_values=enum_values,
            constraints=constraints,
            span=self._span(name_tok),
        )

    def _parse_constraint_value(self) -> Any:
        tok = self._current()
        if tok.type == TokenType.STRING:
            self._advance_token()
            return tok.value
        if tok.type == TokenType.NUMBER:
            self._advance_token()
            return float(tok.value) if "." in tok.value else int(tok.value)
        if tok.type == TokenType.TRUE:
            self._advance_token()
            return True
        if tok.type == TokenType.FALSE:
            self._advance_token()
            return False
        raise ParseError("Invalid constraint value", tok)

    def _advance_token(self) -> Token:
        tok = self._current()
        self.pos += 1
        return tok

    def _parse_rules_block(self) -> RulesBlock:
        kw = self._expect(TokenType.RULES)
        self._expect(TokenType.LBRACE)
        rules: list[RuleStmt] = []
        while self._current().type != TokenType.RBRACE:
            rules.append(self._parse_rule_stmt())
        self._expect(TokenType.RBRACE)
        return RulesBlock(rules=rules, span=self._span(kw))

    def _parse_rule_stmt(self) -> RuleStmt:
        start_tok = self._current()
        if self._match(TokenType.EXPECT):
            kind = "expect"
        elif self._match(TokenType.ASSERT):
            kind = "assert"
        else:
            raise ParseError("Expected 'expect' or 'assert' rule", start_tok)

        condition = self._parse_expr()

        where_clause: Expr | None = None
        if self._match(TokenType.WHERE):
            where_clause = self._parse_expr()

        severity = "warn"
        message = f"{kind.capitalize()} rule failed"
        if self._match(TokenType.ELSE):
            sev_tok = self._current()
            if self._match(TokenType.WARN):
                severity = "warn"
            elif self._match(TokenType.HALT):
                severity = "halt"
            else:
                raise ParseError("Expected 'warn' or 'halt' after 'else'", sev_tok)
            msg_tok = self._match(TokenType.STRING)
            if msg_tok:
                message = msg_tok.value

        return RuleStmt(
            kind=kind,
            condition=condition,
            where_clause=where_clause,
            severity=severity,
            message=message,
            span=self._span(start_tok),
        )

    def _parse_on_failure_block(self) -> OnFailureBlock:
        kw = self._expect(TokenType.ON_FAILURE)
        self._expect(TokenType.LBRACE)
        export_path: str | None = None
        summary = False
        while self._current().type != TokenType.RBRACE:
            tok = self._current()
            if self._match(TokenType.EXPORT):
                path_tok = self._expect(TokenType.STRING, "Expected export file path string")
                export_path = path_tok.value
            elif self._match(TokenType.SUMMARY):
                bool_tok = self._current()
                if self._match(TokenType.TRUE):
                    summary = True
                elif self._match(TokenType.FALSE):
                    summary = False
                else:
                    raise ParseError("Expected 'true' or 'false' after 'summary'", bool_tok)
            else:
                raise ParseError("Unknown directive in on_failure block", tok)
        self._expect(TokenType.RBRACE)
        return OnFailureBlock(export_path=export_path, summary=summary, span=self._span(kw))

    def _parse_expr(self) -> Expr:
        return self._parse_or()

    def _parse_or(self) -> Expr:
        expr = self._parse_and()
        while (op_tok := self._match(TokenType.OR)):
            right = self._parse_and()
            expr = BinaryExpr(op="or", left=expr, right=right, span=self._span(op_tok))
        return expr

    def _parse_and(self) -> Expr:
        expr = self._parse_comparison()
        while (op_tok := self._match(TokenType.AND)):
            right = self._parse_comparison()
            expr = BinaryExpr(op="and", left=expr, right=right, span=self._span(op_tok))
        return expr

    def _parse_comparison(self) -> Expr:
        expr = self._parse_primary()
        comp_types = (
            TokenType.EQ,
            TokenType.NEQ,
            TokenType.GTE,
            TokenType.LTE,
            TokenType.GT,
            TokenType.LT,
        )
        while (op_tok := self._match(*comp_types)):
            right = self._parse_primary()
            expr = BinaryExpr(op=op_tok.value, left=expr, right=right, span=self._span(op_tok))
        return expr

    def _parse_primary(self) -> Expr:  # sourcery skip: low-code-quality
        tok = self._current()

        if tok.type == TokenType.PERCENT:
            self._advance_token()
            return LiteralExpr(value=float(tok.value), kind="percent", span=self._span(tok))

        if tok.type == TokenType.NUMBER:
            self._advance_token()
            num_val: Any = float(tok.value) if "." in tok.value else int(tok.value)
            return LiteralExpr(value=num_val, kind="number", span=self._span(tok))

        if tok.type == TokenType.STRING:
            self._advance_token()
            return LiteralExpr(value=tok.value, kind="string", span=self._span(tok))

        if tok.type in (TokenType.TRUE, TokenType.FALSE):
            self._advance_token()
            return LiteralExpr(value=(tok.type == TokenType.TRUE), kind="bool", span=self._span(tok))

        if tok.type == TokenType.IDENT:
            self._advance_token()
            if self._match(TokenType.LPAREN):
                args: list[Expr] = []
                kwargs: dict[str, Expr] = {}
                if self._current().type != TokenType.RPAREN:
                    while True:
                        if self._current().type == TokenType.IDENT and self._peek().type == TokenType.COLON:
                            kw_name = self._advance_token().value
                            self._advance_token()
                            kwargs[kw_name] = self._parse_expr()
                        else:
                            args.append(self._parse_expr())
                        if not self._match(TokenType.COMMA):
                            break
                self._expect(TokenType.RPAREN, "Expected ')' after function arguments")
                return FuncCallExpr(name=tok.value, args=args, kwargs=kwargs, span=self._span(tok))
            return IdentExpr(name=tok.value, span=self._span(tok))

        if self._match(TokenType.LPAREN):
            inner = self._parse_expr()
            self._expect(TokenType.RPAREN, "Expected ')' after grouped expression")
            return inner

        raise ParseError("Expected expression", tok)
