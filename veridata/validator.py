from __future__ import annotations

from dataclasses import dataclass

from .ast_nodes import (
    BinaryExpr,
    DatasetDecl,
    Expr,
    FuncCallExpr,
    IdentExpr,
    LiteralExpr,
)

SUPPORTED_TYPES = {"string", "int", "integer", "float", "bool", "boolean", "date", "datetime", "enum"}
SUPPORTED_FUNCS = {"completeness", "uniqueness", "outliers", "mean"}
SUPPORTED_OUTLIER_METHODS = {"iqr", "zscore"}


@dataclass
class ValidationIssue:
    level: str
    message: str
    line: int
    col: int


class StaticValidator:
    def validate(self, ast: DatasetDecl) -> list[ValidationIssue]:
        # sourcery skip: low-code-quality
        issues: list[ValidationIssue] = []
        known_fields: set[str] = set()

        if ast.schema:
            for field_decl in ast.schema.fields:
                if field_decl.name in known_fields:
                    issues.append(
                        ValidationIssue(
                            "error",
                            f"Duplicate schema field {field_decl.name!r}",
                            field_decl.span.line,
                            field_decl.span.col,
                        )
                    )
                known_fields.add(field_decl.name)

                if field_decl.field_type not in SUPPORTED_TYPES:
                    issues.append(
                        ValidationIssue(
                            "error",
                            f"Unsupported field type {field_decl.field_type!r} for {field_decl.name!r}",
                            field_decl.span.line,
                            field_decl.span.col,
                        )
                    )

                if field_decl.field_type == "enum" and not field_decl.enum_values:
                    issues.append(
                        ValidationIssue(
                            "error",
                            f"Enum field {field_decl.name!r} must declare at least one value",
                            field_decl.span.line,
                            field_decl.span.col,
                        )
                    )

                constraints_by_name = {c.name: c for c in field_decl.constraints}
                if "min" in constraints_by_name and "max" in constraints_by_name:
                    min_val = constraints_by_name["min"].value
                    max_val = constraints_by_name["max"].value
                    if isinstance(min_val, (int, float)) and isinstance(max_val, (int, float)) and min_val > max_val:
                        c_span = constraints_by_name["min"].span
                        issues.append(
                            ValidationIssue(
                                "error",
                                f"Contradictory bounds on {field_decl.name!r}: min ({min_val}) > max ({max_val})",
                                c_span.line,
                                c_span.col,
                            )
                        )

        if ast.rules:
            for rule in ast.rules.rules:
                self._check_expr(rule.condition, known_fields, issues)
                if rule.where_clause:
                    self._check_expr(rule.where_clause, known_fields, issues)

        return issues

    def _check_expr(self, expr: Expr, known_fields: set[str], issues: list[ValidationIssue]) -> None:
        if isinstance(expr, LiteralExpr):
            if expr.kind == "percent" and not (0.0 <= float(expr.value) <= 100.0):
                issues.append(
                    ValidationIssue(
                        "warning",
                        f"Percentage literal {expr.value}% is outside typical 0%..100% range",
                        expr.span.line,
                        expr.span.col,
                    )
                )
        elif isinstance(expr, IdentExpr):
            if known_fields and expr.name not in known_fields:
                issues.append(
                    ValidationIssue(
                        "error",
                        f"Unknown column {expr.name!r} (not declared in schema)",
                        expr.span.line,
                        expr.span.col,
                    )
                )
        elif isinstance(expr, FuncCallExpr):
            if expr.name not in SUPPORTED_FUNCS:
                issues.append(
                    ValidationIssue(
                        "error",
                        f"Unknown function {expr.name!r}; supported: {sorted(SUPPORTED_FUNCS)}",
                        expr.span.line,
                        expr.span.col,
                    )
                )
            for arg in expr.args:
                if isinstance(arg, IdentExpr) and known_fields and arg.name not in known_fields:
                    issues.append(
                        ValidationIssue(
                            "error",
                            f"Unknown column {arg.name!r} passed to {expr.name}()",
                            arg.span.line,
                            arg.span.col,
                        )
                    )
            if expr.name == "outliers" and "method" in expr.kwargs:
                m_expr = expr.kwargs["method"]
                if isinstance(m_expr, LiteralExpr) and m_expr.value not in SUPPORTED_OUTLIER_METHODS:
                    issues.append(
                        ValidationIssue(
                            "error",
                            f"Unsupported outlier method {m_expr.value!r}; use 'iqr' or 'zscore'",
                            m_expr.span.line,
                            m_expr.span.col,
                        )
                    )
        elif isinstance(expr, BinaryExpr):
            self._check_expr(expr.left, known_fields, issues)
            self._check_expr(expr.right, known_fields, issues)
