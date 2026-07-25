import re

with open("found_file.txt", "r", encoding="utf-8") as f:
    l1_lines = f.read().split('\n')

if l1_lines[0].endswith("ColumnFunctions.cpp"):
    l1_lines = l1_lines[1:]

with open("restored.cpp", "r", encoding="utf-8") as f:
    l2_code = f.read()

# Grab the L2 structs and functions
l2_structs = """
#include "ObserverApi.h"

#pragma pack(push, 1)
struct TakionL2Quote {
  char symbol[8];    
  char mmid[8];      
  double price;      
  unsigned int size; 
  char side;         
  char pad[3];       
}; 
#pragma pack(pop)

#define OMNITRIX_PIPE_NAME "\\\\\\\\.\\\\pipe\\\\TakionData"
#define OMNITRIX_LOG_PATH "C:\\\\Takion\\\\fable_debug.log"
#define L2_RING_BUFFER_SIZE 65536
#define OMNITRIX_SNAPSHOT_INTERVAL_MS 50
#define OMNITRIX_MAX_SYMBOLS 3

static const char *g_symbols[OMNITRIX_MAX_SYMBOLS] = {"NVDA", "QQQ", "AAPL"};

static TakionL2Quote g_L2Buffer[L2_RING_BUFFER_SIZE];
static int g_L2Head = 0, g_L2Tail = 0;
static CRITICAL_SECTION g_L2Cs;

static HANDLE g_hL2PipeThread = NULL;
static HANDLE g_hSubThread = NULL;

static Security *g_attachedSecurities[OMNITRIX_MAX_SYMBOLS] = {NULL, NULL, NULL};

static DWORD g_lastSnapshot = 0;
static DWORD g_lastLog = 0;
static unsigned int g_levelCount = 0;
static unsigned int g_dropped = 0;
static const bool g_verboseLevels = false; 
static FILE *g_logFp = NULL;

static void OmnitrixLog(const char *fmt, ...) {
  FILE *f = g_logFp;
  bool temp = false;
  if (!f) {
    f = _fsopen(OMNITRIX_LOG_PATH, "a", _SH_DENYNO);
    if (!f) return;
    temp = true;
  }
  va_list args;
  va_start(args, fmt);
  vfprintf(f, fmt, args);
  va_end(args);
  fputc('\\n', f);
  if (temp) fclose(f); else fflush(f);
}

DWORD WINAPI L2PipeWorkerThread(LPVOID lpParam) {
  HANDLE hPipe = INVALID_HANDLE_VALUE;

  while (!g_bShutdown) {
    if (hPipe == INVALID_HANDLE_VALUE) {
      hPipe = CreateFileA(OMNITRIX_PIPE_NAME, GENERIC_WRITE, 0, NULL, OPEN_EXISTING, 0, NULL);
      if (hPipe == INVALID_HANDLE_VALUE) {
          Sleep(100);
          continue;
      }
    }

    TakionL2Quote q;
    bool hasData = false;

    EnterCriticalSection(&g_L2Cs);
    if (g_L2Tail != g_L2Head) {
      q = g_L2Buffer[g_L2Tail];
      g_L2Tail = (g_L2Tail + 1) % L2_RING_BUFFER_SIZE;
      hasData = true;
    }
    LeaveCriticalSection(&g_L2Cs);

    if (hasData) {
      if (hPipe != INVALID_HANDLE_VALUE) {
        DWORD written = 0;
        if (!WriteFile(hPipe, &q, sizeof(TakionL2Quote), &written, NULL)) {
          CloseHandle(hPipe);
          hPipe = INVALID_HANDLE_VALUE;
        }
      }
    } else {
      Sleep(1);
    }
  }

  if (hPipe != INVALID_HANDLE_VALUE) CloseHandle(hPipe);
  return 0;
}

static void OmnitrixPush(const TakionL2Quote &q) {
  EnterCriticalSection(&g_L2Cs);
  g_L2Buffer[g_L2Head] = q;
  g_L2Head = (g_L2Head + 1) % L2_RING_BUFFER_SIZE;
  if (g_L2Head == g_L2Tail) {
    g_L2Tail = (g_L2Tail + 1) % L2_RING_BUFFER_SIZE;
    ++g_dropped;
  }
  LeaveCriticalSection(&g_L2Cs);
}

static bool OmnitrixUnpackMmid(unsigned int raw, char *out8) {
  char b[4];
  memcpy(b, &raw, 4);
  int len = 0;
  for (int i = 0; i < 4; ++i) {
    char c = b[i];
    if (c == '\\0' || c == ' ') break;
    bool ok = (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9');
    if (!ok) return false;
    ++len;
  }
  if (len < 2) return false;
  memset(out8, 0, 8);
  memcpy(out8, b, len);
  return true;
}

static void OmnitrixHeapExtractRaw(const unsigned char *secBase, const char *symbol, double nbboBid, double nbboAsk) {
  __try {
    unsigned long long ladderPtr = 0;
    memcpy(&ladderPtr, secBase + 0x1188, 8);
    if (ladderPtr < 0x0000010000000000ULL || ladderPtr > 0x00007FFFFFFFFFFFULL) {
      return; 
    }
    
    const unsigned char *L = (const unsigned char *)ladderPtr;
    const double lo = nbboBid - 5.0, hi = nbboAsk + 5.0;
    const double mid = 0.5 * (nbboBid + nbboAsk);

    struct Seen { unsigned int mmid; unsigned int pk; char side; } seen[600];
    int sn = 0;
    unsigned int pushed = 0;

    for (unsigned int off = 0x0C; off + 0x0C < 0x3000; off += 4) {
      unsigned int m = 0;
      memcpy(&m, L + off, 4);
      char mmid8[8];
      
      if (!OmnitrixUnpackMmid(m, mmid8)) continue;

      unsigned int dollars = 0, frac = 0, size = 0;
      memcpy(&dollars, L + off - 0x0C, 4);
      memcpy(&frac, L + off - 0x08, 4);
      memcpy(&size, L + off - 0x04, 4);

      if (size == 0 || size > 10000000) continue;
      if (frac >= 1000000000u) continue;
      if (dollars == 0 || dollars > 1000000) continue;

      double price = (double)dollars + (double)frac / 1000000000.0;
      if (price < lo || price > hi) continue;   // NBBO-band validation 

      char side = (price <= mid) ? 'B' : 'A';
      unsigned int pk = (unsigned int)(price * 1000.0 + 0.5);
      bool dup = false;
      for (int s = 0; s < sn; ++s) {
        if (seen[s].mmid == m && seen[s].pk == pk && seen[s].side == side) { dup = true; break; }
      }
      
      if (dup) continue;
      if (sn < 600) { seen[sn].mmid = m; seen[sn].pk = pk; seen[sn].side = side; ++sn; }

      TakionL2Quote out;
      memset(&out, 0, sizeof(out));
      memcpy(out.mmid, mmid8, 8);
      strncpy_s(out.symbol, sizeof(out.symbol), symbol, _TRUNCATE);
      out.price = price;
      out.size = size;
      out.side = side;
      
      OmnitrixPush(out);
      ++pushed;

      if (g_verboseLevels && pushed <= 60) {
        OmnitrixLog("  HEAP %-6s %c %-4s %.4f x%u", symbol, side, mmid8, price, size);
      }
    }
    g_levelCount += pushed;

  } __except (EXCEPTION_EXECUTE_HANDLER) { }
}

static void OmnitrixHeapExtract(const Security *sec, const char *symbol) {
  Price tb, ta;
  sec->CalculateL2BidPriceAndSize(tb);
  sec->CalculateL2AskPriceAndSize(ta);
  double nbboBid = tb.toDouble(), nbboAsk = ta.toDouble();
  if (nbboBid <= 0.0 || nbboAsk <= 0.0) return;
  OmnitrixHeapExtractRaw((const unsigned char *)sec, symbol, nbboBid, nbboAsk);
}

class OmnitrixObserver : public Observer {
public:
  virtual void Notify(const Message *message, const Observable *from, const Message *info = NULL) override {
    if (!message) return;
    const Security *sec = (const Security *)from;
    if (!sec) return;

    const char *symbol = sec->GetSymbol();
    if (!symbol) return;

    const DWORD now = GetTickCount();
    if (now - g_lastSnapshot < OMNITRIX_SNAPSHOT_INTERVAL_MS) return;
    g_lastSnapshot = now;

    OmnitrixHeapExtract(sec, symbol);   

    if (now - g_lastLog >= 1000) {
      g_lastLog = now;
      OmnitrixLog("[%.8s] extracted=%u, dropped=%u", symbol, g_levelCount, g_dropped);
      g_levelCount = 0;
    }
  }
};

static OmnitrixObserver g_OmnitrixObserver;

DWORD WINAPI SubscriptionWorkerThread(LPVOID lpParam) {
  bool attached[OMNITRIX_MAX_SYMBOLS] = {false, false, false};
  int remaining = OMNITRIX_MAX_SYMBOLS;
  unsigned int attempt = 0;

  OmnitrixLog("SubscriptionWorkerThread started");

  while (!g_bShutdown && remaining > 0) {
    Sleep(2000);
    ++attempt;

    for (int i = 0; i < OMNITRIX_MAX_SYMBOLS; ++i) {
      if (g_bShutdown) break;
      if (attached[i]) continue;

      TD_LockTradableStockStorageInquiryWait();
      Security *sec = TD_ObtainStock(g_symbols[i], true);
      if (sec) {
        sec->Subscribe();
        sec->AddInThreadObserver(&g_OmnitrixObserver);
      }
      TD_UnlockTradableStockStorageInquiry();

      if (sec) {
        attached[i] = true;
        g_attachedSecurities[i] = sec;
        --remaining;
        OmnitrixLog("ATTACHED %s (attempt %u) loaded=%d (in-thread + L2Calc)", g_symbols[i], attempt, sec->isDayLoaded() ? 1 : 0);
      }
    }
  }
  if (remaining == 0) OmnitrixLog("all symbols attached, depth extractor live");
  return 0;
}
"""

merged_init = """
void InitializeDataPipe() {
  if (!g_RingInitialized) {
    // L1 INIT
    InitializeCriticalSection(&g_RingCs);
    g_hPipeThread = CreateThread(NULL, 0, DataPipeWorkerThread, NULL, 0, NULL);
    
    // L2 INIT
    InitializeCriticalSection(&g_L2Cs);
    g_logFp = _fsopen(OMNITRIX_LOG_PATH, "a", _SH_DENYNO);
    g_hL2PipeThread = CreateThread(NULL, 0, L2PipeWorkerThread, NULL, 0, NULL);
    g_hSubThread = CreateThread(NULL, 0, SubscriptionWorkerThread, NULL, 0, NULL);
    
    g_RingInitialized = true;
    OmnitrixLog("=== Omnitrix Dual-Pipe extractor loaded ===");
  }
}

void TerminateDataPipe() {
  if (g_RingInitialized) {
    // L1 TERMINATE
    if (g_hPipeThread) {
      CancelSynchronousIo(g_hPipeThread);
      WaitForSingleObject(g_hPipeThread, 1000);
      CloseHandle(g_hPipeThread);
      g_hPipeThread = NULL;
    }
    DeleteCriticalSection(&g_RingCs);
    
    // L2 TERMINATE
    if (g_hL2PipeThread) {
      CancelSynchronousIo(g_hL2PipeThread);
      WaitForSingleObject(g_hL2PipeThread, 1000);
      CloseHandle(g_hL2PipeThread);
      g_hL2PipeThread = NULL;
    }
    if (g_hSubThread) {
      CancelSynchronousIo(g_hSubThread);
      WaitForSingleObject(g_hSubThread, 1000);
      CloseHandle(g_hSubThread);
      g_hSubThread = NULL;
    }
    for (int i = 0; i < OMNITRIX_MAX_SYMBOLS; ++i) {
      if (g_attachedSecurities[i]) {
        g_attachedSecurities[i]->RemoveInThreadObserver(&g_OmnitrixObserver);
        TD_ReleaseStock(g_attachedSecurities[i]);
        g_attachedSecurities[i] = NULL;
      }
    }
    DeleteCriticalSection(&g_L2Cs);
    g_RingInitialized = false;
    OmnitrixLog("=== Omnitrix Dual-Pipe extractor unloaded ===");
    if (g_logFp) { fclose(g_logFp); g_logFp = NULL; }
  }
}
"""

inject_idx = 0
for i, line in enumerate(l1_lines):
    if line.startswith("class OneMinuteCsvLoggerRowValue"):
        inject_idx = i
        break

init_idx = 0
for i, line in enumerate(l1_lines):
    if line.startswith("void InitializeDataPipe()"):
        init_idx = i
        break

new_code = "\\n".join(l1_lines[:inject_idx]) + "\\n" + l2_structs + "\\n" + "\\n".join(l1_lines[inject_idx:init_idx]) + "\\n" + merged_init + "\\n"

term_idx = 0
for i, line in enumerate(l1_lines):
    if line.startswith("bool WINAPI IsTraderIdValid"):
        term_idx = i
        break

new_code += "\\n".join(l1_lines[term_idx:])

# Now, we also need to make sure m_lastVol patch is applied!
# The found_file.txt MIGHT NOT have the `m_lastVol` patch if it wasn't the last file in `out.txt`.
# So let's apply the `m_lastVol` patch manually just in case.
new_code = new_code.replace("private:\\n    MarketSorterRow* m_row;\\n\\npublic:\\n    OneMinuteCsvLoggerRowValue(MarketSorterRow* row) : m_row(row) {}", "private:\\n    MarketSorterRow* m_row;\\n    unsigned __int64 m_lastVol;\\n\\npublic:\\n    OneMinuteCsvLoggerRowValue(MarketSorterRow* row) : m_row(row), m_lastVol((unsigned __int64)-1) {}")

patch_str = """        char newText[128];
        sprintf_s(newText, sizeof(newText), "%llu", vol);

        bool changed = (vol != m_lastVol);
        if (changed) {
            m_lastVol = vol;
            SetValue(newText);
            return true;
        }
        
        return false;
    }"""
new_code = new_code.replace("""        char newText[128];
        sprintf_s(newText, sizeof(newText), "%llu", vol);
        SetValue(newText);
        return false;
    }""", patch_str)

# Ensure no UI redraw lag from the previous versions
new_code = new_code.replace("""        // DO NOT call SetValue to prevent UI redraw lag!
        return false;
    }""", patch_str)

with open(r"C:\Users\ADMIN\Desktop\Scraper_Takion_Omnitrix\src\ColumnFunctions.cpp", "w", encoding="utf-8") as f:
    f.write(new_code)
