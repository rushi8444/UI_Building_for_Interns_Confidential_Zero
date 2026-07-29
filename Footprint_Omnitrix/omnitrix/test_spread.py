import unittest
from omnitrix.engine import Instruments, BarSeries, Trade, Aggressor
from omnitrix.engine.spread import parse_spread_symbols, is_spread_formula, evaluate_spread, SyntheticSpreadSeries

class TestSpreadCharts(unittest.TestCase):
    def test_parse_spread_symbols(self):
        self.assertEqual(parse_spread_symbols("AAPL / SPY"), ["AAPL", "SPY"])
        self.assertEqual(parse_spread_symbols("QQQ - SPY"), ["QQQ", "SPY"])
        self.assertEqual(parse_spread_symbols("(2 * AAPL) + SPY"), ["AAPL", "SPY"])

    def test_is_spread_formula(self):
        self.assertTrue(is_spread_formula("AAPL / SPY"))
        self.assertTrue(is_spread_formula("QQQ - SPY"))
        self.assertFalse(is_spread_formula("QQQ"))
        self.assertFalse(is_spread_formula("AAPL"))

    def test_evaluate_spread(self):
        prices = {"AAPL": 200.0, "SPY": 100.0}
        self.assertAlmostEqual(evaluate_spread("AAPL / SPY", prices), 2.0)
        self.assertAlmostEqual(evaluate_spread("AAPL - SPY", prices), 100.0)
        self.assertAlmostEqual(evaluate_spread("2 * AAPL", prices), 400.0)

    def test_synthetic_spread_series_generation(self):
        instruments = Instruments(default_tick=0.01)
        s_aapl = BarSeries("AAPL", instruments, base_tf_s=60)
        s_spy = BarSeries("SPY", instruments, base_tf_s=60)

        # Add trades at same timestamp
        ts = 1700000000000
        for _ in range(10):
            s_aapl.add_trade(Trade("AAPL", 200.0, 10, Aggressor.BUY, ts))
            s_spy.add_trade(Trade("SPY", 100.0, 20, Aggressor.BUY, ts))

        series_dict = {"AAPL": s_aapl, "SPY": s_spy}
        spread = SyntheticSpreadSeries("AAPL / SPY", series_dict)

        bars = spread.view(60)
        self.assertEqual(len(bars), 1)
        self.assertAlmostEqual(bars[0].open, 2.0)
        self.assertAlmostEqual(bars[0].close, 2.0)

if __name__ == "__main__":
    unittest.main()
