#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════╗
║         UNIT CONVERTER  —  Python 3 App         ║
║  Runs a local web server & opens in browser.    ║
║  No third-party packages required.              ║
║  Usage:  python unit_converter.py               ║
╚══════════════════════════════════════════════════╝

Requirements
------------
  pip install mysql-connector-python   (for history logging)

Configuration
-------------
  Edit MYSQL_CONFIG and ANTHROPIC_API_KEY below.
"""

# ── stdlib only for the server ─────────────────────────────────────────────
import http.server
import json
import math
import os
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser
from http import HTTPStatus

# ══════════════════════════════════════════════════════════════════════════════
#  USER CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

PORT = 8765   # localhost port; change if it clashes

# Runtime-populated by _load_config()
ANTHROPIC_API_KEY = ""
MYSQL_CONFIG: dict = {}

_CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".uc_config.json")

def _load_config():
    """Load saved credentials or prompt the user interactively."""
    global ANTHROPIC_API_KEY, MYSQL_CONFIG

    cfg = {}
    if os.path.exists(_CONFIG_FILE):
        try:
            with open(_CONFIG_FILE) as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}

    changed = False

    # Anthropic API key
    if not cfg.get("anthropic_api_key"):
        print()
        print("  -- Anthropic API Key ------------------------------------------")
        print("  Get yours free at: https://console.anthropic.com/")
        val = input("  Paste key (or press Enter to skip AI features): ").strip()
        cfg["anthropic_api_key"] = val
        changed = True
    ANTHROPIC_API_KEY = cfg.get("anthropic_api_key", "")

    # MySQL credentials
    db = cfg.get("mysql", {})
    if not db or cfg.get("mysql_failed"):
        print()
        print("  -- MySQL Configuration ----------------------------------------")
        print("  (Press Enter to keep the shown default)")
        host = input(f"  Host     [{db.get('host','localhost')}]: ").strip() or db.get("host","localhost")
        user = input(f"  User     [{db.get('user','root')}]: ").strip()      or db.get("user","root")
        import getpass
        pwd  = getpass.getpass("  Password (hidden input): ")
        dbn  = input(f"  Database [{db.get('database','unit_converter_db')}]: ").strip() or db.get("database","unit_converter_db")
        db   = {"host": host, "user": user, "password": pwd, "database": dbn}
        cfg["mysql"] = db
        cfg["mysql_failed"] = False
        changed = True

    MYSQL_CONFIG.update(db)

    if changed:
        try:
            with open(_CONFIG_FILE, "w") as f:
                json.dump(cfg, f, indent=2)
            print("  [Credentials saved to .uc_config.json]")
        except Exception:
            pass

def _mark_db_failed():
    """Flag that DB credentials failed so next run re-prompts."""
    try:
        if os.path.exists(_CONFIG_FILE):
            with open(_CONFIG_FILE) as f:
                cfg = json.load(f)
            cfg["mysql_failed"] = True
            with open(_CONFIG_FILE, "w") as f:
                json.dump(cfg, f, indent=2)
    except Exception:
        pass

# ══════════════════════════════════════════════════════════════════════════════
#  CONVERSION DATA
# ══════════════════════════════════════════════════════════════════════════════

CONVERSIONS = {
    "Length": {
        "icon": "📏",
        "units": {
            "Meter": 1, "Kilometer": 1000, "Centimeter": 0.01,
            "Millimeter": 0.001, "Mile": 1609.344, "Yard": 0.9144,
            "Foot": 0.3048, "Inch": 0.0254, "Nautical Mile": 1852,
            "Light Year": 9.461e15,
        },
    },
    "Weight": {
        "icon": "⚖️",
        "units": {
            "Kilogram": 1, "Gram": 0.001, "Milligram": 0.000001,
            "Pound": 0.453592, "Ounce": 0.0283495,
            "Tonne": 1000, "Stone": 6.35029,
        },
    },
    "Temperature": {
        "icon": "🌡️",
        "units": {"Celsius": None, "Fahrenheit": None, "Kelvin": None},
    },
    "Area": {
        "icon": "📐",
        "units": {
            "Square Meter": 1, "Square Kilometer": 1e6,
            "Square Centimeter": 1e-4, "Square Mile": 2_589_988.11,
            "Square Yard": 0.836127, "Square Foot": 0.092903,
            "Acre": 4046.86, "Hectare": 10_000,
        },
    },
    "Volume": {
        "icon": "🧪",
        "units": {
            "Liter": 1, "Milliliter": 0.001, "Cubic Meter": 1000,
            "Gallon (US)": 3.78541, "Quart (US)": 0.946353,
            "Pint (US)": 0.473176, "Cup (US)": 0.236588,
            "Fluid Ounce": 0.0295735, "Tablespoon": 0.0147868,
            "Teaspoon": 0.00492892,
        },
    },
    "Speed": {
        "icon": "🚀",
        "units": {
            "Meter/Second": 1, "Kilometer/Hour": 0.277778,
            "Mile/Hour": 0.44704, "Knot": 0.514444,
            "Foot/Second": 0.3048, "Mach": 343,
        },
    },
    "Time": {
        "icon": "⏱️",
        "units": {
            "Second": 1, "Millisecond": 0.001, "Minute": 60,
            "Hour": 3600, "Day": 86400, "Week": 604800,
            "Month": 2_629_800, "Year": 31_557_600,
        },
    },
    "Data": {
        "icon": "💾",
        "units": {
            "Bit": 0.125, "Byte": 1, "Kilobyte": 1024,
            "Megabyte": 1_048_576, "Gigabyte": 1_073_741_824,
            "Terabyte": 1_099_511_627_776, "Petabyte": 1_125_899_906_842_624,
        },
    },
    "Energy": {
        "icon": "⚡",
        "units": {
            "Joule": 1, "Kilojoule": 1000, "Calorie": 4.184,
            "Kilocalorie": 4184, "Watt-hour": 3600,
            "Kilowatt-hour": 3_600_000, "BTU": 1055.06, "Electronvolt": 1.602e-19,
        },
    },
    "Pressure": {
        "icon": "🔵",
        "units": {
            "Pascal": 1, "Kilopascal": 1000, "Bar": 100000,
            "PSI": 6894.76, "Atmosphere": 101325,
            "Torr": 133.322, "mmHg": 133.322,
        },
    },
}

# ══════════════════════════════════════════════════════════════════════════════
#  CONVERSION ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def _temp_convert(value, from_unit, to_unit):
    to_c = {"Celsius": lambda v: v, "Fahrenheit": lambda v: (v-32)*5/9, "Kelvin": lambda v: v-273.15}
    from_c = {"Celsius": lambda v: v, "Fahrenheit": lambda v: v*9/5+32, "Kelvin": lambda v: v+273.15}
    return from_c[to_unit](to_c[from_unit](value))

def convert(category, from_unit, to_unit, value):
    if category == "Temperature":
        return _temp_convert(value, from_unit, to_unit)
    units = CONVERSIONS[category]["units"]
    return value * units[from_unit] / units[to_unit]

def format_result(value):
    if value == 0:
        return "0"
    abs_v = abs(value)
    if abs_v >= 1e15 or (abs_v < 1e-6 and abs_v != 0):
        return f"{value:.6e}"
    if abs_v >= 1:
        decimals = max(0, 6 - len(str(int(abs_v))))
        return f"{value:,.{decimals}f}".rstrip("0").rstrip(".")
    return f"{value:.8f}".rstrip("0").rstrip(".")

# ══════════════════════════════════════════════════════════════════════════════
#  MYSQL  (optional — graceful fallback if not available)
# ══════════════════════════════════════════════════════════════════════════════

_db_ok = False

def _init_db():
    global _db_ok
    try:
        import mysql.connector
        # Also auto-create the database if it does not exist
        cfg_no_db = {k: v for k, v in MYSQL_CONFIG.items() if k != "database"}
        conn = mysql.connector.connect(**cfg_no_db)
        cur = conn.cursor()
        cur.execute(f"CREATE DATABASE IF NOT EXISTS `{MYSQL_CONFIG['database']}`")
        cur.execute(f"USE `{MYSQL_CONFIG['database']}`")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS conversion_history (
                id           INT AUTO_INCREMENT PRIMARY KEY,
                category     VARCHAR(50),
                from_unit    VARCHAR(50),
                to_unit      VARCHAR(50),
                input_value  DOUBLE,
                result_value DOUBLE,
                converted_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )""")
        conn.commit(); cur.close(); conn.close()
        _db_ok = True
        print(f"  ✔  MySQL connected  ({MYSQL_CONFIG['user']}@{MYSQL_CONFIG['host']}/{MYSQL_CONFIG['database']})")
    except Exception as e:
        print(f"  ⚠  MySQL failed: {e}")
        print("      History disabled. Re-run to enter correct credentials.")
        _mark_db_failed()

def db_save(category, from_unit, to_unit, inp, res):
    if not _db_ok: return
    try:
        import mysql.connector
        conn = mysql.connector.connect(**MYSQL_CONFIG)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO conversion_history (category,from_unit,to_unit,input_value,result_value) VALUES(%s,%s,%s,%s,%s)",
            (category, from_unit, to_unit, inp, res))
        conn.commit(); cur.close(); conn.close()
    except: pass

def db_history(limit=30):
    if not _db_ok: return []
    try:
        import mysql.connector
        conn = mysql.connector.connect(**MYSQL_CONFIG)
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT * FROM conversion_history ORDER BY converted_at DESC LIMIT %s", (limit,))
        rows = cur.fetchall(); cur.close(); conn.close()
        for r in rows:
            r["converted_at"] = str(r["converted_at"])
        return rows
    except: return []

def db_clear():
    if not _db_ok: return False
    try:
        import mysql.connector
        conn = mysql.connector.connect(**MYSQL_CONFIG)
        cur = conn.cursor()
        cur.execute("DELETE FROM conversion_history")
        conn.commit(); cur.close(); conn.close()
        return True
    except: return False

# ══════════════════════════════════════════════════════════════════════════════
#  ANTHROPIC API  — AI explanation
# ══════════════════════════════════════════════════════════════════════════════

def ai_explain(category, from_unit, to_unit, value, result):
    if not ANTHROPIC_API_KEY:
        return "No Anthropic API key set. Re-run and enter your key to enable AI insights."
    prompt = (
        f"Give a short, interesting 2-sentence explanation about converting "
        f"{value} {from_unit} to {result} {to_unit} ({category}). "
        f"Include a real-world analogy or fun fact. Be concise and engaging."
    )
    payload = json.dumps({
        "model": "claude-sonnet-4-6",
        "max_tokens": 200,
        "messages": [{"role": "user", "content": prompt}]
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            return data["content"][0]["text"]
    except Exception as e:
        return f"AI explanation unavailable: {e}"

# ══════════════════════════════════════════════════════════════════════════════
#  HTML  (single-page UI embedded as a Python string)
# ══════════════════════════════════════════════════════════════════════════════

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Unit Converter</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap');

  :root {
    --bg:       #0d0f14;
    --surface:  #161a24;
    --card:     #1d2230;
    --border:   #2a3045;
    --accent:   #5b7fff;
    --accent2:  #a78bfa;
    --green:    #34d399;
    --text:     #e2e8f0;
    --muted:    #8892a4;
    --danger:   #f87171;
    --r:        12px;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'Space Grotesk', sans-serif;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
  }

  /* ── Header ── */
  header {
    background: linear-gradient(135deg, #1a1f35 0%, #0d1220 100%);
    border-bottom: 1px solid var(--border);
    padding: 18px 32px;
    display: flex;
    align-items: center;
    gap: 16px;
  }
  header .logo {
    font-size: 1.5rem;
    font-weight: 700;
    background: linear-gradient(120deg, var(--accent), var(--accent2));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    letter-spacing: -0.5px;
  }
  header .tagline {
    font-size: 0.78rem;
    color: var(--muted);
    font-family: 'JetBrains Mono', monospace;
  }
  header .db-badge {
    margin-left: auto;
    font-size: 0.7rem;
    font-family: 'JetBrains Mono', monospace;
    padding: 4px 10px;
    border-radius: 20px;
    border: 1px solid var(--border);
    color: var(--muted);
  }
  header .db-badge.ok { color: var(--green); border-color: var(--green); }

  /* ── Layout ── */
  main {
    flex: 1;
    display: grid;
    grid-template-columns: 260px 1fr;
    gap: 0;
    max-width: 1100px;
    margin: 0 auto;
    width: 100%;
    padding: 28px 20px;
    gap: 24px;
  }

  /* ── Category sidebar ── */
  .sidebar {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .sidebar-title {
    font-size: 0.7rem;
    font-family: 'JetBrains Mono', monospace;
    color: var(--muted);
    letter-spacing: 0.1em;
    text-transform: uppercase;
    margin-bottom: 6px;
  }
  .cat-btn {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 14px;
    border-radius: var(--r);
    border: 1px solid transparent;
    background: transparent;
    color: var(--muted);
    cursor: pointer;
    font-family: 'Space Grotesk', sans-serif;
    font-size: 0.88rem;
    font-weight: 500;
    transition: all 0.15s;
    text-align: left;
    width: 100%;
  }
  .cat-btn:hover { background: var(--card); color: var(--text); }
  .cat-btn.active {
    background: linear-gradient(135deg, #1e2a4a, #1a2038);
    border-color: var(--accent);
    color: var(--accent);
  }
  .cat-btn .icon { font-size: 1.1rem; width: 22px; text-align: center; }

  /* ── Right panel ── */
  .panel { display: flex; flex-direction: column; gap: 20px; }

  .card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: var(--r);
    padding: 24px;
  }

  /* ── Converter form ── */
  .converter-grid {
    display: grid;
    grid-template-columns: 1fr auto 1fr;
    gap: 12px;
    align-items: end;
    margin-bottom: 20px;
  }
  .field label {
    display: block;
    font-size: 0.72rem;
    font-family: 'JetBrains Mono', monospace;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 6px;
  }
  .field input, .field select {
    width: 100%;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--text);
    font-family: 'JetBrains Mono', monospace;
    font-size: 1rem;
    padding: 10px 14px;
    outline: none;
    transition: border-color 0.15s;
  }
  .field input:focus, .field select:focus { border-color: var(--accent); }
  .field select option { background: var(--surface); }

  .swap-btn {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--muted);
    cursor: pointer;
    font-size: 1.2rem;
    padding: 10px 14px;
    transition: all 0.15s;
    margin-bottom: 0;
    align-self: end;
  }
  .swap-btn:hover { background: var(--card); color: var(--accent); border-color: var(--accent); }

  .convert-btn {
    width: 100%;
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    border: none;
    border-radius: 8px;
    color: #fff;
    cursor: pointer;
    font-family: 'Space Grotesk', sans-serif;
    font-size: 1rem;
    font-weight: 600;
    padding: 12px;
    transition: opacity 0.15s;
    letter-spacing: 0.02em;
  }
  .convert-btn:hover { opacity: 0.88; }
  .convert-btn:active { opacity: 0.75; }

  /* ── Result box ── */
  .result-box {
    display: none;
    background: linear-gradient(135deg, #151c30, #0f1520);
    border: 1px solid var(--accent);
    border-radius: var(--r);
    padding: 20px 24px;
  }
  .result-box.visible { display: block; }
  .result-label { font-size: 0.7rem; font-family: 'JetBrains Mono', monospace; color: var(--muted); text-transform: uppercase; letter-spacing: 0.1em; }
  .result-value {
    font-family: 'JetBrains Mono', monospace;
    font-size: 2rem;
    font-weight: 600;
    color: var(--green);
    margin: 4px 0 2px;
    word-break: break-all;
  }
  .result-eq { font-size: 0.85rem; color: var(--muted); }

  /* ── AI explanation ── */
  .ai-box {
    display: none;
    margin-top: 14px;
    padding: 14px 16px;
    background: #131825;
    border-left: 3px solid var(--accent2);
    border-radius: 0 8px 8px 0;
    font-size: 0.87rem;
    color: var(--text);
    line-height: 1.6;
  }
  .ai-box.visible { display: block; }
  .ai-label { font-size: 0.68rem; font-family: 'JetBrains Mono', monospace; color: var(--accent2); text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 6px; }
  .ai-spinner { display: inline-block; width: 12px; height: 12px; border: 2px solid var(--border); border-top-color: var(--accent2); border-radius: 50%; animation: spin 0.7s linear infinite; vertical-align: middle; margin-right: 6px; }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* ── History ── */
  .history-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 14px;
  }
  .history-header h3 { font-size: 0.9rem; font-weight: 600; }
  .clear-btn {
    font-size: 0.72rem;
    font-family: 'JetBrains Mono', monospace;
    background: transparent;
    border: 1px solid var(--border);
    border-radius: 6px;
    color: var(--danger);
    cursor: pointer;
    padding: 4px 10px;
    transition: all 0.15s;
  }
  .clear-btn:hover { background: #2a1515; border-color: var(--danger); }

  .history-empty { font-size: 0.83rem; color: var(--muted); font-family: 'JetBrains Mono', monospace; text-align: center; padding: 18px 0; }

  table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
  th { text-align: left; font-family: 'JetBrains Mono', monospace; font-size: 0.67rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.08em; padding: 0 10px 10px; border-bottom: 1px solid var(--border); }
  td { padding: 9px 10px; border-bottom: 1px solid #1e2535; color: var(--text); }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: #1a2030; }
  .badge {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.68rem;
    padding: 2px 7px;
    border-radius: 4px;
    background: #1e2a4a;
    color: var(--accent);
  }
  .num { font-family: 'JetBrains Mono', monospace; color: var(--green); }
  .ts { color: var(--muted); font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; }

  .no-mysql-note {
    font-size: 0.75rem;
    font-family: 'JetBrains Mono', monospace;
    color: var(--muted);
    background: #13171f;
    border: 1px dashed var(--border);
    border-radius: 8px;
    padding: 12px 16px;
    text-align: center;
  }

  @media (max-width: 700px) {
    main { grid-template-columns: 1fr; }
    .converter-grid { grid-template-columns: 1fr; }
    .swap-btn { width: 100%; }
  }
</style>
</head>
<body>

<header>
  <div>
    <div class="logo">⟨ UnitConv /⟩</div>
    <div class="tagline">python3 · localhost · anthropic api</div>
  </div>
  <div class="db-badge" id="dbBadge">● MySQL</div>
</header>

<main>
  <!-- Sidebar -->
  <aside class="sidebar">
    <div class="sidebar-title">Categories</div>
    <div id="catList"></div>
  </aside>

  <!-- Main panel -->
  <section class="panel">

    <!-- Converter card -->
    <div class="card">
      <div class="converter-grid">
        <div class="field">
          <label>Value</label>
          <input id="inputVal" type="number" placeholder="Enter value" value="1">
        </div>
        <div>
          <label style="display:block;font-size:0.72rem;color:transparent;margin-bottom:6px;">·</label>
          <button class="swap-btn" onclick="swapUnits()" title="Swap units">⇌</button>
        </div>
        <div class="field">
          <label>From</label>
          <select id="fromUnit"></select>
        </div>
      </div>
      <div class="field" style="margin-bottom:16px;">
        <label>To</label>
        <select id="toUnit"></select>
      </div>
      <button class="convert-btn" onclick="doConvert()">Convert →</button>

      <!-- Result -->
      <div class="result-box" id="resultBox">
        <div class="result-label">Result</div>
        <div class="result-value" id="resultVal">—</div>
        <div class="result-eq" id="resultEq"></div>
        <!-- AI -->
        <div class="ai-box" id="aiBox">
          <div class="ai-label">✦ AI Insight</div>
          <div id="aiText"></div>
        </div>
      </div>
    </div>

    <!-- History card -->
    <div class="card" id="historyCard">
      <div class="history-header">
        <h3>Conversion History</h3>
        <button class="clear-btn" onclick="clearHistory()">Clear all</button>
      </div>
      <div id="historyBody"></div>
    </div>

  </section>
</main>

<script>
const CATS = __CATEGORIES__;
let currentCat = Object.keys(CATS)[0];

// ── Build sidebar ─────────────────────────────────────────────────────────
function buildSidebar() {
  const list = document.getElementById('catList');
  list.innerHTML = '';
  Object.entries(CATS).forEach(([name, info]) => {
    const btn = document.createElement('button');
    btn.className = 'cat-btn' + (name === currentCat ? ' active' : '');
    btn.innerHTML = `<span class="icon">${info.icon}</span>${name}`;
    btn.onclick = () => selectCategory(name);
    list.appendChild(btn);
  });
}

function selectCategory(name) {
  currentCat = name;
  buildSidebar();
  const units = CATS[name].units;
  populateSelect('fromUnit', units, 0);
  populateSelect('toUnit', units, 1);
  document.getElementById('resultBox').classList.remove('visible');
}

function populateSelect(id, units, defaultIdx) {
  const sel = document.getElementById(id);
  const prev = sel.value;
  sel.innerHTML = units.map(u => `<option value="${u}">${u}</option>`).join('');
  if (units.includes(prev)) sel.value = prev;
  else sel.selectedIndex = defaultIdx;
}

function swapUnits() {
  const f = document.getElementById('fromUnit');
  const t = document.getElementById('toUnit');
  [f.value, t.value] = [t.value, f.value];
}

// ── Convert ───────────────────────────────────────────────────────────────
async function doConvert() {
  const value = parseFloat(document.getElementById('inputVal').value);
  const from  = document.getElementById('fromUnit').value;
  const to    = document.getElementById('toUnit').value;
  if (isNaN(value)) { alert('Enter a valid number.'); return; }

  const res = await fetch('/api/convert', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ category: currentCat, from_unit: from, to_unit: to, value })
  });
  const data = await res.json();
  if (data.error) { alert(data.error); return; }

  document.getElementById('resultVal').textContent = `${data.result} ${to}`;
  document.getElementById('resultEq').textContent  = `${value} ${from} = ${data.result} ${to}`;
  document.getElementById('resultBox').classList.add('visible');

  // AI explanation async
  const aiBox  = document.getElementById('aiBox');
  const aiText = document.getElementById('aiText');
  aiBox.classList.add('visible');
  aiText.innerHTML = '<span class="ai-spinner"></span> Generating insight…';

  fetch('/api/explain', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ category: currentCat, from_unit: from, to_unit: to, value, result: data.result })
  })
  .then(r => r.json())
  .then(d => { aiText.textContent = d.explanation; })
  .catch(() => { aiText.textContent = 'AI explanation unavailable.'; });

  loadHistory();
}

// ── History ───────────────────────────────────────────────────────────────
async function loadHistory() {
  const body = document.getElementById('historyBody');
  const res  = await fetch('/api/history');
  const data = await res.json();

  if (!data.db_ok) {
    body.innerHTML = `<div class="no-mysql-note">MySQL not connected. Configure MYSQL_CONFIG in unit_converter.py to enable history logging.</div>`;
    return;
  }
  if (!data.rows.length) {
    body.innerHTML = `<div class="history-empty">No conversions yet.</div>`;
    return;
  }

  body.innerHTML = `
    <table>
      <thead><tr>
        <th>Category</th><th>From</th><th>To</th>
        <th>Input</th><th>Result</th><th>When</th>
      </tr></thead>
      <tbody>
        ${data.rows.map(r => `
          <tr>
            <td><span class="badge">${r.category}</span></td>
            <td>${r.from_unit}</td>
            <td>${r.to_unit}</td>
            <td class="num">${r.input_value}</td>
            <td class="num">${r.result_value}</td>
            <td class="ts">${r.converted_at.slice(0,19)}</td>
          </tr>`).join('')}
      </tbody>
    </table>`;
}

async function clearHistory() {
  if (!confirm('Delete all conversion history?')) return;
  await fetch('/api/history/clear', { method: 'POST' });
  loadHistory();
}

// ── DB badge ──────────────────────────────────────────────────────────────
async function checkDb() {
  const res = await fetch('/api/status');
  const d   = await res.json();
  const badge = document.getElementById('dbBadge');
  if (d.db_ok) { badge.textContent = '● MySQL'; badge.classList.add('ok'); }
}

// ── Init ──────────────────────────────────────────────────────────────────
buildSidebar();
selectCategory(currentCat);
checkDb();
loadHistory();

document.getElementById('inputVal').addEventListener('keydown', e => {
  if (e.key === 'Enter') doConvert();
});
</script>
</body>
</html>
"""

# ══════════════════════════════════════════════════════════════════════════════
#  HTTP REQUEST HANDLER
# ══════════════════════════════════════════════════════════════════════════════

class Handler(http.server.BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass   # silence default access log

    # ── helpers ──────────────────────────────────────────────────────────────
    def _send_json(self, data, status=200):
        body = json.dumps(data, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length)) if length else {}

    # ── GET ───────────────────────────────────────────────────────────────────
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            cats = {k: {"icon": v["icon"], "units": list(v["units"].keys())}
                    for k, v in CONVERSIONS.items()}
            page = HTML.replace("__CATEGORIES__", json.dumps(cats))
            body = page.encode()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", len(body))
            self.end_headers()
            self.wfile.write(body)

        elif self.path == "/api/history":
            rows = db_history()
            self._send_json({"db_ok": _db_ok, "rows": rows})

        elif self.path == "/api/status":
            self._send_json({"db_ok": _db_ok})

        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    # ── POST ──────────────────────────────────────────────────────────────────
    def do_POST(self):
        data = self._body()

        if self.path == "/api/convert":
            try:
                cat  = data["category"]
                frm  = data["from_unit"]
                to   = data["to_unit"]
                val  = float(data["value"])
                res  = convert(cat, frm, to, val)
                fmt  = format_result(res)
                db_save(cat, frm, to, val, res)
                self._send_json({"result": fmt})
            except Exception as e:
                self._send_json({"error": str(e)}, 400)

        elif self.path == "/api/explain":
            try:
                explanation = ai_explain(
                    data["category"], data["from_unit"], data["to_unit"],
                    data["value"], data["result"]
                )
                self._send_json({"explanation": explanation})
            except Exception as e:
                self._send_json({"explanation": f"Error: {e}"})

        elif self.path == "/api/history/clear":
            ok = db_clear()
            self._send_json({"ok": ok})

        else:
            self.send_error(HTTPStatus.NOT_FOUND)

# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print()
    print("╔══════════════════════════════════════════════════╗")
    print("║         UNIT CONVERTER  —  Python 3 App         ║")
    print("║  Runs a local web server & opens in browser.    ║")
    print("║  No third-party packages required.              ║")
    print("║  Usage:  python unit_converter.py               ║")
    print("╚══════════════════════════════════════════════════╝")
    _load_config()
    print()
    print("  Initialising…")

    _init_db()

    url = f"http://localhost:{PORT}"
    server = http.server.ThreadingHTTPServer(("", PORT), Handler)

    print(f"  ✔  Server running at {url}")
    print(f"  ✔  Opening browser…")
    print()
    print("  Press Ctrl+C to stop.\n")

    threading.Timer(0.6, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\n  Server stopped. Goodbye!\n")
        server.shutdown()

if __name__ == "__main__":
    main()
