"""Quantitative Order Book Microstructure Support / Resistance Engine.

Features:
  1. Contiguous Zone Clustering: Groups adjacent ticks above threshold into Price Zones [Min, Max].
  2. Time-Persistence Anti-Spoofing: Requires liquidity to persist for >= 2.5s before displaying.
  3. Top-N Ranking: Filters strictly to Top 3 Support & Top 3 Resistance levels in view.
  4. Vectorized NumPy Operations: Fast array calculations for 30+ FPS render loops.
"""

from __future__ import annotations
from dataclasses import dataclass
import numpy as np


@dataclass(slots=True)
class Level:
    """Legacy level representation for backward compatibility."""
    ti: int
    score: float
    size: int
    held: int


@dataclass(slots=True)
class SRZone:
    """Quantitative Order Book Support/Resistance Zone."""
    side: str                 # 'bid' (support) or 'ask' (resistance)
    p_min: float              # minimum price in zone
    p_max: float              # maximum price in zone
    vwap_price: float         # volume-weighted average price of zone
    total_volume: float       # aggregated resting volume
    peak_volume: float        # peak volume at a single tick
    duration_sec: float       # continuous time persisted above threshold (seconds)
    score: float              # quantitative rank score
    p_min_ti: int             # min tick index
    p_max_ti: int             # max tick index
    peak_ti: int              # peak tick index

    @property
    def ti(self) -> int:
        """Compatibility property for legacy level callers."""
        return self.peak_ti

    @property
    def size(self) -> float:
        return self.total_volume


class MicrostructureSRTracker:
    """High-Performance Quantitative Order Book S/R Detection Engine."""

    def __init__(self, persistence_sec: float = 2.5, max_gap_ticks: int = 2, top_n: int = 3):
        self.persistence_sec = persistence_sec
        self.max_gap_ticks = max_gap_ticks
        self.top_n = top_n
        self._tick_tracker: dict[int, float] = {}   # {tick_index: elapsed_seconds}

    def reset(self) -> None:
        self._tick_tracker.clear()

    def update(self, cols: list, mid_ti: float | None, tick_size: float = 0.01):
        """Processes current book snapshot and returns (support_zones, resistance_zones, all_top_zones)."""
        if not cols or mid_ti is None:
            self.reset()
            return [], [], []

        current_col = cols[-1]
        book = current_col.book
        if not book:
            return [], [], []

        col_dt = getattr(current_col, 'dt', 1.0) or 1.0

        # 1. Compute dynamic volume threshold (1.5x mean depth floor)
        arr_vols = np.fromiter(book.values(), dtype=np.float64)
        if arr_vols.size == 0:
            return [], [], []

        mean_vol = float(np.mean(arr_vols))
        vol_threshold = max(200.0, mean_vol * 1.5)

        # 2. Time-Persistence Filter (Anti-Spoofing tracking)
        present_tis = set(book.keys())
        active_tis = {ti for ti, sz in book.items() if sz >= vol_threshold}

        # Instantly purge pulled / canceled liquidity
        stale = set(self._tick_tracker.keys()) - present_tis
        for ti in stale:
            del self._tick_tracker[ti]

        # Accumulate continuous duration for active ticks
        for ti in active_tis:
            self._tick_tracker[ti] = self._tick_tracker.get(ti, 0.0) + col_dt

        # Decay ticks dropping below threshold
        sub_threshold = set(self._tick_tracker.keys()) - active_tis
        for ti in sub_threshold:
            self._tick_tracker[ti] = max(0.0, self._tick_tracker[ti] - col_dt * 1.5)
            if self._tick_tracker[ti] <= 0:
                del self._tick_tracker[ti]

        # Filter qualifying ticks meeting persistence threshold
        qualifying = sorted([ti for ti in active_tis if self._tick_tracker.get(ti, 0.0) >= self.persistence_sec])
        if not qualifying:
            return [], [], []

        # 3. Vectorized NumPy Contiguous Zone Clustering
        tis_arr = np.array(qualifying, dtype=np.int64)
        gaps = np.where(np.diff(tis_arr) > self.max_gap_ticks)[0]
        sub_groups = np.split(tis_arr, gaps + 1)

        support_zones: list[SRZone] = []
        resistance_zones: list[SRZone] = []

        for grp in sub_groups:
            p_min_ti = int(grp[0])
            p_max_ti = int(grp[-1])
            
            grp_vols = np.array([book.get(t, 0) for t in grp], dtype=np.float64)
            grp_prices = grp * tick_size
            total_vol = float(np.sum(grp_vols))
            
            if total_vol <= 0:
                continue

            vwap_price = float(np.sum(grp_prices * grp_vols) / total_vol)
            peak_idx = int(np.argmax(grp_vols))
            peak_ti = int(grp[peak_idx])
            peak_vol = float(grp_vols[peak_idx])

            durations = [self._tick_tracker.get(t, self.persistence_sec) for t in grp]
            avg_dur = float(np.mean(durations)) if durations else self.persistence_sec

            # Quantitative score: Volume * Log Persistence * Density Peak
            score = total_vol * np.log1p(avg_dur) * (1.0 + 0.25 * (peak_vol / max(1.0, mean_vol)))
            
            side = 'bid' if p_max_ti < mid_ti else ('ask' if p_min_ti > mid_ti else 'bid')
            zone = SRZone(
                side=side,
                p_min=p_min_ti * tick_size,
                p_max=p_max_ti * tick_size,
                vwap_price=vwap_price,
                total_volume=total_vol,
                peak_volume=peak_vol,
                duration_sec=avg_dur,
                score=score,
                p_min_ti=p_min_ti,
                p_max_ti=p_max_ti,
                peak_ti=peak_ti,
            )

            if side == 'bid':
                support_zones.append(zone)
            else:
                resistance_zones.append(zone)

        # 4. Top-3 Ranking Filter
        support_zones.sort(key=lambda z: z.score, reverse=True)
        resistance_zones.sort(key=lambda z: z.score, reverse=True)

        top_sup = support_zones[:self.top_n]
        top_res = resistance_zones[:self.top_n]

        return top_sup, top_res, top_sup + top_res


# Aliases for backward compatibility
SRTracker = MicrostructureSRTracker
Zone = SRZone
