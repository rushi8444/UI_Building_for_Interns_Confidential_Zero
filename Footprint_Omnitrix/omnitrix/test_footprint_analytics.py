import unittest
from omnitrix.engine import Bar, Aggressor, Instruments

class TestFootprintAnalytics(unittest.TestCase):
    def test_value_area_calculation(self):
        instruments = Instruments(default_tick=0.01)
        ti100 = instruments.to_index("QQQ", 100.00)
        ti101 = instruments.to_index("QQQ", 100.01)
        ti102 = instruments.to_index("QQQ", 100.02)

        bar = Bar(start_ts=1000, tf_s=60, price=100.0)
        bar.add(100.00, ti100, 100, Aggressor.BUY)
        bar.add(100.01, ti101, 800, Aggressor.BUY)  # POC
        bar.add(100.02, ti102, 100, Aggressor.SELL)

        self.assertEqual(bar.poc, ti101)
        vah, val = bar.value_area(0.70)
        self.assertIsNotNone(vah)
        self.assertIsNotNone(val)
        self.assertTrue(val <= bar.poc <= vah)

    def test_imbalances_calculation(self):
        instruments = Instruments(default_tick=0.01)
        ti100 = instruments.to_index("QQQ", 100.00)
        ti101 = instruments.to_index("QQQ", 100.01)

        bar = Bar(start_ts=1000, tf_s=60, price=100.0)
        # Sell 10 at 100.00, Buy 100 at 100.01 (100 >= 3 * 10 -> Buy imbalance at ti101)
        bar.add(100.00, ti100, 10, Aggressor.SELL)
        bar.add(100.01, ti101, 100, Aggressor.BUY)

        buy_imb, sell_imb = bar.imbalances(factor=3.0, min_vol=20)
        self.assertIn(ti101, buy_imb)

if __name__ == "__main__":
    unittest.main()
