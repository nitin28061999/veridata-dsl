from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SourceSpan:
    line: int
    col: int


class ASTNode:
    span: SourceSpan


@dataclass
class ConstraintSpec(ASTNode):
    name: str
    value: Any = None
    span: SourceSpan = field(default_factory=lambda: SourceSpan(1, 1))


@dataclass
class FieldDecl(ASTNode):
    name: str
    field_type: str
    enum_values: list[str] = field(default_factory=list)
    constraints: list[ConstraintSpec] = field(default_factory=list)
    span: SourceSpan = field(default_factory=lambda: SourceSpan(1, 1))


@dataclass
class SchemaBlock(ASTNode):
    fields: list[FieldDecl] = field(default_factory=list)
    span: SourceSpan = field(default_factory=lambda: SourceSpan(1, 1))


class Expr(ASTNode):
    pass


@dataclass
class LiteralExpr(Expr):
    value: Any
    kind: str  # "number", "percent", "string", "bool"
    span: SourceSpan = field(default_factory=lambda: SourceSpan(1, 1))


@dataclass
class IdentExpr(Expr):
    name: str
    span: SourceSpan = field(default_factory=lambda: SourceSpan(1, 1))


@dataclass
class FuncCallExpr(Expr):
    name: str
    args: list[Expr] = field(default_factory=list)
    kwargs: dict[str, Expr] = field(default_factory=dict)
    span: SourceSpan = field(default_factory=lambda: SourceSpan(1, 1))


@dataclass
class BinaryExpr(Expr):
    op: str
    left: Expr
    right: Expr
    span: SourceSpan = field(default_factory=lambda: SourceSpan(1, 1))


@dataclass
class RuleStmt(ASTNode):
    kind: str  # "expect" or "assert"
    condition: Expr
    where_clause: Expr | None = None
    severity: str = "warn"  # "warn" or "halt"
    message: str = ""
    span: SourceSpan = field(default_factory=lambda: SourceSpan(1, 1))


@dataclass
class RulesBlock(ASTNode):
    rules: list[RuleStmt] = field(default_factory=list)
    span: SourceSpan = field(default_factory=lambda: SourceSpan(1, 1))


@dataclass
class OnFailureBlock(ASTNode):
    export_path: str | None = None
    summary: bool = False
    span: SourceSpan = field(default_factory=lambda: SourceSpan(1, 1))


@dataclass
class DatasetDecl(ASTNode):
    name: str
    source_path: str
    schema: SchemaBlock | None = None
    rules: RulesBlock | None = None
    on_failure: OnFailureBlock | None = None
    span: SourceSpan = field(default_factory=lambda: SourceSpan(1, 1))
