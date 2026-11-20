from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import Lexer, PandasTranspiler, Parser, StaticValidator


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="veridata", description="VeriData DSL check & Pandas transpiler")
    parser.add_argument("command", choices=["check", "compile"])
    parser.add_argument("script", type=Path, help="Path to .vd DSL file")
    parser.add_argument("-o", "--output", type=Path, default=Path("generated_audit.py"), help="Output .py path")
    args = parser.parse_args(argv)

    source = args.script.read_text(encoding="utf-8")
    tokens = Lexer(source).tokenize()
    ast = Parser(tokens).parse()
    issues = StaticValidator().validate(ast)

    for issue in issues:
        print(f"[{issue.level.upper()}] {issue.line}:{issue.col} - {issue.message}")

    if any(i.level == "error" for i in issues):
        return 1

    if args.command == "compile":
        py_code = PandasTranspiler().transpile(ast)
        args.output.write_text(py_code, encoding="utf-8")
        print(f"Compiled {args.script} -> {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
