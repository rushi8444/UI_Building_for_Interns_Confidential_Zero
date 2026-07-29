import unittest
from omnitrix.engine import Bar
from omnitrix.engine.signals import detect_cvd_divergence

class TestCVDDivergence(unittest.TestCase):
    def test_bearish_divergence_detection(self):
        # Create 5 bars where price makes a Higher High, but CVD makes a Lower High
        bars = [
            Bar(start_ts=1000, tf_s=60, price=100.0),
            Bar(start_ts=1060, tf_s=60, price=105.0), # Swing High 1 (idx 1, high 105)
            Bar(start_ts=1120, tf_s=60, price=102.0),
            Bar(start_ts=1180, tf_s=60, price=108.0), # Swing High 2 (idx 3, high 108)
            Bar(start_ts=1240, tf_s=60, price=104.0),
        ]
        bars[0].high = 101.0; bars[0].low = 99.0
        bars[1].high = 105.0; bars[1].low = 101.0
        bars[2].high = 103.0; bars[2].low = 100.0
        bars[3].high = 108.0; bars[3].low = 103.0
        bars[4].high = 105.0; bars[4].low = 102.0

        # CVD: high at idx 1 (500), lower high at idx 3 (300)
        cvd_series = [100.0, 500.0, 400.0, 300.0, 200.0]

        divs = detect_cvd_divergence(bars, cvd_series, window=1)
        self.assertTrue(any(d["type"] == "bearish" for d in divs))
        bear_div = next(d for d in divs if d["type"] == "bearish")
        self.assertEqual(bear_div["idx1"], 1)
        self.assertEqual(bear_div["idx2"], 3)

    def test_bullish_divergence_detection(self):
        # Create 5 bars where price makes a Lower Low, but CVD makes a Higher Low
        bars = [
            Bar(start_ts=1000, tf_s=60, price=100.0),
            Bar(start_ts=1060, tf_s=60, price=95.0), # Swing Low 1 (idx 1, low 95)
            Bar(start_ts=1120, tf_s=60, price=98.0),
            Bar(start_ts=1180, tf_s=60, price=90.0), # Swing Low 2 (idx 3, low 90)
            Bar(start_ts=1240, tf_s=60, price=93.0),
        ]
        bars[0].high = 102.0; bars[0].low = 99.0
        bars[1].high = 98.0;  bars[1].low = 95.0
        bars[2].high = 100.0; bars[2].low = 97.0
        bars[3].high = 94.0;  bars[3].low = 90.0
        bars[4].high = 96.0;  bars[4].low = 92.0

        # CVD: low at idx 1 (-500), higher low at idx 3 (-200)
        cvd_series = [-100.0, -500.0, -300.0, -200.0, -100.0]

        divs = detect_cvd_divergence(bars, cvd_series, window=1)
        self.assertTrue(any(d["type"] == "bullish" for d in divs))
        bull_div = next(d for d in divs if d["type"] == "bullish")
        self.assertEqual(bull_div["idx1"], 1)
        self.assertEqual(bull_div["idx2"], 3)

if __name__ == "__main__":
    unittest.main()
