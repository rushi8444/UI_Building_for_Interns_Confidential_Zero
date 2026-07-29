import unittest
from omnitrix.engine import Instruments, BarSeries, Trade, Aggressor

class TestTickImmutability(unittest.TestCase):
    def test_past_completed_candles_are_immutable(self):
        instruments = Instruments(default_tick=0.01)
        series = BarSeries("SPY", instruments)

        # Feed 250 trades
        # 1-100: Bar 0
        # 101-200: Bar 1
        # 201-250: Bar 2 (Active)
        for i in range(1, 251):
            tr = Trade(
                symbol="SPY",
                price=500.0 + (i % 10) * 0.1,
                size=10,
                aggressor=Aggressor.BUY if i % 2 == 0 else Aggressor.SELL,
                ts_ms=1700000000000 + i * 100
            )
            series.add_trade(tr)

        bars = series.view_ticks(100)
        self.assertEqual(len(bars), 3)

        # Snapshot bar 0 and bar 1 state
        bar0_open, bar0_high, bar0_low, bar0_close = bars[0].open, bars[0].high, bars[0].low, bars[0].close
        bar1_open, bar1_high, bar1_low, bar1_close = bars[1].open, bars[1].high, bars[1].low, bars[1].close
        bar0_volume = bars[0].volume
        bar1_volume = bars[1].volume

        # Stream another 100 live trades (fills Bar 2 to 100 ticks, starts Bar 3)
        for i in range(251, 351):
            tr = Trade(
                symbol="SPY",
                price=600.0 + (i % 5) * 0.5,
                size=50,
                aggressor=Aggressor.BUY,
                ts_ms=1700000000000 + i * 100
            )
            series.add_trade(tr)

        bars_after = series.view_ticks(100)
        self.assertEqual(len(bars_after), 4)

        # Check that historical Bar 0 and Bar 1 remain completely unchanged
        self.assertEqual(bars_after[0].open, bar0_open)
        self.assertEqual(bars_after[0].high, bar0_high)
        self.assertEqual(bars_after[0].low, bar0_low)
        self.assertEqual(bars_after[0].close, bar0_close)
        self.assertEqual(bars_after[0].volume, bar0_volume)

        self.assertEqual(bars_after[1].open, bar1_open)
        self.assertEqual(bars_after[1].high, bar1_high)
        self.assertEqual(bars_after[1].low, bar1_low)
        self.assertEqual(bars_after[1].close, bar1_close)
        self.assertEqual(bars_after[1].volume, bar1_volume)

if __name__ == "__main__":
    unittest.main()
