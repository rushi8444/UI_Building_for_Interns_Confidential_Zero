# Beginner's Guide (ELI5)

New to Takion extensions and Windows named pipes? This explains the whole thing
from the ground up.

---

## The big picture

Takion is a trading platform that receives a firehose of market data straight
from the exchanges. We want that data in Python — for order-flow charts,
strategies, or recording to disk for backtests.

Takion is C++ and doesn't speak Python. So we build a **C++ extension DLL** that
Takion loads into itself. From inside, it can read the data directly.

### How the two programs talk: named pipes

A **named pipe** is a high-speed private tube between two programs on the same
machine.

- **Server:** the Python script creates the tube and waits.
- **Client:** the C++ DLL inside Takion connects and pushes data in.

**This is why you start Python first.** No tube, nothing to connect to.

---

## Two kinds of market data, two tubes

**Level 1** — the summary: open, high, low, last, best bid/ask, total volume.
Small and steady.

**Level 2** — every individual resting limit order: price, size, and *which
venue* it's on (NSDQ, ARCA, BATS, EDGX…). Enormous and fast.

If both shared one tube, the L2 firehose would starve L1. So there are two.

### Tube 1 — `\\.\pipe\TakionOHLCV` (Level 1)

Comes from a **custom column** we add to Takion's Market Sorter window, called
`omnitrixds`.

Why a column? Because of a quirk: before 09:30 ET, Takion sets the `Security`
object's volume to **zero** — it doesn't count pre-market prints as "official"
volume. But the Market Sorter window still *displays* the true number, because
it has to show you something. So we read the number off the row itself and get
correct pre-market volume.

Each update is packed into a 104-byte record and pushed down the tube.

> **One trap:** the timestamp in that record is *milliseconds since midnight*,
> not a normal Unix timestamp. Treat it as a clock time, not a date.

**The column also does a second job:** every basket row it draws tells us that
symbol exists, so it builds the symbol list automatically. Add a ticker to your
Market Sorter and it starts streaming within a couple of seconds. Nothing is
hardcoded.

### Tube 2 — `\\.\pipe\TakionData` (Level 2)

This is the deep order book. Each record is 32 bytes: symbol, venue, price,
size, and side (`B` = bid, `A` = ask).

After sending every level of one snapshot, we send a special marker record with
side `'C'` for **complete**. That's Python's cue: *"the book is fully sent, draw
it now."* Without it you'd render half-built books that flicker.

---

## How we get Level 2 (the interesting part)

Takion has no public "give me the whole book" function that includes the direct
ECN feeds. What it *does* have is a memory buffer it fills in order to draw the
Market Maker montage — and that buffer contains the real venue-by-venue depth.

So the DLL:

1. Attaches an **observer** to each security — a callback Takion invokes whenever
   something changes.
2. On each callback, reads that montage buffer and pulls out every
   `(venue, price, size)` row it finds.
3. **Checks the book actually belongs to that symbol** before sending it.

Step 3 matters more than it sounds. The buffer is shared, so a sweep can pick up
*another* symbol's rows. Early on, stocks trading at similar prices produced
identical books — Boeing showing RTX's orders. Now a book is only published if
its best bid/ask line up with that symbol's own quote. If not, the whole sweep is
thrown away rather than sending you wrong data.

**The thing that made it work for every symbol** was frequency. That buffer is
only filled now and then per symbol. Checking every 50 milliseconds caught it
rarely — around half the basket, and which half kept changing. Checking on
*every* update message (~900/second) catches it whenever it's populated, which
took coverage to 100 %.

---

## The Python side

`test_all.py` runs two background threads:

- One reads the L1 tube and tracks last/bid/ask/volume per symbol.
- One reads the L2 tube, collects `B`/`A` records, and publishes a book each time
  it sees a `'C'`.

It prints a live table of the whole basket. `test_all.py QQQ` also prints the
full book for one symbol.

---

## Summary

1. Python opens the tubes and waits.
2. Takion starts and loads the C++ DLL.
3. The DLL reads the Market Sorter for L1 (with correct pre-market volume) and
   the montage buffer for L2 (with real ECN depth).
4. Every book is validated against its own symbol before being sent.
5. Records are batched — thousands per write — so nothing is dropped.
6. Python reassembles the books and shows them.

If you want the actual mechanics and source code, read
[TECHNICAL_DEEP_DIVE.md](TECHNICAL_DEEP_DIVE.md). It also lists the approaches
that were tried and **measured not to work**, which is worth reading before
changing anything.
