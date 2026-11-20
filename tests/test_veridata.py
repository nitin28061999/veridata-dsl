import unittest
from pathlib import Path

from veridata import Lexer, PandasTranspiler, Parser, StaticValidator


class VeriDataTests(unittest.TestCase):
    def test_valid_orders_spec_compiles(self) -> None:
        src = Path("examples/orders.vd").read_text(encoding="utf-8")
        tokens = Lexer(src).tokenize()
        ast = Parser(tokens).parse()
        issues = StaticValidator().validate(ast)
        self.assertEqual([i for i in issues if i.level == "error"], [])
        code = PandasTranspiler().transpile(ast)
        self.assertIn("def run_audit(", code)
        self.assertIn("_metric_outliers", code)

    def test_static_validator_catches_contradictory_bounds(self) -> None:
        src = '''
        dataset "BadBounds" from "data.csv" {
          schema {
            amount: float [min: 500, max: 10]
          }
        }
        '''
        ast = Parser(Lexer(src).tokenize()).parse()
        issues = StaticValidator().validate(ast)
        self.assertTrue(any("Contradictory bounds" in i.message for i in issues))

    def test_static_validator_catches_unknown_column(self) -> None:
        src = '''
        dataset "UnknownCol" from "data.csv" {
          schema {
            id: string
          }
          rules {
            expect completeness(missing_col) == 100% else halt "Missing"
          }
        }
        '''
        ast = Parser(Lexer(src).tokenize()).parse()
        issues = StaticValidator().validate(ast)
        self.assertTrue(any("Unknown column 'missing_col'" in i.message for i in issues))


if __name__ == "__main__":
    unittest.main()
