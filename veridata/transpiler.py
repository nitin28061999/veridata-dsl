from __future__ import annotations

from .ast_nodes import (
    BinaryExpr,
    DatasetDecl,
    Expr,
    FuncCallExpr,
    IdentExpr,
    LiteralExpr,
)


class PandasTranspiler:
    def transpile(self, ast: DatasetDecl) -> str:
        lines: list[str] = [
            "import json",
            "import sys",
            "import numpy as np",
            "import pandas as pd",
            "",
            "",
            "def _metric_completeness(df: pd.DataFrame, col: str) -> float:",
            "    if len(df) == 0:",
            "        return 100.0",
            "    return float(df[col].notna().mean() * 100.0)",
            "",
            "",
            "def _metric_uniqueness(df: pd.DataFrame, col: str) -> float:",
            "    non_null = df[col].dropna()",
            "    if len(non_null) == 0:",
            "        return 100.0",
            "    return float(non_null.nunique() / len(non_null) * 100.0)",
            "",
            "",
            "def _metric_mean(df: pd.DataFrame, col: str) -> float:",
            "    return float(pd.to_numeric(df[col], errors='coerce').mean())",
            "",
            "",
            "def _metric_outliers(df: pd.DataFrame, col: str, method: str = 'iqr', threshold: float = 1.5) -> float:",
            "    s = pd.to_numeric(df[col], errors='coerce').dropna()",
            "    if len(s) == 0:",
            "        return 0.0",
            "    if method == 'zscore':",
            "        std = s.std()",
            "        if std == 0 or np.isnan(std):",
            "            return 0.0",
            "        mask = ((s - s.mean()).abs() / std) > threshold",
            "    else:",
            "        q1, q3 = s.quantile(0.25), s.quantile(0.75)",
            "        iqr = q3 - q1",
            "        mask = (s < (q1 - threshold * iqr)) | (s > (q3 + threshold * iqr))",
            "    return float(mask.mean() * 100.0)",
            "",
            "",
            "def run_audit(csv_path: str | None = None) -> dict:",
            f"    source = csv_path or {ast.source_path!r}",
            "    df = pd.read_csv(source)",
            "    results = []",
            "    has_halt = False",
            "",
        ]

        if ast.schema:
            lines.append("    # --- Schema Checks ---")
            for f in ast.schema.fields:
                if f.field_type in ("date", "datetime"):
                    lines.append(f"    if {f.name!r} in df.columns:")
                    lines.append(f"        df[{f.name!r}] = pd.to_datetime(df[{f.name!r}], errors='coerce')")
                for c in f.constraints:
                    if c.name == "not_null":
                        lines.append(f"    if {f.name!r} in df.columns and df[{f.name!r}].isna().any():")
                        lines.append(
                            f"        results.append({{'rule': 'schema.{f.name}.not_null', 'status': 'fail', 'severity': 'halt', 'message': 'Null values found in {f.name}'}})"
                        )
                        lines.append("        has_halt = True")
                    elif c.name == "unique":
                        lines.append(f"    if {f.name!r} in df.columns and not df[{f.name!r}].dropna().is_unique:")
                        lines.append(
                            f"        results.append({{'rule': 'schema.{f.name}.unique', 'status': 'fail', 'severity': 'halt', 'message': 'Duplicate values found in {f.name}'}})"
                        )
                        lines.append("        has_halt = True")
                    elif c.name == "min":
                        lines.append(f"    if {f.name!r} in df.columns and (pd.to_numeric(df[{f.name!r}], errors='coerce') < {c.value!r}).any():")
                        lines.append(
                            f"        results.append({{'rule': 'schema.{f.name}.min', 'status': 'fail', 'severity': 'warn', 'message': 'Values below min {c.value!r} in {f.name}'}})"
                        )
                    elif c.name == "max":
                        lines.append(f"    if {f.name!r} in df.columns and (pd.to_numeric(df[{f.name!r}], errors='coerce') > {c.value!r}).any():")
                        lines.append(
                            f"        results.append({{'rule': 'schema.{f.name}.max', 'status': 'fail', 'severity': 'warn', 'message': 'Values above max {c.value!r} in {f.name}'}})"
                        )
                if f.field_type == "enum" and f.enum_values:
                    allowed = repr(set(f.enum_values))
                    lines.append(f"    if {f.name!r} in df.columns:")
                    lines.append(f"        invalid_enum = ~df[{f.name!r}].dropna().isin({allowed})")
                    lines.append("        if invalid_enum.any():")
                    lines.append(
                        f"            results.append({{'rule': 'schema.{f.name}.enum', 'status': 'fail', 'severity': 'warn', 'message': f'Invalid enum values in {f.name}: {{int(invalid_enum.sum())}} rows'}})"
                    )

        if ast.rules:
            lines.append("")
            lines.append("    # --- Audit Rules ---")
            for idx, rule in enumerate(ast.rules.rules, start=1):
                rule_id = f"rule_{idx}_{rule.kind}"
                target_var = "sub_df" if rule.where_clause else "df"
                if rule.where_clause:
                    where_code = self._emit_row_expr(rule.where_clause, "df")
                    lines.append(f"    sub_df = df[{where_code}]")
                if rule.kind == "expect" or self._is_aggregate_expr(rule.condition):
                    agg_code = self._emit_agg_expr(rule.condition, target_var)
                    lines.append(f"    passed_{idx} = bool({agg_code})")
                else:
                    row_code = self._emit_row_expr(rule.condition, target_var)
                    lines.append(f"    passed_{idx} = bool(({row_code}).fillna(False).all())")

                lines.append(f"    if not passed_{idx}:")
                lines.append(
                    f"        results.append({{'rule': {rule_id!r}, 'status': 'fail', 'severity': {rule.severity!r}, 'message': {rule.message!r}}})"
                )
                if rule.severity == "halt":
                    lines.append("        has_halt = True")
                else:
                    lines.append(
                        f"        results.append({{'rule': {rule_id!r}, 'status': 'pass', 'severity': {rule.severity!r}, 'message': 'OK'}})"
                    )

        export_path = ast.on_failure.export_path if ast.on_failure else None
        show_summary = ast.on_failure.summary if ast.on_failure else True

        lines.extend([
            "",
            "    report = {",
            f"        'dataset': {ast.name!r},",
            "        'rows_evaluated': int(len(df)),",
            "        'has_halt': has_halt,",
            "        'results': results,",
            "    }",
        ])

        if export_path:
            lines.extend([
                f"    with open({export_path!r}, 'w', encoding='utf-8') as fh:",
                "        json.dump(report, fh, indent=2)",
            ])

        if show_summary:
            lines.append("    print(json.dumps(report, indent=2))")

        lines.extend([
            "    return report",
            "",
            "",
            "if __name__ == '__main__':",
            "    override = sys.argv[1] if len(sys.argv) > 1 else None",
            "    out = run_audit(override)",
            "    if out['has_halt']:",
            "        sys.exit(1)",
        ])

        return "\n".join(lines) + "\n"

    def _is_aggregate_expr(self, expr: Expr) -> bool:
        if isinstance(expr, FuncCallExpr):
            return True
        if isinstance(expr, BinaryExpr):
            return self._is_aggregate_expr(expr.left) or self._is_aggregate_expr(expr.right)
        return False

    def _emit_agg_expr(self, expr: Expr, df_var: str) -> str:
        if isinstance(expr, LiteralExpr):
            return repr(expr.value)
        if isinstance(expr, FuncCallExpr):
            col_arg = expr.args[0] if expr.args else None
            col_name = col_arg.name if isinstance(col_arg, IdentExpr) else ""
            if expr.name == "completeness":
                return f"_metric_completeness({df_var}, {col_name!r})"
            if expr.name == "uniqueness":
                return f"_metric_uniqueness({df_var}, {col_name!r})"
            if expr.name == "mean":
                return f"_metric_mean({df_var}, {col_name!r})"
            if expr.name == "outliers":
                method = "iqr"
                threshold = 1.5
                if "method" in expr.kwargs and isinstance(expr.kwargs["method"], LiteralExpr):
                    method = str(expr.kwargs["method"].value)
                if "threshold" in expr.kwargs and isinstance(expr.kwargs["threshold"], LiteralExpr):
                    threshold = float(expr.kwargs["threshold"].value)
                return f"_metric_outliers({df_var}, {col_name!r}, method={method!r}, threshold={threshold!r})"
        if isinstance(expr, BinaryExpr):
            op_map = {"and": "and", "or": "or", "==": "==", "!=": "!=", ">=": ">=", "<=": "<=", ">": ">", "<": "<"}
            py_op = op_map[expr.op]
            left_s = self._emit_agg_expr(expr.left, df_var)
            right_s = self._emit_agg_expr(expr.right, df_var)
            return f"({left_s} {py_op} {right_s})"
        raise ValueError(f"Unsupported aggregate expression: {expr!r}")

    def _emit_row_expr(self, expr: Expr, df_var: str) -> str:
        if isinstance(expr, LiteralExpr):
            return repr(expr.value)
        if isinstance(expr, IdentExpr):
            return f"{df_var}[{expr.name!r}]"
        if isinstance(expr, BinaryExpr):
            left_s = self._emit_row_expr(expr.left, df_var)
            right_s = self._emit_row_expr(expr.right, df_var)
            if expr.op == "and":
                return f"(({left_s}) & ({right_s}))"
            if expr.op == "or":
                return f"(({left_s}) | ({right_s}))"
            return f"(({left_s}) {expr.op} ({right_s}))"
        raise ValueError(f"Unsupported row expression: {expr!r}")
