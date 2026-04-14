# ============================================================
# CFOS-XG PRO 75 TITAN - VERSION 7-3
# FIXED PRODUCTION VERSION (LUCKY-7-82-fixed.py)
# ZAČETEK DELA 1 / 8
# OSNOVA SISTEMA
# ============================================================
#
# ============================================================
# SYSTEM DOCUMENTATION
# ============================================================
# CFOS-XG PRO 75 TITAN is an advanced live football analytics
# and betting decision engine. It processes real-time match
# statistics to produce probabilistic bet recommendations.
#
# ARCHITECTURE (8 MAJOR PARTS):
#   PART 1 (Lines 1-317)       OSNOVA     - Setup, colors, helpers
#   PART 2 (Lines 319-1581)    ENGINE     - Poisson / Tempo / Market
#   PART 3 (Lines 1585-1839)   LEARNING   - Historical data engine
#   PART 4 (Lines 1843-1987)   SNAPSHOT   - Data collection system
#   PART 5 (Lines 1997-2350)   MEMORY     - Match memory / timeline / attack wave
#   PART 6 (Lines 2359-2519)   HISTORY    - History score / exact score
#   PART 7 (Lines 2527-7299)   MODEL      - Core calculation engine
#   PART 8 (Lines 7300-7549)   OUTPUT     - Izpis / analiza / main
#
# KEY FUNCTIONS:
#   izracunaj_model(data)         - Computes all match metrics from CSV row
#   predict_next_goal_smart(...)  - 9-signal weighted consensus predictor
#   bet_decision(r)               - Master bet decision engine
#   print_live_match_memory(r)    - Prints timeline / attack wave section
#
# CSV INPUT FORMAT (comma-separated, 32+ columns):
#   Col 0:  home team name
#   Col 1:  away team name
#   Col 2:  odds_home   (e.g. 2.10)
#   Col 3:  odds_draw   (e.g. 3.30)
#   Col 4:  odds_away   (e.g. 3.50)
#   Col 5:  minute      (e.g. 68)
#   Col 6:  score_home  (e.g. 1)
#   Col 7:  score_away  (e.g. 0)
#   Col 8:  xg_home     (e.g. 0.80)
#   Col 9:  xg_away     (e.g. 0.50)
#   Col 10: shots_home
#   Col 11: shots_away
#   Col 12: sot_home    (shots on target)
#   Col 13: sot_away
#   Col 14: attacks_home
#   Col 15: attacks_away
#   Col 16: danger_home
#   Col 17: danger_away
#   Col 18: big_chances_home
#   Col 19: big_chances_away
#   Col 20: yellow_home
#   Col 21: yellow_away
#   Col 22: red_home
#   Col 23: red_away
#   Col 24: possession_home (%)
#   Col 25: possession_away (%)
#   Col 26: blocked_home
#   Col 27: blocked_away
#   Col 28: bcm_home    (big chances missed)
#   Col 29: bcm_away
#   Col 30: corners_home
#   Col 31: corners_away
#
# EXAMPLE INPUT:
#   "Arsenal,Chelsea,2.10,3.30,3.80,68,1,0,0.80,0.50,6,4,3,2,22,18,8,5,2,1,1,0,0,0,58,42,1,2,0,1,5,3"
#
# EXAMPLE OUTPUT:
#   =============== BET DECISION ===============
#   MINUTE: 68
#   BET: NEXT GOAL HOME
#   CONFIDENCE: HIGH
#   VALID: 68-73
#   ============================================
#
# BET DECISION PHASES:
#   Phase 1 (<45 min)   : Always NO BET (insufficient data)
#   Phase 2 (45-55 min) : Wait for signal activation
#   Phase 3 (55-75 min) : NEXT GOAL SMART top priority (conf >= 0.72)
#   Phase 4 (70+ min)   : MASTER FREEZE FILTER blocks fake signals
#   Phase 5 (any)       : UNIVERSAL SCORING - 7 bet types scored, winner picked
#
# BET TYPES:
#   NEXT GOAL HOME  - Home team scores next
#   NEXT GOAL AWAY  - Away team scores next
#   COMEBACK HOME   - Home team equalises / overtakes
#   COMEBACK AWAY   - Away team equalises / overtakes
#   DRAW            - Score stays level
#   NO GOAL         - No more goals in match
#   NO BET          - Insufficient edge, wait
#
# CONFIDENCE LEVELS:
#   HIGH   - top_score >= 7.5 AND gap >= 1.0
#   MEDIUM - top_score >= 5.5 AND gap >= 0.5
#   LOW    - all other cases
# ============================================================

import math
import random
import os
import time
import csv
from io import StringIO

# ------------------------------------------------------------
# NASTAVITVE
# ------------------------------------------------------------
SIM_BASE = 40000
SIM_HIGH = 90000
SIM_EXTREME = 140000

SIM_EXACT_BASE = 25000
SIM_EXACT_HIGH = 60000

LEARN_FILE = "cfos75_learn_log.csv"
SNAP_FILE = "cfos75_snapshots_pending.csv"
MATCH_MEM_FILE = "cfos75_match_memory.csv"
MATCH_RESULT_FILE = "cfos75_match_results.csv"


# ------------------------------------------------------------
# ANSI / BARVE
# ------------------------------------------------------------
def init_ansi():
    if os.name == "nt":
        try:
            os.system("")  # 🔥 KLJUČNO za Windows CMD
            return True
        except:
            return False
    return True


ANSI_ON = init_ansi()

BOLD = "\033[1m" if ANSI_ON else ""
RESET = "\033[0m" if ANSI_ON else ""

RED = "\033[91m" if ANSI_ON else ""
GREEN = "\033[92m" if ANSI_ON else ""
YELLOW = "\033[93m" if ANSI_ON else ""
BLUE = "\033[94m" if ANSI_ON else ""
MAGENTA = "\033[95m" if ANSI_ON else ""
CYAN = "\033[96m" if ANSI_ON else ""
WHITE = "\033[97m" if ANSI_ON else ""
ORANGE = "\033[33m" if ANSI_ON else ""

# =========================
# CUSTOM SEKCIJSKE BARVE
# =========================
COL_XG = GREEN
COL_PM = YELLOW
COL_LAMBDA = CYAN
COL_MC = MAGENTA

COL_TEMPO = YELLOW
COL_NEXT = GREEN
COL_MOM = YELLOW
COL_PRESS = YELLOW


def btxt(text, color="", bold=False):
    if not ANSI_ON:
        return str(text)
    return f"{BOLD if bold else ''}{color}{text}{RESET}"


def cl(label, value, color="", bold=False):
    if not ANSI_ON:
        return f"{label.ljust(28)} {value}"
    return f"{btxt(label.ljust(28), color, bold)} {btxt(str(value), color, bold)}"


# ------------------------------------------------------------
# POMOŽNE FUNKCIJE
# ------------------------------------------------------------
def pct(x):
    return round(x * 100, 2)


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def safe_float(x, default=0.0):
    try:
        return float(str(x).replace(",", "."))
    except:
        return default


def safe_int(x, default=0):
    try:
        sx = str(x).strip()
        if ":" in sx:
            sx = sx.split(":", 1)[0].strip()
        return int(float(sx.replace(",", ".")))
    except:
        return default


def safe_div(a, b, default=0.0):
    if b == 0:
        return default
    return a / b


def get_idx(data, i, default="0"):
    return data[i] if i < len(data) else default


def get_num(data, i, default=0.0):
    return safe_float(get_idx(data, i, str(default)), default)


def parse_csv_line(line):
    try:
        reader = csv.reader(StringIO(line))
        row = next(reader)
        return [x.strip() for x in row]
    except:
        return [x.strip() for x in line.split(",")]


def safe_input(prompt=""):
    try:
        return input(prompt)
    except EOFError:
        return ""


def normalize_csv_row(row, min_len=90):
    """
    Normalizira CSV vrstico za CFOS PRO 75.
    - ohrani fiksni vrstni red osnovnih polj
    - minute je vedno index 5
    - manjkajoča polja dopolni z "0"
    """
    if row is None:
        row = []
    row = [str(x).strip() for x in list(row)]
    if len(row) < min_len:
        row.extend(["0"] * (min_len - len(row)))
    return row


def file_has_data(path):
    return os.path.exists(path) and os.path.getsize(path) > 0


def fmt2(x):
    return round(float(x), 2)


def fmt3(x):
    return round(float(x), 3)


def fmt4(x):
    return round(float(x), 4)


def blend(base, factor, weight=0.35):
    return base * (1 + (factor - 1.0) * weight)


# ------------------------------------------------------------
# BARVNA LOGIKA
# ------------------------------------------------------------
def color_prob(p):
    if p >= 0.65:
        return GREEN
    if p >= 0.45:
        return YELLOW
    return RED


def color_edge(edge):
    if edge >= 0.05:
        return GREEN
    if edge <= -0.05:
        return RED
    return YELLOW


def color_conf(conf):
    if conf >= 70:
        return GREEN
    if conf >= 45:
        return YELLOW
    return RED


def confidence_band(conf):
    if conf >= 70:
        return "VISOKA"
    if conf >= 45:
        return "SREDNJA"
    return "NIZKA"


def normalize_outcome_label(value):
    v = str(value or "").strip().upper()

    if v in ("HOME", "H", "1", "DOMAČI", "DOMACI"):
        return "HOME"
    if v in ("AWAY", "A", "2", "GOST"):
        return "AWAY"
    if v in ("DRAW", "D", "X", "REMI"):
        return "DRAW"

    return v


# ------------------------------------------------------------
# BUCKETI
# ------------------------------------------------------------
def bucket_minute(m):
    if m < 30:
        return "0-29"
    if m < 60:
        return "30-59"
    if m < 76:
        return "60-75"
    return "76-90"


def bucket_xg(x):
    if x < 0.7:
        return "low"
    if x < 1.4:
        return "mid"
    return "high"


def bucket_sot(s):
    if s <= 3:
        return "low"
    return "high"


def bucket_shots(s):
    if s <= 7:
        return "low"
    if s <= 13:
        return "mid"
    return "high"


def bucket_score_diff(sd):
    if sd <= -2:
        return "-2-"
    if sd == -1:
        return "-1"
    if sd == 0:
        return "0"
    if sd == 1:
        return "+1"
    return "+2+"


def bucket_danger(d):
    if d < 45:
        return "low"
    if d < 90:
        return "mid"
    return "high"


# ------------------------------------------------------------
# PREVODI / METRIKE
# ------------------------------------------------------------
def game_type_slo(gt):
    mapping = {
        "DEAD": "MRTVA IGRA",
        "SLOW": "POČASNA IGRA",
        "BALANCED": "URAVNOTEŽENA IGRA",
        "PRESSURE": "PRITISK",
        "ATTACK_WAVE": "NAPADNI VAL",
        "CHAOS": "KAOS"
    }
    return mapping.get(gt, gt)


def pass_acc_rate(accurate, passes):
    return safe_div(accurate, passes, 0.0)


def danger_to_shot_conv(shots, danger):
    return safe_div(shots, danger, 0.0)


def shot_quality(xg, shots):
    return safe_div(xg, shots, 0.0)


def sot_ratio(sot, shots):
    return safe_div(sot, shots, 0.0)


def big_chance_ratio(big_chances, shots):
    return safe_div(big_chances, shots, 0.0)


# ============================================================
# KONEC DELA 1 / 8
# ============================================================
# ============================================================
# CFOS-XG PRO 75 TITAN
# ZAČETEK DELA 2 / 8
# POISSON / TEMPO / MARKET HELPERJI
# ============================================================

def poisson_sample(lam):
    if lam <= 0:
        return 0
    L = math.exp(-lam)
    k = 0
    p = 1.0
    while p > L and k < 12:
        k += 1
        p *= random.random()
    return k - 1


def poisson_pmf(k, lam):
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    try:
        return math.exp(-lam) * (lam ** k) / math.factorial(k)
    except:
        return 0.0


def bivariate_poisson_sample(lam_h, lam_a, lam_c):
    shared = poisson_sample(clamp(lam_c, 0, 0.08))
    gh = poisson_sample(max(0.0, lam_h))
    ga = poisson_sample(max(0.0, lam_a))
    return gh + shared, ga + shared


def classify_game_type(minute, xg_total, shots_total, sot_total, danger_total, tempo_shots, xg_rate):
    if (
            shots_total <= 4 and
            xg_total <= 0.35 and
            danger_total <= 12 and
            tempo_shots < 0.18 and
            xg_rate < 0.015
    ):
        return "DEAD"

    if shots_total <= 9 and xg_total <= 0.90 and tempo_shots < 0.16:
        return "SLOW"

    if shots_total >= 14 and sot_total >= 6 and danger_total >= 90:
        return "ATTACK_WAVE"

    if shots_total >= 10 and danger_total >= 70 and xg_rate >= 0.020:
        return "PRESSURE"

    if (xg_total >= 2.10) or (shots_total >= 18 and sot_total >= 7 and danger_total >= 60):
        return "CHAOS"

    return "BALANCED"


def game_type_goal_multiplier(game_type):
    if game_type == "DEAD":
        return 0.78
    if game_type == "SLOW":
        return 0.90
    if game_type == "PRESSURE":
        return 1.05
    if game_type == "ATTACK_WAVE":
        return 1.11
    if game_type == "CHAOS":
        return 1.10
    return 1.00


def estimate_effective_end_minute(minute):
    if minute >= 90:
        return 97
    return 95


def estimate_minutes_left(minute):
    return max(1, estimate_effective_end_minute(minute) - minute)


def time_left_fraction(minute):
    ml = estimate_minutes_left(minute)
    return max(0.01, ml / 90.0), ml


def tempo_goal_multiplier(tempo_shots, tempo_danger, tempo_att, minute):
    notes = []
    mult = 1.0

    if tempo_shots >= 0.22:
        mult *= 1.04
        notes.append("TEMPO shots_high")
    if tempo_shots >= 0.30:
        mult *= 1.03

    if tempo_danger >= 1.10:
        mult *= 1.04
        notes.append("TEMPO danger_high")

    if tempo_att >= 2.20:
        mult *= 1.02
        notes.append("TEMPO attacks_high")

    if tempo_shots < 0.12 and tempo_danger < 0.75 and minute >= 55:
        mult *= 0.90
        notes.append("TEMPO low")

    return clamp(mult, 0.84, 1.14), notes


def xgr_goal_multiplier(xg_rate_total, minute):
    notes = []
    mult = 1.0

    if xg_rate_total >= 0.020:
        mult *= 1.05
        notes.append("XGR hot")
    if xg_rate_total >= 0.030:
        mult *= 1.03
    if 0 < xg_rate_total < 0.010 and minute >= 50:
        mult *= 0.91
        notes.append("XGR low")

    return clamp(mult, 0.86, 1.12), notes


def implied_probs_from_odds(odds_home, odds_draw, odds_away):
    if odds_home <= 0 or odds_draw <= 0 or odds_away <= 0:
        return 0.0, 0.0, 0.0, 0.0

    raw_h = 1 / odds_home
    raw_x = 1 / odds_draw
    raw_a = 1 / odds_away

    s = raw_h + raw_x + raw_a
    if s <= 0:
        return 0.0, 0.0, 0.0, 0.0

    return raw_h / s, raw_x / s, raw_a / s, s - 1.0


def edge_from_model(model_p, market_p):
    return model_p - market_p


def adaptive_simulations(pre_h, pre_x, pre_a):
    best = max(pre_h, pre_x, pre_a)

    if best < 0.42:
        return SIM_EXTREME
    if best < 0.55:
        return SIM_HIGH
    return SIM_BASE


def adaptive_exact_simulations(best_1x2):
    if best_1x2 < 0.45:
        return SIM_EXACT_HIGH
    return SIM_EXACT_BASE


def next_goal_signal(p_home_next, p_away_next):
    if p_home_next >= 0.45 and p_home_next > p_away_next:
        return "NASLEDNJI GOL -> DOMAČI PRITISK"
    if p_away_next >= 0.45 and p_away_next > p_home_next:
        return "NASLEDNJI GOL -> GOSTUJOČI PRITISK"
    return "NASLEDNJI GOL -> URAVNOTEŽENO / NEGOTOVO"


def match_signal(p_goal, p_home_next, p_away_next):
    if p_goal < 0.25:
        return "NIZEK GOL | NASLEDNJI GOL URAVNOTEŽENO"
    if p_goal >= 0.55:
        return "VISOK GOL | ODPRTA TEKMA"
    if p_home_next > p_away_next and p_home_next >= 0.35:
        return "SREDNJI GOL | NASLEDNJI GOL DOMA"
    if p_away_next > p_home_next and p_away_next >= 0.35:
        return "SREDNJI GOL | NASLEDNJI GOL GOST"
    return "SREDNJI GOL | NASLEDNJI GOL URAVNOTEŽENO"


# ============================================================
# NEXT GOAL BET ENGINE
# ============================================================
def next_goal_bet_engine(p_home_next, p_away_next, lam_h, lam_a, momentum, tempo_shots, tempo_danger, game_type):
    home_ng = float(p_home_next or 0.0)
    away_ng = float(p_away_next or 0.0)
    lam_h = float(lam_h or 0.0)
    lam_a = float(lam_a or 0.0)
    lam_diff = lam_h - lam_a
    momentum = float(momentum or 0.0)
    tempo_high = float(tempo_shots or 0.0) > 0.18 or float(tempo_danger or 0.0) > 1.2
    game_type = str(game_type or "")

    # ------------------------------------------------------------
    # ALWAYS PREDICTION
    # ------------------------------------------------------------
    if home_ng > away_ng:
        next_goal_prediction = "HOME"
    else:
        next_goal_prediction = "AWAY"

    # ------------------------------------------------------------
    # BET ENGINE
    # ------------------------------------------------------------
    next_goal_bet = "NO BET"
    next_goal_reason = "LOW EDGE"

    # Edge filter: skip bet when margin is too small
    if abs(home_ng - away_ng) < 0.08:
        return next_goal_prediction, "NO BET", "EDGE TOO SMALL"

    if home_ng > 0.57 and lam_diff > 0.35 and momentum > 0.18:
        next_goal_bet = "HOME"
        next_goal_reason = "STRONG HOME PRESSURE"
    elif home_ng > 0.52 and lam_diff > 0.20 and momentum > 0.10:
        next_goal_bet = "HOME"
        next_goal_reason = "HOME MOMENTUM + LAMBDA"
    elif away_ng > 0.42 and momentum < -0.12:
        next_goal_bet = "AWAY"
        next_goal_reason = "AWAY MOMENTUM"
    elif away_ng > 0.38 and lam_diff < -0.20 and momentum < -0.08:
        next_goal_bet = "AWAY"
        next_goal_reason = "AWAY LAMBDA + MOMENTUM"
    elif home_ng > 0.53 and away_ng > 0.28 and abs(momentum) < 0.20 and tempo_high:
        next_goal_bet = "AWAY"
        next_goal_reason = "FAKE HOME PRESSURE"
    elif game_type == "ATTACK_WAVE" and away_ng > 0.30:
        next_goal_bet = "AWAY"
        next_goal_reason = "OPEN GAME"

    return next_goal_prediction, next_goal_bet, next_goal_reason


# ============================================================
# NEXT GOAL SMART ENGINE (PREDICT_NEXT_GOAL_SMART)
# ============================================================

def predict_next_goal_smart(
    p_home_next, p_away_next,
    lam_h, lam_a,
    danger_h, danger_a,
    xg_h, xg_a,
    momentum,
    pressure_h, pressure_a,
    tempo_danger,
    sot_h, sot_a,
    game_type,
    minute,
    score_diff=0,
    mc_home=None,
    mc_away=None,
    hist_home=None,
    hist_away=None,
    p_goal=None,
    mc_draw=None,
    hist_draw=None,
    final_third_h=None,
    final_third_a=None,
    gk_saves_h=None,
    gk_saves_a=None,
):
    """
    Smart next goal prediction with 8+ weighted signals and confidence score.
    WEIGHTING: P(next)=25%, Lambda=20%, Danger=15%, Momentum=15%,
               Pressure=10%, xG=10%, GameType+SOT=5%
    Returns dict with prediction, confidence (0.0-1.0), scores and details.
    """
    p_home_next = float(p_home_next or 0.0)
    p_away_next = float(p_away_next or 0.0)
    lam_h = float(lam_h or 0.0)
    lam_a = float(lam_a or 0.0)
    danger_h = float(danger_h or 0.0)
    danger_a = float(danger_a or 0.0)
    xg_h = float(xg_h or 0.0)
    xg_a = float(xg_a or 0.0)
    momentum = float(momentum or 0.0)
    pressure_h = float(pressure_h or 0.0)
    pressure_a = float(pressure_a or 0.0)
    tempo_danger = float(tempo_danger or 0.0)
    sot_h = float(sot_h or 0.0)
    sot_a = float(sot_a or 0.0)
    minute = int(float(minute or 0))
    game_type = str(game_type or "BALANCED")
    score_diff = int(float(score_diff or 0))
    mc_home = float(mc_home) if mc_home is not None else None
    mc_away = float(mc_away) if mc_away is not None else None
    hist_home = float(hist_home) if hist_home is not None else None
    hist_away = float(hist_away) if hist_away is not None else None
    p_goal = float(p_goal) if p_goal is not None else None
    mc_draw = float(mc_draw) if mc_draw is not None else None
    hist_draw = float(hist_draw) if hist_draw is not None else None
    final_third_h = float(final_third_h) if final_third_h is not None else 0.0
    final_third_a = float(final_third_a) if final_third_a is not None else 0.0
    gk_saves_h = float(gk_saves_h) if gk_saves_h is not None else 0.0
    gk_saves_a = float(gk_saves_a) if gk_saves_a is not None else 0.0

    # ============================================================
    # NO REAL DOMINANCE FILTER (SAFE - CFOS COMPATIBLE)
    # ============================================================
    no_real_dominance = False

    if abs(momentum) < 0.05:
        if danger_h > 0 and danger_a > 0 and pressure_h > 0 and pressure_a > 0:

            dr = danger_h / danger_a
            pr = pressure_h / pressure_a

            if dr < 1:
                dr = 1 / dr
            if pr < 1:
                pr = 1 / pr

            if dr < 1.15 and pr < 1.15:
                no_real_dominance = True

    if tempo_danger > 2.0 and abs(momentum) < 0.08:
        no_real_dominance = True

    # SIGNAL WEIGHTS
    W_PNEXT = 0.25
    W_LAMBDA = 0.20
    W_DANGER = 0.15
    W_MOMENTUM = 0.15
    W_PRESSURE = 0.10
    W_XG = 0.10
    W_GAMETYPE = 0.05
    TOTAL_SIGNALS = 9  # number of directional signals used for confidence

    # SIGNAL 1: P(next) probability (25%)
    p_total = p_home_next + p_away_next
    if p_total > 1e-9:
        p_home_norm = p_home_next / p_total
        p_away_norm = p_away_next / p_total
    else:
        p_home_norm = 0.5
        p_away_norm = 0.5
    sig1_h = (p_home_norm - 0.5) * 2.0
    sig1_a = (p_away_norm - 0.5) * 2.0

    # SIGNAL 2: Lambda difference (20%)
    lam_total_s = lam_h + lam_a
    if lam_total_s > 1e-9:
        lam_diff_s = (lam_h - lam_a) / lam_total_s
    else:
        lam_diff_s = 0.0
    sig2_h = lam_diff_s
    sig2_a = -lam_diff_s

    # SIGNAL 3: Danger difference (15%)
    danger_total_s = danger_h + danger_a
    if danger_total_s > 1e-9:
        danger_diff_s = (danger_h - danger_a) / danger_total_s
    else:
        danger_diff_s = 0.0
    sig3_h = danger_diff_s
    sig3_a = -danger_diff_s

    # SIGNAL 4: Momentum (15%)
    sig4_h = clamp(momentum, -1.0, 1.0)
    sig4_a = -sig4_h

    # SIGNAL 5: Pressure difference (10%)
    pressure_total_s = pressure_h + pressure_a
    if pressure_total_s > 1e-9:
        press_diff_s = (pressure_h - pressure_a) / pressure_total_s
    else:
        press_diff_s = 0.0
    sig5_h = press_diff_s
    sig5_a = -press_diff_s

    # SIGNAL 6: xG difference (10%)
    xg_total_s = xg_h + xg_a
    if xg_total_s > 1e-9:
        xg_diff_s = (xg_h - xg_a) / xg_total_s
    else:
        xg_diff_s = 0.0
    sig6_h = xg_diff_s
    sig6_a = -xg_diff_s

    # ============================================================
    # REAL SIGNAL AGREEMENT (ANTI DUPLICATE)
    # ============================================================

    signals = 0

    # momentum (najbolj pomemben)
    if abs(sig4_h) > 0.15:
        signals += 1

    # danger
    if abs(sig3_h) > 0.12:
        signals += 1

    # pressure
    if abs(sig5_h) > 0.12:
        signals += 1

    # lambda
    if abs(sig2_h) > 0.10:
        signals += 1

    # xG (slabši signal → manjši threshold)
    if abs(sig6_h) > 0.08:
        signals += 1

    # SIGNAL 7: SOT ratio (part of game type weight)
    sot_total_s = sot_h + sot_a
    if sot_total_s > 1e-9:
        sot_diff_s = (sot_h - sot_a) / sot_total_s
    else:
        sot_diff_s = 0.0

    # SIGNAL 8: Pitch Zone (final_third entries)
    ft_total_s = final_third_h + final_third_a
    if ft_total_s > 1e-9:
        ft_diff_s = (final_third_h - final_third_a) / ft_total_s
    else:
        ft_diff_s = 0.0
    sig8_h = ft_diff_s
    sig8_a = -ft_diff_s

    # pitch_zone_factor: amplify score for team with dominant final_third entries
    pitch_zone_factor_h = 1.0
    pitch_zone_factor_a = 1.0
    if final_third_h > max(1.0, final_third_a * 1.3):
        pitch_zone_factor_h = 1.08
    elif final_third_a > max(1.0, final_third_h * 1.3):
        pitch_zone_factor_a = 1.08

    # SIGNAL 9: GK Activity (keeper saves as danger indicator)
    gk_total_s = gk_saves_h + gk_saves_a
    sig9_h = 0.0
    sig9_a = 0.0
    if gk_total_s > 1e-9:
        gk_diff_s = (gk_saves_h - gk_saves_a) / gk_total_s
        # More saves on HOME keeper → AWAY is more dangerous
        sig9_h = -gk_diff_s
        sig9_a = gk_diff_s

    # count new signals for no_real_dominance check
    if abs(sig8_h) > 0.12:
        signals += 1
    if abs(sig9_h) > 0.10:
        signals += 1

    # ============================================================
    # SAFE TEMPO MULTIPLIER
    # ============================================================

    if tempo_danger > 1.5:
        tempo_mult = 1.05
    elif tempo_danger > 1.2:
        tempo_mult = 1.03
    elif tempo_danger < 0.8:
        tempo_mult = 0.95
    else:
        tempo_mult = 1.0

    # GAME TYPE MODIFIER (boosts dominant side in aggressive game types)
    gt_boost_h = 0.0
    gt_boost_a = 0.0
    if game_type in ("PRESSURE", "ATTACK_WAVE", "CHAOS"):
        if danger_diff_s > 0:
            gt_boost_h = 0.15
        else:
            gt_boost_a = 0.15

    # MINUTE PENALTY (84+ = smaller attack multiplier)
    if minute >= 84:
        minute_mult = 0.85
    elif minute >= 80:
        minute_mult = 0.92
    else:
        minute_mult = 1.0

    # WEIGHTED COMPOSITE SCORES
    # Each signal contributes its weight × normalised directional value (-1 to +1).
    # Positive score_h means model favours home as next goalscorer; negative means away.
    # Multipliers applied after summation:
    #   tempo_mult        — amplifies score when match tempo is high (>1.5 danger/min)
    #   minute_mult       — reduces score in final minutes (84+) to avoid late overconfidence
    #   pitch_zone_factor — boosts the side dominating final-third entries (>30% advantage)
    score_h = (
        W_PNEXT * sig1_h +        # 25% — p(next goal) probability
        W_LAMBDA * sig2_h +       # 20% — lambda (expected goals rate) dominance
        W_DANGER * sig3_h +       # 15% — danger attack dominance
        W_MOMENTUM * sig4_h +     # 15% — match momentum direction
        W_PRESSURE * sig5_h +     # 10% — pressure index dominance
        W_XG * sig6_h +           # 10% — accumulated xG dominance
        W_GAMETYPE * (sot_diff_s + gt_boost_h)  # 5% — SOT ratio + game type boost
    ) * tempo_mult * minute_mult * pitch_zone_factor_h

    score_a = (
        W_PNEXT * sig1_a +        # 25% — p(next goal) probability
        W_LAMBDA * sig2_a +       # 20% — lambda (expected goals rate) dominance
        W_DANGER * sig3_a +       # 15% — danger attack dominance
        W_MOMENTUM * sig4_a +     # 15% — match momentum direction
        W_PRESSURE * sig5_a +     # 10% — pressure index dominance
        W_XG * sig6_a +           # 10% — accumulated xG dominance
        W_GAMETYPE * (-sot_diff_s + gt_boost_a)  # 5% — SOT ratio + game type boost
    ) * tempo_mult * minute_mult * pitch_zone_factor_a

    # ============================================================
    # COUNTER / FAKE PRESSURE / GAME CONTEXT DETECTOR
    # ============================================================

    counter_risk = False
    fake_pressure = False

    # slab pritisk brez dovolj kakovosti zaključkov
    if minute >= 75 and danger_h > danger_a:
        if sot_h <= sot_a + 2 and abs(momentum) < 0.12:
            fake_pressure = True

    if minute >= 80 and danger_h > danger_a and xg_h >= xg_a:
        if sot_h <= sot_a + 2 and lam_h <= max(lam_a * 2.6, lam_a + 0.22):
            fake_pressure = True

    # domači lovijo rezultat, gost pa je še vedno nevaren / market ga še drži
    away_context_strong = False
    if mc_away is not None and mc_home is not None and mc_away >= mc_home + 0.12:
        away_context_strong = True
    if hist_away is not None and hist_home is not None and hist_away >= hist_home + 0.18:
        away_context_strong = True

    if minute >= 80 and score_diff < 0:
        if tempo_danger > 1.10 and abs(momentum) < 0.35:
            if lam_a >= 0.18 or away_context_strong:
                counter_risk = True

    if minute >= 80 and score_diff > 0:
        if tempo_danger > 1.10 and abs(momentum) < 0.35:
            if lam_h >= 0.18 or (mc_home is not None and mc_away is not None and mc_home >= mc_away + 0.12):
                counter_risk = True

    if fake_pressure:
        score_h *= 0.55
        score_a *= 0.92

    if counter_risk and score_diff < 0:
        score_h *= 0.72
        score_a *= 1.12
    elif counter_risk and score_diff > 0:
        score_a *= 0.72
        score_h *= 1.12

    no_real_dominance = signals <= 2

    # ============================================================
    # NO REAL DOMINANCE APPLY (EXACT FIX)
    # ============================================================
    if no_real_dominance:
        score_h = score_h * 0.35
        score_a = score_a * 0.35

    # PREDICTION
    prediction = "HOME" if score_h >= score_a else "AWAY"

    # ============================================================
    # DRAW ZONE FILTER
    # ============================================================

    if abs(score_h - score_a) < 0.05:
        prediction = "NO BET"

    # CONFIDENCE SCORE (agreement % across 9 directional signals)
    if prediction == "HOME":
        agree = [
            sig1_h > 0,
            sig2_h > 0,
            sig3_h > 0,
            sig4_h > 0,
            sig5_h > 0,
            sig6_h > 0,
            sot_diff_s > 0,
            sig8_h > 0,
            sig9_h > 0,
        ]
    else:
        agree = [
            sig1_a > 0,
            sig2_a > 0,
            sig3_a > 0,
            sig4_a > 0,
            sig5_a > 0,
            sig6_a > 0,
            sot_diff_s < 0,
            sig8_a > 0,
            sig9_a > 0,
        ]

    agreement_count = sum(agree)

    # context penalties: ne dovoli fake 7/7 v nasprotju z rezultatom/MC/history
    if prediction == "HOME":
        if score_diff < 0:
            agreement_count -= 1
        if mc_away is not None and mc_home is not None and mc_away > mc_home:
            agreement_count -= 1
        if hist_away is not None and hist_home is not None and hist_away > hist_home:
            agreement_count -= 1
    elif prediction == "AWAY":
        if score_diff > 0:
            agreement_count -= 1
        if mc_home is not None and mc_away is not None and mc_home > mc_away:
            agreement_count -= 1
        if hist_home is not None and hist_away is not None and hist_home > hist_away:
            agreement_count -= 1

    if fake_pressure:
        agreement_count -= 1
    if counter_risk:
        agreement_count -= 1

    agreement_count = max(0, min(TOTAL_SIGNALS, agreement_count))
    confidence = round(agreement_count / TOTAL_SIGNALS, 3)



    # ============================================================
    # ANTI OVERCONFIDENCE
    # ============================================================

    # če ni dominance → cap
    if abs(momentum) < 0.08:
        confidence *= 0.75

    # če je balanced game
    if abs(danger_h - danger_a) < 0.2 * max(1, danger_h + danger_a):
        confidence *= 0.80

    # če je low pressure
    if pressure_h < 8 and pressure_a < 8:
        confidence *= 0.85

    if fake_pressure:
        confidence *= 0.72

    if counter_risk:
        confidence *= 0.78

    # LOW GOAL / DRAW DOMINANCE LIMITER
    if p_goal is not None:
        if p_goal < 0.30:
            confidence *= 0.45
        elif p_goal < 0.40:
            confidence *= 0.58
        elif p_goal < 0.50:
            confidence *= 0.72

    draw_pressure = 0.0
    if mc_draw is not None:
        draw_pressure = max(draw_pressure, mc_draw)
    if hist_draw is not None:
        draw_pressure = max(draw_pressure, hist_draw)

    if draw_pressure >= 0.62:
        confidence *= 0.55
    elif draw_pressure >= 0.55:
        confidence *= 0.68
    elif draw_pressure >= 0.50:
        confidence *= 0.80

    if p_goal is not None and draw_pressure >= 0.55 and p_goal < 0.50:
        prediction = "NO BET"

    if p_goal is not None and p_goal < 0.35 and abs(score_h - score_a) < 0.20:
        prediction = "NO BET"

    # HARD CAP
    if confidence > 0.85:
        confidence *= 0.90

    confidence = round(confidence, 3)

    # FINAL ROUND (NUJNO)
    confidence = round(confidence, 3)

    return {
        "prediction": prediction,
        "confidence": confidence,
        "score_h": round(score_h, 4),
        "score_a": round(score_a, 4),
        "signals_agreement": agreement_count,
        "tempo_mult": round(tempo_mult, 3),
        "minute_mult": round(minute_mult, 3),
    }


# ============================================================
# BALANCE COUNTER FILTER
# ============================================================
def cfos_balance_counter(danger_h, danger_a, shots_h, shots_a, counter_goal):
    danger_h = float(danger_h or 0.0)
    danger_a = float(danger_a or 0.0)
    shots_h = float(shots_h or 0.0)
    shots_a = float(shots_a or 0.0)
    counter_goal = normalize_outcome_label(counter_goal)

    dominant_side = None

    if danger_h >= max(1.0, danger_a * 1.35) and shots_h >= max(1.0, shots_a * 1.20):
        dominant_side = "HOME"
    elif danger_a >= max(1.0, danger_h * 1.35) and shots_a >= max(1.0, shots_h * 1.20):
        dominant_side = "AWAY"

    if dominant_side and counter_goal in ("HOME", "AWAY") and counter_goal != dominant_side:
        counter_goal = dominant_side

    return dominant_side, counter_goal



def side_name_from_diff(diff, pos_text="HOME", neg_text="AWAY", neutral_text="BALANCED", eps=1e-9):
    if diff > eps:
        return pos_text
    if diff < -eps:
        return neg_text
    return neutral_text


def favorite_side(r):
    oh = float(r.get("odds_home", 0) or 0)
    oa = float(r.get("odds_away", 0) or 0)
    if oh > 0 and oa > 0:
        if oh < oa:
            return "HOME"
        if oa < oh:
            return "AWAY"
    imp_h = float(r.get("imp_h", 0) or 0)
    imp_a = float(r.get("imp_a", 0) or 0)
    return side_name_from_diff(imp_h - imp_a, "HOME", "AWAY", "BALANCED")


def goal_factor_scale_label(value):
    v = float(value or 0)
    if v < 0.85:
        return "DEAD"
    if v < 0.95:
        return "LOW"
    if v <= 1.05:
        return "NORMAL"
    if v <= 1.15:
        return "BUILDING"
    if v <= 1.25:
        return "GOAL"
    return "VERY LIKELY"


def game_type_pressure_side(r):
    gt = str(r.get("game_type", "BALANCED"))
    momentum = float(r.get("momentum", 0) or 0)
    pressure_h = float(r.get("pressure_h", 0) or 0)
    pressure_a = float(r.get("pressure_a", 0) or 0)
    danger_h = float(r.get("danger_h", 0) or 0)
    danger_a = float(r.get("danger_a", 0) or 0)
    shots_h = float(r.get("shots_h", 0) or 0)
    shots_a = float(r.get("shots_a", 0) or 0)

    bias = (pressure_h - pressure_a) * 0.7 + (danger_h - danger_a) * 0.04 + (shots_h - shots_a) * 0.18 + momentum * 12.0
    side = side_name_from_diff(bias, "HOME", "AWAY", "BALANCED", eps=0.05)

    if gt == "ATTACK_WAVE":
        return f"ATTACK_WAVE ({side} pressure)" if side != "BALANCED" else "ATTACK_WAVE"
    if gt == "PRESSURE":
        return f"PRESSURE ({side} pressure)" if side != "BALANCED" else "PRESSURE"
    if gt == "CHAOS":
        return f"CHAOS ({side} edge)" if side != "BALANCED" else "CHAOS"
    if gt == "BALANCED":
        return "BALANCED"
    return gt


def lge_state_value(r):
    gt = str(r.get("game_type", "BALANCED"))
    if gt in ("PRESSURE", "ATTACK_WAVE", "CHAOS"):
        return "ACTIVE"
    if bool(r.get("wave", {}).get("active", False)):
        return "ACTIVE"
    notes = list(r.get("tempo_notes", []) or []) + list(r.get("xgr_notes", []) or [])
    return "ACTIVE" if notes else "PASSIVE"


def high_side_label(home_val, away_val, threshold=0.0, high_text="high", low_text="LOW"):
    diff = float(home_val or 0) - float(away_val or 0)
    if diff > threshold:
        return f"HOME ({high_text})"
    if diff < -threshold:
        return f"AWAY ({high_text})"
    return low_text


def print_razumevanje(r):
    print(f"\n{MAGENTA}--------------- LEARNING INTERPRETACIJA ----------------{RESET}\n")

    xg_side = side_name_from_diff(float(r.get("xg_h", 0) or 0) - float(r.get("xg_a", 0) or 0), "HOME", "AWAY", "BALANCED", eps=0.08)
    sot_side = side_name_from_diff(float(r.get("sot_h", 0) or 0) - float(r.get("sot_a", 0) or 0), "HOME", "AWAY", "BALANCED", eps=0.25)
    shot_side = side_name_from_diff(float(r.get("shots_h", 0) or 0) - float(r.get("shots_a", 0) or 0), "HOME", "AWAY", "BALANCED", eps=0.5)
    danger_side = side_name_from_diff(float(r.get("danger_h", 0) or 0) - float(r.get("danger_a", 0) or 0), "HOME", "AWAY", "BALANCED", eps=1.0)
    score_diff = int(r.get("score_diff", 0) or 0)

    print(f"Bucket {bucket_minute(r['minute'])}")
    print(f"xG:{bucket_xg(r['xg_total'])}".ljust(14) + f"→ {xg_side}")
    print(f"SOT:{bucket_sot(r['sot_total'])}".ljust(14) + f"→ {sot_side}")
    print(f"SH:{bucket_shots(r['shots_total'])}".ljust(14) + f"→ {shot_side}")

    if score_diff > 0:
        sd_text = "HOME (vodi)"
    elif score_diff < 0:
        sd_text = "AWAY (vodi)"
    else:
        sd_text = "DRAW"
    print(f"SD:{bucket_score_diff(score_diff)}".ljust(14) + f"→ {sd_text}")
    print(f"DNG:{bucket_danger(r['danger_total'])}".ljust(14) + f"→ {danger_side}")
    print("Game type".ljust(14) + f"→ {game_type_pressure_side(r)}")
    print(f"FAVOR: {favorite_side(r)}")

    print_live_match_memory(r)
    tg = float(r.get('timeline', {}).get('trend_factor_goal', 1.0) or 1.0)
    print("Scale".ljust(28), "DEAD<0.85 | LOW 0.85-0.95 | NORMAL 0.95-1.05 | BUILD 1.05-1.15 | GOAL 1.15-1.25 | VERY LIKELY >1.25")
    print_live_lge(r)

def print_interpretacija(r):
    print(f"\n{MAGENTA}--------------- INTERPRETACIJA MODELA ----------------{RESET}\n")

    top_scores = r.get("top_scores", []) or []
    top1 = top_scores[0] if len(top_scores) >= 1 else ("N/A", 0.0)
    top2 = top_scores[1] if len(top_scores) >= 2 else None
    top3 = top_scores[2] if len(top_scores) >= 3 else None

    print("Top:")
    print(f"{top1[0]} → {pct(top1[1])} %")
    if top2:
        print(f"{top2[0]} → {pct(top2[1])} %")
    if top3:
        print(f"{top3[0]} → {pct(top3[1])} %")

    print("\nTo je tipična situacija:\n")

    gt = str(r.get("game_type", "BALANCED"))
    momentum = float(r.get("momentum", 0.0))
    lam_h = float(r.get("lam_h", 0.0))
    lam_a = float(r.get("lam_a", 0.0))
    p_goal = float(r.get("p_goal", 0.0))
    p_home_next = float(r.get("p_home_next", 0.0))
    p_away_next = float(r.get("p_away_next", 0.0))
    hist_draw = float(r.get("hist_draw", 0.0))
    rx = float(r.get("rx", 1.0))
    sot_h = float(r.get("sot_h", 0.0))
    sot_a = float(r.get("sot_a", 0.0))

    if gt == "BALANCED":
        print("tekma uravnotežena")
        print("brez jasne dominance")
        print("→ rezultat stabilen")
    elif gt == "PRESSURE":
        print("ena ekipa močneje pritiska")
        print("tekma ni več povsem mirna")
        print("→ gol je bolj verjeten")
    elif gt == "ATTACK_WAVE":
        print("tekma je odprta")
        print("napadi prihajajo v valovih")
        print("→ možen hiter preobrat")
    elif gt == "CHAOS":
        print("tekma je kaotična")
        print("ritem je zelo visok")
        print("→ rezultat lahko hitro skoči")
    else:
        print("tekma je počasna")
        print("malo čistih akcij")
        print("→ rezultat se lahko zadrži")

    print("\nModel je to predvidel kot Top1.\n")
    print("Ključni signali:\n")

    print(f"History: DRAW {round(hist_draw * 100)}%")
    print(f"Learning: DRAW {(rx - 1.0) * 100:+.1f}%")

    if abs(sot_h - sot_a) <= 1:
        print("SOT: izenačeno")
    elif sot_h > sot_a:
        print("SOT: rahlo HOME")
    else:
        print("SOT: rahlo AWAY")

    if lam_h > lam_a + 0.05:
        print("Lambda: rahlo HOME")
    elif lam_a > lam_h + 0.05:
        print("Lambda: rahlo AWAY")
    else:
        print("Lambda: skoraj izenačeno")

    print(f"Goal probability: {round(p_goal * 100)}%")

    if abs(momentum) < 0.08:
        print("Momentum: majhen")
    elif momentum > 0:
        print("Momentum: HOME pritisk")
    else:
        print("Momentum: AWAY pritisk")

    print(f"Game type: {gt}")

    print("\nTo pomeni:\n")

    final_h = float(r.get("meta_home", 0.0) or 0.0)
    final_d = float(r.get("meta_draw", 0.0) or 0.0)
    final_a = float(r.get("meta_away", 0.0) or 0.0)

    hist_h = float(r.get("hist_home", 0.0) or 0.0)
    hist_d = float(r.get("hist_draw", 0.0) or 0.0)
    hist_a = float(r.get("hist_away", 0.0) or 0.0)

    live_side = max(
        [("HOME", final_h), ("DRAW", final_d), ("AWAY", final_a)],
        key=lambda x: x[1]
    )[0]

    hist_side = max(
        [("HOME", hist_h), ("DRAW", hist_d), ("AWAY", hist_a)],
        key=lambda x: x[1]
    )[0]

    if live_side == "AWAY" and hist_side == "DRAW":
        print("Tekma je še odprta, čeprav gostje vodijo.")
        print("Gostje so trenutno nevarnejši in bližje naslednjemu golu.")
        print("Vendar zgodovina kaže možnost comebacka.")
        print("Domači še vedno lahko dosežejo gol.")
        print("Možna sta oba scenarija: gol gostov ali gol domačih.")

    elif live_side == "AWAY" and hist_side == "AWAY":
        print("Gostje kontrolirajo tekmo.")
        print("Prihajajo do boljših priložnosti.")
        print("Domači težko ustvarijo nevarnost.")
        print("Zelo verjeten naslednji gol gostov.")
        print("Tekma se lahko odloči.")

    elif live_side == "HOME" and hist_side == "AWAY":
        print("Domači pritiskajo.")
        print("Gostje pa ostajajo nevarni iz kontre.")
        print("Možen je nasprotni gol gostov.")
        print("Tekma je zelo odprta.")

    elif live_side == "HOME":
        print("Domači imajo pobudo.")
        print("Več napadov in večji pritisk.")
        print("Gol domačih je verjeten.")

    elif live_side == "DRAW":
        print("Tekma je izenačena.")
        print("Tempo ni enostranski.")
        print("Možen gol na obe strani.")

    else:
        if p_goal >= 0.55:
            print("Obe ekipi prideta do priložnosti.")
            print("Gol je verjeten.")
        else:
            print("Tempo ni dovolj močan.")
            print("Manj prostora za gol.")

    if abs(lam_h - lam_a) < 0.08:
        print("Smer gola je nejasna.")
    elif lam_h > lam_a:
        print("Rahla smer je proti HOME.")
    else:
        print("Rahla smer je proti AWAY.")

    print(f"Zato model vidi: {top1[0]}")
    print("")
    print(f"SMER: H {final_h * 100:.0f}% | D {final_d * 100:.0f}% | A {final_a * 100:.0f}%")
    print(f"HISTORY: H {hist_h * 100:.0f}% | D {hist_d * 100:.0f}% | A {hist_a * 100:.0f}%")

    print("\nČe pade gol:\n")
    if lam_h > lam_a + 0.05:
        print("lambda rahlo HOME")
        if top2:
            print(f"→ {top2[0]}")
    elif lam_a > lam_h + 0.05:
        print("lambda rahlo AWAY")
        if top2:
            print(f"→ {top2[0]}")
    else:
        print("lambda skoraj izenačeno")
        if top2:
            print(f"→ možen {top2[0]}")

    if abs(sot_h - sot_a) <= 1 and top3:
        print("\nSOT izenačen")
        print(f"→ možen {top3[0]}")

    print("\nNEXT GOAL:")
    print(f"HOME {round(p_home_next * 100)}%")
    print(f"AWAY {round(p_away_next * 100)}%")

    if abs(p_home_next - p_away_next) <= 0.06:
        print("\n→ skoraj 50-50")
    elif p_home_next > p_away_next:
        print("\n→ rahla prednost HOME")
    else:
        print("\n→ rahla prednost AWAY")

    max_mc = max(float(r.get("mc_h_adj", 0.0)), float(r.get("mc_x_adj", 0.0)), float(r.get("mc_a_adj", 0.0)))
    if max_mc < 0.60:
        print("\nModel ni overconfident.")
    else:
        print("\nModel ima močnejše zaupanje v Top1.")



def print_cfos_history_engine(r):
    print("\n================ CFOS HISTORY ENGINE =================\n")

    base_h = float(r.get("hist_home", 0) or 0)
    base_d = float(r.get("hist_draw", 0) or 0)
    base_a = float(r.get("hist_away", 0) or 0)

    print("BASE (FINAL HISTORY)")
    print(f"H {base_h:.3f}")
    print(f"D {base_d:.3f}")
    print(f"A {base_a:.3f}\n")

    learn_h = float(r.get("rh", 1.0) or 1.0)
    learn_d = float(r.get("rx", 1.0) or 1.0)
    learn_a = float(r.get("ra", 1.0) or 1.0)

    print("LEARNING RATIOS")
    print(f"H x{learn_h:.3f}")
    print(f"D x{learn_d:.3f}")
    print(f"A x{learn_a:.3f}\n")

    post_h = base_h * learn_h
    post_d = base_d * learn_d
    post_a = base_a * learn_a

    norm = post_h + post_d + post_a
    if norm > 0:
        post_h /= norm
        post_d /= norm
        post_a /= norm

    print("AFTER LEARNING (normalized)")
    print(f"H {post_h:.3f}")
    print(f"D {post_d:.3f}")
    print(f"A {post_a:.3f}\n")

    momentum = float(r.get("momentum", 0) or 0)
    lam_h = float(r.get("lam_h", 0) or 0)
    lam_a = float(r.get("lam_a", 0) or 0)
    danger_h = float(r.get("danger_h", 0) or 0)
    danger_a = float(r.get("danger_a", 0) or 0)

    momentum_side = "HOME" if momentum > 0.08 else "AWAY" if momentum < -0.08 else "NONE"
    lambda_side = "HOME" if lam_h > lam_a else "AWAY" if lam_a > lam_h else "NONE"
    danger_side = "HOME" if danger_h > danger_a else "AWAY" if danger_a > danger_h else "NONE"

    print("LIVE ADJUST")
    print(f"Momentum        {momentum_side}")
    print(f"Lambda bias     {lambda_side}")
    print(f"Danger bias     {danger_side}\n")

    after_live_h = float(r.get("mc_h_adj", r.get("mc_h_raw", 0)) or 0)
    after_live_d = float(r.get("mc_x_adj", r.get("mc_x_raw", 0)) or 0)
    after_live_a = float(r.get("mc_a_adj", r.get("mc_a_raw", 0)) or 0)

    print("AFTER LIVE")
    print(f"H {after_live_h:.3f}")
    print(f"D {after_live_d:.3f}")
    print(f"A {after_live_a:.3f}\n")

    final_h = float(r.get("meta_home", after_live_h) or after_live_h)
    final_d = float(r.get("meta_draw", after_live_d) or after_live_d)
    final_a = float(r.get("meta_away", after_live_a) or after_live_a)

    print("FINAL (MODEL)")
    print(f"H {final_h:.3f}")
    print(f"D {final_d:.3f}")
    print(f"A {final_a:.3f}")

    print("\n====================================================\n")


def confidence_score_base(p_goal, mc_h, mc_x, mc_a, timeline_n):
    best_1x2 = max(mc_h, mc_x, mc_a)

    conf = 24.0

    conf += best_1x2 * 45.0
    conf += abs(mc_h - mc_a) * 18.0
    conf += p_goal * 10.0

    if timeline_n >= 2:
        conf += 6.0
    if timeline_n >= 3:
        conf += 4.0

    return clamp(conf, 1.0, 100.0)


def safe_log(p):
    return math.log(max(1e-9, p))


def softmax3(a, b, c):
    m = max(a, b, c)
    ea = math.exp(a - m)
    eb = math.exp(b - m)
    ec = math.exp(c - m)
    s = ea + eb + ec
    return ea / s, eb / s, ec / s


def closeness(a, b):
    return 1.0 - min(1.0, abs(a - b))




def apply_meta_meta_iq(mc_h_adj, mc_x_adj, mc_a_adj, hist_home, hist_draw, hist_away, lam_h, lam_a, momentum):
    # =====================================================
    # META-META IQ ENGINE (SELF AWARE MODEL)
    # =====================================================

    # save BEFORE
    mc_h_before = mc_h_adj
    mc_x_before = mc_x_adj
    mc_a_before = mc_a_adj

    self_trust = 0.0
    consensus = 0

    if mc_h_adj > mc_x_adj and hist_home > hist_draw and lam_h > lam_a:
        consensus += 1

    if mc_a_adj > mc_x_adj and hist_away > hist_draw and lam_a > lam_h:
        consensus += 1

    if mc_x_adj > mc_h_adj and hist_draw > hist_home:
        consensus += 1

    if consensus >= 2:
        self_trust += 1.5

    disagreement = 0

    if abs(mc_h_adj - hist_home) > 0.20:
        disagreement += 1

    if abs(mc_a_adj - hist_away) > 0.20:
        disagreement += 1

    if abs(lam_h - lam_a) < 0.05 and abs(momentum) > 0.12:
        disagreement += 1

    if disagreement >= 2:
        self_trust -= 1.2

    if self_trust > 1:
        mc_h_adj *= 1.04
        mc_a_adj *= 1.04
        mc_x_adj *= 0.94
    elif self_trust < -1:
        mc_x_adj *= 1.08

    s = mc_h_adj + mc_x_adj + mc_a_adj
    if s > 0:
        mc_h_adj /= s
        mc_x_adj /= s
        mc_a_adj /= s

    # =====================================================
    # META-META IQ PRINT
    # =====================================================
    print("")
    print("============= META-META IQ =============")
    print(f"IQ self_trust : {self_trust:.3f}")
    print(f"Consensus     : {consensus}")
    print(f"Disagreement  : {disagreement}")

    print("")
    print("MC BEFORE IQ")
    print(f"H: {mc_h_before:.2f}")
    print(f"X: {mc_x_before:.2f}")
    print(f"A: {mc_a_before:.2f}")

    print("")
    print("MC AFTER IQ")
    print(f"H: {mc_h_adj:.2f}")
    print(f"X: {mc_x_adj:.2f}")
    print(f"A: {mc_a_adj:.2f}")

    return mc_h_adj, mc_x_adj, mc_a_adj, self_trust

def meta_calibrate_1x2(
        mc_h, mc_x, mc_a,
        imp_h, imp_x, imp_a,
        lam_h, lam_a,
        p_goal,
        momentum,
        pressure_h, pressure_a,
        xg_h, xg_a,
        minute,
        score_diff,
        team_power,
        hist_n
):
    lam_diff = lam_h - lam_a
    xg_diff = xg_h - xg_a
    pressure_diff = pressure_h - pressure_a

    if minute <= 20:
        lam_diff *= 0.55
        xg_diff *= 0.55
        momentum *= 0.55
        team_power *= 0.70

    log_h = safe_log(mc_h)
    log_x = safe_log(mc_x)
    log_a = safe_log(mc_a)

    # lambda
    log_h += lam_diff * 0.22
    log_a -= lam_diff * 0.22

    # xg
    log_h += xg_diff * 0.18
    log_a -= xg_diff * 0.18

    # momentum
    log_h += momentum * 0.16
    log_a -= momentum * 0.16

    # team strength
    log_h += team_power * 0.20
    log_a -= team_power * 0.20

    # pressure
    if pressure_h > pressure_a:
        log_h += min(0.12, (pressure_h - pressure_a) * 0.006)
    elif pressure_a > pressure_h:
        log_a += min(0.12, (pressure_a - pressure_h) * 0.006)

    # draw killer
    if p_goal > 0.55:
        log_x -= 0.15

    if minute > 70 and score_diff != 0:
        log_x -= 0.10

    h, x, a = softmax3(log_h, log_x, log_a)

    h = max(0.03, h)
    x = max(0.06, x)
    a = max(0.03, a)

    s = h + x + a
    if s > 0:
        h /= s
        x /= s
        a /= s

    return h, x, a


# ============================================================
# KONEC DELA 2 / 8
# ============================================================
# ============================================================
# CFOS-XG PRO 75 TITAN
# ZAČETEK DELA 3 / 8
# LEARNING ENGINE
# ============================================================

def load_history():
    rows = []
    if not os.path.exists(LEARN_FILE):
        return rows

    try:
        with open(LEARN_FILE, "r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if not header:
                return rows

            header0 = header[0].strip().lower() if header else ""

            for parts in reader:
                if not parts or len(parts) < 7:
                    continue

                if header0 == "home":
                    rows.append({
                        "home": parts[0],
                        "away": parts[1],
                        "minute": safe_int(parts[2]),
                        "xg_total": safe_float(parts[3]),
                        "sot_total": safe_float(parts[4]),
                        "shots_total": safe_float(parts[5]),
                        "score_diff": safe_int(parts[6]),
                        "lam_pred": safe_float(parts[10]),
                        "p_goal_pred": safe_float(parts[11]),
                        "mc_h": safe_float(parts[12]) if len(parts) > 12 else 0.0,
                        "mc_x": safe_float(parts[13]) if len(parts) > 13 else 0.0,
                        "mc_a": safe_float(parts[14]) if len(parts) > 14 else 0.0,
                        "final_outcome": parts[15].strip().upper() if len(parts) > 15 else "",
                        "goal_to_end": safe_int(parts[16]) if len(parts) > 16 else 0,
                        "ts": parts[17] if len(parts) > 17 else "",
                        "game_type": parts[18].strip().upper() if len(parts) > 18 else "",
                        "danger_bucket": parts[19].strip().lower() if len(parts) > 19 else "",
                    })
                else:
                    rows.append({
                        "home": "",
                        "away": "",
                        "minute": safe_int(parts[0]),
                        "xg_total": safe_float(parts[1]),
                        "sot_total": safe_float(parts[2]),
                        "shots_total": safe_float(parts[3]),
                        "score_diff": safe_int(parts[4]),
                        "lam_pred": safe_float(parts[5]),
                        "p_goal_pred": safe_float(parts[6]),
                        "mc_h": safe_float(parts[7]),
                        "mc_x": safe_float(parts[8]),
                        "mc_a": safe_float(parts[9]),
                        "final_outcome": parts[10].strip().upper() if len(parts) > 10 else "",
                        "goal_to_end": safe_int(parts[11]) if len(parts) > 11 else 0,
                        "ts": parts[12] if len(parts) > 12 else "",
                        "game_type": "",
                        "danger_bucket": "",
                    })

    except Exception as e:
        print("Napaka v load_history():", e)
        return []

    return rows


def select_subset(history, minute, xg_total, sot_total, shots_total, score_diff, game_type="", danger_total=0):
    if not history:
        return []

    bm = bucket_minute(minute)
    bx = bucket_xg(xg_total)
    bs = bucket_sot(sot_total)
    bsh = bucket_shots(shots_total)
    bd = bucket_score_diff(score_diff)
    bdanger = bucket_danger(danger_total)

    primary = []
    fallback = []

    for r in history:
        score = 0

        # ============================================================
        # STRICT SCORE STATE FILTER (fix DRAW bias)
        # ============================================================

        # če nekdo vodi +1, ne mešaj z 0-0
        if score_diff != 0:
            if r["score_diff"] != score_diff:
                continue

        if bucket_minute(r["minute"]) == bm:
            score += 1
        if bucket_xg(r["xg_total"]) == bx:
            score += 1
        if bucket_sot(r["sot_total"]) == bs:
            score += 1
        if bucket_shots(r["shots_total"]) == bsh:
            score += 1
        if bucket_score_diff(r["score_diff"]) == bd:
            score += 1

        base_ok = score >= 2
        if not base_ok:
            continue

        fallback.append(r)

        gt_ok = True
        if game_type and r.get("game_type"):
            gt_ok = (r["game_type"].upper() == game_type.upper())

        danger_ok = True
        if r.get("danger_bucket", ""):
            danger_ok = (r["danger_bucket"].lower() == bdanger)

        if gt_ok and danger_ok:
            primary.append(r)

    # ============================================================
    # AUTO HISTORY EXPANSION
    # ============================================================

    # strict history
    if len(primary) >= 12:
        return primary

    # fallback history
    if len(fallback) >= 12:
        return fallback

    # ------------------------------------------------------------
    # WIDE HISTORY (ignore sot + shots)
    # ------------------------------------------------------------
    wide = []

    for r in history:

        score = 0

        # ============================================================
        # STRICT SCORE STATE FILTER (fix DRAW bias)
        # ============================================================

        # če nekdo vodi +1, ne mešaj z 0-0
        if score_diff != 0:
            if r["score_diff"] != score_diff:
                continue

        if bucket_minute(r["minute"]) == bm:
            score += 1
        if bucket_xg(r["xg_total"]) == bx:
            score += 1
        if bucket_score_diff(r["score_diff"]) == bd:
            score += 1

        if score >= 2:
            wide.append(r)

    if len(wide) >= 20:
        return wide

    # ------------------------------------------------------------
    # SUPER WIDE (minute only)
    # ------------------------------------------------------------
    last = [r for r in history if bucket_minute(r["minute"]) == bm]

    if len(last) >= 20:
        return last

    # ------------------------------------------------------------
    # GLOBAL fallback
    # ------------------------------------------------------------
    if len(history) >= 30:
        return history

    return []


def learn_factor_goal(history, minute, xg_total, sot_total, shots_total, score_diff, game_type="", danger_total=0):
    subset = select_subset(history, minute, xg_total, sot_total, shots_total, score_diff, game_type, danger_total)
    n = len(subset)
    if n < 4:
        return 1.0, n

    obs = sum(r["goal_to_end"] for r in subset) / n
    pred = sum(r["lam_pred"] for r in subset) / n
    if pred <= 1e-9:
        return 1.0, n

    f = obs / pred
    f = clamp(f, 0.86, 1.15)
    return f, n


def learn_factor_1x2(history, minute, xg_total, sot_total, shots_total, score_diff, game_type="", danger_total=0):
    subset = select_subset(history, minute, xg_total, sot_total, shots_total, score_diff, game_type, danger_total)
    n = len(subset)
    if n < 4:
        return 1.0, 1.0, 1.0, n

    obs_h = sum(1 for r in subset if r["final_outcome"] == "H") / n
    obs_x = sum(1 for r in subset if r["final_outcome"] == "D") / n
    obs_a = sum(1 for r in subset if r["final_outcome"] == "A") / n

    pred_h = sum(r["mc_h"] for r in subset) / n
    pred_x = sum(r["mc_x"] for r in subset) / n
    pred_a = sum(r["mc_a"] for r in subset) / n

    if pred_h < 1e-9 or pred_x < 1e-9 or pred_a < 1e-9:
        return 1.0, 1.0, 1.0, n

    rh = clamp(obs_h / pred_h, 0.80, 1.15)
    rx = clamp(obs_x / pred_x, 0.85, 1.08)
    ra = clamp(obs_a / pred_a, 0.80, 1.15)

    return rh, rx, ra, n


# ============================================================
# LEARN RATIOS (1X2) PRINT WITH REAL %
# ============================================================
def print_learn_ratios(rh, rx, ra, n_1x2):
    ph = (rh - 1.0) * 100.0
    pd = (rx - 1.0) * 100.0
    pa = (ra - 1.0) * 100.0

    base = 1 / 3

    h_est = int(n_1x2 * base * rh)
    d_est = int(n_1x2 * base * rx)
    a_est = int(n_1x2 * base * ra)

    h_pct = (h_est / n_1x2 * 100) if n_1x2 else 0
    d_pct = (d_est / n_1x2 * 100) if n_1x2 else 0
    a_pct = (a_est / n_1x2 * 100) if n_1x2 else 0

    print("")
    print(f"Learn ratios (1X2)  (bucket n: {n_1x2})")
    print("")
    print(f"H  {rh:.3f}   ({ph:+.1f}%)   ≈ {h_est}/{n_1x2}   → {h_pct:.1f}%")
    print(f"D  {rx:.3f}   ({pd:+.1f}%)   ≈ {d_est}/{n_1x2}   → {d_pct:.1f}%")
    print(f"A  {ra:.3f}   ({pa:+.1f}%)   ≈ {a_est}/{n_1x2}   → {a_pct:.1f}%")




# ============================================================
# KONEC DELA 3 / 8
# ============================================================
# ============================================================
# CFOS-XG PRO 75 TITAN
# ZAČETEK DELA 4 / 8
# SNAPSHOT SISTEM
# ============================================================

def save_snapshot(home, away, minute, xg_total, sot_total, shots_total, score_diff,
                  odds_home, odds_draw, odds_away,
                  lam_total_raw, p_goal_raw, mc_h_raw, mc_x_raw, mc_a_raw,
                  score_home, score_away, game_type, danger_total):
    ts = str(int(time.time()))
    header = [
        "home", "away", "minute", "xg_total", "sot_total", "shots_total", "score_diff",
        "odds_h", "odds_x", "odds_a", "lam_total_raw", "p_goal_raw",
        "mc_h_raw", "mc_x_raw", "mc_a_raw", "score_home", "score_away",
        "ts", "game_type", "danger_bucket"
    ]

    new_row = [
        home, away, minute, f"{xg_total:.4f}", f"{sot_total:.4f}", f"{shots_total:.4f}",
        score_diff, f"{odds_home:.4f}", f"{odds_draw:.4f}", f"{odds_away:.4f}",
        f"{lam_total_raw:.6f}", f"{p_goal_raw:.6f}", f"{mc_h_raw:.6f}", f"{mc_x_raw:.6f}",
        f"{mc_a_raw:.6f}", score_home, score_away, ts, game_type, bucket_danger(danger_total)
    ]

    rows = []
    if os.path.exists(SNAP_FILE):
        try:
            with open(SNAP_FILE, "r", encoding="utf-8", newline="") as f:
                reader = csv.reader(f)
                _ = next(reader, None)
                for parts in reader:
                    if not parts:
                        continue
                    if len(parts) >= 3 and parts[0] == home and parts[1] == away and safe_int(parts[2]) == minute:
                        continue
                    rows.append(parts)
        except:
            rows = []

    rows.append(new_row)

    try:
        with open(SNAP_FILE, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(rows)
        print("Snapshot shranjen v", SNAP_FILE)
    except Exception as e:
        print("Napaka pri shranjevanju snapshot:", e)


def finalize_snapshots(final_h, final_a, filter_home=None, filter_away=None):
    if not os.path.exists(SNAP_FILE):
        print("Ni snapshotov za zaključek.")
        return

    all_rows = []
    header = None

    try:
        with open(SNAP_FILE, "r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if not header:
                print("Ni snapshotov za zaključek.")
                return
            for row in reader:
                if row:
                    all_rows.append(row)
    except Exception as e:
        print("Napaka pri branju snapshot:", e)
        return

    remaining_rows = []
    to_finalize = []

    for parts in all_rows:
        if len(parts) < 18:
            continue

        snap_home = parts[0]
        snap_away = parts[1]

        if filter_home is not None and filter_away is not None:
            if snap_home == filter_home and snap_away == filter_away:
                to_finalize.append(parts)
            else:
                remaining_rows.append(parts)
        else:
            to_finalize.append(parts)

    if not to_finalize:
        print("Ni ustreznih snapshotov.")
        return

    need_header = not file_has_data(LEARN_FILE)

    try:
        with open(LEARN_FILE, "a", encoding="utf-8", newline="") as out:
            writer = csv.writer(out)
            if need_header:
                writer.writerow([
                    "home", "away", "minute", "xg_total", "sot_total", "shots_total", "score_diff",
                    "odds_h", "odds_x", "odds_a", "lam_total_raw", "p_goal_raw",
                    "mc_h_raw", "mc_x_raw", "mc_a_raw", "final_outcome", "goal_to_end",
                    "ts", "game_type", "danger_bucket"
                ])

            for parts in to_finalize:
                snap_score_home = safe_int(parts[15])
                snap_score_away = safe_int(parts[16])

                if final_h > final_a:
                    outcome = "H"
                elif final_h == final_a:
                    outcome = "D"
                else:
                    outcome = "A"

                goal_to_end = max(0, (final_h + final_a) - (snap_score_home + snap_score_away))
                game_type = parts[18] if len(parts) > 18 else ""
                danger_bucket = parts[19] if len(parts) > 19 else ""

                writer.writerow([
                    parts[0], parts[1], parts[2], parts[3], parts[4], parts[5],
                    parts[6], parts[7], parts[8], parts[9], parts[10], parts[11],
                    parts[12], parts[13], parts[14], outcome, goal_to_end, parts[17] if len(parts) > 17 else "",
                    game_type, danger_bucket
                ])
    except Exception as e:
        print("Napaka pri pisanju v LEARN_FILE:", e)

    if len(remaining_rows) == 0:
        try:
            os.remove(SNAP_FILE)
        except:
            pass
    else:
        try:
            with open(SNAP_FILE, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(header)
                writer.writerows(remaining_rows)
        except Exception as e:
            print("Napaka pri pisanju preostalih snapshot:", e)

    print("Snapshoti zaključeni in premaknjeni v", LEARN_FILE)


# ============================================================
# KONEC DELA 4 / 8
# ============================================================
# ============================================================
# CFOS-XG PRO 75 TITAN
# ZAČETEK DELA 5 / 8
# MATCH MEMORY / TIMELINE / ATTACK WAVE
# ============================================================
# ============================================================
# SAVE MATCH RESULT
# ============================================================

def save_match_result(home, away, minute, prediction_1x2, prediction_score, result_1x2, result_score, history_pred=""):
    header = [
        "home", "away", "minute",
        "prediction_1x2", "prediction_score",
        "history_pred",
        "result_1x2", "result_score"
    ]

    prediction_1x2 = normalize_outcome_label(prediction_1x2)
    result_1x2 = normalize_outcome_label(result_1x2)
    history_pred = normalize_outcome_label(history_pred)

    rows = []

    try:
        if os.path.exists(MATCH_RESULT_FILE):
            with open(MATCH_RESULT_FILE, "r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if not row:
                        continue

                    same_match = (
                        row.get("home", "") == home and
                        row.get("away", "") == away and
                        safe_int(row.get("minute", 0)) == safe_int(minute)
                    )

                    if same_match:
                        continue

                    rows.append([
                        row.get("home", ""),
                        row.get("away", ""),
                        safe_int(row.get("minute", 0)),
                        normalize_outcome_label(row.get("prediction_1x2", "")),
                        row.get("prediction_score", ""),
                        normalize_outcome_label(row.get("history_pred", "")),
                        normalize_outcome_label(row.get("result_1x2", "")),
                        row.get("result_score", "")
                    ])
    except:
        rows = []

    rows.append([
        home, away, safe_int(minute), prediction_1x2, prediction_score,
        history_pred, result_1x2, result_score
    ])

    try:
        with open(MATCH_RESULT_FILE, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(rows)
    except:
        pass


def load_match_results(home, away):
    rows = []
    if not os.path.exists(MATCH_RESULT_FILE):
        return rows

    try:
        with open(MATCH_RESULT_FILE, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("home") == home and row.get("away") == away:
                    rows.append({
                        "home": row.get("home", ""),
                        "away": row.get("away", ""),
                        "minute": safe_int(row.get("minute", 0)),
                        "prediction_1x2": normalize_outcome_label(row.get("prediction_1x2", "")),
                        "prediction_score": row.get("prediction_score", ""),
                        "history_pred": normalize_outcome_label(row.get("history_pred", "")),
                        "result_1x2": normalize_outcome_label(row.get("result_1x2", "")),
                        "result_score": row.get("result_score", "")
                    })
    except:
        return []

    rows.sort(key=lambda x: x["minute"])
    return rows


def load_match_memory(home, away):
    rows = []
    if not os.path.exists(MATCH_MEM_FILE):
        return rows

    try:
        with open(MATCH_MEM_FILE, "r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            _ = next(reader, None)
            for parts in reader:
                if len(parts) < 22:
                    continue
                if parts[0] == home and parts[1] == away:
                    rows.append({
                        "home": parts[0],
                        "away": parts[1],
                        "minute": safe_int(parts[2]),
                        "score_home": safe_int(parts[3]),
                        "score_away": safe_int(parts[4]),
                        "shots_h": safe_float(parts[5]),
                        "shots_a": safe_float(parts[6]),
                        "sot_h": safe_float(parts[7]),
                        "sot_a": safe_float(parts[8]),
                        "danger_h": safe_float(parts[9]),
                        "danger_a": safe_float(parts[10]),
                        "att_h": safe_float(parts[11]),
                        "att_a": safe_float(parts[12]),
                        "pos_h": safe_float(parts[13]),
                        "pos_a": safe_float(parts[14]),
                        "xg_h": safe_float(parts[15]),
                        "xg_a": safe_float(parts[16]),
                        "odds_h": safe_float(parts[17]),
                        "odds_x": safe_float(parts[18]),
                        "odds_a": safe_float(parts[19]),
                        "corners_h": safe_float(parts[20]),
                        "corners_a": safe_float(parts[21]),
                    })
    except:
        return []

    rows.sort(key=lambda x: x["minute"])
    return rows


def save_match_memory(home, away, minute, score_home, score_away,
                      shots_h, shots_a, sot_h, sot_a, danger_h, danger_a,
                      att_h, att_a, pos_h, pos_a, xg_h, xg_a,
                      odds_h, odds_x, odds_a, corners_h, corners_a):
    need_header = not file_has_data(MATCH_MEM_FILE)

    existing = load_match_memory(home, away)

    # snapshot samo če je nova minuta
    for r in existing:
        if r["minute"] == minute:
            return False

    try:
        with open(MATCH_MEM_FILE, "a", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            if need_header:
                writer.writerow([
                    "home", "away", "minute", "score_home", "score_away", "shots_h", "shots_a",
                    "sot_h", "sot_a", "danger_h", "danger_a", "att_h", "att_a", "pos_h", "pos_a",
                    "xg_h", "xg_a", "odds_h", "odds_x", "odds_a", "corners_h", "corners_a"
                ])
            writer.writerow([
                home, away, minute, score_home, score_away,
                f"{shots_h:.4f}", f"{shots_a:.4f}", f"{sot_h:.4f}", f"{sot_a:.4f}",
                f"{danger_h:.4f}", f"{danger_a:.4f}", f"{att_h:.4f}", f"{att_a:.4f}",
                f"{pos_h:.4f}", f"{pos_a:.4f}", f"{xg_h:.4f}", f"{xg_a:.4f}",
                f"{odds_h:.4f}", f"{odds_x:.4f}", f"{odds_a:.4f}",
                f"{corners_h:.4f}", f"{corners_a:.4f}"
            ])
    except Exception as e:
        print("Napaka pri shranjevanju match memory:", e)
        return False
    return True


def clear_match_memory(home, away):
    if not os.path.exists(MATCH_MEM_FILE):
        return

    try:
        kept = []
        header = None

        with open(MATCH_MEM_FILE, "r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            for parts in reader:
                if len(parts) < 2:
                    continue
                if not (parts[0] == home and parts[1] == away):
                    kept.append(parts)

        if not kept:
            try:
                os.remove(MATCH_MEM_FILE)
            except:
                pass
        else:
            with open(MATCH_MEM_FILE, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                if header:
                    writer.writerow(header)
                writer.writerows(kept)
    except:
        pass


def avg_delta(seq):
    if len(seq) < 2:
        return 0.0
    deltas = []
    for i in range(1, len(seq)):
        deltas.append(seq[i] - seq[i - 1])
    return sum(deltas) / len(deltas)


def compute_timeline_factors(rows):
    out = {
        "n": len(rows),
        "trend_factor_goal": 1.0,
        "trend_home": 1.0,
        "trend_away": 1.0,
        "notes": [],
        "true_momentum_text": "Ni dovolj 10-min podatkov"
    }
    if len(rows) < 2:
        return out

    last_min = rows[-1]["minute"]
    recent_rows = [r for r in rows if r["minute"] >= last_min - 10]
    if len(recent_rows) < 2:
        return out
    first = recent_rows[0]
    last = recent_rows[-1]
    span = max(1, last["minute"] - first["minute"])

    shots_h_pm = (last["shots_h"] - first["shots_h"]) / span
    shots_a_pm = (last["shots_a"] - first["shots_a"]) / span
    sot_h_pm = (last["sot_h"] - first["sot_h"]) / span
    sot_a_pm = (last["sot_a"] - first["sot_a"]) / span
    danger_h_pm = (last["danger_h"] - first["danger_h"]) / span
    danger_a_pm = (last["danger_a"] - first["danger_a"]) / span
    att_h_pm = (last["att_h"] - first["att_h"]) / span
    att_a_pm = (last["att_a"] - first["att_a"]) / span
    xg_h_pm = (last["xg_h"] - first["xg_h"]) / span
    xg_a_pm = (last["xg_a"] - first["xg_a"]) / span

    danger_total_seq = [(r["danger_h"] + r["danger_a"]) for r in rows]
    shots_total_seq = [(r["shots_h"] + r["shots_a"]) for r in rows]
    sot_total_seq = [(r["sot_h"] + r["sot_a"]) for r in rows]
    xg_total_seq = [(r["xg_h"] + r["xg_a"]) for r in rows]

    avg_danger_step = avg_delta(danger_total_seq)
    avg_shots_step = avg_delta(shots_total_seq)
    avg_sot_step = avg_delta(sot_total_seq)
    avg_xg_step = avg_delta(xg_total_seq)

    trend_goal = 1.0
    if avg_danger_step >= 4:
        trend_goal += 0.03
        out["notes"].append("TM danger_rising")
    if avg_shots_step >= 0.7:
        trend_goal += 0.03
        out["notes"].append("TM shots_rising")
    if avg_sot_step >= 0.25:
        trend_goal += 0.04
        out["notes"].append("TM sot_rising")
    if avg_xg_step >= 0.07:
        trend_goal += 0.04
        out["notes"].append("TM xg_rising")
    if avg_danger_step <= 1 and avg_shots_step <= 0.2 and avg_sot_step <= 0.05 and last["minute"] >= 60:
        trend_goal -= 0.07
        out["notes"].append("TM game_flat")

    trend_goal = clamp(trend_goal, 0.88, 1.18)

    home_push = (
        shots_h_pm * 0.10 +
        sot_h_pm * 0.34 +
        danger_h_pm * 0.012 +
        att_h_pm * 0.005 +
        xg_h_pm * 0.40
    )
    away_push = (
        shots_a_pm * 0.10 +
        sot_a_pm * 0.34 +
        danger_a_pm * 0.012 +
        att_a_pm * 0.005 +
        xg_a_pm * 0.40
    )

    home_factor = clamp(1.0 + clamp(home_push, -0.10, 0.15), 0.86, 1.18)
    away_factor = clamp(1.0 + clamp(away_push, -0.10, 0.15), 0.86, 1.18)

    out["trend_factor_goal"] = trend_goal
    out["trend_home"] = home_factor
    out["trend_away"] = away_factor
    out["true_momentum_text"] = " | ".join(out["notes"]) if out["notes"] else "Ni dovolj 10-min podatkov"
    return out


def detect_attack_wave(rows, minute):
    out = {
        "active": False,
        "home": 1.0,
        "away": 1.0,
        "goal": 1.0,
        "notes": []
    }

    if len(rows) < 2:
        return out

    last_min = rows[-1]["minute"]
    recent_rows = [r for r in rows if r["minute"] >= last_min - 10]

    if len(recent_rows) < 2:
        return out

    first = recent_rows[0]
    last = recent_rows[-1]
    span = max(1, last["minute"] - first["minute"])

    d_danger_h = last["danger_h"] - first["danger_h"]
    d_danger_a = last["danger_a"] - first["danger_a"]
    d_shots_h = last["shots_h"] - first["shots_h"]
    d_shots_a = last["shots_a"] - first["shots_a"]
    d_sot_h = last["sot_h"] - first["sot_h"]
    d_sot_a = last["sot_a"] - first["sot_a"]
    d_xg_h = last["xg_h"] - first["xg_h"]
    d_xg_a = last["xg_a"] - first["xg_a"]

    if (
            (d_danger_h >= 8 and span <= 5) or
            (d_shots_h >= 2 and d_sot_h >= 1) or
            (d_xg_h >= 0.18)
    ):
        out["home"] *= 1.07
        out["goal"] *= 1.02
        out["active"] = True
        out["notes"].append(
            f"WAVE HOME dDanger={round(d_danger_h, 1)} dShots={round(d_shots_h, 1)} dSOT={round(d_sot_h, 1)} dXG={round(d_xg_h, 3)}")

    if (
            (d_danger_a >= 8 and span <= 5) or
            (d_shots_a >= 2 and d_sot_a >= 1) or
            (d_xg_a >= 0.18)
    ):
        out["away"] *= 1.07
        out["goal"] *= 1.04
        out["active"] = True
        out["notes"].append(
            f"WAVE AWAY dDanger={round(d_danger_a, 1)} dShots={round(d_shots_a, 1)} dSOT={round(d_sot_a, 1)} dXG={round(d_xg_a, 3)}")

    out["home"] = clamp(out["home"], 1.0, 1.14)
    out["away"] = clamp(out["away"], 1.0, 1.14)
    out["goal"] = clamp(out["goal"], 1.0, 1.10)
    return out


# ============================================================
# KONEC DELA 5 / 8
# ============================================================
# ============================================================
# CFOS-XG PRO 75 TITAN
# ZAČETEK DELA 6 / 8
# HISTORY SCORE / EXACT SCORE / ANALIZA PREDLOGA STAVE
# ============================================================

def history_score_bias(history, minute, xg_total, sot_total, shots_total, score_diff, game_type="", danger_total=0):
    subset = select_subset(history, minute, xg_total, sot_total, shots_total, score_diff, game_type, danger_total)
    n = len(subset)
    if n < 10:
        return None

    p_home = sum(1 for r in subset if r["final_outcome"] == "H") / n
    p_draw = sum(1 for r in subset if r["final_outcome"] == "D") / n
    p_away = sum(1 for r in subset if r["final_outcome"] == "A") / n
    p_goal = sum(1 for r in subset if r["goal_to_end"] > 0) / n
    p_no_goal = 1.0 - p_goal

    return {
        "n": n,
        "p_home": p_home,
        "p_draw": p_draw,
        "p_away": p_away,
        "p_goal": p_goal,
        "p_no_goal": p_no_goal,
    }


def exact_score_history_bias(history, minute, xg_total, sot_total, shots_total, score_diff,
                             score_home, score_away, game_type="", danger_total=0):
    subset = select_subset(history, minute, xg_total, sot_total, shots_total, score_diff, game_type, danger_total)
    n = len(subset)
    if n < 10:
        return None

    p_no_goal = sum(r["goal_to_end"] == 0 for r in subset) / n
    p_goal = 1.0 - p_no_goal

    return {
        "n": n,
        "p_no_goal": p_no_goal,
        "p_goal": p_goal,
    }


def final_score_prediction(score_home, score_away, lam_h, lam_a, lam_c,
                           history, minute, xg_total, sot_total, shots_total,
                           score_diff, game_type="", danger_total=0, sim_count=SIM_EXACT_BASE):
    score_dist = {}

    for _ in range(sim_count):
        gh, ga = bivariate_poisson_sample(lam_h, lam_a, lam_c)
        gh = min(gh, 5)
        ga = min(ga, 5)
        fh = score_home + gh
        fa = score_away + ga
        key = f"{fh}-{fa}"
        score_dist[key] = score_dist.get(key, 0) + 1

    total_raw = sum(score_dist.values())
    if total_raw > 0:
        for k in score_dist:
            score_dist[k] /= total_raw

    hist = history_score_bias(history, minute, xg_total, sot_total, shots_total, score_diff, game_type, danger_total)
    exact_hist = exact_score_history_bias(history, minute, xg_total, sot_total, shots_total, score_diff,
                                          score_home, score_away, game_type, danger_total)

    for k in list(score_dist.keys()):
        fh, fa = k.split("-")
        fh = int(fh)
        fa = int(fa)
        mult = 1.0

        if hist is not None:
            if fh > fa:
                mult *= (0.90 + hist["p_home"])
            elif fh == fa:
                mult *= (0.90 + hist["p_draw"])
            else:
                mult *= (0.90 + hist["p_away"])

        if exact_hist is not None:
            if fh == score_home and fa == score_away:
                mult *= (0.90 + exact_hist["p_no_goal"])
            else:
                mult *= (0.90 + exact_hist["p_goal"])

        score_dist[k] *= mult

    total_adj = sum(score_dist.values())
    if total_adj > 0:
        for k in score_dist:
            score_dist[k] /= total_adj

    sorted_scores = sorted(score_dist.items(), key=lambda x: x[1], reverse=True)
    return sorted_scores[:5], hist, exact_hist


def lge_notes(game_type, tempo_notes, xgr_notes, wave_active=False):
    notes = [f"GT GT {game_type}"]
    notes.extend(tempo_notes)
    notes.extend(xgr_notes)
    if wave_active:
        notes.append("WAVE active")
    return "ACTIVE | " + "; ".join(notes)


def predlog_stave(r):
    # 1) Najprej verjetnost izida, ne edge
    if r["mc_x_adj"] >= 0.60:
        return "X", "DRAW DOMINANT"

    if r["mc_h_adj"] >= 0.55 and r["edge_h"] >= 0.05:
        return "1", "MODEL + VALUE"

    if r["mc_a_adj"] >= 0.55 and r["edge_a"] >= 0.05:
        return "2", "MODEL + VALUE"

    # 2) Če ni ekstremne dominance, potem strong value
    if r["edge_a"] >= 0.12 and r["mc_a_adj"] >= 0.25:
        return "2", "STRONG VALUE"

    if r["edge_h"] >= 0.12 and r["mc_h_adj"] >= 0.30:
        return "1", "STRONG VALUE"

    if r["edge_x"] >= 0.07 and r["mc_x_adj"] >= 0.30:
        return "X", "VALUE"

    if r["edge_h"] >= 0.08 and r["mc_h_adj"] >= 0.50:
        return "1", "VALUE"

    if r["edge_a"] >= 0.08 and r["mc_a_adj"] >= 0.45:
        return "2", "VALUE"

    # 3) Goal/no-goal fallback
    if r["p_goal"] >= 0.62:
        return "GOL", "OPEN GAME"

    if r["p_no_goal"] >= 0.62:
        return "NO GOAL", "CLOSED GAME"

    return "NO BET", "NO EDGE"


def moje_predvidevanje(r):
    score_txt = r["top_scores"][0][0] if r["top_scores"] else "N/A"

    tip, razlog = predlog_stave(r)

    # IZID IZ MC (NE SCORE)
    if r["mc_h_adj"] > r["mc_x_adj"] and r["mc_h_adj"] > r["mc_a_adj"]:
        izid = "DOMAČI"
    elif r["mc_a_adj"] > r["mc_h_adj"] and r["mc_a_adj"] > r["mc_x_adj"]:
        izid = "GOST"
    else:
        izid = "REMI"

    return {
        "napoved_izida": izid,
        "napoved_rezultata": score_txt,
        "moja_stava": tip,
        "razlog_stave": razlog
    }


# ============================================================
# KONEC DELA 6 / 8
# ============================================================
# ============================================================
# CFOS-XG PRO 75 TITAN
# ZAČETEK DELA 7.1/ 8
# GLAVNI MODEL
# ============================================================

def izracunaj_model(data, final_third_fm_h=None, final_third_fm_a=None):
    """
    Main model computation function. Calculates all match metrics from a raw CSV data row.

    Args:
        data (list or str): CSV row data. Either a list of string/float values or a
            comma-separated string. Expected columns (0-indexed):
            0: home team name         1: away team name
            2: odds_home              3: odds_draw        4: odds_away
            5: minute                 6: score_home       7: score_away
            8: xg_home                9: xg_away
            10: shots_home            11: shots_away
            12: sot_home              13: sot_away
            14: attacks_home          15: attacks_away
            16: danger_home           17: danger_away
            18: big_chances_home      19: big_chances_away
            20: yellow_home           21: yellow_away
            22: red_home              23: red_away
            24: possession_home (%)   25: possession_away (%)
            26: blocked_home          27: blocked_away
            28: bcm_home              29: bcm_away
            30: corners_home          31: corners_away
        final_third_fm_h (float, optional): Final third entries for home team
            sourced from match memory. Used as fallback when CSV value is 0.
        final_third_fm_a (float, optional): Final third entries for away team
            sourced from match memory. Used as fallback when CSV value is 0.

    Returns:
        dict: Comprehensive result dictionary with all computed metrics:
            Raw inputs: minute, score_diff, xg_h, xg_a, sot_h, sot_a, etc.
            Lambda engine: lam_h, lam_a, lam_c, lam_total, lam_h_raw, etc.
            Probabilities: p_goal, p_home_next, p_away_next, p_goal_raw
            Momentum/tempo: momentum, tempo_shots, tempo_danger, tempo_att
            Monte Carlo: mc_h_raw, mc_x_raw, mc_a_raw, mc_h_adj, mc_x_adj, mc_a_adj
            Predictions: next_goal_prediction, next_goal_prediction_smart
            Learning: lf_goal, lf_1x2, rh, rx, ra, n_goal, n_1x2
            Timeline/memory: timeline (dict), wave (dict), lge (str)
            Scores: top_scores (list of (bet_type, score) tuples)

    Example:
        csv_row = "Arsenal,Chelsea,2.10,3.30,3.80,68,1,0,0.80,0.50,6,4,3,2,22,18,8,5,2,1,1,0,0,0,58,42,1,2,0,1,5,3"
        r = izracunaj_model(csv_row)
        # r["p_goal"]    -> e.g. 0.72
        # r["momentum"]  -> e.g. 0.15  (positive = home momentum)
        # r["game_type"] -> e.g. "PRESSURE"
    """
    # Safety initializations for variables that may be used before assignment
    counter_blocked = False
    dominant_side = None
    next_goal_prediction = "N/A"
    next_goal_bet = "NO BET"
    next_goal_reason = ""

    data = normalize_csv_row(data)

    def get_safe(idx):
        if idx < len(data):
            try:
                return float(data[idx])
            except:
                return None
        return None

    # ============================================================
    # CFOS CSV CORE MAP (FIXED)
    # 0 home | 1 away | 2 odds_home | 3 odds_draw | 4 odds_away
    # 5 minute | 6 score_home | 7 score_away | 8 xg_home | 9 xg_away
    # 10 shots_home | 11 shots_away | 12 sot_home | 13 sot_away
    # 14 attacks_home | 15 attacks_away | 16 danger_home | 17 danger_away
    # 18 big_chances_home | 19 big_chances_away | 20 yellow_home | 21 yellow_away
    # 22 red_home | 23 red_away | 24 possession_home | 25 possession_away
    # 26 blocked_home | 27 blocked_away | 28 bcm_home | 29 bcm_away
    # 30 corners_home | 31 corners_away
    # ============================================================

    home = get_idx(data, 0, "HOME")
    away = get_idx(data, 1, "AWAY")

    odds_home = get_num(data, 2)
    odds_draw = get_num(data, 3)
    odds_away = get_num(data, 4)

    minute = safe_int(get_idx(data, 5, "0"))
    score_home = safe_int(get_idx(data, 6, "0"))
    score_away = safe_int(get_idx(data, 7, "0"))
    score_diff = score_home - score_away

    xg_h = get_num(data, 8)
    xg_a = get_num(data, 9)

    shots_h = get_num(data, 10)
    shots_a = get_num(data, 11)
    sot_h = get_num(data, 12)
    sot_a = get_num(data, 13)

    attacks_h = get_num(data, 14)
    attacks_a = get_num(data, 15)

    danger_h = get_num(data, 16)
    danger_a = get_num(data, 17)

    bc_h = clamp(get_num(data, 18), 0.0, 5.0)
    bc_a = clamp(get_num(data, 19), 0.0, 5.0)

    y_h = get_num(data, 20)
    y_a = get_num(data, 21)
    red_h = get_num(data, 22)
    red_a = get_num(data, 23)
    pos_h = get_num(data, 24)
    pos_a = get_num(data, 25)

    blocked_h = get_num(data, 26)
    blocked_a = get_num(data, 27)
    bcm_h = get_num(data, 28)
    bcm_a = get_num(data, 29)
    corners_h = get_num(data, 30)
    corners_a = get_num(data, 31)

    # združena imena za stare dele kode
    yellow_h = y_h
    yellow_a = y_a
    passes_h = get_safe(34)
    passes_a = get_safe(35)
    duels_h = get_safe(44)
    duels_a = get_safe(45)

    # ============================================================
    # AUTO SWAP DISABLED (BUG FIX)
    # ============================================================

    swap_flag = False

    # ============================================================
    # CFOS CSV FORMAT VALIDATOR (CRITICAL)
    # ============================================================

    if minute < 1 or minute > 130:
        print(f"⚠️  WARNING: Minute {minute} - suspicious but continuing")

    if xg_h > 15 or xg_a > 15:
        print(f"⚠️  WARNING: xG unrealistic ({xg_h}, {xg_a}) but continuing")

    if shots_h > 60 or shots_a > 60:
        print(f"⚠️  WARNING: shots unrealistic but continuing")

    # =========================
    # VALIDATOR
    # =========================

    if sot_h > shots_h:
        print(f"⚠️  WARNING: SOT home ({sot_h}) > shots home ({shots_h}) - adjusting")
        sot_h = shots_h

    if sot_a > shots_a:
        print(f"⚠️  WARNING: SOT away ({sot_a}) > shots away ({shots_a}) - adjusting")
        sot_a = shots_a

    if bc_h > shots_h:
        shots_h = bc_h

    if bc_a > shots_a:
        shots_a = bc_a

    if pos_h + pos_a > 105:
        raise ValueError("NAPAKA: possession vsota > 105")

    # NEGATIVE VALUE CHECK
    if xg_h < 0 or xg_a < 0:
        raise ValueError("NAPAKA: negativen xG")

    if shots_h < 0 or shots_a < 0:
        raise ValueError("NAPAKA: negativni shots")

    if sot_h < 0 or sot_a < 0:
        raise ValueError("NAPAKA: negativni SOT")

    if danger_h < 0 or danger_a < 0:
        raise ValueError("NAPAKA: negativni danger attacks")

    if shots_h > 40 or shots_a > 40:
        print(f"⚠️  WARNING: shots count high ({shots_h}, {shots_a}) but continuing")

    if sot_h > 20 or sot_a > 20:
        print(f"⚠️  WARNING: SOT count high ({sot_h}, {sot_a}) but continuing")

    blocked_h = get_num(data, 26)
    blocked_a = get_num(data, 27)
    bcm_h = get_num(data, 28)
    bcm_a = get_num(data, 29)
    corners_h = get_num(data, 30)
    corners_a = get_num(data, 31)

    if corners_h < 0 or corners_a < 0:
        print(f"⚠️  WARNING: negative corners - clamping to 0")
        corners_h = max(0, corners_h)
        corners_a = max(0, corners_a)

    if corners_h > 25 or corners_a > 25:
        print(f"⚠️  WARNING: corners count high ({corners_h}, {corners_a}) but continuing")

    gk_saves_h = get_num(data, 32)
    gk_saves_a = get_num(data, 33)
    passes_h = get_num(data, 34)
    passes_a = get_num(data, 35)
    acc_pass_h = get_num(data, 36)
    acc_pass_a = get_num(data, 37)

    acc_pass_h = clamp(acc_pass_h, 0.0, passes_h)
    acc_pass_a = clamp(acc_pass_a, 0.0, passes_a)

    tackles_h = get_num(data, 38)
    tackles_a = get_num(data, 39)
    inter_h = get_num(data, 40)
    inter_a = get_num(data, 41)
    clear_h = get_num(data, 42)
    clear_a = get_num(data, 43)
    duels_h = get_num(data, 44)
    duels_a = get_num(data, 45)
    offsides_h = get_num(data, 46)
    offsides_a = get_num(data, 47)
    throw_h = get_num(data, 48)
    throw_a = get_num(data, 49)
    fouls_h = get_num(data, 50)
    fouls_a = get_num(data, 51)

    prematch_h = get_num(data, 52)
    prematch_a = get_num(data, 53)
    prev_odds_home = get_num(data, 54)
    prev_odds_draw = get_num(data, 55)
    prev_odds_away = get_num(data, 56)
    elo_h = get_num(data, 57)
    elo_a = get_num(data, 58)

    # =========================================================
    # TEAM STRENGTH ENGINE
    # =========================================================

    # prematch strength (0-1)
    pm_diff = prematch_h - prematch_a

    # ELO difference
    elo_diff = (elo_h - elo_a) / 400.0

    # odds favorit
    odds_bias = 0
    if odds_home > 0 and odds_away > 0:
        odds_bias = (1 / odds_home) - (1 / odds_away)

    # kombinirana moč
    team_power = (
        pm_diff * 0.50 +
        elo_diff * 0.30 +
        odds_bias * 0.20
    )

    team_power = clamp(team_power, -0.35, 0.35)

    # --------------------------------------------------------
    # PRO 75 - DODATNI FOTMOB PODATKI (DINAMIČNI)
    # če jih ni, so 0
    # --------------------------------------------------------
    keypasses_h = get_num(data, 59)
    keypasses_a = get_num(data, 60)

    crosses_h = get_num(data, 61)
    crosses_a = get_num(data, 62)

    tackles_extra_h = get_num(data, 63)
    tackles_extra_a = get_num(data, 64)

    inter_extra_h = get_num(data, 65)
    inter_extra_a = get_num(data, 66)

    clear_extra_h = get_num(data, 67)
    clear_extra_a = get_num(data, 68)

    duels_extra_h = get_num(data, 69)
    duels_extra_a = get_num(data, 70)

    aerials_h = get_num(data, 71)
    aerials_a = get_num(data, 72)

    dribbles_h = get_num(data, 73)
    dribbles_a = get_num(data, 74)

    throw_extra_h = get_num(data, 75)
    throw_extra_a = get_num(data, 76)

    final_third_h = get_num(data, 77)
    final_third_a = get_num(data, 78)

    long_balls_h = get_num(data, 79)
    long_balls_a = get_num(data, 80)

    gk_saves_extra_h = get_num(data, 81)
    gk_saves_extra_a = get_num(data, 82)

    bc_created_h = get_num(data, 83)
    bc_created_a = get_num(data, 84)

    bc_created_h = clamp(bc_created_h, 0.0, 3.0)
    bc_created_a = clamp(bc_created_a, 0.0, 3.0)

    action_left = get_num(data, 85)
    action_mid = get_num(data, 86)
    action_right = get_num(data, 87)

    pass_acc_extra_h = get_num(data, 88)
    pass_acc_extra_a = get_num(data, 89)

    # FOTMOB EXTRA — FIXED INDEX MAP

    key_pass_h = get_num(data, 90)
    key_pass_a = get_num(data, 91)

    cross_h = get_num(data, 92)
    cross_a = get_num(data, 93)

    # 🔥 SHIFT FIX
    aerial_h = get_num(data, 96)
    aerial_a = get_num(data, 97)

    dribble_h = get_num(data, 98)
    dribble_a = get_num(data, 99)

    final_third_h = get_num(data, 100)
    final_third_a = get_num(data, 101)

    long_ball_h = get_num(data, 102)
    long_ball_a = get_num(data, 103)

    big_chance_h = get_num(data, 104)
    big_chance_a = get_num(data, 105)
    if keypasses_h == 0 and key_pass_h > 0:
        keypasses_h = key_pass_h
    if keypasses_a == 0 and key_pass_a > 0:
        keypasses_a = key_pass_a

    if crosses_h == 0 and cross_h > 0:
        crosses_h = cross_h
    if crosses_a == 0 and cross_a > 0:
        crosses_a = cross_a

    if aerials_h == 0 and aerial_h > 0:
        aerials_h = aerial_h
    if aerials_a == 0 and aerial_a > 0:
        aerials_a = aerial_a

    if dribbles_h == 0 and dribble_h > 0:
        dribbles_h = dribble_h
    if dribbles_a == 0 and dribble_a > 0:
        dribbles_a = dribble_a

    final_third_h = final_third_h or 0
    final_third_a = final_third_a or 0
    final_third_fm_h = final_third_fm_h or 0
    final_third_fm_a = final_third_fm_a or 0

    # Use match-memory final_third values as fallback when CSV values are zero (home and away)
    if final_third_h == 0 and final_third_fm_h > 0:
        final_third_h = final_third_fm_h

    if final_third_a == 0 and final_third_fm_a > 0:
        final_third_a = final_third_fm_a

    if long_balls_h == 0 and long_ball_h > 0:
        long_balls_h = long_ball_h
    if long_balls_a == 0 and long_ball_a > 0:
        long_balls_a = long_ball_a

    if bc_created_h == 0 and big_chance_h > 0:
        bc_created_h = big_chance_h
    if bc_created_a == 0 and big_chance_a > 0:
        bc_created_a = big_chance_a

    # če so v osnovnih poljih 0, uporabi dodatna FotMob polja
    if tackles_h == 0 and tackles_extra_h > 0:
        tackles_h = tackles_extra_h
    if tackles_a == 0 and tackles_extra_a > 0:
        tackles_a = tackles_extra_a

    if inter_h == 0 and inter_extra_h > 0:
        inter_h = inter_extra_h
    if inter_a == 0 and inter_extra_a > 0:
        inter_a = inter_extra_a

    if clear_h == 0 and clear_extra_h > 0:
        clear_h = clear_extra_h
    if clear_a == 0 and clear_extra_a > 0:
        clear_a = clear_extra_a

    if duels_h == 0 and duels_extra_h > 0:
        duels_h = duels_extra_h
    if duels_a == 0 and duels_extra_a > 0:
        duels_a = duels_extra_a

    if throw_h == 0 and throw_extra_h > 0:
        throw_h = throw_extra_h
    if throw_a == 0 and throw_extra_a > 0:
        throw_a = throw_extra_a

    if gk_saves_h == 0 and gk_saves_extra_h > 0:
        gk_saves_h = gk_saves_extra_h
    if gk_saves_a == 0 and gk_saves_extra_a > 0:
        gk_saves_a = gk_saves_extra_a

    # če so v osnovnih poljih 0, uporabi dodatna FotMob polja

    if acc_pass_h == 0 and pass_acc_extra_h > 0 and passes_h > 0:
        acc_pass_h = passes_h * (pass_acc_extra_h / 100.0)

    if acc_pass_h == 0 and pass_acc_extra_h > 0 and passes_h > 0:
        acc_pass_h = passes_h * (pass_acc_extra_h / 100.0)

    if acc_pass_a == 0 and pass_acc_extra_a > 0 and passes_a > 0:
        acc_pass_a = passes_a * (pass_acc_extra_a / 100.0)

    acc_pass_h = clamp(acc_pass_h, 0.0, passes_h)
    acc_pass_a = clamp(acc_pass_a, 0.0, passes_a)

    synthetic_xg_used = False

    if xg_h <= 0.05:
        base_h = (sot_h * 0.18) + (shots_h * 0.040) + (danger_h * 0.006)
        base_h += blocked_h * 0.020 + bcm_h * 0.060 + bc_h * 0.080 + corners_h * 0.010 + gk_saves_a * 0.030
        base_h += keypasses_h * 0.025 + crosses_h * 0.012 + dribbles_h * 0.015 + final_third_h * 0.004 + bc_created_h * 0.050
        tscale = clamp((minute / 90.0) ** 0.80, 0.45, 1.00)
        xg_h = clamp(base_h * tscale, 0.0, 2.60)
        synthetic_xg_used = True

    if xg_a <= 0.05:
        base_a = (sot_a * 0.20) + (shots_a * 0.042) + (danger_a * 0.0075)
        base_a += blocked_a * 0.020 + bcm_a * 0.060 + bc_a * 0.080 + corners_a * 0.010 + gk_saves_h * 0.030
        base_a += keypasses_a * 0.025 + crosses_a * 0.012 + dribbles_a * 0.015 + final_third_a * 0.004 + bc_created_a * 0.050
        tscale = clamp((minute / 90.0) ** 0.80, 0.45, 1.00)
        xg_a = clamp(base_a * tscale, 0.0, 2.60)
        synthetic_xg_used = True

    xg_total = xg_h + xg_a
    sot_total = sot_h + sot_a
    shots_total = shots_h + shots_a
    danger_total = danger_h + danger_a

    # =========================================================
    # 🔥 SOT MOMENTUM (GLOBAL PRESSURE)
    # =========================================================

    sot_diff = sot_h - sot_a

    sot_momentum = 1.0

    if sot_total >= 3:
        if abs(sot_diff) >= 2:
            sot_momentum = 1.12
        elif abs(sot_diff) == 1:
            sot_momentum = 1.06

    save_match_memory(
        home=home, away=away, minute=minute, score_home=score_home, score_away=score_away,
        shots_h=shots_h, shots_a=shots_a, sot_h=sot_h, sot_a=sot_a, danger_h=danger_h, danger_a=danger_a,
        att_h=attacks_h, att_a=attacks_a, pos_h=pos_h, pos_a=pos_a, xg_h=xg_h, xg_a=xg_a,
        odds_h=odds_home, odds_x=odds_draw, odds_a=odds_away, corners_h=corners_h, corners_a=corners_a
    )
    match_rows = load_match_memory(home, away)
    timeline = compute_timeline_factors(match_rows)
    wave = detect_attack_wave(match_rows, minute)

    time_left_fraction_value, minutes_left_real = time_left_fraction(minute)

# ZAČETEK DELA 7.2/ 8

    tempo_shots_h = shots_h / max(1, minute)
    tempo_shots_a = shots_a / max(1, minute)
    tempo_shots = shots_total / max(1, minute)
    tempo_att = (attacks_h + attacks_a) / max(1, minute)
    danger_total = danger_h + danger_a

    if danger_total > 0:
        tempo_danger = danger_total / max(1, minute)

    elif shots_total > 0:
        # fallback če danger ni podan → uporabi shots + SOT
        tempo_danger = ((shots_total * 1.2) + (sot_total * 2.0)) / max(1, minute)

    else:
        tempo_danger = 0

    tempo_danger *= clamp(0.85 + (minute / 220), 0.85, 1.15)

    tempo_danger = clamp(tempo_danger, 0, 2.2)

    xg_rate_h = xg_h / max(1, minute)
    xg_rate_a = xg_a / max(1, minute)
    xg_rate_total = xg_total / max(1, minute)

    tempo_goal_mult, tempo_notes = tempo_goal_multiplier(tempo_shots, tempo_danger, tempo_att, minute)
    xgr_mult, xgr_notes = xgr_goal_multiplier(xg_rate_total, minute)

    game_type = classify_game_type(

        # ============================================================
        # 🔥 SLOW → PRESSURE OVERRIDE (CRITICAL FIX)
        # ============================================================

        minute=minute,
        xg_total=xg_total,
        shots_total=shots_total,
        sot_total=sot_total,
        danger_total=danger_total,
        tempo_shots=tempo_shots,
        xg_rate=xg_rate_total
    )

    if game_type == "SLOW":
        if tempo_danger >= 1.10:
            game_type = "PRESSURE"
        elif tempo_danger >= 1.00 and tempo_shots >= 0.12:
            game_type = "PRESSURE"

    game_type_goal_mult = game_type_goal_multiplier(game_type)

    pass_acc_h = pass_acc_rate(acc_pass_h, passes_h)
    pass_acc_a = pass_acc_rate(acc_pass_a, passes_a)
    d2s_h = danger_to_shot_conv(shots_h, danger_h)
    d2s_a = danger_to_shot_conv(shots_a, danger_a)
    shot_q_h = shot_quality(xg_h, shots_h)
    shot_q_a = shot_quality(xg_a, shots_a)
    sot_r_h = sot_ratio(sot_h, shots_h)
    sot_r_a = sot_ratio(sot_a, shots_a)
    bc_r_h = big_chance_ratio(bc_h, shots_h)
    bc_r_a = big_chance_ratio(bc_a, shots_a)

    # PRO 75 - momentum uporablja tudi dodatne FotMob podatke, če obstajajo
    attack_h = xg_h * 3.0 + shots_h * 0.25 + sot_h * 0.85 + bc_h * 1.7 + keypasses_h * 0.16 + crosses_h * 0.05 + dribbles_h * 0.07
    attack_a = xg_a * 3.0 + shots_a * 0.25 + sot_a * 0.85 + bc_a * 1.7 + keypasses_a * 0.16 + crosses_a * 0.05 + dribbles_a * 0.07

    danger_idx_h = (
        sot_h * 1.0 +
        bc_h * 1.4 +
        xg_h * 3.8 +
        keypasses_h * 0.12 +
        bc_created_h * 0.15
    )

    danger_idx_a = (
        sot_a * 1.0 +
        bc_a * 1.4 +
        xg_a * 3.8 +
        keypasses_a * 0.12 +
        bc_created_a * 0.15
    )

    danger_idx_h = clamp(danger_idx_h, 0.0, 6.5)
    danger_idx_a = clamp(danger_idx_a, 0.0, 6.5)

    pressure_h = (
        sot_h * 1.20 +
        bc_h * 1.50 +
        danger_idx_h * 0.55 +
        tempo_shots_h * 6.5 +
        corners_h * 0.08
    )

    pressure_a = (
        sot_a * 1.20 +
        bc_a * 1.50 +
        danger_idx_a * 0.55 +
        tempo_shots_a * 6.5 +
        corners_a * 0.08
    )

    pressure_h = clamp(pressure_h, 0.0, 12.0)
    pressure_a = clamp(pressure_a, 0.0, 12.0)

    pressure_total = clamp(pressure_h + pressure_a, 0, 50)

    attack_sum = attack_h + attack_a

    if attack_sum < 0.50:
        momentum = 0.0
    else:
        momentum = (attack_h - attack_a) / attack_sum

        # =========================================================
        # MOMENTUM STABILIZER (ANTI FAKE DOMINANCE)
        # =========================================================
        if score_diff == 0:

            xg_diff = abs(xg_h - xg_a)
            pressure_diff = abs(pressure_h - pressure_a)
            danger_diff_mom = abs(danger_h - danger_a)

            # ZELO IZRAZITO nizka razlika
            if xg_diff < 0.06 and pressure_diff < 0.4 and danger_diff_mom < 2:
                momentum *= 0.30

            # RESNIČNO izrazito nizka razlika NA VEČ METRIK
            elif xg_diff < 0.12 and pressure_diff < 0.8 and danger_diff_mom < 5:
                momentum *= 0.50

            # PRIBLIZNO izenačeno - samo ko je vsaj zmerna uravnoteženost
            elif xg_diff < 0.40 and pressure_diff < 2.5:
                momentum *= 0.75

            # Sicer ohrani momentum (jasna dominacija ene strani)

    # MOMENTUM NORMALIZATION (FIX UNDERREACTION)
    if minute < 30:
        momentum *= 0.85
    elif minute < 65:
        momentum *= 1.00
    else:
        momentum *= 1.15

    # small noise filter

    # SMART NOISE FILTER (NE UBIJE MOMENTUMA)
    if abs(momentum) < 0.03:
        momentum *= 0.4

    momentum = clamp(momentum, -0.70, 0.70)

    # ============================================================
    # SPLIT CONTROL DETECTOR (CRITICAL)
    # ============================================================

    split_control = False

    if (
        attacks_h > attacks_a * 1.4
        and danger_h > danger_a * 1.5
        and xg_a > xg_h * 3
    ):
        split_control = True

    # ============================================================
    # MOMENTUM LIMITER
    # ============================================================

    if split_control:
        momentum *= 0.7

    # DEBUG (lahko kasneje izbrišeš)

    lambda_core_h = (
        xg_h * 0.60 +
        danger_h * 0.0048 +
        sot_h * 0.100 +
        shots_h * 0.028 +
        bc_h * 0.090 +
        corners_h * 0.013
    )
    lambda_core_a = (
        xg_a * 0.60 +
        danger_a * 0.0048 +
        sot_a * 0.100 +
        shots_a * 0.028 +
        bc_a * 0.090 +
        corners_a * 0.013
    )

    # PRO 75 - dodaten vpliv, samo če podatki obstajajo
    lambda_core_h += keypasses_h * 0.011 + crosses_h * 0.005 + dribbles_h * 0.006 + final_third_h * 0.0015 + bc_created_h * 0.028
    lambda_core_a += keypasses_a * 0.011 + crosses_a * 0.005 + dribbles_a * 0.006 + final_third_a * 0.0015 + bc_created_a * 0.028

    # PRESSURE MULTIPLIER (samo če je resničen pritisk)
    if pressure_h > 8 and danger_h > 40:
        lambda_core_h *= (1.0 + min(0.15, (pressure_h / 50) * 0.10))

    if pressure_a > 8 and danger_a > 40:
        lambda_core_a *= (1.0 + min(0.15, (pressure_a / 50) * 0.10))

    # BIG CHANCE AMPLIFICATION
    if bc_h >= 2 and minute >= 55:
        lambda_core_h *= 1.30

    if bc_a >= 2 and minute >= 55:
        lambda_core_a *= 1.30

    # LATE GAME SPIKE (samo ko je RESNIČEN razlog - samo dominantna ekipa)
    if minute >= 70 and abs(score_diff) == 1:
        if momentum > 0.12 and danger_h > danger_a:
            lambda_core_h *= 1.12
        elif momentum < -0.12 and danger_a > danger_h:
            lambda_core_a *= 1.12

    stage_factor = clamp(0.55 + (minute / 90.0) * 0.65, 0.55, 1.18)
    pre_h = 0.33
    pre_x = 0.34
    pre_a = 0.33

    lam_h_raw = lambda_core_h * (minutes_left_real / 90) * stage_factor
    lam_a_raw = lambda_core_a * (minutes_left_real / 90) * stage_factor

    # =========================================================
    # 🔥 SOT ROTATION DETECTOR (ELITE SIGNAL)
    # =========================================================

    if len(match_rows) >= 2:
        prev = match_rows[-2]

        prev_sot_h = prev.get("sot_h", 0)
        prev_sot_a = prev.get("sot_a", 0)

        sot_delta_h = sot_h - prev_sot_h
        sot_delta_a = sot_a - prev_sot_a

        # 🔥 BURST DETECTOR
        if sot_delta_h >= 2:
            lam_h_raw *= 1.15

        if sot_delta_a >= 2:
            lam_a_raw *= 1.15

    # 🔥 APPLY SOT MOMENTUM
    lam_h_raw *= sot_momentum
    lam_a_raw *= sot_momentum

    # TEAM STRENGTH APPLY
    lam_h_raw *= (1 + team_power)
    lam_a_raw *= (1 - team_power)

    # ===== CONTROL BASE (NE DIRAJ SPODAJ) =====
    base_h = lam_h_raw
    base_a = lam_a_raw

    if minute >= 88 and score_diff == 0:
        lam_h_raw *= 0.2
        lam_a_raw *= 0.2

    # 🔥 ANTI FAKE DRAW (PRAVO MESTO)
    if (
            game_type == "SLOW" and
            tempo_danger >= 1.20 and
            xg_total >= 0.6 and
            minute >= 40
    ):
        lam_h_raw *= 1.08
        lam_a_raw *= 1.08

    # =========================================
    # ✅ CONTROL LAYER (NOVO - 10/10 FIX)
    # =========================================
    mult_h = 1.0
    mult_a = 1.0

    # MOMENTUM CONTROL (NAMOESTO DIRECT *=)
    if momentum > 0.18:
        mult_h *= 1.12
        mult_a *= 0.92
    elif momentum < -0.18:
        mult_a *= 1.12
        mult_h *= 0.92

    lam_h_raw = blend(lam_h_raw, tempo_goal_mult, 0.30)
    lam_h_raw = blend(lam_h_raw, xgr_mult, 0.25)
    lam_h_raw = blend(lam_h_raw, game_type_goal_mult, 0.30)

    lam_a_raw = blend(lam_a_raw, tempo_goal_mult, 0.30)
    lam_a_raw = blend(lam_a_raw, xgr_mult, 0.25)
    lam_a_raw = blend(lam_a_raw, game_type_goal_mult, 0.30)

    # 🔥 CHAOS GAME BOOST (ubije remi)
    if game_type == "CHAOS" and minute >= 50:
        lam_h_raw *= 1.05
        lam_a_raw *= 1.05

    # ✅ FALLBACK MOMENTUM (SAMO če NI timeline podatkov)
    if abs(momentum) < 0.05 and timeline["n"] < 2 and minute < 55:

        fallback_raw = (
            (sot_h - sot_a) * 0.06 +
            (shots_h - shots_a) * 0.02 +
            (keypasses_h - keypasses_a) * 0.04
        )

        norm = abs(sot_h) + abs(sot_a) + abs(shots_h) + abs(shots_a) + abs(keypasses_h) + abs(keypasses_a)

        if norm > 0:
            momentum = fallback_raw / norm
        else:
            momentum = 0.0

        momentum = clamp(momentum, -0.70, 0.70)

    # ✅ DEBUG NA KONCU
    # print("DEBUG momentum FINAL:", momentum)

    momentum_boost = clamp(momentum * 1.15, -0.30, 0.30)

    # 🔥 MOMENTUM DOMINANCE LOCK
    if abs(momentum) > 0.18:
        if momentum > 0:
            lam_h_raw *= 1.08
            lam_a_raw *= 0.95
        else:
            lam_a_raw *= 1.08
            lam_h_raw *= 0.95

    # MOMENTUM EXTREME BOOST
    if abs(momentum) > 0.20:
        momentum_boost *= 1.15

    momentum_boost = clamp(momentum_boost, -0.34, 0.34)

    lam_h_raw *= (1 + momentum_boost)
    lam_a_raw *= (1 - momentum_boost)

    # 🔥 EXTREME DOMINANCE FINISHER
    if minute >= 75 and abs(momentum) > 0.15:
        if momentum > 0:
            lam_h_raw *= 1.10
        else:
            lam_a_raw *= 1.10

    # LOSING TEAM DOMINANCE BOOST (SOFTER)
    if score_diff > 0:  # home vodi
        if (
                momentum < -0.08 and
                danger_a > danger_h * 0.80 and
                xg_a > xg_h
        ):
            lam_a_raw *= 1.18

    elif score_diff < 0:  # away vodi
        if (
                momentum > 0.08 and
                danger_h > danger_a * 0.80 and
                xg_h > xg_a
        ):
            lam_h_raw *= 1.18

    # COMBINED QUALITY BOOST (SMART)
    quality_h = (shot_q_h * 0.6) + (sot_r_h * 0.4)
    quality_a = (shot_q_a * 0.6) + (sot_r_a * 0.4)

    if quality_h >= 0.16:
        lam_h_raw *= 1.07
    elif quality_h >= 0.12:
        lam_h_raw *= 1.03

    if quality_a >= 0.16:
        lam_a_raw *= 1.07
    elif quality_a >= 0.12:
        lam_a_raw *= 1.03

    # ============================================================
    # XG DOMINANCE OVERRIDE (KLJUČNO)
    # ============================================================

    if minute >= 45:
        if xg_h > xg_a * 1.4:
            lam_h_raw *= 1.15
        elif xg_a > xg_h * 1.4:
            lam_a_raw *= 1.15

    # 🔥 UNDERDOG REAL BOOST
    if odds_away >= 3.5 and momentum < -0.12 and xg_a > xg_h:
        lam_a_raw *= 1.12

    if odds_home >= 3.5 and momentum > 0.12 and xg_h > xg_a:
        lam_h_raw *= 1.12

    # UNDERDOG PRESSURE RULE
    if (
            odds_away >= 6.0 and
            danger_a >= danger_h * 0.95 and
            minute >= 55
    ):
        lam_a_raw *= 1.18

    if (
            odds_home >= 6.0 and
            danger_h >= danger_a * 0.95 and
            minute >= 55
    ):
        lam_h_raw *= 1.18

    # EXTREME UNDERDOG REVERSAL
    if (
            odds_away >= 5.5 and
            momentum < -0.15 and
            xg_a > xg_h * 1.2 and
            minute >= 50
    ):
        lam_a_raw *= 1.20

    if (
            odds_home >= 5.5 and
            momentum > 0.15 and
            xg_h > xg_a * 1.2 and
            minute >= 50
    ):
        lam_h_raw *= 1.20

    # ============================================================
    # PRESSURE STABILIZER (UPGRADED)
    # ============================================================

    if pressure_total > 22:
        lam_h_raw *= 1.10
        lam_a_raw *= 1.10

    elif pressure_total > 16:
        lam_h_raw *= 1.05
        lam_a_raw *= 1.05

    if timeline["n"] >= 2:
        lam_h_raw *= timeline["trend_home"]
        lam_a_raw *= timeline["trend_away"]

    if wave["active"]:
        lam_h_raw *= wave["home"]
        lam_a_raw *= wave["away"]

    # SMART DRAW BOOST PRO (FIX REAL DOMINANCE)
    if score_diff == 0 and minute >= 60:

        # 🔥 SOT PRESSURE DRAW KILLER
        if abs(sot_h - sot_a) >= 1 and abs(danger_h - danger_a) >= 10:
            if sot_h > sot_a:
                lam_h_raw *= 1.12
            else:
                lam_a_raw *= 1.12
    # ============================================================
    # ZAČETEK DELA 7.3 / 8
    # DOMINANCE / FLOW / LATE GAME / HISTORY / META
    # ============================================================

    dominance = (danger_h - danger_a) / max(1, danger_total)
    danger_dominance = dominance  # save danger-based dominance for return dict

    # ============================================================
    # BASE DOMINANCE
    # ============================================================

    # DOMA dominira
    if momentum > 0.04 and dominance > 0.10:
        lam_h_raw *= 1.15

    # GOST dominira
    elif momentum < -0.04 and dominance < -0.10:
        lam_a_raw *= 1.15

    # fallback na danger dominance
    elif dominance > 0.18:
        lam_h_raw *= 1.10

    elif dominance < -0.18:
        lam_a_raw *= 1.10

    # res balanced
    else:
        lam_h_raw *= 1.02
        lam_a_raw *= 1.02

    # ============================================================
    # LATE DOMINANCE KILLER
    # ============================================================

    if minute >= 55:
        if momentum > 0.12 and xg_h > xg_a:
            lam_h_raw *= 1.20
        elif momentum < -0.12 and xg_a > xg_h:
            lam_a_raw *= 1.20

    # ============================================================
    # STRONG LATE DRAW PUSH
    # ============================================================

    if minute >= 72 and abs(score_diff) == 1:

        lam_total_now = lam_h_raw + lam_a_raw

        # HOME lovi
        if score_diff < 0:
            lam_h_raw *= 1.35
            lam_a_raw *= 0.90

            if lam_total_now > 0.40:
                lam_h_raw *= 1.15

        # AWAY lovi
        elif score_diff > 0:
            lam_a_raw *= 1.35
            lam_h_raw *= 0.90

            if lam_total_now > 0.40:
                lam_a_raw *= 1.15

    # ============================================================
    # LATE DRAW PROTECTION
    # ============================================================

    if minute >= 70 and abs(score_diff) == 1:

        lam_total_now = lam_h_raw + lam_a_raw

        # HOME zaostaja
        if score_diff < 0:
            if abs(momentum) < 0.45:
                lam_h_raw *= 1.20
                lam_a_raw *= 0.93

            if lam_total_now > 0.45:
                lam_h_raw *= 1.10

        # AWAY zaostaja
        elif score_diff > 0:
            if abs(momentum) < 0.45:
                lam_a_raw *= 1.20
                lam_h_raw *= 0.93

            if lam_total_now > 0.45:
                lam_a_raw *= 1.10

    # ============================================================
    # LEAD PROTECTION
    # ============================================================

    if minute >= 60:
        if score_diff == -1 and danger_a > danger_h * 1.4:
            lam_a_raw *= 1.12
            lam_h_raw *= 0.88

        elif score_diff == 1 and danger_h > danger_a * 1.4:
            lam_h_raw *= 1.12
            lam_a_raw *= 0.88

    # ============================================================
    # LEAD CONTROL (late game fix)
    # ============================================================

    if minute >= 75 and score_diff == 1:

        if momentum > 0:
            lam_h_raw *= 1.12
            lam_a_raw *= 0.90

        elif momentum < 0:
            lam_a_raw *= 1.08

    # ============================================================
    # LOSING TEAM LAST PUSH
    # ============================================================

    if minute >= 80:

        # HOME vodi -> AWAY push
        if score_home > score_away:
            if momentum < -0.02 and pressure_a > pressure_h:
                lam_a_raw *= 1.18

            if sot_a > sot_h:
                lam_a_raw *= 1.08

            if abs(danger_h - danger_a) <= 6:
                lam_a_raw *= 1.05

        # AWAY vodi -> HOME push
        elif score_away > score_home:
            if momentum > 0.02 and pressure_h > pressure_a:
                lam_h_raw *= 1.18

            if sot_h > sot_a:
                lam_h_raw *= 1.08

            if abs(danger_h - danger_a) <= 6:
                lam_h_raw *= 1.05

    # ============================================================
    # RED CARD
    # ============================================================

    if red_h > red_a:
        lam_h_raw *= 0.82
        lam_a_raw *= 1.10
    elif red_a > red_h:
        lam_a_raw *= 0.82
        lam_h_raw *= 1.10

    # ============================================================
    # IMPLIED ODDS REALITY CHECK
    # ============================================================

    imp_h, imp_x, imp_a, overround = implied_probs_from_odds(
        odds_home, odds_draw, odds_away
    )

    if imp_h > 0 and imp_a > 0:
        if lam_h_raw > lam_a_raw * 1.90 and imp_h < 0.45 and minute < 35:
            lam_h_raw *= 0.90
        if lam_a_raw > lam_h_raw * 1.90 and imp_a < 0.45 and minute < 35:
            lam_a_raw *= 0.90

    # ============================================================
    # FINAL REALITY CHECK
    # ============================================================

    if minute >= 50:
        if xg_h > xg_a * 1.3 and lam_h_raw <= lam_a_raw:
            lam_h_raw *= 1.12
        elif xg_a > xg_h * 1.3 and lam_a_raw <= lam_h_raw:
            lam_a_raw *= 1.12

    lam_h_raw = clamp(max(0.0, lam_h_raw), 0.0, 1.60)
    lam_a_raw = clamp(max(0.0, lam_a_raw), 0.0, 1.60)

    # ============================================================
    # CONTROL FIX
    # ============================================================

    ratio_h = lam_h_raw / max(0.0001, base_h)
    ratio_a = lam_a_raw / max(0.0001, base_a)

    ratio_h = clamp(ratio_h, 0.55, 1.95)
    ratio_a = clamp(ratio_a, 0.55, 1.95)

    lam_h_raw = base_h * ratio_h
    lam_a_raw = base_a * ratio_a

    # ============================================================
    # APPLY CONTROL LAYER
    # ============================================================

    mult_h = clamp(mult_h, 0.75, 1.45)
    mult_a = clamp(mult_a, 0.75, 1.45)

    lam_h_raw *= mult_h
    lam_a_raw *= mult_a

    # ============================================================
    # CFOS PATCH v1.0 (BIG CHANCE + PRESSURE)
    # ============================================================

    if bc_a >= 2 and minute >= 65:
        lam_a_raw *= 1.25

    if bc_h >= 2 and minute >= 65:
        lam_h_raw *= 1.25

    if pressure_a > pressure_h * 1.6:
        lam_a_raw *= 1.20

    if pressure_h > pressure_a * 1.6:
        lam_h_raw *= 1.20

    lam_h_raw = clamp(lam_h_raw, 0.0, 1.60)
    lam_a_raw = clamp(lam_a_raw, 0.0, 1.60)

    # ============================================================
    # 🔥 ANTI COUNTER + FALSE MOMENTUM FIX (FINAL)
    # ============================================================

    lam_total_before = lam_h_raw + lam_a_raw

    anti_high_tempo = (tempo_shots > 0.22 or tempo_danger > 1.15)
    anti_high_lambda = (lam_h_raw + lam_a_raw) > 1.20
    anti_no_wave = not wave["active"]

    danger_ratio = safe_div(danger_h, danger_a, 1.0)

    # FIX 1: OVERPRESSURE COUNTER
    if minute >= 60:
        if anti_high_tempo and anti_high_lambda and anti_no_wave:
            lam_h_raw *= 0.80
            lam_a_raw *= 1.30

    # FIX 2: LEADING TEAM RISK (CORRECTED)
    if minute >= 60 and score_diff == 1:
        if abs(momentum) > 0.18:
            # zmanjšaj dominantno stran
            if lam_a_raw > lam_h_raw:
                lam_a_raw *= 0.85
            else:
                lam_h_raw *= 0.85

    # FIX 3: FAKE DOMINANCE
    if minute >= 60 and sot_h >= 3 and attacks_h > attacks_a:
        if anti_no_wave and danger_ratio < 1.30:
            lam_h_raw *= 0.85

    # FIX 4: FALSE MOMENTUM TRAP  ✅ (NOVO)
    if minute >= 55:
        if anti_no_wave and tempo_shots < 0.28:
            if momentum > 0.12:
                lam_h_raw *= 0.85
                lam_a_raw *= 0.85

    # FIX 5: LAMBDA RATIO LIMIT
    if minute >= 60:
        lam_a_to_h_ratio = safe_div(lam_a_raw, lam_h_raw, 1.0)
        if lam_a_to_h_ratio > 4.0:
            lam_a_raw *= 0.75
        lam_h_to_a_ratio = safe_div(lam_h_raw, lam_a_raw, 1.0)
        if lam_h_to_a_ratio > 4.0:
            lam_h_raw *= 0.75

    # NORMALIZACIJA
    lam_total_after = lam_h_raw + lam_a_raw
    if lam_total_after > 0:
        scale = lam_total_before / lam_total_after
        lam_h_raw *= scale
        lam_a_raw *= scale

    # FINAL CLAMP
    lam_h_raw = clamp(lam_h_raw, 0.0, 1.60)
    lam_a_raw = clamp(lam_a_raw, 0.0, 1.60)
    # ============================================================
    # CFOS-XG PRO 77 STABILIZERJI
    # ============================================================

    if minute >= 70 and game_type not in ("PRESSURE", "ATTACK_WAVE", "CHAOS"):
        lam_h_raw *= 0.93
        lam_a_raw *= 0.93

    chaos_index = (tempo_danger * 1.4) + tempo_shots
    if chaos_index > 1.40:
        lam_h_raw *= 1.05
        lam_a_raw *= 1.05

    lam_c_raw = 0.0

    if game_type in ("PRESSURE", "ATTACK_WAVE", "CHAOS"):
        lam_c_raw += 0.015

        if score_diff == 0 and minute >= 65 and game_type == "CHAOS":
            lam_c_raw += 0.02
        elif score_diff == 0 and minute >= 65 and game_type in ("PRESSURE", "ATTACK_WAVE"):
            lam_c_raw += 0.01

        if pressure_total >= 18 and ((xg_total >= 0.9) or (sot_total >= 4) or (danger_total >= 75)):
            lam_c_raw += 0.02

        if (keypasses_h + keypasses_a) >= 8 and minute >= 55:
            lam_c_raw += 0.01

    lam_c_raw = clamp(lam_c_raw, 0.0, 0.08)

    lam_total_raw = lam_h_raw + lam_a_raw + lam_c_raw
    if lam_total_raw > 2.10:
        scale = 2.10 / lam_total_raw
        lam_h_raw *= scale
        lam_a_raw *= scale
        lam_c_raw *= scale
        lam_total_raw = lam_h_raw + lam_a_raw + lam_c_raw

    p_goal_raw = 1 - math.exp(-lam_total_raw) if lam_total_raw > 0 else 0.0

    # ============================================================
    # HISTORY LAMBDA APPLY
    # ============================================================

    history = load_history()

    lf_goal, n_goal = learn_factor_goal(
        history=history,
        minute=minute,
        xg_total=xg_total,
        sot_total=sot_total,
        shots_total=shots_total,
        score_diff=score_diff,
        game_type=game_type,
        danger_total=danger_total
    )

    if history is not None and lf_goal is not None and n_goal >= 3:
        lam_h_raw *= lf_goal
        lam_a_raw *= lf_goal

    lam_h_raw = clamp(lam_h_raw, 0.01, 5.0)
    lam_a_raw = clamp(lam_a_raw, 0.01, 5.0)

    # ============================================================
    # COUNTER PRESSURE DETECTOR
    # ============================================================

    if minute >= 58:

        danger_ratio_h = danger_h / max(1, danger_a)
        danger_ratio_a = danger_a / max(1, danger_h)

        # AWAY pritiska -> HOME counter
        if sot_a > sot_h and danger_ratio_a >= 0.85 and shots_h <= shots_a + 2:
            lam_h_raw *= 1.15

        # HOME pritiska -> AWAY counter
        if sot_h > sot_a and danger_ratio_h >= 0.85 and shots_a <= shots_h + 2:
            lam_a_raw *= 1.15

    # ============================================================
    # LOW VOLUME FINISHER
    # ============================================================

    if minute >= 60:

        if shots_h <= 8 and sot_h <= 2 and momentum < -0.05:
            lam_h_raw *= 1.12

        if shots_a <= 8 and sot_a <= 2 and momentum > 0.05:
            lam_a_raw *= 1.12

    # ============================================================
    # FAKE DOMINANCE FLIP
    # ============================================================

    if minute >= 62:

        if sot_a > sot_h and danger_a >= danger_h * 0.90 and attacks_a < attacks_h:
            lam_h_raw *= 1.10

        if sot_h > sot_a and danger_h >= danger_a * 0.90 and attacks_h < attacks_a:
            lam_a_raw *= 1.10

    # ============================================================
    # GLOBAL FAKE CONTROL DETECTOR
    # ============================================================

    fake_control = False

    losing_side = "HOME" if score_diff < 0 else "AWAY"
    leading_side = "AWAY" if score_diff < 0 else "HOME"

    shots_losing = shots_h if losing_side == "HOME" else shots_a
    shots_leading = shots_a if losing_side == "HOME" else shots_h

    sot_losing = sot_h if losing_side == "HOME" else sot_a
    sot_leading = sot_a if losing_side == "HOME" else sot_h

    danger_losing = danger_h if losing_side == "HOME" else danger_a
    danger_leading = danger_a if losing_side == "HOME" else danger_h

    if (
        minute >= 65
        and abs(score_diff) == 1
        and shots_losing >= shots_leading * 0.70
        and sot_losing >= sot_leading * 0.60
        and tempo_danger < 1.08
        and game_type in ("BALANCED", "PRESSURE")
    ):
        fake_control = True

    if fake_control:
        if losing_side == "HOME":
            lam_h_raw *= 1.28
            lam_a_raw *= 0.88
        else:
            lam_a_raw *= 1.28
            lam_h_raw *= 0.88

    # ============================================================
    # GLOBAL LATE BOOST LIMITER (CRITICAL FIX)
    # ============================================================

    if minute >= 70 and abs(score_diff) == 1:

        # max razmerje med ekipama
        max_ratio = 1.75

        if lam_h_raw > lam_a_raw * max_ratio:
            lam_h_raw = lam_a_raw * max_ratio

        if lam_a_raw > lam_h_raw * max_ratio:
            lam_a_raw = lam_h_raw * max_ratio

        # dodatno: omeji absolutno eksplozijo
        lam_total_tmp = lam_h_raw + lam_a_raw

        if lam_total_tmp > 1.35:
            scale = 1.35 / lam_total_tmp
            lam_h_raw *= scale
            lam_a_raw *= scale

    # Overflow protection: clamp raw lambdas to finite range
    if not math.isfinite(lam_h_raw):
        lam_h_raw = 0.0
    if not math.isfinite(lam_a_raw):
        lam_a_raw = 0.0
    if not math.isfinite(lam_c_raw):
        lam_c_raw = 0.0
    lam_h_raw = clamp(lam_h_raw, 0.0, 10.0)
    lam_a_raw = clamp(lam_a_raw, 0.0, 10.0)
    lam_c_raw = clamp(lam_c_raw, 0.0, 10.0)

    lam_h = clamp(lam_h_raw, 0.0, 1.60)
    lam_a = clamp(lam_a_raw, 0.0, 1.60)
    lam_c = clamp(lam_c_raw * lf_goal * timeline["trend_factor_goal"] * wave["goal"], 0.0, 0.08)

    # ============================================================
    # PRESSURE BOOST
    # ============================================================

    if minute >= 60 and danger_h > danger_a * 2 and tempo_danger > 1.0:
        boost = 1.0 + (danger_h / max(danger_a, 1)) * 0.15
        lam_h *= min(boost, 1.6)

    lam_total = lam_h + lam_a + lam_c

    if lam_total > 2.20:
        scale = 2.20 / lam_total
        lam_h *= scale
        lam_a *= scale
        lam_c *= scale
        lam_total = lam_h + lam_a + lam_c

    # ============================================================
    # SECOND HALF BOOST
    # ============================================================

    if minute >= 46:
        lam_h *= 1.25
        lam_a *= 1.25

    # ============================================================
    # ANTI 0-0 KILLER
    # ============================================================

    if minute >= 55:
        if tempo_danger > 1.2 or tempo_shots > 0.18:
            lam_h *= 1.08
            lam_a *= 1.08

        if abs(momentum) > 0.15:
            lam_h *= 1.06
            lam_a *= 1.06

    lam_h = clamp(lam_h, 0.0, 1.60)
    lam_a = clamp(lam_a, 0.0, 1.60)
    lam_total = lam_h + lam_a + lam_c

    # ============================================================
    # CFOS OVERPRESSURE + HIGH LAMBDA + COUNTER EQUALIZER
    # ============================================================

    lam_ratio = 0.0
    high_tempo = False
    high_lambda = False
    no_wave = True
    overpressure_home = False
    overpressure_away = False
    leading_side = "DRAW"

    if minute >= 55:

        score_diff = score_home - score_away

        if lam_h > 0:
            lam_ratio = lam_a / lam_h
        else:
            lam_ratio = 2.0

        tempo_shots_chk = float(tempo_shots or 0.0)
        tempo_danger_chk = float(tempo_danger or 0.0)
        high_tempo = (tempo_shots_chk > 0.22 or tempo_danger_chk > 1.15)

        high_pressure_home = pressure_h > pressure_a * 1.25
        high_pressure_away = pressure_a > pressure_h * 1.25

        lam_total = lam_h + lam_a + lam_c
        p_goal_est = 1 - math.exp(-lam_total) if lam_total > 0 else 0.0
        high_lambda = (
            lam_total > 1.20
            or p_goal_est > 0.65
            or lam_h > 0.80
            or lam_a > 0.80
        )

        attack_wave = "YES" if wave["active"] else "NO"
        no_wave = not wave["active"]

        overpressure_home = (
            high_tempo
            and high_pressure_home
            and high_lambda
            and no_wave
        )

        overpressure_away = (
            high_tempo
            and high_pressure_away
            and high_lambda
            and no_wave
        )

        if score_diff < 0:
            leading_side = "AWAY"
            if lam_ratio > 1.4 and (overpressure_away or high_lambda):
                lam_a *= 0.80
                lam_h *= 1.22
                lam_c += 0.08

        elif score_diff > 0:
            leading_side = "HOME"
            inv_lam_ratio = (1 / lam_ratio) if lam_ratio > 0 else 2.0
            if inv_lam_ratio > 1.4 and (overpressure_home or high_lambda):
                lam_h *= 0.80
                lam_a *= 1.22
                lam_c += 0.08

        if momentum > 0.35 and danger_h > danger_a * 1.5:
            lam_h *= 1.10
        elif momentum < -0.35 and danger_a > danger_h * 1.5:
            lam_a *= 1.10

        if lam_total > 1.55:
            lam_h *= 0.92
            lam_a *= 0.92
            lam_c += 0.05

        if minute >= 70 and (overpressure_home or overpressure_away):
            lam_c += 0.06

        lam_h = clamp(lam_h, 0.0, 1.60)
        lam_a = clamp(lam_a, 0.0, 1.60)
        lam_c = clamp(lam_c, 0.0, 0.20)
        lam_total = lam_h + lam_a + lam_c

    # ============================================================
    # UPSET FILTER
    # ============================================================

    if minute >= 55:

        if imp_h < imp_a and lam_a > lam_h * 1.35:
            lam_a *= 0.88

        if imp_a < imp_h and lam_h > lam_a * 1.35:
            lam_h *= 0.88

    # ============================================================
    # COUNTER GOAL PROTECTION
    # ============================================================

    if minute >= 65:

        if momentum > 0.14 and danger_h > danger_a * 1.5:
            lam_a *= 0.85

        if momentum < -0.14 and danger_a > danger_h * 1.5:
            lam_h *= 0.85

    # ============================================================
    # COUNTER ATTACK RISK
    # ============================================================

    counter_boost_home = 1.0
    counter_boost_away = 1.0
    MAX_COUNTER_BOOST = 1.70  # hard cap to prevent runaway lambda amplification

    if score_diff < 0 and minute >= 70:
        if momentum > 0.12 and lam_a < 0.40:
            # Enhanced: scale boost with xG quality of away team
            xg_quality_boost = 1.15 if (xg_a > 0 and xg_h > 0 and xg_a > xg_h) else 1.0
            counter_boost_away = min(1.55 * xg_quality_boost, MAX_COUNTER_BOOST)

    if score_diff > 0 and minute >= 70:
        if momentum < -0.12 and lam_h < 0.40:
            # Enhanced: scale boost with xG quality of home team
            xg_quality_boost = 1.15 if (xg_h > 0 and xg_a > 0 and xg_h > xg_a) else 1.0
            counter_boost_home = min(1.55 * xg_quality_boost, MAX_COUNTER_BOOST)

    lam_h *= counter_boost_home
    lam_a *= counter_boost_away

    # ============================================================
    # LEADING TEAM COUNTER GOAL
    # ============================================================

    counter_boost_home = 1.0
    counter_boost_away = 1.0

    if score_diff > 0:
        if momentum < -0.18 and tempo_shots > 0.18:
            counter_boost_home = 1.22
            counter_boost_away = 0.88

    elif score_diff < 0:
        if momentum > 0.18 and tempo_shots > 0.18:
            counter_boost_away = 1.22
            counter_boost_home = 0.88

    lam_h *= counter_boost_home
    lam_a *= counter_boost_away

    # ============================================================
    # LAMBDA ROTATION (CRITICAL FIX)
    # ============================================================

    if lam_h > 0:
        lam_ratio_sc = lam_a / lam_h
        if lam_ratio_sc > 3.0:
            scale = 3.0 / lam_ratio_sc
            lam_a *= scale
    lam_total = lam_h + lam_a + lam_c

    # ============================================================
    # MIN FLOW
    # ============================================================

    if 0 < lam_total < 0.35:
        scale = 0.35 / lam_total
        lam_h *= scale
        lam_a *= scale
        lam_total = lam_h + lam_a + lam_c

    if lam_total > 2.20:
        scale = 2.20 / lam_total
        lam_h *= scale
        lam_a *= scale
        lam_c *= scale
        lam_total = lam_h + lam_a + lam_c

    p_goal = 1 - math.exp(-lam_total) if lam_total > 0 else 0.0
    p_goal = clamp(p_goal, 0.0, 1.0)

    if (lam_h + lam_a) > 0:
        p_home_next = (lam_h / (lam_h + lam_a)) * p_goal
        p_away_next = (lam_a / (lam_h + lam_a)) * p_goal
    else:
        p_home_next = 0.0
        p_away_next = 0.0

    p_no_goal = 1 - p_goal

    rate_per_min = lam_total / max(1, minutes_left_real)
    p_goal_5 = 1 - math.exp(-rate_per_min * min(5, minutes_left_real))
    p_goal_10 = 1 - math.exp(-rate_per_min * min(10, minutes_left_real))

    pre_h = clamp((score_diff * 0.08) + (lam_h * 0.20) + 0.32, 0.05, 0.85)
    pre_a = clamp((-score_diff * 0.08) + (lam_a * 0.20) + 0.30, 0.05, 0.85)
    pre_x = clamp(1.0 - pre_h - pre_a, 0.05, 0.80)

    # ============================================================
    # DRAW CRUSHERS
    # ============================================================

    if minute >= 30 and tempo_danger >= 1.15:
        pre_x *= 0.80

    if abs(momentum) > 0.12:
        pre_x *= 0.82

    if minute >= 60:
        if abs(lam_h - lam_a) > 0.12:
            pre_x *= 0.75

    if tempo_danger > 1.2:
        pre_x *= 0.80

    if minute >= 60 and game_type in ("PRESSURE", "ATTACK_WAVE"):
        if tempo_danger >= 1.10 and tempo_shots >= 0.15:
            pre_x *= 0.75

        if pressure_total >= 14:
            pre_x *= 0.85

        if p_goal >= 0.35:
            pre_x *= 0.85

    if minute >= 45 and score_diff == 0 and tempo_shots < 0.18 and abs(momentum) < 0.08:
        pre_x = pre_x + (pre_x * 0.08)

    if abs(lam_h - lam_a) < 0.12 and lam_total > 0.45 and abs(momentum) < 0.08:
        pre_x *= 1.02

    s_pre = pre_h + pre_x + pre_a
    pre_h /= s_pre
    pre_x /= s_pre
    pre_a /= s_pre

    # ============================================================
    # MONTE CARLO
    # ============================================================

    sim_used = adaptive_simulations(pre_h, pre_x, pre_a)

    w_h = 0
    w_x = 0
    w_a = 0

    for _ in range(sim_used):
        gh, ga = bivariate_poisson_sample(lam_h, lam_a, lam_c)
        fh = score_home + gh
        fa = score_away + ga

        if fh > fa:
            w_h += 1
        elif fh == fa:
            w_x += 1
        else:
            w_a += 1

    mc_h_raw = w_h / sim_used
    mc_x_raw = w_x / sim_used
    mc_a_raw = w_a / sim_used

    if minute >= 75 and abs(lam_h - lam_a) > 0.10:
        mc_x_raw *= 0.75 if minute >= 80 else 0.78

    if minute >= 60 and game_type in ("PRESSURE", "ATTACK_WAVE"):
        if tempo_danger >= 1.10 and p_goal >= 0.42:
            mc_x_raw *= 0.90

        if pressure_total >= 14 and abs(momentum) >= 0.06:
            mc_x_raw *= 0.93

    # ============================================================
    # LEARN FACTOR 1X2
    # ============================================================

    rh, rx, ra, n_1x2 = learn_factor_1x2(
        history=history,
        minute=minute,
        xg_total=xg_total,
        sot_total=sot_total,
        shots_total=shots_total,
        score_diff=score_diff,
        game_type=game_type,
        danger_total=danger_total
    )

    mc_h_adj = mc_h_raw * rh
    mc_x_adj = mc_x_raw * min(rx, 1.05)
    mc_a_adj = mc_a_raw * ra

    # ============================================================
    # HISTORY SCORE BIAS
    # ============================================================

    hist_bias = history_score_bias(
        history=history,
        minute=minute,
        xg_total=xg_total,
        sot_total=sot_total,
        shots_total=shots_total,
        score_diff=score_diff,
        game_type=game_type,
        danger_total=danger_total
    )

    if hist_bias is not None:
        hist_n = hist_bias["n"]
        hist_home = hist_bias["p_home"]
        hist_draw = hist_bias["p_draw"]
        hist_away = hist_bias["p_away"]
    else:
        hist_n = 0
        hist_home = mc_h_adj
        hist_draw = mc_x_adj
        hist_away = mc_a_adj

    # ============================================================
    # SAVE BUCKET HISTORY
    # ============================================================

    hist_home_bucket = hist_home
    hist_draw_bucket = hist_draw
    hist_away_bucket = hist_away

    # ============================================================
    # MATCH MEMORY
    # ============================================================

    mem_rows = load_match_results(home, away)
    mem_n = len(mem_rows)

    mem_home = 0.0
    mem_draw = 0.0
    mem_away = 0.0

    for r in mem_rows:
        res = str(r.get("result_1x2", "")).strip().upper()

        if res == "HOME":
            mem_home += 1
        elif res == "DRAW":
            mem_draw += 1
        elif res == "AWAY":
            mem_away += 1

    if mem_n > 0:
        mem_home /= mem_n
        mem_draw /= mem_n
        mem_away /= mem_n

    # ============================================================
    # MONTE CARLO HISTORY
    # ============================================================

    mc_n = 50
    mc_home_hist = mc_h_adj
    mc_draw_hist = mc_x_adj
    mc_away_hist = mc_a_adj

    # ============================================================
    # COMBINE ALL HISTORY
    # ============================================================

    total_n = hist_n + mem_n + mc_n

    if total_n > 0:
        hist_home = (
            hist_home_bucket * hist_n +
            mem_home * mem_n +
            mc_home_hist * mc_n
        ) / total_n

        hist_draw = (
            hist_draw_bucket * hist_n +
            mem_draw * mem_n +
            mc_draw_hist * mc_n
        ) / total_n

        hist_away = (
            hist_away_bucket * hist_n +
            mem_away * mem_n +
            mc_away_hist * mc_n
        ) / total_n

    # ============================================================
    # HISTORY BIAS PRINT
    # ============================================================

    print()
    print("============= HISTORY BIAS =============")

    print("BUCKET")
    print("HOME", round(hist_home_bucket, 4))
    print("DRAW", round(hist_draw_bucket, 4))
    print("AWAY", round(hist_away_bucket, 4))
    print("N   ", hist_n)

    print()
    print("MATCH MEMORY")
    print("HOME", round(mem_home, 4))
    print("DRAW", round(mem_draw, 4))
    print("AWAY", round(mem_away, 4))
    print("N   ", mem_n)

    print()
    print("MONTE CARLO")
    print("HOME", round(mc_home_hist, 4))
    print("DRAW", round(mc_draw_hist, 4))
    print("AWAY", round(mc_away_hist, 4))
    print("N   ", mc_n)

    print()
    print("FINAL HISTORY")
    print("HOME", round(hist_home, 4))
    print("DRAW", round(hist_draw, 4))
    print("AWAY", round(hist_away, 4))
    print("TOTAL", total_n)

    print("========================================")
    print()

    if hist_home >= hist_draw and hist_home >= hist_away:
        history_pred = "HOME"
    elif hist_away >= hist_home and hist_away >= hist_draw:
        history_pred = "AWAY"
    else:
        history_pred = "DRAW"

    # ============================================================
    # META-META IQ ENGINE
    # ============================================================

    mc_h_adj, mc_x_adj, mc_a_adj, self_trust = apply_meta_meta_iq(
        mc_h_adj=mc_h_adj,
        mc_x_adj=mc_x_adj,
        mc_a_adj=mc_a_adj,
        hist_home=hist_home,
        hist_draw=hist_draw,
        hist_away=hist_away,
        lam_h=lam_h,
        lam_a=lam_a,
        momentum=momentum
    )

    # ============================================================
    # META CALIBRATION
    # ============================================================

    mc_h_before_meta = mc_h_adj
    mc_x_before_meta = mc_x_adj
    mc_a_before_meta = mc_a_adj

    mc_h_adj, mc_x_adj, mc_a_adj = meta_calibrate_1x2(
        mc_h=mc_h_adj,
        mc_x=mc_x_adj,
        mc_a=mc_a_adj,
        imp_h=imp_h,
        imp_x=imp_x,
        imp_a=imp_a,
        lam_h=lam_h,
        lam_a=lam_a,
        p_goal=p_goal,
        momentum=momentum,
        pressure_h=pressure_h,
        pressure_a=pressure_a,
        xg_h=xg_h,
        xg_a=xg_a,
        minute=minute,
        score_diff=score_diff,
        team_power=team_power,
        hist_n=hist_n
    )

    print("\n================ META CALIBRATION ================")
    print("Minute".ljust(18), minute)

    print("BEFORE META")
    print("HOME".ljust(8), f"{mc_h_before_meta:.4f}")
    print("DRAW".ljust(8), f"{mc_x_before_meta:.4f}")
    print("AWAY".ljust(8), f"{mc_a_before_meta:.4f}")

    print("\nAFTER META")
    print("HOME".ljust(8), f"{mc_h_adj:.4f}")
    print("DRAW".ljust(8), f"{mc_x_adj:.4f}")
    print("AWAY".ljust(8), f"{mc_a_adj:.4f}")

    print("=================================================\n")

    # ============================================================
    # SPLIT CONTROL META CORRECTION
    # ============================================================

    if split_control:
        mc_x_adj *= 1.35  # draw boost +35%
        mc_a_adj *= 0.80  # away reduce -20%
        mc_h_adj *= 1.10  # home slight boost +10%

    s = mc_h_adj + mc_x_adj + mc_a_adj
    if s > 1e-9:
        mc_h_adj /= s
        mc_x_adj /= s
        mc_a_adj /= s
    else:
        mc_h_adj, mc_x_adj, mc_a_adj = mc_h_raw, mc_x_raw, mc_a_raw

    # ============================================================
    # REAL-TIME vs HISTORY MIX (AFTER META)
    # ============================================================

    rt_strength = (
        abs(lam_h - lam_a) * 2 +
        abs(p_home_next - p_away_next) +
        abs(mc_h_adj - mc_a_adj)
    )

    if rt_strength > 1:
        rt_strength = 1

    effective_hist_n = hist_n + mem_n

    if mem_n >= 2:
        effective_hist_n += 10

    hist_conf = effective_hist_n / 50
    if hist_conf > 1:
        hist_conf = 1

    hist_weight = hist_conf * (1 - rt_strength * 0.6) * 0.35
    rt_weight = 1 - hist_weight

    mc_h_adj = mc_h_adj * rt_weight + hist_home * hist_weight
    mc_x_adj = mc_x_adj * rt_weight + hist_draw * hist_weight
    mc_a_adj = mc_a_adj * rt_weight + hist_away * hist_weight

    s = mc_h_adj + mc_x_adj + mc_a_adj
    if s > 1e-9:
        mc_h_adj /= s
        mc_x_adj /= s
        mc_a_adj /= s
    else:
        mc_h_adj, mc_x_adj, mc_a_adj = mc_h_raw, mc_x_raw, mc_a_raw
# ZAČETEK DELA 7.4/ 8

    # ============================================================
    # LATE EQUALIZER BALANCER (SOFT FIX)
    # ============================================================
    if minute >= 70 and abs(score_diff) == 1:

        # HOME izgublja
        if score_diff < 0:
            lam_h *= 1.20
            lam_a *= 0.92
            lam_h += 0.12

        # AWAY izgublja
        else:
            lam_a *= 1.20
            lam_h *= 0.92
            lam_a += 0.12

        lam_h = clamp(lam_h, 0.0, 1.80)
        lam_a = clamp(lam_a, 0.0, 1.80)
        lam_c = clamp(lam_c, 0.0, 0.08)
        lam_total = clamp(lam_h + lam_a + lam_c, 0.0, 2.20)

        p_goal = 1 - math.exp(-lam_total)
        p_no_goal = math.exp(-lam_total)

        lam_attack = lam_h + lam_a
        if lam_attack > 0:
            p_home_next = (lam_h / lam_attack) * p_goal
            p_away_next = (lam_a / lam_attack) * p_goal
        else:
            p_home_next = 0.0
            p_away_next = 0.0
    # ============================================================
    # LATE DRAW PROTECTION AFTER HISTORY
    # samo če ekipa, ki izgublja, res pritiska za izenačenje
    # ============================================================
    if minute >= 72 and abs(score_diff) == 1 and p_goal >= 0.40:

        draw_protection = False

        # DOMA izgublja -> doma mora res pritiskati
        if score_diff < 0:
            if (
                    momentum >= 0.08
                    and pressure_h >= pressure_a * 0.95
                    and p_home_next >= 0.24
                    and lam_h >= lam_a * 0.55
            ):
                draw_protection = True

        # GOST izgublja -> gost mora res pritiskati
        elif score_diff > 0:
            if (
                    momentum <= -0.08
                    and pressure_a >= pressure_h * 0.95
                    and p_away_next >= 0.24
                    and lam_a >= lam_h * 0.55
            ):
                draw_protection = True

        if draw_protection:

            mc_x_adj *= 1.22

            if score_diff < 0:
                mc_a_adj *= 0.94
            elif score_diff > 0:
                mc_h_adj *= 0.94

            s = mc_h_adj + mc_x_adj + mc_a_adj
            if s > 0:
                mc_h_adj /= s
                mc_x_adj /= s
                mc_a_adj /= s


    # ============================================================
    # LATE DRAW LIMITER AFTER LEARNING
    # ============================================================

    exact_sim_used = adaptive_exact_simulations(max(mc_h_adj, mc_x_adj, mc_a_adj))
    top_scores, hist_bias, exact_hist = final_score_prediction(
        score_home, score_away, lam_h, lam_a, lam_c,
        history, minute, xg_total, sot_total, shots_total, score_diff, game_type, danger_total,
        sim_count=exact_sim_used

    )

    if minute >= 75 and score_diff == 0:
        if tempo_danger >= 1.55 and shots_total >= 15:
            mc_x_adj *= 0.90

        if abs(danger_h - danger_a) >= 15:
            mc_x_adj *= 0.93

        if p_goal >= 0.38:
            mc_x_adj *= 0.94

        s = mc_h_adj + mc_x_adj + mc_a_adj
        if s > 1e-9:
            mc_h_adj /= s
            mc_x_adj /= s
            mc_a_adj /= s

        exact_sim_used = adaptive_exact_simulations(max(mc_h_adj, mc_x_adj, mc_a_adj))
        top_scores, hist_bias, exact_hist = final_score_prediction(
            score_home, score_away, lam_h, lam_a, lam_c,
            history, minute, xg_total, sot_total, shots_total, score_diff, game_type, danger_total,
            sim_count=exact_sim_used
        )

    # ============================================================
    # LATE EQUALIZER LIMITER (NO HARD OVERRIDE)
    # ============================================================
    if minute >= 70 and abs(score_diff) == 1:
        if score_diff < 0:
            mc_x_adj = max(mc_x_adj, 0.28)
            mc_a_adj = min(mc_a_adj, 0.62)
        elif score_diff > 0:
            mc_x_adj = max(mc_x_adj, 0.28)
            mc_h_adj = min(mc_h_adj, 0.62)

        s = mc_h_adj + mc_x_adj + mc_a_adj
        if s > 1e-9:
            mc_h_adj /= s
            mc_x_adj /= s
            mc_a_adj /= s

    mc_h_adj = clamp(mc_h_adj, 0.0, 1.0)
    mc_x_adj = clamp(mc_x_adj, 0.0, 1.0)
    mc_a_adj = clamp(mc_a_adj, 0.0, 1.0)

    edge_h = edge_from_model(mc_h_adj, imp_h)
    edge_x = edge_from_model(mc_x_adj, imp_x)
    edge_a = edge_from_model(mc_a_adj, imp_a)

    conf = confidence_score_base(p_goal, mc_h_adj, mc_x_adj, mc_a_adj, timeline["n"])

    # DOMINANCE BONUS
    dominance = max(mc_h_adj, mc_x_adj, mc_a_adj)
    dominance_bonus = max(0, dominance - 0.55) * 20
    conf += dominance_bonus

    conf = clamp(conf, 1.0, 100.0)

    band = confidence_band(conf)

    ng_signal = next_goal_signal(p_home_next, p_away_next)
    m_signal = match_signal(p_goal, p_home_next, p_away_next)

    lge = lge_notes(game_type, tempo_notes, xgr_notes, wave["active"])

    pass_acc_h = pass_acc_rate(acc_pass_h, passes_h)
    pass_acc_a = pass_acc_rate(acc_pass_a, passes_a)
    d2s_h = danger_to_shot_conv(shots_h, danger_h)
    d2s_a = danger_to_shot_conv(shots_a, danger_a)
    shot_q_h = shot_quality(xg_h, shots_h)
    shot_q_a = shot_quality(xg_a, shots_a)
    sot_r_h = sot_ratio(sot_h, shots_h)
    sot_r_a = sot_ratio(sot_a, shots_a)
    bc_r_h = big_chance_ratio(bc_h, shots_h)
    bc_r_a = big_chance_ratio(bc_a, shots_a)

    # ==========================================
    # LIVE BET FILTER
    # ==========================================

    max_mc = max(mc_h_adj, mc_x_adj, mc_a_adj)

    use_filter = False
    use_reason = "FILTER FAIL"

    # BALANCED filter
    if minute >= 45 and game_type == "BALANCED" and conf >= 52 and max_mc >= 0.50:
        use_filter = True
        use_reason = "PASS | BALANCED | 45+ | conf>=52 | max_mc>=0.50"

    # CHAOS filter
    elif minute >= 70 and game_type == "CHAOS" and conf >= 60 and max_mc >= 0.62 and p_goal >= 0.35:
        use_filter = True
        use_reason = "PASS | CHAOS | 70+ | conf>=60 | max_mc>=0.62"

    # PRESSURE / ATTACK_WAVE optional
    elif minute >= 65 and game_type in ("PRESSURE", "ATTACK_WAVE") and conf >= 58 and max_mc >= 0.58:
        use_filter = True
        use_reason = "PASS | PRESSURE/WAVE | 65+ | conf>=58 | max_mc>=0.58"

    # SLOW filter
    elif minute >= 50 and game_type == "SLOW" and conf >= 60 and max_mc >= 0.65 and score_diff != 0:
        use_filter = True
        use_reason = "PASS | SLOW | 50+ | conf>=60 | max_mc>=0.65"

    predikcija = moje_predvidevanje({
        "edge_h": edge_h,
        "edge_x": edge_x,
        "edge_a": edge_a,
        "mc_h_adj": mc_h_adj,
        "mc_x_adj": mc_x_adj,
        "mc_a_adj": mc_a_adj,
        "p_goal": p_goal,
        "p_no_goal": p_no_goal,
        "top_scores": top_scores
    })

    if minute >= 75 and odds_draw < 1.55:
        predikcija["moja_stava"] = "NO BET"
        predikcija["razlog_stave"] = "LATE TRAP"

    # ============================================================
    # SAVE FINAL RESULT (MATCH MEMORY)
    # ============================================================

    if minute >= 90:

        if score_home > score_away:
            result = "HOME"
        elif score_home < score_away:
            result = "AWAY"
        else:
            result = "DRAW"

        save_match_result(
            home=home,
            away=away,
            minute=minute,
            prediction_1x2=predikcija["napoved_izida"],
            prediction_score=predikcija["napoved_rezultata"],
            result_1x2=result,
            result_score=f"{score_home}-{score_away}",
            history_pred=history_pred
        )

        clear_match_memory(home, away)

    # ============================================================
    # FIX NEXT GOAL SIGNAL
    # ============================================================

    lam_attack = lam_h + lam_a

    if lam_attack > 0:
        p_home_next = (lam_h / lam_attack) * p_goal
        p_away_next = (lam_a / lam_attack) * p_goal
    else:
        p_home_next = 0.0
        p_away_next = 0.0

    # ============================================================
    # NEXT GOAL CONSISTENCY FIX
    # ============================================================

    if danger_h > danger_a and p_away_next > p_home_next:
        p_home_next *= 1.15

    if danger_a > danger_h and p_home_next > p_away_next:
        p_away_next *= 1.15

    s_next = p_home_next + p_away_next
    if s_next > p_goal and s_next > 1e-9:
        scale = p_goal / s_next
        p_home_next *= scale
        p_away_next *= scale

    if fake_control:
        if losing_side == "HOME":
            p_home_next *= 1.22
            p_away_next *= 0.85
        else:
            p_away_next *= 1.22
            p_home_next *= 0.85

    # ============================================================
    # NEXT GOAL SAFETY GUARD 1: NO_GOAL_GUARD (BEFORE ENGINE)
    # If no-goal probability is high, block the bet without calling the engine
    # ============================================================
    if (1.0 - p_goal) >= 0.33:
        next_goal_prediction = "HOME" if p_home_next > p_away_next else "AWAY"
        next_goal_bet = "NO BET"
        next_goal_reason = "NO GOAL RISK HIGH"
    else:
        next_goal_prediction, next_goal_bet, next_goal_reason = next_goal_bet_engine(
            p_home_next=p_home_next,
            p_away_next=p_away_next,
            lam_h=lam_h,
            lam_a=lam_a,
            momentum=momentum,
            tempo_shots=tempo_shots,
            tempo_danger=tempo_danger,
            game_type=game_type,
        )

    next_goal_prediction_smart = predict_next_goal_smart(
        p_home_next=p_home_next,
        p_away_next=p_away_next,
        lam_h=lam_h,
        lam_a=lam_a,
        danger_h=danger_h,
        danger_a=danger_a,
        xg_h=xg_h,
        xg_a=xg_a,
        momentum=momentum,
        pressure_h=pressure_h,
        pressure_a=pressure_a,
        tempo_danger=tempo_danger,
        sot_h=sot_h,
        sot_a=sot_a,
        game_type=game_type,
        minute=minute,
        score_diff=score_diff,
        mc_home=mc_h_adj,
        mc_away=mc_a_adj,
        hist_home=hist_home,
        hist_away=hist_away,
        p_goal=p_goal,
        mc_draw=mc_x_adj,
        hist_draw=hist_draw,
        final_third_h=final_third_h,
        final_third_a=final_third_a,
        gk_saves_h=gk_saves_h,
        gk_saves_a=gk_saves_a,
    )

    # ============================================================
    # SMART NEXT GOAL ALIGNMENT
    # združi osnovni next goal engine + smart engine v en logičen signal
    # ============================================================
    ng_smart_pred = normalize_outcome_label(next_goal_prediction_smart.get("prediction"))
    ng_smart_conf = float(next_goal_prediction_smart.get("confidence", 0) or 0)
    # ============================================================
    # FINAL NEXT GOAL ARBITER (ENGINE LOCK)
    # uskladi smart engine, raw p_goal in draw-heavy state v en končni signal
    # ============================================================
    draw_heavy_state = max(float(mc_x_adj or 0.0), float(hist_draw or 0.0))
    low_goal_state = p_goal < 0.50

    if low_goal_state:
        ng_smart_conf *= 0.72
    if draw_heavy_state >= 0.55:
        ng_smart_conf *= 0.68
    elif draw_heavy_state >= 0.50:
        ng_smart_conf *= 0.82

    ng_smart_conf = clamp(ng_smart_conf, 0.0, 1.0)

    if draw_heavy_state >= 0.55 and p_goal < 0.50:
        if ng_smart_conf < 0.62:
            # ng_smart_pred blocked; next_goal_bet will be cleared by guards below
            ng_smart_pred = "NO BET"

    # Quantitative DRAW pressure test: block bet when draw signal is dominant
    if draw_heavy_state >= 0.58 and p_goal < 0.55:
        if ng_smart_conf < 0.68:
            # ng_smart_pred blocked; next_goal_bet will be cleared by guards below
            ng_smart_pred = "NO BET"

    if p_goal < 0.35:
        next_goal_bet = "NO BET"
        if ng_smart_conf < 0.70:
            ng_smart_pred = "NO BET"

    # SMART ENGINE PRIORITY: use smart pred whenever confidence is sufficient
    if ng_smart_pred in ("HOME", "AWAY") and ng_smart_conf >= 0.52:
        next_goal_prediction = ng_smart_pred

    # Activate smart bet with tighter threshold
    if next_goal_bet == "NO BET" and ng_smart_pred in ("HOME", "AWAY") and ng_smart_conf >= 0.60 and p_goal >= 0.30 and draw_heavy_state < 0.60:
        next_goal_bet = ng_smart_pred
        next_goal_reason = "SMART NEXT GOAL ALIGNMENT"
    elif ng_smart_pred in ("HOME", "AWAY") and ng_smart_conf >= 0.72 and p_goal >= 0.30 and draw_heavy_state < 0.55:
        next_goal_bet = ng_smart_pred
        next_goal_reason = "SMART HIGH CONFIDENCE"

    # ============================================================
    # NEXT GOAL SAFETY GUARDS 2 & 3 (FINAL OVERRIDE AFTER SMART ALIGNMENT)
    # ============================================================

    # GUARD 2: SMART_CONF_GUARD - block bet when smart confidence is insufficient (regardless of p_goal)
    if ng_smart_conf < 0.55 and next_goal_bet != "NO BET":
        next_goal_bet = "NO BET"
        if ng_smart_conf < 0.48:
            next_goal_reason = "SMART CONFIDENCE CRITICAL (<48%)"
        else:
            next_goal_reason = "SMART CONFIDENCE TOO LOW"

    # GUARD 3: EDGE_GUARD - block bet when borderline confidence with no clear dominance
    elif (
        0.48 <= ng_smart_conf <= 0.55
        and 0.30 <= p_goal < 0.45
        and abs(p_home_next - p_away_next) < 0.15
        and next_goal_bet != "NO BET"
    ):
        next_goal_bet = "NO BET"
        next_goal_reason = "MEDIUM CONFIDENCE - NO EDGE"

    counter_goal_raw = next_goal_bet if normalize_outcome_label(next_goal_bet) in ("HOME", "AWAY") else next_goal_prediction
    dominant_side, counter_goal = cfos_balance_counter(
        danger_h,
        danger_a,
        shots_h,
        shots_a,
        counter_goal_raw
    )

    counter_blocked = False

    if dominant_side == "HOME" and next_goal_prediction == "AWAY":
        next_goal_prediction = "HOME"
        counter_blocked = True
    elif dominant_side == "AWAY" and next_goal_prediction == "HOME":
        next_goal_prediction = "AWAY"
        counter_blocked = True

    if dominant_side is not None and normalize_outcome_label(counter_goal_raw) != normalize_outcome_label(counter_goal):
        counter_blocked = True

    return {

        "home": home, "away": away, "minute": minute,
        "score_home": score_home, "score_away": score_away, "score_diff": score_diff,
        "xg_h": xg_h, "xg_a": xg_a, "xg_total": xg_total,
        "shots_h": shots_h, "shots_a": shots_a, "shots_total": shots_total,
        "sot_h": sot_h, "sot_a": sot_a, "sot_total": sot_total,
        "attacks_h": attacks_h, "attacks_a": attacks_a,
        "danger_h": danger_h, "danger_a": danger_a, "danger_total": danger_total,
        "corners_h": corners_h, "corners_a": corners_a,
        "odds_home": odds_home, "odds_draw": odds_draw, "odds_away": odds_away,
        "lam_h_raw": lam_h_raw, "lam_a_raw": lam_a_raw, "lam_c_raw": lam_c_raw, "lam_total_raw": lam_total_raw,
        "lam_h": lam_h, "lam_a": lam_a, "lam_c": lam_c, "lam_total": lam_total,
        "p_goal_raw": p_goal_raw, "p_goal": p_goal, "p_no_goal": p_no_goal,
        "p_home_next": p_home_next, "p_away_next": p_away_next,
        "next_goal_prediction": next_goal_prediction,
        "next_goal_bet": next_goal_bet, "next_goal_reason": next_goal_reason,
        "dominant_side": dominant_side, "counter_goal": counter_goal, "counter_blocked": counter_blocked,
        "p_goal_5": p_goal_5, "p_goal_10": p_goal_10,
        "mc_h_raw": mc_h_raw, "mc_x_raw": mc_x_raw, "mc_a_raw": mc_a_raw,
        "mc_h_adj": mc_h_adj, "mc_x_adj": mc_x_adj, "mc_a_adj": mc_a_adj,
        "lf_goal": lf_goal, "n_goal": n_goal, "rh": rh, "rx": rx, "ra": ra, "n_1x2": n_1x2,
        "timeline": timeline, "wave": wave, "game_type": game_type,
        "tempo_shots": tempo_shots, "tempo_att": tempo_att, "tempo_danger": tempo_danger,
        "xg_rate_h": xg_rate_h, "xg_rate_a": xg_rate_a, "xg_rate_total": xg_rate_total,
        "attack_h": attack_h, "attack_a": attack_a, "danger_idx_h": danger_idx_h, "danger_idx_a": danger_idx_a,
        "pressure_h": pressure_h, "pressure_a": pressure_a, "pressure_total": pressure_total,
        "momentum": momentum, "synthetic_xg_used": synthetic_xg_used,
        "minutes_left_real": minutes_left_real, "sim_used": sim_used, "exact_sim_used": exact_sim_used,
        "tempo_notes": tempo_notes, "xgr_notes": xgr_notes,
        "y_h": y_h, "y_a": y_a, "red_h": red_h, "red_a": red_a,
        "blocked_h": blocked_h, "blocked_a": blocked_a,
        "bcm_h": bcm_h, "bcm_a": bcm_a,
        "gk_saves_h": gk_saves_h, "gk_saves_a": gk_saves_a,
        "passes_h": passes_h, "passes_a": passes_a,
        "acc_pass_h": acc_pass_h, "acc_pass_a": acc_pass_a,
        "tackles_h": tackles_h, "tackles_a": tackles_a,
        "inter_h": inter_h, "inter_a": inter_a,
        "clear_h": clear_h, "clear_a": clear_a,
        "duels_h": duels_h, "duels_a": duels_a,
        "offsides_h": offsides_h, "offsides_a": offsides_a,
        "throw_h": throw_h, "throw_a": throw_a,
        "fouls_h": fouls_h, "fouls_a": fouls_a,
        "prematch_h": prematch_h, "prematch_a": prematch_a,
        "prev_odds_home": prev_odds_home, "prev_odds_draw": prev_odds_draw, "prev_odds_away": prev_odds_away,
        "elo_h": elo_h, "elo_a": elo_a,
        "imp_h": imp_h, "imp_x": imp_x, "imp_a": imp_a, "overround": overround,
        "edge_h": edge_h, "edge_x": edge_x, "edge_a": edge_a,
        "confidence": conf, "confidence_band": band,
        "next_goal_signal": ng_signal, "match_signal": m_signal,
        "lge": lge,
        "top_scores": top_scores, "hist_bias": hist_bias, "exact_hist": exact_hist,
        "hist_home": hist_home, "hist_draw": hist_draw, "hist_away": hist_away,
        "history_pred": history_pred,
        "pass_acc_h": pass_acc_h, "pass_acc_a": pass_acc_a,
        "d2s_h": d2s_h, "d2s_a": d2s_a,
        "shot_q_h": shot_q_h, "shot_q_a": shot_q_a,
        "sot_r_h": sot_r_h, "sot_r_a": sot_r_a,
        "bc_r_h": bc_r_h, "bc_r_a": bc_r_a,
        "keypasses_h": keypasses_h, "keypasses_a": keypasses_a,
        "crosses_h": crosses_h, "crosses_a": crosses_a,
        "aerials_h": aerials_h, "aerials_a": aerials_a,
        "dribbles_h": dribbles_h, "dribbles_a": dribbles_a,
        "final_third_h": final_third_h, "final_third_a": final_third_a,
        "long_balls_h": long_balls_h, "long_balls_a": long_balls_a,
        "bc_created_h": bc_created_h, "bc_created_a": bc_created_a,
        "action_left": action_left, "action_mid": action_mid, "action_right": action_right,
        "napoved_izida": predikcija["napoved_izida"],
        "napoved_rezultata": predikcija["napoved_rezultata"],
        "moja_stava": predikcija["moja_stava"],
        "razlog_stave": predikcija["razlog_stave"],
        "max_mc": max_mc,
        "use_filter": use_filter,
        "use_reason": use_reason,
        "lam_ratio": lam_ratio,
        "high_tempo": high_tempo,
        "high_lambda": high_lambda,
        "no_wave": no_wave,
        "overpressure_home": overpressure_home,
        "overpressure_away": overpressure_away,
        "leading_side": leading_side,
        "dominance": danger_dominance,
        "next_goal_prediction_smart": next_goal_prediction_smart,
        "signals_agreement": int((next_goal_prediction_smart or {}).get("signals_agreement", 0) or 0),
    }


# ============================================================
# KONEC DELA 7 / 8
# ============================================================
# ============================================================
# CFOS-XG PRO 75 TITAN
# ZAČETEK DELA 8.1 / 8
# IZPIS / ANALIZA / MAIN
# ============================================================

def print_stat(name, h, a):
    if h is None:
        h = 0
    if a is None:
        a = 0

    try:
        h = int(float(h))
    except:
        pass

    try:
        a = int(float(a))
    except:
        pass

    print(f"{name.ljust(22)} {str(h).rjust(5)} vs {str(a).ljust(5)}")



# ============================================================
# LIVE TAG SYSTEM (1 LIVE per window)
# ============================================================

CMD_WIDTH = 95
_live_used = False

def live_reset():
    global _live_used
    _live_used = False

def live_print(label, value, live=False):
    global _live_used
    left = f"{label:<18} {value}"
    pad = max(1, CMD_WIDTH - len(left))
    if live and not _live_used:
        print(left + "LIVE".rjust(pad))
        _live_used = True
    else:
        print(left)

def _fmt_live_num(value, digits=3):
    try:
        return f"{float(value):.{digits}f}"
    except:
        return str(value)

def _fmt_live_pct(value):
    try:
        return f"{float(value):.2%}"
    except:
        return str(value)

def _dominance_text(r):
    h = (
        r.get("danger_h", 0) * 2.0 +
        r.get("attacks_h", 0) * 0.4 +
        r.get("shots_h", 0) * 1.5 +
        r.get("sot_h", 0) * 2.5 +
        r.get("final_third_h", 0) * 0.3
    )
    a = (
        r.get("danger_a", 0) * 2.0 +
        r.get("attacks_a", 0) * 0.4 +
        r.get("shots_a", 0) * 1.5 +
        r.get("sot_a", 0) * 2.5 +
        r.get("final_third_a", 0) * 0.3
    )
    if h > a * 1.15:
        return "DOMA KONTROLA", GREEN
    elif a > h * 1.15:
        return "GOST KONTROLA", GREEN
    return "URAVNOTEŽENO", YELLOW

def _match_direction_text(r):
    h = (
        r.get("momentum", 0) * 5 +
        r.get("pressure_h", 0) -
        r.get("pressure_a", 0) +
        r.get("danger_h", 0) * 0.15 -
        r.get("danger_a", 0) * 0.15
    )
    if h > 1.5:
        return "→→→ DOMA PRITISK", GREEN
    elif h < -1.5:
        return "←←← GOST PRITISK", GREEN
    return "↔ URAVNOTEŽENO", YELLOW

def print_live_lge(r):
    live_reset()
    print(f"\n{MAGENTA}--------------- LGE ----------------{RESET}\n")
    live_print("STATE", lge_state_value(r))
    wave_side = side_name_from_diff(
        (float(r.get('pressure_h', 0) or 0) - float(r.get('pressure_a', 0) or 0)) * 0.8 +
        (float(r.get('danger_h', 0) or 0) - float(r.get('danger_a', 0) or 0)) * 0.05 +
        (float(r.get('momentum', 0) or 0)) * 10.0,
        "HOME", "AWAY", "NO", eps=0.08
    )
    if not bool(r.get('wave', {}).get('active', False)) and str(r.get('game_type', '')) != 'ATTACK_WAVE':
        wave_side = "NO"
    live_print("ATTACK_WAVE", wave_side)
    live_print("TEMPO shots", high_side_label(r.get('shots_h', 0), r.get('shots_a', 0), threshold=0.5), True)
    live_print("TEMPO danger", high_side_label(r.get('danger_h', 0), r.get('danger_a', 0), threshold=1.0))
    live_print("FAVOR", favorite_side(r))

def print_live_match_memory(r):
    """
    Prints the MATCH MEMORY section showing timeline trends, attack wave status and LGE.

    Args:
        r (dict): Match result dictionary with keys:
            - timeline (dict): Timeline aggregation data with fields:
                - n (int): Number of timeline snapshots recorded
                - trend_factor_goal (float): Goal likelihood trend multiplier
                - trend_home (float): Home team trend factor
                - trend_away (float): Away team trend factor
                - true_momentum_text (str): Human-readable momentum description
            - wave (dict): Attack wave detector output with 'active' (bool) field
            - lge (str): Last goal event description string

    Prints:
        MATCH MEMORY section with timeline snapshot count, goal/home/away trend
        factors, true momentum label, attack wave active flag, and LGE event.
    """
    live_reset()
    print(f"\n{MAGENTA}--------------- MATCH MEMORY ----------------{RESET}\n")
    tg = float(r.get("timeline", {}).get("trend_factor_goal", 1.0) or 1.0)
    live_print("Timeline snapshots", r.get("timeline", {}).get("n", 0))
    live_print("Timeline goal factor", f"{tg:.3f}", True)
    live_print("Timeline HOME factor", f"{float(r.get('timeline', {}).get('trend_home', 0.0) or 0.0):.3f}")
    live_print("Timeline AWAY factor", f"{float(r.get('timeline', {}).get('trend_away', 0.0) or 0.0):.3f}")
    live_print("True momentum", r.get("timeline", {}).get("true_momentum_text", "N/A"))
    live_print("Attack wave", "YES" if r.get("wave", {}).get("active", False) else "NO")
    live_print("LGE", r.get("lge", ""))

def print_live_tempo_rate(r):
    live_reset()
    print(f"\n{MAGENTA}--------------- TEMPO / RATE ----------------{RESET}\n")
    live_print("Tempo shots", _fmt_live_num(r.get("tempo_shots", 0), 3), True)
    live_print("Tempo attacks", _fmt_live_num(r.get("tempo_att", 0), 3))
    live_print("Tempo danger", _fmt_live_num(r.get("tempo_danger", 0), 3))
    live_print("xG rate total", _fmt_live_num(r.get("xg_rate_total", 0), 4))
    live_print("xG rate HOME", _fmt_live_num(r.get("xg_rate_h", 0), 4))
    live_print("xG rate AWAY", _fmt_live_num(r.get("xg_rate_a", 0), 4))
    live_print("Minutes left est.", r.get("minutes_left_real", 0))

def print_live_extended_stats(r):
    live_reset()
    print(f"\n{MAGENTA}--------------- EXTENDED STATS ----------------{RESET}\n")
    live_print("Attacks", f"{round(r.get('attacks_h', 0), 2)} {round(r.get('attacks_a', 0), 2)}", True)
    live_print("Blocked shots", f"{round(r.get('blocked_h', 0), 2)} {round(r.get('blocked_a', 0), 2)}")
    live_print("Big ch. missed", f"{round(r.get('bcm_h', 0), 2)} {round(r.get('bcm_a', 0), 2)}")
    live_print("Corners", f"{round(r.get('corners_h', 0), 2)} {round(r.get('corners_a', 0), 2)}")
    live_print("GK saves", f"{round(r.get('gk_saves_h', 0), 2)} {round(r.get('gk_saves_a', 0), 2)}")
    live_print("Passes", f"{round(r.get('passes_h', 0), 2)} {round(r.get('passes_a', 0), 2)}")
    live_print("Acc. passes", f"{round(r.get('acc_pass_h', 0), 2)} {round(r.get('acc_pass_a', 0), 2)}")
    live_print("Danger->shot", f"{round(r.get('d2s_h', 0), 3)} {round(r.get('d2s_a', 0), 3)}")
    live_print("Shot quality", f"{round(r.get('shot_q_h', 0), 3)} {round(r.get('shot_q_a', 0), 3)}")
    live_print("SOT ratio", f"{round(r.get('sot_r_h', 0), 3)} {round(r.get('sot_r_a', 0), 3)}")
    live_print("Big chance ratio", f"{round(r.get('bc_r_h', 0), 3)} {round(r.get('bc_r_a', 0), 3)}")
    live_print("Game type", r.get("game_type", ""))

def print_live_momentum_engine(r):
    live_reset()
    print(f"\n{MAGENTA}--------------- MOMENTUM ENGINE ----------------{RESET}\n")
    live_print("Attack index", f"{round(r.get('attack_h', 0), 2)} {round(r.get('attack_a', 0), 2)}")
    live_print("Danger index", f"{round(r.get('danger_idx_h', 0), 2)} {round(r.get('danger_idx_a', 0), 2)}")
    live_print("Pressure", f"{round(r.get('pressure_h', 0), 2)} {round(r.get('pressure_a', 0), 2)}")
    live_print("Momentum", _fmt_live_num(r.get("momentum", 0), 3), True)

def print_live_lambda_engine(r):
    live_reset()
    print(f"\n{MAGENTA}--------------- LAMBDA ENGINE ----------------{RESET}\n")
    live_print("Lambda home (RAW)", _fmt_live_num(r.get("lam_h_raw", 0), 3), True)
    live_print("Lambda away (RAW)", _fmt_live_num(r.get("lam_a_raw", 0), 3))
    live_print("Lambda shared (RAW)", _fmt_live_num(r.get("lam_c_raw", 0), 3))
    live_print("Lambda total (RAW)", _fmt_live_num(r.get("lam_total_raw", 0), 3))
    live_print("P(goal) RAW", f"{pct(r.get('p_goal_raw', 0))} %")
    live_print("Lambda home (CAL)", _fmt_live_num(r.get("lam_h", 0), 3))
    live_print("Lambda away (CAL)", _fmt_live_num(r.get("lam_a", 0), 3))
    live_print("Lambda shared (CAL)", _fmt_live_num(r.get("lam_c", 0), 3))
    live_print("Lambda total (CAL)", _fmt_live_num(r.get("lam_total", 0), 3))

def print_live_overpressure_engine(r):
    live_reset()
    print(f"\n{MAGENTA}--------------- OVERPRESSURE ENGINE ----------------{RESET}\n")
    live_print("Lam ratio", _fmt_live_num(r.get("lam_ratio", 0), 2), True)
    live_print("High tempo", str(r.get("high_tempo", False)))
    live_print("High lambda", str(r.get("high_lambda", False)))
    live_print("No attack wave", str(r.get("no_wave", True)))
    live_print("Overpressure HOME", str(r.get("overpressure_home", False)))
    live_print("Overpressure AWAY", str(r.get("overpressure_away", False)))
    live_print("Leading side", r.get("leading_side", "DRAW"))
    live_print("Lambda HOME", _fmt_live_num(r.get("lam_h", 0), 3))
    live_print("Lambda AWAY", _fmt_live_num(r.get("lam_a", 0), 3))
    live_print("Lambda DRAW", _fmt_live_num(r.get("lam_c", 0), 3))

def print_live_goal_probability(r):
    live_reset()
    print(f"\n{MAGENTA}--------------- GOAL PROBABILITY (CAL) ----------------{RESET}\n")
    live_print("Any goal", f"{pct(r.get('p_goal', 0))} %", True)
    live_print("Home next goal", f"{pct(r.get('p_home_next', 0))} %")
    live_print("Away next goal", f"{pct(r.get('p_away_next', 0))} %")
    live_print("No goal", f"{pct(r.get('p_no_goal', 0))} %")
    live_print("Goal next 5 min", f"{pct(r.get('p_goal_5', 0))} %")
    live_print("Goal next 10 min", f"{pct(r.get('p_goal_10', 0))} %")

def print_live_match_direction(r):
    txt, col = _match_direction_text(r)
    live_reset()
    print(f"\n{MAGENTA}--------------- MATCH DIRECTION ----------------{RESET}\n")
    live_print("", btxt(txt, col, True), True)


def print_next_goal_bet(r):
    print()
    print("--------------- NEXT GOAL ----------------")
    print(f"Prediction       {r.get('next_goal_prediction', 'AWAY')}")
    print(f"Bet              {r.get('next_goal_bet', 'NO BET')}")
    print(f"Reason           {r.get('next_goal_reason', 'LOW EDGE')}")
    print("------------------------------------------------")


def print_counter_control(r):
    print("\n--------------- COUNTER CONTROL ----------------\n")

    dominant_side = r.get('dominant_side')
    counter_goal = r.get('counter_goal', 'NONE')
    counter_blocked = bool(r.get('counter_blocked', False))

    if dominant_side is None:
        print("Dominant side      NONE")
    else:
        print(f"Dominant side      {dominant_side}")

    print(f"Counter goal       {counter_goal}")
    print(f"Counter blocked    {'YES' if counter_blocked else 'NO'}")

def print_live_dominance(r):
    txt, col = _dominance_text(r)
    live_reset()
    print(f"\n{MAGENTA}--------------- DOMINANCE ----------------{RESET}\n")
    live_print("", btxt(txt, col, True), True)



def print_dominance(r):
    txt, col = _dominance_text(r)
    print("")
    print("--------------- DOMINANCE ----------------")
    print(btxt(txt, col, True))


def print_match_direction(r):
    txt, col = _match_direction_text(r)
    print("")
    print("--------------- MATCH DIRECTION ----------------")
    print(btxt(txt, col, True))


def format_prob_line(label, p):
    col = color_prob(p)
    return f"{label.ljust(28)} {btxt(str(pct(p)) + ' %', col, True)}"


def format_edge_line(name, model_p, market_p, edge):
    edge_col = color_edge(edge)
    return f"{name.ljust(12)} {str(round(model_p * 100, 1)).rjust(8)} {str(round(market_p * 100, 1)).rjust(10)} {btxt(str(round(edge * 100, 1)).rjust(10), edge_col, True)}"
# =========================================================
# CFOS FOCUS ENGINE (PRECISION)
# =========================================================

def focus_engine(minute, score_diff):

    # -----------------------------------------------------
    # 0–15
    # -----------------------------------------------------
    if minute <= 15:
        return [
            "tempo_shots",
            "tempo_danger",
            "xg_rate_total",
            "game_type",
            "IGNORE: momentum, MC, META"
        ]

    # -----------------------------------------------------
    # 15–30
    # -----------------------------------------------------
    if minute <= 30:
        return [
            "tempo_shots",
            "tempo_danger",
            "xg_rate_total",
            "pressure_total",
            "P(goal)",
            "IGNORE: final 1X2"
        ]

    # -----------------------------------------------------
    # 30–45
    # -----------------------------------------------------
    if minute <= 45:
        if score_diff == 0:
            return [
                "momentum",
                "SOT_ratio",
                "pressure_total",
                "lambda_total",
                "Away/Home next goal"
            ]
        else:
            return [
                "comeback_pressure",
                "lambda_stronger_side",
                "momentum",
                "tempo_danger"
            ]

    # -----------------------------------------------------
    # 45–60
    # -----------------------------------------------------
    if minute <= 60:
        if score_diff == 0:
            return [
                "momentum",
                "pressure_total",
                "SOT_ratio",
                "lambda_total",
                "next_goal_signal"
            ]
        else:
            return [
                "comeback_probability",
                "attack_wave",
                "momentum",
                "lambda_losing_team"
            ]

    # -----------------------------------------------------
    # 60–75
    # -----------------------------------------------------
    if minute <= 75:
        if score_diff == 0:
            return [
                "momentum",
                "lambda_home",
                "lambda_away",
                "draw_crusher",
                "P(goal)"
            ]
        else:
            return [
                "comeback",
                "kill_game",
                "attack_wave",
                "timeline_trend"
            ]

    # -----------------------------------------------------
    # 75+
    # -----------------------------------------------------
    if score_diff == 0:
        return [
            "P(goal)",
            "lambda_stronger",
            "momentum",
            "MC_exact"
        ]

    return [
        "last_goal_probability",
        "comeback_pressure",
        "time_decay",
        "kill_game_lambda"
    ]

def print_top_signals(r):
    signals = []

    if r["danger_h"] > 0 and r["danger_a"] > 0:
        if r["danger_h"] > r["danger_a"] * 1.60:
            signals.append(("Danger dominance DOMA", RED))
        elif r["danger_a"] > r["danger_h"] * 1.60:
            signals.append(("Danger dominance GOST", RED))

    if r["wave"]["active"]:
        signals.append(("Attack wave aktiven", RED))

    if r["tempo_danger"] >= 1.30:
        signals.append(("Tempo danger spike", YELLOW))

    if abs(r["momentum"]) >= 0.20:
        side = "DOMA" if r["momentum"] > 0 else "GOST"
        signals.append((f"Momentum {side}", YELLOW))

    best_edge = max(r["edge_h"], r["edge_x"], r["edge_a"])

    if best_edge >= 0.05:
        signals.append(("Value edge zaznan", GREEN))

    if r["p_goal"] >= 0.65:
        signals.append(("Visoka verjetnost gola", GREEN))

    print(f"\n{CYAN}{BOLD}================ TOP SIGNALI ================ {RESET}\n")
    if not signals:
        print("Ni močnih signalov.")
        return

    for i, (txt, col) in enumerate(signals[:5], 1):
        print(f"{i}. {btxt(txt, col, True)}")


def print_5_korakov(r):
    print(f"\n{CYAN}{BOLD}================ 5 KLJUČNIH KORAKOV [PRO 75] ================ {RESET}\n")

    if (
            r["momentum"] < -0.08 and
            r["pressure_a"] > r["pressure_h"] * 1.20
    ):
        txt1 = "1. Pressure -> GOST PRITISK (REAL)"

    elif (
            r["momentum"] > 0.08 and
            r["pressure_h"] > r["pressure_a"] * 1.20
    ):
        txt1 = "1. Pressure -> DOMA PRITISK (REAL)"

    elif r["danger_h"] > r["danger_a"] * 1.20:
        txt1 = "1. Danger attacks -> DOMA pritisk"

    elif r["danger_a"] > r["danger_h"] * 1.20:
        txt1 = "1. Danger attacks -> GOST pritisk"

    else:
        txt1 = "1. Game -> URAVNOTEŽENO"

    print(f"{RED}{BOLD}{txt1}{RESET}")

    if r["tempo_danger"] >= 1.20 or r["tempo_shots"] >= 0.20:
        txt2 = "2. Tempo danger / tempo shots -> VISOK TEMPO"
    elif r["tempo_danger"] >= 0.85 or r["tempo_shots"] >= 0.12:
        txt2 = "2. Tempo danger / tempo shots -> SREDNJI TEMPO"
    else:
        txt2 = "2. Tempo danger / tempo shots -> NIZEK TEMPO"
    print(f"{YELLOW}{BOLD}{txt2}{RESET}")

    if r["wave"]["active"] and r["timeline"]["trend_factor_goal"] >= 1.05:
        txt3 = "3. Attack wave / timeline trend -> MOČAN VAL"
    elif r["wave"]["active"]:
        txt3 = "3. Attack wave / timeline trend -> ATTACK WAVE AKTIVEN"
    elif r["timeline"]["trend_factor_goal"] >= 1.08:
        txt3 = "3. Attack wave / timeline trend -> TIMELINE RASTE"
    elif r["timeline"]["trend_factor_goal"] <= 0.95:
        txt3 = "3. Attack wave / timeline trend -> TIMELINE ZAVIRA"
    else:
        txt3 = "3. Attack wave / timeline trend -> BREZ MOČNEGA SIGNALA"
    print(f"{MAGENTA}{BOLD}{txt3}{RESET}")

    if r["p_goal"] >= 0.60:
        txt4 = "4. Any goal / next goal signal -> VISOKA VERJETNOST GOLA"
    elif r["p_goal"] >= 0.35:
        if r["p_home_next"] > r["p_away_next"] and r["p_home_next"] >= 0.20:
            txt4 = "4. Any goal / next goal signal -> SREDNJI GOL | DOMA RAHLA PREDNOST"
        elif r["p_away_next"] > r["p_home_next"] and r["p_away_next"] >= 0.20:
            txt4 = "4. Any goal / next goal signal -> SREDNJI GOL | GOST RAHLA PREDNOST"
        else:
            txt4 = "4. Any goal / next goal signal -> SREDNJI GOL | URAVNOTEŽENO"
    else:
        txt4 = "4. Any goal / next goal signal -> NIZKA VERJETNOST GOLA"
    print(f"{GREEN}{BOLD}{txt4}{RESET}")

    best_edge = max(r["edge_h"], r["edge_x"], r["edge_a"])
    if best_edge >= 0.05:
        if best_edge == r["edge_h"]:
            txt5 = f"5. EDGE proti marketu -> VALUE na 1 ({round(best_edge * 100, 1)} %)"
        elif best_edge == r["edge_x"]:
            txt5 = f"5. EDGE proti marketu -> VALUE na X ({round(best_edge * 100, 1)} %)"
        else:
            txt5 = f"5. EDGE proti marketu -> VALUE na 2 ({round(best_edge * 100, 1)} %)"
    elif best_edge <= -0.05:
        txt5 = f"5. EDGE proti marketu -> MARKET PROTI MODELU ({round(best_edge * 100, 1)} %)"
    else:
        txt5 = f"5. EDGE proti marketu -> BREZ MOČNE VALUE PREDNOSTI ({round(best_edge * 100, 1)} %)"
    print(f"{BLUE}{BOLD}{txt5}{RESET}")


def cfos_analiza_sistema(r):
    print(f"\n{CYAN}{BOLD}================ CFOS ANALIZA SISTEMA ================ {RESET}\n")

    if r["danger_h"] > r["danger_a"] * 1.35:
        print(btxt("• Danger napadi močno na strani DOMA", RED, True))
    elif r["danger_a"] > r["danger_h"] * 1.35:
        print(btxt("• Danger napadi močno na strani GOST", RED, True))
    else:
        print(btxt("• Danger napadi niso izrazito enostranski", YELLOW, True))

    if r["tempo_danger"] >= 1.20:
        print(btxt("• Tempo nevarnih napadov je visok", YELLOW, True))
    else:
        print("• Tempo nevarnih napadov je normalen ali nizek")

    if r["wave"]["active"]:
        print(btxt("• Attack wave je AKTIVEN", RED, True))
    else:
        print("• Attack wave ni aktiven")

    if r["timeline"]["trend_factor_goal"] >= 1.08:
        print(btxt("• Timeline kaže rast verjetnosti gola", GREEN, True))
    elif r["timeline"]["trend_factor_goal"] <= 0.95:
        print(btxt("• Timeline zavira gol", YELLOW, True))
    else:
        print("• Timeline je nevtralen")

    if r["p_goal"] >= 0.55:
        print(btxt("• Model vidi visoko verjetnost gola", GREEN, True))
    elif r["p_goal"] <= 0.25:
        print(btxt("• Model vidi nizko verjetnost gola", RED, True))
    else:
        print(btxt("• Model vidi srednjo verjetnost gola", YELLOW, True))

    if r["p_home_next"] > r["p_away_next"] and r["p_home_next"] >= 0.35:
        print(btxt("• Naslednji gol je bolj verjeten DOMA", GREEN, True))
    elif r["p_away_next"] > r["p_home_next"] and r["p_away_next"] >= 0.35:
        print(btxt("• Naslednji gol je bolj verjeten GOST", GREEN, True))
    else:
        print(btxt("• Naslednji gol ni dovolj jasen", YELLOW, True))

    # =========================================================
    # CFOS TREND OVERRIDE (8/8 OUTPUT FIX)
    # =========================================================

    napoved = r["napoved_izida"]
    stava = r["moja_stava"]
    razlog = r["razlog_stave"]

    minute = r["minute"]

    hist_goal = 0
    exact_no_goal = 0

    if r.get("hist_bias") is not None:
        hist_goal = r["hist_bias"].get("p_goal", 0)

    if r.get("exact_hist") is not None:
        exact_no_goal = r["exact_hist"].get("p_no_goal", 0)

    # =====================================================
    # HISTORY FILTER (RULE 1/2/3)
    # =====================================================

    history_block = False

    # Extract current ng_smart signal for RULE4/RULE5
    _ng_smart_cur = r.get("next_goal_prediction_smart") or {}
    _ng_smart_conf_cur = float(_ng_smart_cur.get("confidence", 0) or 0)
    _ng_smart_pred_cur = str(_ng_smart_cur.get("prediction", "") or "")

    # RULE 1
    if minute >= 50 and hist_goal <= 0.20 and exact_no_goal >= 0.75:
        history_block = True
        razlog = "RULE1 STRONG HISTORY NO GOAL"

    # RULE 2
    elif r["p_goal"] >= 0.75 and hist_goal <= 0.25 and exact_no_goal >= 0.70:
        history_block = True
        razlog = "RULE2 MODEL HISTORY CONFLICT"

    # RULE 3
    elif minute >= 78 and hist_goal <= 0.30 and exact_no_goal >= 0.65:
        history_block = True
        razlog = "RULE3 LATE HISTORY LOCK"

    # RULE 4: NEXT GOAL SMART CONFIDENCE TOO LOW
    elif _ng_smart_conf_cur < 0.55 and r["p_goal"] < 0.45:
        history_block = True
        razlog = "RULE4 NEXT GOAL SMART CONFIDENCE TOO LOW"

    # RULE 5: DRAW DOMINATES + NO CLEAR NEXT GOAL SIDE
    elif minute >= 60 and r.get("mc_x_adj", 0) > 0.60 and _ng_smart_pred_cur not in ("HOME", "AWAY"):
        history_block = True
        razlog = "RULE5 DRAW DOMINATES + NO CLEAR NEXT GOAL"

    # =====================================================
    # AUTO BET DECISION
    # =====================================================

    if history_block:

        stava = "NO BET"
        razlog = "HISTORY BLOCK"

    else:

        # =====================================================
        # LAMBDA TRAP (SAFE VERSION)
        # =====================================================
        if r.get("lam_h", 0) > r.get("lam_a", 0) and r.get("momentum", 0) < -0.05:
            stava = "NO BET"
            razlog = "LAMBDA TRAP"

        # =====================================================
        # AUTO BET DECISION
        # =====================================================

        # =====================================================
        # SMART BLOCK (CRITICAL - FIRST FILTER)
        # =====================================================
        if r.get("signals_agreement", 7) <= 2:
            stava = "NO BET"
            razlog = "SMART NO CONSENSUS"

        else:
            next_goal_conf = max(r["p_home_next"], r["p_away_next"])

            # ============================================================
            # NEXT GOAL CONSISTENCY OVERRIDE (CRITICAL)
            # ============================================================

            if next_goal_conf < 0.55:
                stava = "NO BET"
                razlog = "LOW NEXT GOAL CONFIDENCE"

            elif abs(r["p_home_next"] - r["p_away_next"]) < 0.10:
                stava = "NO BET"
                razlog = "NO CLEAR NEXT GOAL SIDE"

            elif minute >= 70 and next_goal_conf < 0.65:
                stava = "NO BET"
                razlog = "LATE LOW CONFIDENCE"

            # STRONG DRAW
            elif minute >= 60 and r["mc_x_adj"] >= 0.65:
                stava = "NO BET"
                razlog = "STRONG DRAW"

            # LATE GOAL (strong)
            elif (
                minute >= 70
                and r["p_goal"] >= 0.65
                and abs(r["score_diff"]) <= 1
            ):
                if r["p_home_next"] > r["p_away_next"]:
                    stava = "NEXT GOAL HOME"
                    razlog = "LATE PRESSURE HOME"
                else:
                    stava = "NEXT GOAL AWAY"
                    razlog = "LATE PRESSURE AWAY"

            # LATE GOAL (weak)
            elif minute >= 70 and r["p_goal"] >= 0.35:
                stava = "LATE GOAL"
                razlog = "LATE PRESSURE"

            # NEXT GOAL SIGNAL
            elif r["p_home_next"] >= 0.48:
                stava = "NEXT GOAL HOME"
                razlog = "NEXT GOAL SIGNAL"

            elif r["p_away_next"] >= 0.48:
                stava = "NEXT GOAL AWAY"
                razlog = "NEXT GOAL SIGNAL"

            # MOMENTUM
            elif abs(r["momentum"]) > 0.15:
                if r["momentum"] > 0:
                    stava = "NEXT GOAL HOME"
                    razlog = "MOMENTUM HOME"
                else:
                    stava = "NEXT GOAL AWAY"
                    razlog = "MOMENTUM AWAY"

            # FINAL SAFETY
            else:
                stava = "NO BET"
                razlog = "NO EDGE"

    # =====================================================
    # NEXT GOAL override
    # =====================================================

    if not history_block:

        if r["p_away_next"] >= 0.48 and r["momentum"] < -0.08:
            napoved = "GOST"
            stava = "2"
            razlog = "NEXT GOAL + MOMENTUM GOST"

        elif r["p_home_next"] >= 0.48 and r["momentum"] > 0.08:
            napoved = "DOMAČI"
            stava = "1"
            razlog = "NEXT GOAL + MOMENTUM DOMA"

        # HIGH GOAL + MOMENTUM
        elif r["p_goal"] >= 0.60 and abs(r["momentum"]) > 0.12:

            if r["momentum"] > 0:
                napoved = "DOMAČI"
                stava = "1"
            else:
                napoved = "GOST"
                stava = "2"

            razlog = "HIGH GOAL + MOMENTUM"
    print(f"\n{MAGENTA}Moje predvidevanje:{RESET}")
    print("Napoved izida".ljust(28), btxt(napoved, CYAN, True))
    rezultat = r["napoved_rezultata"]

    sh = r["score_home"]
    sa = r["score_away"]

    if r["p_away_next"] >= 0.48 and r["momentum"] < -0.08:
        rezultat = f"{sh}-{sa + 1}"

    elif r["p_home_next"] >= 0.48 and r["momentum"] > 0.08:
        rezultat = f"{sh + 1}-{sa}"

    # ZAČETEK DELA 8.2 / 8

    # =====================================================
    # AUTO BET DECISION (CMD)
    # =====================================================

    minute = r["minute"]
    score_diff = r["score_diff"]

    edge_home = r["edge_h"]
    edge_draw = r["edge_x"]
    edge_away = r["edge_a"]

    mc_home = r["mc_h_adj"]
    mc_draw = r["mc_x_adj"]
    mc_away = r["mc_a_adj"]

    # 1X2 VALUE EDGE IMA PREDNOST
    if edge_away >= 0.08 and mc_away >= 0.65:
        stava = "2"
        razlog = "VALUE EDGE AWAY"

    elif edge_home >= 0.08 and mc_home >= 0.65:
        stava = "1"
        razlog = "VALUE EDGE HOME"

    elif edge_draw >= 0.08 and mc_draw >= 0.55:
        stava = "X"
        razlog = "VALUE EDGE DRAW"

    # STRONG DRAW
    elif minute >= 60 and mc_draw >= 0.65:
        stava = "NO BET"
        razlog = "STRONG DRAW"

    # LATE GOAL
    elif (
            minute >= 70
            and r["p_goal"] >= 0.65
            and r["lam_total"] >= 1.05
            and abs(score_diff) <= 1
    ):
        stava = "LATE GOAL"
        razlog = "LATE PRESSURE"

    # NEXT GOAL
    elif r["p_home_next"] >= 0.48:
        stava = "NEXT GOAL HOME"
        razlog = "NEXT GOAL SIGNAL"

    elif r["p_away_next"] >= 0.48:
        stava = "NEXT GOAL AWAY"
        razlog = "NEXT GOAL SIGNAL"

    # MOMENTUM
    elif abs(r["momentum"]) > 0.15:
        if r["momentum"] > 0:
            stava = "NEXT GOAL HOME"
            razlog = "MOMENTUM HOME"
        else:
            stava = "NEXT GOAL AWAY"
            razlog = "MOMENTUM AWAY"

    # LATE COMEBACK RISK
    elif (
            minute >= 84
            and abs(score_diff) == 1
            and r["sot_h"] >= r["sot_a"]
            and r["shots_h"] >= r["shots_a"]
    ):
        stava = "NO BET"
        razlog = "LATE COMEBACK RISK"

    # DEFAULT
    else:
        stava = "NO BET"
        razlog = "NO EDGE"

    print("Napoved rezultata".ljust(28), btxt(rezultat, CYAN, True))
    print("Kaj bi stavil".ljust(28), btxt(stava, GREEN if stava != "NO BET" else YELLOW, True))
    print("Zakaj".ljust(28), razlog)
    print(f"\n{MAGENTA}Na kaj moraš biti najbolj pozoren:{RESET}")
    print(f"{btxt('- Danger attacks', YELLOW, True)}")
    print(f"{btxt('- Tempo danger / tempo shots', ORANGE, True)}")
    print(f"{btxt('- Attack wave / timeline trend', RED, True)}")
    print(f"{btxt('- Any goal / next goal signal', GREEN, True)}")
    print(f"{btxt('- EDGE proti marketu', BLUE, True)}")



# ============================================================
# CFOS SLO INTERPRETACIJA (GLOBAL)
# ============================================================
def cfos_slo_interpretacija(
    lge_state,
    attack_wave,
    tempo_shots_side,
    tempo_danger_side,
    lge_favor,
    momentum,
    lam_home,
    lam_away,
    lam_total,
    p_goal,
    next_goal_pred,
    bet
):

    print("\n=============== CFOS RAZLAGA =================\n")

    print("LGE:")
    print(f"Stanje LGE: {lge_state}")
    print(f"Attack wave: {attack_wave}")

    if tempo_shots_side == "AWAY" and tempo_danger_side == "HOME":
        print("GOST ustvarja več pritiska in več strelov.")
        print("DOMA ima bolj nevarne napade in kvalitetnejše priložnosti.")
        print("To je tipičen scenarij protinapada DOMA.")
    elif tempo_shots_side == "HOME" and tempo_danger_side == "AWAY":
        print("DOMA ustvarja več pritiska in več strelov.")
        print("GOST ima bolj nevarne napade in kvalitetnejše priložnosti.")
        print("To je tipičen scenarij protinapada GOST.")
    elif lge_favor == "HOME":
        print("Model daje prednost DOMA za naslednji gol.")
    elif lge_favor == "AWAY":
        print("Model daje prednost GOST za naslednji gol.")
    else:
        print("Situacija je uravnotežena brez jasnega favorita.")

    print()
    print("MOMENTUM:")

    if momentum > 0.2:
        print("Trenutni pritisk je na strani DOMA.")
        print("DOMA pogosteje napada in drži igro v napadu.")
    elif momentum < -0.2:
        print("Trenutni pritisk je na strani GOST.")
        print("GOST pogosteje napada in ustvarja več priložnosti.")
    else:
        print("Ni izrazitega pritiska ene ekipe.")
        print("Tekma je uravnotežena.")

    print()
    print("LAMBDA:")

    if lam_total > 1.5:
        print("Verjetnost gola je visoka.")
    elif lam_total > 1.0:
        print("Verjetnost gola je zmerna.")
    else:
        print("Verjetnost gola je nizka.")

    if lam_home > lam_away:
        print("Model vidi večjo možnost gola za DOMA.")
    elif lam_away > lam_home:
        print("Model vidi večjo možnost gola za GOST.")
    else:
        print("Model vidi zelo podobno možnost gola za obe ekipi.")

    print()
    print("VERJETNOST GOLA:")

    if p_goal > 0.75:
        print("Gol je zelo verjeten v naslednjih minutah.")
    elif p_goal > 0.55:
        print("Gol je verjeten v naslednjih minutah.")
    else:
        print("Gol ni zelo verjeten.")

    print()
    print("NASLEDNJI GOL:")

    if next_goal_pred == "HOME":
        print("Model preferira DOMA kot naslednjega strelca.")
    elif next_goal_pred == "AWAY":
        print("Model preferira GOST kot naslednjega strelca.")
    else:
        print("Ni jasnega favorita za naslednji gol.")

    if bet == "NO BET":
        print("Prednost ni dovolj velika za varno stavo.")
    else:
        print(f"Situacija primerna za stavo: {bet}")

    print("\n============================================\n")

def izpis_rezultata(r):
    print(f"\n{CYAN}{BOLD}================ CFOS-XG PRO 75 TITAN [POLNA VERZIJA] ================={RESET}\n")

    print("MATCH".ljust(28), r["home"], "vs", r["away"])
    print("Minute".ljust(28), r["minute"])
    print("Score".ljust(28), f'{r["score_home"]}-{r["score_away"]}')
    print("Score diff".ljust(28), r["score_diff"])
    print(cl("TEST XG", "BARVA XG", COL_XG, True))
    print(cl("TEST PM", "BARVA PM", COL_PM, True))
    print(cl("TEST LAMBDA", "BARVA LAMBDA", COL_LAMBDA, True))
    print(cl("TEST MC", "BARVA MC", COL_MC, True))
    print(cl("xG home", round(r["xg_h"], 3), COL_XG, True))
    print(cl("xG away", round(r["xg_a"], 3), COL_XG, True))
    print(cl("xG source", "SYNTHETIC" if r["synthetic_xg_used"] else "REAL", COL_XG, True))

    print(f"\n{MAGENTA}--------------- LEARNING ----------------{RESET}\n")
    print("Bucket".ljust(28),
          f'{bucket_minute(r["minute"])} | xG:{bucket_xg(r["xg_total"])} | SOT:{bucket_sot(r["sot_total"])} | SH:{bucket_shots(r["shots_total"])} | SD:{bucket_score_diff(r["score_diff"])} | DNG:{bucket_danger(r["danger_total"])}')
    print("Game type".ljust(28), r["game_type"])
    print("Learn factor (GOAL)".ljust(28), round(r["lf_goal"], 3), f'(bucket n: {r["n_goal"]})')

    # ============================================================
    # LEARN RATIOS (1X2) — WITH % AND MATCH COUNT + REAL %
    # ============================================================
    ph = (r["rh"] - 1.0) * 100.0
    pd = (r["rx"] - 1.0) * 100.0
    pa = (r["ra"] - 1.0) * 100.0

    base = 1 / 3
    h_est = int(r["n_1x2"] * base * r["rh"])
    d_est = int(r["n_1x2"] * base * r["rx"])
    a_est = int(r["n_1x2"] * base * r["ra"])

    h_pct = (h_est / r["n_1x2"] * 100) if r["n_1x2"] else 0
    d_pct = (d_est / r["n_1x2"] * 100) if r["n_1x2"] else 0
    a_pct = (a_est / r["n_1x2"] * 100) if r["n_1x2"] else 0

    print("")
    print(f"Learn ratios (1X2)  (bucket n: {r['n_1x2']})")
    print("")
    print(f"H  {r['rh']:.3f}   ({ph:+.1f}%)   ≈ {h_est}/{r['n_1x2']}   → {h_pct:.1f}%")
    print(f"D  {r['rx']:.3f}   ({pd:+.1f}%)   ≈ {d_est}/{r['n_1x2']}   → {d_pct:.1f}%")
    print(f"A  {r['ra']:.3f}   ({pa:+.1f}%)   ≈ {a_est}/{r['n_1x2']}   → {a_pct:.1f}%")

    print_live_match_memory(r)

    print_razumevanje(r)

    print_live_tempo_rate(r)

    print_live_extended_stats(r)

    print(f"\n{MAGENTA}--------------- FOTMOB EXTRA ----------------{RESET}\n")
    print("Key passes".ljust(28), round(r["keypasses_h"], 2), round(r["keypasses_a"], 2))
    print("Crosses".ljust(28), round(r["crosses_h"], 2), round(r["crosses_a"], 2))
    print("Aerial duels".ljust(28), round(r["aerials_h"], 2), round(r["aerials_a"], 2))
    print("Dribbles".ljust(28), round(r["dribbles_h"], 2), round(r["dribbles_a"], 2))
    print("Final third entries".ljust(28), round(r["final_third_h"], 2), round(r["final_third_a"], 2))
    print("Long balls".ljust(28), round(r["long_balls_h"], 2), round(r["long_balls_a"], 2))
    print("Big ch. created".ljust(28), round(r["bc_created_h"], 2), round(r["bc_created_a"], 2))
    print("Action areas".ljust(28), round(r["action_left"], 2), round(r["action_mid"], 2), round(r["action_right"], 2))

    print_live_momentum_engine(r)

    print_live_lambda_engine(r)

    print_live_overpressure_engine(r)

    print_live_goal_probability(r)
    print_next_goal_bet(r)
    print_counter_control(r)

    # ============================================================
    # NEXT GOAL SMART PREDICTION
    # ============================================================
    ng_smart = r.get("next_goal_prediction_smart") or {}
    if ng_smart:
        print()
        print(f"{COL_NEXT}--------------- NEXT GOAL SMART ----------------{RESET}")
        print(f"Prediction".ljust(28), btxt(str(ng_smart.get("prediction", "N/A")), COL_NEXT, True))
        conf_val = float(ng_smart.get("confidence", 0) or 0)
        conf_pct = round(conf_val * 100, 1)
        conf_col = GREEN if conf_val >= 0.57 else YELLOW if conf_val >= 0.43 else RED
        print(f"Confidence".ljust(28), btxt(f"{conf_pct} %", conf_col, True))
        print(f"Score HOME".ljust(28), round(ng_smart.get("score_h", 0), 4))
        print(f"Score AWAY".ljust(28), round(ng_smart.get("score_a", 0), 4))
        print(f"Signals agreement".ljust(28), f"{ng_smart.get('signals_agreement', 0)}/7")
        print(f"Tempo mult".ljust(28), ng_smart.get("tempo_mult", 1.0))
        print(f"Minute mult".ljust(28), ng_smart.get("minute_mult", 1.0))
        print("------------------------------------------------")



    print("META HOME".ljust(28), round(r["mc_h_adj"], 4))
    print("META DRAW".ljust(28), round(r["mc_x_adj"], 4))
    print("META AWAY".ljust(28), round(r["mc_a_adj"], 4))

    print(f"\n{MAGENTA}--------------- MONTE CARLO ----------------{RESET}\n")
    print(cl("Monte Carlo sims", r["sim_used"], COL_MC))
    print(cl("Exact score sims", r["exact_sim_used"], COL_MC))
    print(cl("Away win (RAW)", f'{pct(r["mc_a_raw"])} %', COL_MC, True))
    print(cl("Draw (RAW)", f'{pct(r["mc_x_raw"])} %', COL_MC, True))
    print(cl("Home win (RAW)", f'{pct(r["mc_h_raw"])} %', COL_MC, True))
    print(cl("Away win (CAL)", f'{pct(r["mc_a_adj"])} %', COL_MC, True))
    print(cl("Draw (CAL)", f'{pct(r["mc_x_adj"])} %', COL_MC, True))
    print(cl("Home win (CAL)", f'{pct(r["mc_h_adj"])} %', COL_MC, True))

    print(f"\n{MAGENTA}--------------- FINAL SCORE PREDICTION ----------------{RESET}\n")
    if r["top_scores"]:
        print("Most likely final".ljust(28), f'{r["top_scores"][0][0]} | {pct(r["top_scores"][0][1])} %')
        for i, (score, p) in enumerate(r["top_scores"][:5], 1):
            print(f"Top {i}".ljust(28), f'{score} | {pct(p)} %')
    else:
        print("Most likely final".ljust(28), "N/A")

    print_interpretacija(r)
    print_cfos_history_engine(r)

    print(f"\n{MAGENTA}--------------- HISTORY SCORE BIAS ----------------{RESET}\n")
    if r["hist_bias"] is None:
        print("History bucket".ljust(28), "Ni dovolj podatkov")
    else:
        print("History bucket".ljust(28), f'n={r["hist_bias"]["n"]}')
        # HISTORY STRENGTH
        hist_n = r["hist_bias"]["n"]

        if hist_n < 20:
            strength = "WEAK"
        elif hist_n < 40:
            strength = "OK"
        elif hist_n < 80:
            strength = "GOOD"
        else:
            strength = "STRONG"

        print("History strength".ljust(28), strength)
        print("Hist HOME".ljust(28), f'{pct(r["hist_bias"]["p_home"])} %')
        print("Hist DRAW".ljust(28), f'{pct(r["hist_bias"]["p_draw"])} %')
        print("Hist AWAY".ljust(28), f'{pct(r["hist_bias"]["p_away"])} %')
        print("Hist GOAL".ljust(28), f'{pct(r["hist_bias"]["p_goal"])} %')

        # HISTORY PREDICTION
        hist_home = r["hist_bias"]["p_home"]
        hist_draw = r["hist_bias"]["p_draw"]
        hist_away = r["hist_bias"]["p_away"]

        if hist_home > hist_draw and hist_home > hist_away:
            hist_pred = "HOME"
        elif hist_away > hist_home and hist_away > hist_draw:
            hist_pred = "AWAY"
        else:
            hist_pred = "DRAW"

        print("History prediction".ljust(28), hist_pred)

    print(f"\n{MAGENTA}--------------- EXACT SCORE HISTORY ----------------{RESET}\n")
    if r["exact_hist"] is None:
        print("Exact history".ljust(28), "Ni dovolj podatkov")
    else:
        print("Exact history".ljust(28), f'n={r["exact_hist"]["n"]}')
        print("Exact no goal".ljust(28), f'{pct(r["exact_hist"]["p_no_goal"])} %')
        print("Exact goal".ljust(28), f'{pct(r["exact_hist"]["p_goal"])} %')

    print(f"\n{MAGENTA}--------------- 1X2 (MODEL vs MARKET) ----------------{RESET}\n")
    print("Outcome       Model %   Market %     EDGE %")
    print("------------------------------------------")
    print(format_edge_line("HOME", r["mc_h_adj"], r["imp_h"], r["edge_h"]))
    print(format_edge_line("DRAW", r["mc_x_adj"], r["imp_x"], r["edge_x"]))
    print(format_edge_line("AWAY", r["mc_a_adj"], r["imp_a"], r["edge_a"]))

    print(f"\n{MAGENTA}--------------- TEAM / MARKET ----------------{RESET}\n")
    print("Prematch strength".ljust(28), r["prematch_h"], r["prematch_a"])
    print("ELO".ljust(28), r["elo_h"], r["elo_a"])
    print("Prev odds".ljust(28), r["prev_odds_home"], r["prev_odds_draw"], r["prev_odds_away"])
    print("Market overround".ljust(28), f'{round(r["overround"] * 100, 2)} %')

    print(f"\n{MAGENTA}--------------- CONFIDENCE ----------------{RESET}\n")
    print("Confidence".ljust(28), btxt(f'{round(r["confidence"], 1)} /100', color_conf(r["confidence"]), True))
    print("Confidence band".ljust(28), btxt(r["confidence_band"], color_conf(r["confidence"]), True))

    print(f"\n{MAGENTA}--------------- LIVE FILTER ----------------{RESET}\n")
    print("Max MC".ljust(28), round(r["max_mc"], 3))
    print("Use filter".ljust(28), "YES" if r["use_filter"] else "NO")
    print("Filter reason".ljust(28), r["use_reason"])
    print(f"\n{MAGENTA}--------------- CFOS FOCUS ENGINE ----------------{RESET}\n")

    minute = r["minute"]
    score_diff = r["score_diff"]

    if minute <= 30:
        print("- GLEJ: tempo_shots")
        print("- GLEJ: tempo_danger")
        print("- GLEJ: xg_rate_total")
        print("- GLEJ: P(goal)")

    elif minute <= 60:

        if score_diff == 0:
            print("- GLEJ: momentum")
            print("- GLEJ: SOT ratio")
            print("- GLEJ: pressure")
            print("- GLEJ: lambda total")
            print("- GLEJ: next goal signal")
        else:
            print("- GLEJ: comeback pressure")
            print("- GLEJ: momentum")
            print("- GLEJ: attack wave")
            print("- GLEJ: lambda losing team")

    elif minute <= 75:

        if score_diff == 0:
            print("- GLEJ: momentum")
            print("- GLEJ: lambda home")
            print("- GLEJ: lambda away")
            print("- GLEJ: draw crusher")
        else:
            print("- GLEJ: comeback")
            print("- GLEJ: kill game")
            print("- GLEJ: timeline trend")

    else:

        if score_diff == 0:
            print("- GLEJ: last goal probability")
            print("- GLEJ: momentum")
            print("- GLEJ: lambda stronger")
        else:
            print("- GLEJ: comeback last")
            print("- GLEJ: time decay")
            print("- GLEJ: kill game")

    print_5_korakov(r)

    print(f"\n{CYAN}{BOLD}================ NEXT GOAL SIGNAL ================ {RESET}\n")
    ng_color = GREEN if ("DOMAČI" in r["next_goal_signal"] or "GOSTUJOČI" in r["next_goal_signal"]) else YELLOW
    print(btxt(r["next_goal_signal"], ng_color, True))

    print(f"\n{CYAN}{BOLD}================ MATCH SIGNAL ================ {RESET}\n")
    if r["p_goal"] < 0.25:
        print(btxt("• NIZKA VERJETNOST GOLA", RED, True))
    elif r["p_goal"] >= 0.55:
        print(btxt("• VISOKA VERJETNOST GOLA", GREEN, True))
    else:
        print(btxt("• SREDNJA VERJETNOST GOLA", YELLOW, True))
    print(btxt(r["match_signal"], CYAN, True))

    print_top_signals(r)
    cfos_analiza_sistema(r)

    print(f"\n{CYAN}=========================================================== {RESET}")
    # ============================================================
    # CFOS SLO INTERPRETACIJA - DODATEK
    # ============================================================
    cfos_slo_interpretacija(
        lge_state=str(r.get("lge_state", lge_state_value(r)) or "PASSIVE"),
        attack_wave=str(r.get("wave", {}).get("active", False) and side_name_from_diff(
            float(r.get("danger_h", 0) or 0) - float(r.get("danger_a", 0) or 0),
            "HOME",
            "AWAY",
            "NO",
            eps=1.0
        ) or "NO"),
        tempo_shots_side=side_name_from_diff(
            float(r.get("shots_h", 0) or 0) - float(r.get("shots_a", 0) or 0),
            "HOME",
            "AWAY",
            "BALANCED",
            eps=0.5
        ),
        tempo_danger_side=side_name_from_diff(
            float(r.get("danger_h", 0) or 0) - float(r.get("danger_a", 0) or 0),
            "HOME",
            "AWAY",
            "BALANCED",
            eps=1.0
        ),
        lge_favor=side_name_from_diff(
            float(r.get("lam_h", 0) or 0) - float(r.get("lam_a", 0) or 0),
            "HOME",
            "AWAY",
            "BALANCED",
            eps=0.03
        ),
        momentum=float(r.get("momentum", 0) or 0),
        lam_home=float(r.get("lam_h", 0) or 0),
        lam_away=float(r.get("lam_a", 0) or 0),
        lam_total=float(r.get("lam_total", 0) or 0),
        p_goal=float(r.get("p_goal", 0) or 0),
        next_goal_pred=(
            "HOME" if float(r.get("p_home_next", 0) or 0) > float(r.get("p_away_next", 0) or 0)
            else "AWAY" if float(r.get("p_away_next", 0) or 0) > float(r.get("p_home_next", 0) or 0)
            else "BALANCED"
        ),
        bet=str(r.get("next_goal_bet", "NO BET") or "NO BET")
    )

# ============================================================
# CFOS ACCURACY COUNTER
# ============================================================


def cfos_accuracy():

    file = "cfos75_accuracy_log.csv"

    if not os.path.exists(file):
        return

    total = 0
    correct_total = 0

    draw_total = 0
    draw_correct = 0

    late_total = 0
    late_correct = 0

    home_total = 0
    home_correct = 0

    away_total = 0
    away_correct = 0
    hit_1x2 = 0

    try:
        with open(file, newline='', encoding="utf-8") as f:
            r = csv.DictReader(f)

            for row in r:

                total += 1

                pred = row.get("prediction")
                real = row.get("final_result")
                correct = row.get("correct")
                minute = int(row.get("minute", 0))

                if correct == "1":
                    correct_total += 1

                # DRAW
                if pred == "REMI":
                    draw_total += 1
                    if correct == "1":
                        draw_correct += 1

                # LATE GAME
                if minute >= 70:
                    late_total += 1
                    if correct == "1":
                        late_correct += 1

                # HOME
                if pred == "DOMAČI":
                    home_total += 1
                    if correct == "1":
                        home_correct += 1

                # AWAY
                if pred == "GOST":
                    away_total += 1
                    if correct == "1":
                        away_correct += 1
                if correct == "1":
                    hit_1x2 += 1
    except Exception as e:
        print("Napaka pri branju accuracy log:", e)
        return

    if total == 0:
        return

    print()
    print("============= CFOS PRO ACCURACY =============")

    print("TOTAL".ljust(18), f"{correct_total}/{total} ({round(correct_total / total * 100, 1)}%)")

    if draw_total > 0:
        print("DRAW".ljust(18), f"{draw_correct}/{draw_total} ({round(draw_correct / draw_total * 100, 1)}%)")

    if late_total > 0:
        print("LATE 70+".ljust(18), f"{late_correct}/{late_total} ({round(late_correct / late_total * 100, 1)}%)")

    if home_total > 0:
        print("HOME".ljust(18), f"{home_correct}/{home_total} ({round(home_correct / home_total * 100, 1)}%)")

    if away_total > 0:
        print("AWAY".ljust(18), f"{away_correct}/{away_total} ({round(away_correct / away_total * 100, 1)}%)")

    print("=============================================")
    print("============= CFOS ACCURACY =============")
    print("Matches         ", total)
    print("1X2 correct     ", hit_1x2, f"({round(hit_1x2 / total * 100, 1)}%)")
    print("========================================")
    print()

def history_accuracy():

    file = MATCH_RESULT_FILE

    if not os.path.exists(file):
        return

    total = 0
    correct = 0

    h_ok = 0
    x_ok = 0
    a_ok = 0

    try:
        with open(file, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)

            for r in reader:

                hist = normalize_outcome_label(r.get("history_pred", ""))
                result = normalize_outcome_label(r.get("result_1x2", ""))

                if hist == "" or result == "":
                    continue

                total += 1

                if hist == result:
                    correct += 1

                    if result == "HOME":
                        h_ok += 1
                    elif result == "DRAW":
                        x_ok += 1
                    elif result == "AWAY":
                        a_ok += 1

        acc = (correct / total * 100) if total > 0 else 0.0

        print("")
        print("============= HISTORY ACCURACY =============")
        print(f"Matches          {total}")
        print(f"Correct          {correct}")
        print(f"Accuracy         {acc:.1f}%")
        print(f"HOME correct     {h_ok}")
        print(f"DRAW correct     {x_ok}")
        print(f"AWAY correct     {a_ok}")
        print("============================================")

    except Exception as e:
        print("Napaka v history_accuracy():", e)

# ============================================================
# CFOS FINAL BET ENGINE (FULL PRO VERSION + HIGH IQ)
# DAJ V 8/8
# KLIC NA KONCU IZPISA: bet_decision(r)
# ============================================================

LAST_BET = None
LAST_MINUTE = 0
LAST_MATCH_KEY = None


def bet_decision(r):
    """
    Master bet decision engine for live football betting.

    Evaluates all available signals and model outputs to produce a single
    bet recommendation with confidence level, printed to stdout.

    Args:
        r (dict): Match result dictionary containing all computed metrics.
            Required keys:
            - minute (int/float): Current match minute (0-90+)
            - score_diff (int): Score difference home minus away
            - home (str): Home team name
            - away (str): Away team name
            - p_goal (float): Probability of a goal occurring (0.0-1.0)
            - p_home_next (float): Probability home team scores next
            - p_away_next (float): Probability away team scores next
            - lam_h, lam_a (float): Expected goals rate (lambda) for home/away
            - xg_h, xg_a (float): Expected goals accumulated for home/away
            - sot_h, sot_a (float): Shots on target for home/away
            - danger_h, danger_a (float): Danger attack index for home/away
            - momentum (float): Match momentum (positive=home, negative=away)
            - mc_h_adj, mc_x_adj, mc_a_adj (float): Monte Carlo 1X2 probabilities
            - next_goal_prediction_smart (dict): Output from predict_next_goal_smart()
                with 'prediction' (str) and 'confidence' (float) keys
            - red_h, red_a (float): Red cards for home/away teams
            - odds_home, odds_draw, odds_away (float): Market odds (0 if unavailable)

    Prints:
        Formatted BET DECISION block with:
        - Main bet recommendation
        - Confidence level (HIGH / MEDIUM / LOW / LOCKED / EARLY GAME)
        - Top 5 alternative bets with scores
        - Model diagnostics (p_goal, stronger side, MC/history values)

    Decision Phases:
        1. EARLY GAME (< 45 min)    : Always NO BET — insufficient data
        2. EARLY PRESSURE (45-55)   : Wait for signal activation thresholds
        3. SMART PRIORITY (55-75)   : ng_smart_conf >= 0.72 triggers direct bet
        4. MASTER FREEZE (70+ min)  : NO BET when low lambda/tempo/goal/balanced
        5. UNIVERSAL SCORING        : Score all 7 bet types, select highest

    Example:
        # CSV: "Arsenal,Chelsea,2.1,3.3,3.8,68,1,0,0.80,0.50,6,4,3,2,22,18,8,5,..."
        r = izracunaj_model(csv_row)
        bet_decision(r)
        # Output:
        #   =============== BET DECISION ===============
        #   MINUTE: 68
        #   BET: NEXT GOAL HOME
        #   CONFIDENCE: HIGH
        #   VALID: 68-73
        #   ============================================
    """

    global LAST_BET
    global LAST_MINUTE
    global LAST_MATCH_KEY

    # =====================================================
    # BASIC INPUT
    # =====================================================

    minute = int(float(r.get("minute", 0) or 0))
    score_diff = int(float(r.get("score_diff", 0) or 0))

    home = str(r.get("home", "") or "")
    away = str(r.get("away", "") or "")
    match_key = f"{home} vs {away}"

    p_goal = float(r.get("p_goal", 0) or 0)
    p_home_next = float(r.get("p_home_next", 0) or 0)
    p_away_next = float(r.get("p_away_next", 0) or 0)

    lam_h = float(r.get("lam_h", 0) or 0)
    lam_a = float(r.get("lam_a", 0) or 0)

    xg_h = float(r.get("xg_h", 0) or 0)
    xg_a = float(r.get("xg_a", 0) or 0)

    sot_h = float(r.get("sot_h", 0) or 0)
    sot_a = float(r.get("sot_a", 0) or 0)

    danger_h = float(r.get("danger_h", 0) or 0)
    danger_a = float(r.get("danger_a", 0) or 0)

    momentum = float(r.get("momentum", 0) or 0)

    mc_h = float(r.get("mc_h_adj", r.get("mc_h_raw", 0)) or 0)
    mc_x = float(r.get("mc_x_adj", r.get("mc_x_raw", 0)) or 0)
    mc_a = float(r.get("mc_a_adj", r.get("mc_a_raw", 0)) or 0)

    hist_home = float(r.get("hist_home", 0) or 0)
    hist_draw = float(r.get("hist_draw", 0) or 0)
    hist_away = float(r.get("hist_away", 0) or 0)

    meta_home = float(r.get("meta_home", mc_h) or 0)
    meta_draw = float(r.get("meta_draw", mc_x) or 0)
    meta_away = float(r.get("meta_away", mc_a) or 0)

    tempo_shots = float(r.get("tempo_shots", 0) or 0)
    tempo_danger = float(r.get("tempo_danger", 0) or 0)

    dominance = float(r.get("dominance", 0) or 0)

    # next goal smart prediction
    ng_smart = r.get("next_goal_prediction_smart") or {}
    ng_smart_pred = str(ng_smart.get("prediction", "") or "")
    ng_smart_conf = float(ng_smart.get("confidence", 0) or 0)

    # optional high-IQ extras
    red_h = float(r.get("red_h", 0) or 0)
    red_a = float(r.get("red_a", 0) or 0)

    odds_home = float(r.get("odds_home", 0) or 0)
    odds_draw = float(r.get("odds_draw", 0) or 0)
    odds_away = float(r.get("odds_away", 0) or 0)

    # =====================================================
    # RESET ZA NOVO TEKMO
    # =====================================================

    if LAST_MATCH_KEY != match_key:
        LAST_BET = None
        LAST_MINUTE = 0
        LAST_MATCH_KEY = match_key

    # =====================================================
    # ONLY AFTER 45
    # =====================================================

    if minute < 45:
        print()
        print("=============== BET DECISION ===============")
        print()
        print("MINUTE:", minute)
        print()
        print("BET: NO BET")
        print("CONFIDENCE: EARLY GAME")
        print()
        print("ALTERNATIVE:")
        print("2) NO BET")
        print("3) NO BET")
        print("4) NO BET")
        print("5) NO BET")
        print()
        print("MODEL:")
        print("P_GOAL:", round(p_goal, 2))
        print("STRONGER SIDE: NONE")
        print("MC:", round(mc_h, 2), "/", round(mc_x, 2), "/", round(mc_a, 2))
        print("HISTORY:", round(hist_home, 2), "/", round(hist_draw, 2), "/", round(hist_away, 2))
        print()
        print("============================================")
        return

    # =====================================================
    # 45-55 EARLY PHASE: VERY STRICT FILTER
    # =====================================================

    lam_diff_early = abs(lam_h - lam_a)

    if 45 <= minute < 55:
        if p_goal < 0.35 or abs(momentum) < 0.10 or lam_diff_early < 0.15:
            print()
            print("=============== BET DECISION ===============")
            print()
            print("MINUTE:", minute, "(45-55 early phase)")
            print()
            print("BET: NO BET")
            print("CONFIDENCE: EARLY PHASE - WAITING")
            print()
            print("ALTERNATIVE:")
            print("2) NO BET")
            print("3) NO BET")
            print("4) NO BET")
            print("5) NO BET")
            print()
            print("MODEL:")
            print("P_GOAL:", round(p_goal, 2))
            print("STRONGER SIDE: NONE")
            print("MC:", round(mc_h, 2), "/", round(mc_x, 2), "/", round(mc_a, 2))
            print()
            print("============================================")
            return

    # =====================================================
    # NG SMART TOP PRIORITY (ABOVE ALL OTHER FILTERS)
    # =====================================================

    if ng_smart_pred in ("HOME", "AWAY") and ng_smart_conf >= 0.72 and p_goal >= 0.30:
        _ng_main_bet = f"NEXT GOAL {ng_smart_pred}"
        _ng_confidence = "HIGH" if ng_smart_conf >= 0.82 else "MEDIUM"

        LAST_BET = _ng_main_bet
        LAST_MINUTE = minute

        print()
        print("=============== BET DECISION ===============")
        print()
        print("MINUTE:", minute)
        print()
        print("BET:", _ng_main_bet)
        print("CONFIDENCE:", _ng_confidence)
        print("VALID:", minute, "-", int(minute + 5))
        print()
        print("ALTERNATIVE:")
        print("2) NO BET")
        print("3) NO BET")
        print("4) NO BET")
        print("5) NO BET")
        print()
        print("MODEL:")
        print("P_GOAL:", round(p_goal, 2))
        print("STRONGER SIDE:", ng_smart_pred)
        print("MC:", round(mc_h, 2), "/", round(mc_x, 2), "/", round(mc_a, 2))
        print("HISTORY:", round(hist_home, 2), "/", round(hist_draw, 2), "/", round(hist_away, 2))
        print(f"NEXT GOAL SMART: {ng_smart_pred} (conf: {round(ng_smart_conf * 100, 1)} %)")
        print()
        print("============================================")
        return

    # =====================================================
    # MASTER FREEZE FILTER (ANTI FAKE AWAY)
    # =====================================================

    lam_total = lam_h + lam_a

    low_lambda = lam_total < 0.45
    low_tempo = tempo_shots < 0.14 and tempo_danger < 1.05
    low_goal = p_goal < 0.38
    balanced = abs(momentum) < 0.10 and abs(lam_h - lam_a) < 0.12

    if minute >= 70 and low_lambda and low_tempo and low_goal and balanced:
        print()
        print("=============== BET DECISION ===============")
        print()
        print("MINUTE:", minute)
        print()
        print("BET: NO BET")
        print("CONFIDENCE: HIGH")
        print("VALID:", minute, "-", int(minute + 5))
        print()
        print("ALTERNATIVE:")
        print("2) NO GOAL")
        print("3) DRAW")
        print("4) NEXT GOAL HOME")
        print("5) NEXT GOAL AWAY")
        print()
        print("MODEL:")
        print("P_GOAL:", round(p_goal, 2))
        print("STRONGER SIDE: NONE")
        print("MC:", round(mc_h, 2), "/", round(mc_x, 2), "/", round(mc_a, 2))
        print()
        print("============================================")

        return

    # =====================================================
    # BASIC DIFFS
    # =====================================================

    sot_diff = abs(sot_h - sot_a)
    xg_diff = abs(xg_h - xg_a)
    danger_diff = abs(danger_h - danger_a)
    lam_diff = abs(lam_h - lam_a)

    # =====================================================
    # STRONGER SIDE SCORE
    # =====================================================

    side_score_h = 0.0
    side_score_a = 0.0

    if p_home_next > p_away_next:
        side_score_h += 2.0
    elif p_away_next > p_home_next:
        side_score_a += 2.0

    if lam_h > lam_a:
        side_score_h += 2.0
    elif lam_a > lam_h:
        side_score_a += 2.0

    if xg_h > xg_a:
        side_score_h += 1.5
    elif xg_a > xg_h:
        side_score_a += 1.5

    if sot_h > sot_a:
        side_score_h += 1.2
    elif sot_a > sot_h:
        side_score_a += 1.2

    if danger_h > danger_a:
        side_score_h += 2.0
    elif danger_a > danger_h:
        side_score_a += 2.0

    if momentum > 0.08:
        side_score_h += 1.8
    elif momentum < -0.08:
        side_score_a += 1.8

    if dominance > 0.08:
        side_score_h += 1.0
    elif dominance < -0.08:
        side_score_a += 1.0

    if meta_home > meta_away and meta_home > meta_draw:
        side_score_h += 1.0
    elif meta_away > meta_home and meta_away > meta_draw:
        side_score_a += 1.0

    if hist_home > hist_away and hist_home > hist_draw:
        side_score_h += 0.8
    elif hist_away > hist_home and hist_away > hist_draw:
        side_score_a += 0.8

    stronger_side = "NONE"
    if side_score_h > side_score_a:
        stronger_side = "HOME"
    elif side_score_a > side_score_h:
        stronger_side = "AWAY"

    # =====================================================
    # STRONGER SIDE HARD LOCK
    # =====================================================

    if mc_h >= 0.80 and mc_h > mc_a and mc_h > mc_x:
        stronger_side = "HOME"
    elif mc_a >= 0.80 and mc_a > mc_h and mc_a > mc_x:
        stronger_side = "AWAY"
    elif ng_smart_pred == "HOME" and ng_smart_conf >= 0.70 and mc_h >= 0.60:
        stronger_side = "HOME"
    elif ng_smart_pred == "AWAY" and ng_smart_conf >= 0.70 and mc_a >= 0.60:
        stronger_side = "AWAY"

    # =====================================================
    # FILTERS
    # =====================================================

    fake_pressure = False
    fake_reason = ""

    if abs(momentum) > 0.15 and sot_diff == 0 and xg_diff < 0.20:
        fake_pressure = True
        fake_reason = "Momentum without SOT/xG support"

    if abs(momentum) > 0.18 and danger_diff < 10 and lam_diff < 0.12:
        fake_pressure = True
        fake_reason = "Momentum not confirmed by danger/lambda"

    if tempo_shots < 0.10 and tempo_danger < 0.75 and abs(momentum) > 0.14:
        fake_pressure = True
        fake_reason = "Momentum without tempo"

    chaos = False
    if tempo_shots > 0.30 and tempo_danger > 1.60 and abs(momentum) < 0.05:
        chaos = True

    draw_crush = False
    if score_diff == 0:
        if (
            p_goal > 0.44
            or tempo_shots > 0.18
            or tempo_danger > 1.20
            or abs(momentum) > 0.12
            or lam_diff > 0.18
        ):
            draw_crush = True

    late_one_goal_context = False
    if minute >= 80 and abs(score_diff) == 1:
        if tempo_danger >= 1.10 and p_goal <= 0.62:
            late_one_goal_context = True

    # =====================================================
    # SCORE SYSTEM FOR ALL BET TYPES
    # =====================================================

    scores = {
        "NEXT GOAL HOME": 0.0,
        "NEXT GOAL AWAY": 0.0,
        "COMEBACK HOME": 0.0,
        "COMEBACK AWAY": 0.0,
        "DRAW": 0.0,
        "NO GOAL": 0.0,
        "NO BET": 0.0,
    }

    # -----------------------------------------------------
    # NEXT GOAL HOME
    # -----------------------------------------------------

    if p_goal > 0.50:
        scores["NEXT GOAL HOME"] += 2.0

    if p_home_next > p_away_next:
        scores["NEXT GOAL HOME"] += 2.0

    if stronger_side == "HOME":
        scores["NEXT GOAL HOME"] += 2.0

    if lam_h > lam_a:
        scores["NEXT GOAL HOME"] += 1.5

    if xg_h > xg_a:
        scores["NEXT GOAL HOME"] += 1.0

    if sot_h > sot_a:
        scores["NEXT GOAL HOME"] += 1.0

    if danger_h > danger_a:
        scores["NEXT GOAL HOME"] += 1.5

    if momentum > 0.10:
        scores["NEXT GOAL HOME"] += 1.2

    if tempo_shots > 0.14:
        scores["NEXT GOAL HOME"] += 0.8

    if tempo_danger > 1.00:
        scores["NEXT GOAL HOME"] += 0.8

    if mc_h > mc_x and mc_h > mc_a:
        scores["NEXT GOAL HOME"] += 1.0

    if meta_home > meta_draw and meta_home > meta_away:
        scores["NEXT GOAL HOME"] += 1.0

    if hist_home > hist_draw and hist_home > hist_away:
        scores["NEXT GOAL HOME"] += 0.6

    if fake_pressure or chaos:
        scores["NEXT GOAL HOME"] -= 2.0

    if late_one_goal_context and score_diff < 0 and mc_a >= mc_h:
        scores["NEXT GOAL HOME"] -= 1.6

    # smart next goal signal boost (HOME)
    if ng_smart_pred == "HOME" and ng_smart_conf >= 0.57:
        scores["NEXT GOAL HOME"] += 1.0 + ng_smart_conf
    elif ng_smart_pred == "HOME" and ng_smart_conf >= 0.43:
        scores["NEXT GOAL HOME"] += 0.6

    # -----------------------------------------------------
    # NEXT GOAL AWAY
    # -----------------------------------------------------

    if p_goal > 0.50:
        scores["NEXT GOAL AWAY"] += 2.0

    if p_away_next > p_home_next:
        scores["NEXT GOAL AWAY"] += 2.0

    if stronger_side == "AWAY":
        scores["NEXT GOAL AWAY"] += 2.0

    if lam_a > lam_h:
        scores["NEXT GOAL AWAY"] += 1.5

    if xg_a > xg_h:
        scores["NEXT GOAL AWAY"] += 1.0

    if sot_a > sot_h:
        scores["NEXT GOAL AWAY"] += 1.0

    if danger_a > danger_h:
        scores["NEXT GOAL AWAY"] += 1.5

    if momentum < -0.10:
        scores["NEXT GOAL AWAY"] += 1.2

    if tempo_shots > 0.14:
        scores["NEXT GOAL AWAY"] += 0.8

    if tempo_danger > 1.00:
        scores["NEXT GOAL AWAY"] += 0.8

    if mc_a > mc_x and mc_a > mc_h:
        scores["NEXT GOAL AWAY"] += 1.0

    if meta_away > meta_draw and meta_away > meta_home:
        scores["NEXT GOAL AWAY"] += 1.0

    if hist_away > hist_draw and hist_away > hist_home:
        scores["NEXT GOAL AWAY"] += 0.6

    if fake_pressure or chaos:
        scores["NEXT GOAL AWAY"] -= 2.0

    if late_one_goal_context and score_diff > 0 and mc_h >= mc_a:
        scores["NEXT GOAL AWAY"] -= 1.6

    # smart next goal signal boost (AWAY)
    if ng_smart_pred == "AWAY" and ng_smart_conf >= 0.57:
        scores["NEXT GOAL AWAY"] += 1.0 + ng_smart_conf
    elif ng_smart_pred == "AWAY" and ng_smart_conf >= 0.43:
        scores["NEXT GOAL AWAY"] += 0.6

    # -----------------------------------------------------
    # COMEBACK HOME
    # -----------------------------------------------------

    if score_diff < 0:
        scores["COMEBACK HOME"] += 2.5

    if stronger_side == "HOME" and score_diff < 0:
        scores["COMEBACK HOME"] += 2.0

    if p_goal > 0.42 and score_diff < 0:
        scores["COMEBACK HOME"] += 1.5

    if p_home_next > p_away_next and score_diff < 0:
        scores["COMEBACK HOME"] += 1.5

    if lam_h > lam_a and score_diff < 0:
        scores["COMEBACK HOME"] += 1.2

    if xg_h > xg_a and score_diff < 0:
        scores["COMEBACK HOME"] += 1.0

    if danger_h > danger_a and score_diff < 0:
        scores["COMEBACK HOME"] += 1.2

    if momentum > 0.10 and score_diff < 0:
        scores["COMEBACK HOME"] += 1.0

    if mc_x >= mc_h and score_diff < 0:
        scores["COMEBACK HOME"] += 0.5

    if hist_draw >= hist_away and score_diff < 0:
        scores["COMEBACK HOME"] += 0.4

    if fake_pressure:
        scores["COMEBACK HOME"] -= 2.0

    # -----------------------------------------------------
    # COMEBACK AWAY
    # -----------------------------------------------------

    if score_diff > 0:
        scores["COMEBACK AWAY"] += 2.5

    if stronger_side == "AWAY" and score_diff > 0:
        scores["COMEBACK AWAY"] += 2.0

    if p_goal > 0.42 and score_diff > 0:
        scores["COMEBACK AWAY"] += 1.5

    if p_away_next > p_home_next and score_diff > 0:
        scores["COMEBACK AWAY"] += 1.5

    if lam_a > lam_h and score_diff > 0:
        scores["COMEBACK AWAY"] += 1.2

    if xg_a > xg_h and score_diff > 0:
        scores["COMEBACK AWAY"] += 1.0

    if danger_a > danger_h and score_diff > 0:
        scores["COMEBACK AWAY"] += 1.2

    if momentum < -0.10 and score_diff > 0:
        scores["COMEBACK AWAY"] += 1.0

    if mc_x >= mc_a and score_diff > 0:
        scores["COMEBACK AWAY"] += 0.5

    if hist_draw >= hist_home and score_diff > 0:
        scores["COMEBACK AWAY"] += 0.4

    if fake_pressure:
        scores["COMEBACK AWAY"] -= 2.0

    # -----------------------------------------------------
    # DRAW
    # -----------------------------------------------------

    if score_diff == 0:
        scores["DRAW"] += 2.0

    if minute >= 75:
        scores["DRAW"] += 1.0

    if p_goal < 0.38:
        scores["DRAW"] += 1.8

    if mc_x > mc_h and mc_x > mc_a:
        scores["DRAW"] += 2.0

    if hist_draw >= hist_home and hist_draw >= hist_away:
        scores["DRAW"] += 1.2

    if meta_draw >= meta_home and meta_draw >= meta_away:
        scores["DRAW"] += 1.2

    if abs(momentum) < 0.08:
        scores["DRAW"] += 1.0

    if tempo_shots < 0.16:
        scores["DRAW"] += 0.8

    if tempo_danger < 1.05:
        scores["DRAW"] += 0.8

    if lam_diff < 0.15:
        scores["DRAW"] += 0.8

    if draw_crush or chaos:
        scores["DRAW"] -= 3.0

    # -----------------------------------------------------
    # NO GOAL
    # -----------------------------------------------------

    if minute >= 82:
        scores["NO GOAL"] += 2.0

    if p_goal < 0.30:
        scores["NO GOAL"] += 2.2

    if tempo_shots < 0.14:
        scores["NO GOAL"] += 1.2

    if tempo_danger < 0.95:
        scores["NO GOAL"] += 1.2

    if abs(momentum) < 0.06:
        scores["NO GOAL"] += 0.8

    if lam_diff < 0.18:
        scores["NO GOAL"] += 0.6

    if mc_x >= mc_h and mc_x >= mc_a:
        scores["NO GOAL"] += 1.0

    if hist_draw >= hist_home and hist_draw >= hist_away:
        scores["NO GOAL"] += 0.6

    if p_goal > 0.45:
        scores["NO GOAL"] -= 2.0

    if tempo_danger > 1.20 or tempo_shots > 0.18:
        scores["NO GOAL"] -= 1.2

    # -----------------------------------------------------
    # NO BET
    # -----------------------------------------------------

    scores["NO BET"] = 1.0

    if fake_pressure:
        scores["NO BET"] += 2.5

    if chaos:
        scores["NO BET"] += 2.5

    if 0.38 <= p_goal <= 0.50:
        scores["NO BET"] += 1.0

    if abs(side_score_h - side_score_a) < 1.0:
        scores["NO BET"] += 1.0

    if abs(mc_h - mc_a) < 0.08 and mc_x < 0.45:
        scores["NO BET"] += 0.8

    if draw_crush and score_diff == 0:
        scores["NO BET"] += 0.8

    # =====================================================
    # SAFETY ADJUSTMENTS
    # =====================================================

    if score_diff != 0:
        scores["DRAW"] -= 1.5

    if abs(score_diff) >= 2:
        scores["COMEBACK HOME"] -= 2.0
        scores["COMEBACK AWAY"] -= 2.0

    if stronger_side == "NONE":
        scores["NEXT GOAL HOME"] -= 1.0
        scores["NEXT GOAL AWAY"] -= 1.0

    # =====================================================
    # HIGH IQ GAME STATE PSYCHOLOGY
    # =====================================================

    if minute >= 87 and score_diff == 0:
        if tempo_shots < 0.18 and tempo_danger < 1.10:
            scores["NO GOAL"] += 2.5
            scores["DRAW"] += 1.5
            scores["NEXT GOAL HOME"] -= 1.5
            scores["NEXT GOAL AWAY"] -= 1.5

    # =====================================================
    # HIGH IQ FAVORITE PROTECTION
    # =====================================================

    if minute >= 80 and abs(score_diff) == 1:
        if meta_home > meta_away and score_diff > 0:
            scores["NO GOAL"] += 1.5
            scores["DRAW"] += 0.8
            scores["COMEBACK AWAY"] -= 1.5

        if meta_away > meta_home and score_diff < 0:
            scores["NO GOAL"] += 1.5
            scores["DRAW"] += 0.8
            scores["COMEBACK HOME"] -= 1.5

    # =====================================================
    # HIGH IQ RED CARD LOGIC
    # =====================================================

    if red_h > red_a:
        scores["NEXT GOAL AWAY"] += 1.8
        scores["COMEBACK AWAY"] += 1.0
        scores["NEXT GOAL HOME"] -= 1.5

    elif red_a > red_h:
        scores["NEXT GOAL HOME"] += 1.8
        scores["COMEBACK HOME"] += 1.0
        scores["NEXT GOAL AWAY"] -= 1.5

    # =====================================================
    # HIGH IQ LAST MINUTE SPIKE
    # =====================================================

    if minute >= 87:
        if tempo_shots > 0.22 or tempo_danger > 1.30:
            scores["NEXT GOAL HOME"] += 1.2
            scores["NEXT GOAL AWAY"] += 1.2
            scores["NO GOAL"] -= 1.5

    # =====================================================
    # HIGH IQ CONTEXT REASONING
    # =====================================================

    if minute >= 85 and score_diff == 0:
        signals = 0

        if tempo_shots > 0.18:
            signals += 1
        if tempo_danger > 1.15:
            signals += 1
        if abs(momentum) > 0.10:
            signals += 1
        if lam_diff > 0.15:
            signals += 1
        if stronger_side != "NONE":
            signals += 1
        if p_goal > 0.45:
            signals += 1

        if signals >= 4:
            scores["NEXT GOAL HOME"] += 1.5
            scores["NEXT GOAL AWAY"] += 1.5
            scores["DRAW"] -= 2.0

    # =====================================================
    # HIGH IQ UNCERTAINTY FILTER
    # =====================================================

    if abs(side_score_h - side_score_a) < 0.8 and p_goal < 0.45:
        scores["NO BET"] += 2.0

    # =====================================================
    # HIGH IQ CONTRADICTION DETECTOR
    # =====================================================

    contradiction = 0

    if momentum > 0.08 and xg_a > xg_h:
        contradiction += 1

    if momentum < -0.08 and xg_h > xg_a:
        contradiction += 1

    if danger_diff < 5 and abs(momentum) > 0.12:
        contradiction += 1

    if lam_diff < 0.08 and abs(momentum) > 0.14:
        contradiction += 1

    if contradiction >= 2:
        scores["NO BET"] += 2.0
        scores["NEXT GOAL HOME"] -= 1.0
        scores["NEXT GOAL AWAY"] -= 1.0

    # =====================================================
    # HIGH IQ SMART DRAW FILTER
    # =====================================================

    if score_diff == 0 and minute >= 82:
        if p_goal > 0.46 and stronger_side != "NONE":
            scores["DRAW"] -= 2.0

        if tempo_danger > 1.15:
            scores["DRAW"] -= 1.2

    # =====================================================
    # HIGH IQ LATE KILL LOGIC
    # =====================================================

    if minute >= 85 and abs(score_diff) == 1:
        if stronger_side == "HOME" and score_diff > 0:
            scores["COMEBACK AWAY"] -= 2.0

        if stronger_side == "AWAY" and score_diff < 0:
            scores["COMEBACK HOME"] -= 2.0

    # =====================================================
    # HIGH IQ CHAOS DETECTOR
    # =====================================================

    if tempo_shots > 0.28 and tempo_danger > 1.55:
        scores["NEXT GOAL HOME"] += 0.8
        scores["NEXT GOAL AWAY"] += 0.8
        scores["NO GOAL"] -= 1.5

    # =====================================================
    # HIGH IQ MARKET SANITY CHECK
    # =====================================================

    if odds_home > 0 and odds_away > 0:
        if odds_home < odds_away * 0.6:
            scores["NEXT GOAL HOME"] += 0.5
        elif odds_away < odds_home * 0.6:
            scores["NEXT GOAL AWAY"] += 0.5

    # =====================================================
    # SORT TOP 5
    # =====================================================

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top5 = ranked[:5]

    # Edge case: scores dict is empty or all values are zero — fall back to NO BET
    if not top5:
        print()
        print("=============== BET DECISION ===============")
        print()
        print("MINUTE:", minute)
        print()
        print("BET: NO BET")
        print("CONFIDENCE: LOW")
        print()
        print("============================================")
        return

    main_bet = top5[0][0]

    # =====================================================
    # BLOCK BET
    # =====================================================

    if LAST_BET not in (None, "", "NO BET"):
        if minute - LAST_MINUTE <= 3:
            print()
            print("=============== BET DECISION ===============")
            print()
            print("MINUTE:", minute)
            print()
            print("BET:", LAST_BET)
            print("CONFIDENCE: LOCKED")
            print("VALID:", LAST_MINUTE, "-", int(LAST_MINUTE + 5))
            print()
            print("ALTERNATIVE:")
            if len(top5) > 1:
                print("2)", top5[1][0])
            else:
                print("2) NO BET")
            if len(top5) > 2:
                print("3)", top5[2][0])
            else:
                print("3) NO BET")
            if len(top5) > 3:
                print("4)", top5[3][0])
            else:
                print("4) NO BET")
            if len(top5) > 4:
                print("5)", top5[4][0])
            else:
                print("5) NO BET")
            print()
            print("MODEL:")
            print("P_GOAL:", round(p_goal, 2))
            print("STRONGER SIDE:", stronger_side)
            print("MC:", round(mc_h, 2), "/", round(mc_x, 2), "/", round(mc_a, 2))
            print("HISTORY:", round(hist_home, 2), "/", round(hist_draw, 2), "/", round(hist_away, 2))
            print()
            print("============================================")
            return

    # =====================================================
    # CONFIDENCE
    # =====================================================

    top_score = top5[0][1]
    second_score = top5[1][1] if len(top5) > 1 else 0.0
    gap = top_score - second_score

    confidence = "LOW"
    if top_score >= 7.5 and gap >= 1.0:
        confidence = "HIGH"
    elif top_score >= 5.5 and gap >= 0.5:
        confidence = "MEDIUM"

    # Context-aware confidence for NEXT GOAL bets: require stronger SMART signal
    if main_bet in ("NEXT GOAL HOME", "NEXT GOAL AWAY"):
        if ng_smart_conf < 0.50:
            confidence = "LOW"
        elif ng_smart_conf < 0.65 and confidence == "HIGH":
            confidence = "MEDIUM"

    if main_bet == "NO BET":
        confidence = "LOW"

    # =====================================================
    # FINAL MODEL OVERRIDE (ABSOLUTE CONTROL)
    # =====================================================

    override_reason = ""

    if mc_a >= 0.80 and mc_a > mc_h and mc_a > mc_x:
        main_bet = "AWAY"
        confidence = "HIGH"
        stronger_side = "AWAY"
        override_reason = "MODEL DOMINANT OVERRIDE"
    elif r.get("mc_h", 0.0) >= 0.80 and r.get("mc_h", 0.0) > r.get("mc_a", 0.0) and r.get("mc_h", 0.0) > r.get(
        "mc_x", 0.0):
        main_bet = "HOME"
        confidence = "HIGH"
        stronger_side = "HOME"
        override_reason = "MODEL DOMINANT OVERRIDE"

    elif r.get("edge_away", 0.0) >= 0.12 and r.get("mc_a", 0.0) >= 0.60 and r.get("p_goal", 0.0) >= 0.55:
        main_bet = "AWAY"
        confidence = "HIGH" if r.get("mc_a", 0.0) >= 0.70 else "MEDIUM"
        stronger_side = "AWAY"
        override_reason = "STRONG VALUE OVERRIDE"

    elif r.get("edge_home", 0.0) >= 0.12 and r.get("mc_h", 0.0) >= 0.60 and r.get("p_goal", 0.0) >= 0.55:
        main_bet = "HOME"
        confidence = "HIGH" if r.get("mc_h", 0.0) >= 0.70 else "MEDIUM"
        stronger_side = "HOME"
        override_reason = "STRONG VALUE OVERRIDE"

    # =====================================================
    # NEXT GOAL SAFETY GUARDS (FINAL PROTECTION)
    # Block next-goal bets when edge is insufficient
    # =====================================================

    p_no_goal = 1.0 - p_goal

    # GUARD 1: NO_GOAL_GUARD - high no-goal probability blocks next-goal bets
    if p_no_goal >= 0.33 and main_bet in ("NEXT GOAL HOME", "NEXT GOAL AWAY"):
        main_bet = "NO BET"
        confidence = "MEDIUM"

    # GUARD 2: SMART_CONF_GUARD - block next-goal bets when SMART confidence is insufficient (regardless of p_goal)
    elif ng_smart_conf < 0.55 and main_bet in ("NEXT GOAL HOME", "NEXT GOAL AWAY"):
        main_bet = "NO BET"
        confidence = "LOW" if ng_smart_conf < 0.48 else "MEDIUM"

    # GUARD 3: EDGE_GUARD - borderline confidence with no clear dominance blocks next-goal bets
    elif (
        0.48 <= ng_smart_conf <= 0.55
        and 0.30 <= p_goal < 0.45
        and abs(p_home_next - p_away_next) < 0.15
        and main_bet in ("NEXT GOAL HOME", "NEXT GOAL AWAY")
    ):
        main_bet = "NO BET"
        confidence = "MEDIUM"

    # =====================================================
    # SAVE LOCK
    # =====================================================

    if main_bet != "NO BET":
        LAST_BET = main_bet
        LAST_MINUTE = minute
    else:
        LAST_BET = None
        LAST_MINUTE = 0

    # =====================================================
    # PRINT
    # =====================================================

    print()
    print("=============== BET DECISION ===============")
    print()
    print("MINUTE:", minute)
    print()
    print("BET:", main_bet)
    print("CONFIDENCE:", confidence)

    if main_bet != "NO BET":
        print("VALID:", minute, "-", int(minute + 5))

    print()
    print("ALTERNATIVE:")

    if len(top5) > 1:
        print("2)", top5[1][0])
    else:
        print("2) NO BET")

    if len(top5) > 2:
        print("3)", top5[2][0])
    else:
        print("3) NO BET")

    if len(top5) > 3:
        print("4)", top5[3][0])
    else:
        print("4) NO BET")

    if len(top5) > 4:
        print("5)", top5[4][0])
    else:
        print("5) NO BET")

    print()
    print("MODEL:")
    print("P_GOAL:", round(p_goal, 2))
    print("STRONGER SIDE:", stronger_side)
    print("MC:", round(mc_h, 2), "/", round(mc_x, 2), "/", round(mc_a, 2))
    print("HISTORY:", round(hist_home, 2), "/", round(hist_draw, 2), "/", round(hist_away, 2))
    if ng_smart_pred:
        print(f"NEXT GOAL SMART: {ng_smart_pred} (conf: {round(ng_smart_conf * 100, 1)} %)")

    if override_reason:
        print("OVERRIDE:", override_reason)

    if fake_pressure:
        print("FILTER:", fake_reason)

    print()
    print("============================================")

def main():
    print(f"\n{CYAN}{BOLD}================ CFOS-XG PRO 75 TITAN [POLNA VERZIJA] ================={RESET}\n")
    print("CSV FORMAT PRO 75:")
    print("0 home")
    print("1 away")
    print("2 odds_home")
    print("3 odds_draw")
    print("4 odds_away")
    print("5 minute")
    print("6 score_home")
    print("7 score_away")
    print("8 xg_home")
    print("9 xg_away")
    print("10 shots_home")
    print("11 shots_away")
    print("12 sot_home")
    print("13 sot_away")
    print("14 attacks_home")
    print("15 attacks_away")
    print("16 dangerous_attacks_home")
    print("17 dangerous_attacks_away")
    print("18 big_chances_home")
    print("19 big_chances_away")
    print("20 yellow_home")
    print("21 yellow_away")
    print("22 red_home")
    print("23 red_away")
    print("24 possession_home")
    print("25 possession_away")
    print("26 blocked_shots_home")
    print("27 blocked_shots_away")
    print("28 big_chances_missed_home")
    print("29 big_chances_missed_away")
    print("30 corners_home")
    print("31 corners_away")
    print("32 gk_saves_home")
    print("33 gk_saves_away")
    print("34 passes_home")
    print("35 passes_away")
    print("36 accurate_passes_home")
    print("37 accurate_passes_away")
    print("38 tackles_home")
    print("39 tackles_away")
    print("40 interceptions_home")
    print("41 interceptions_away")
    print("42 clearances_home")
    print("43 clearances_away")
    print("44 duels_won_home")
    print("45 duels_won_away")
    print("46 offsides_home")
    print("47 offsides_away")
    print("48 throw_ins_home")
    print("49 throw_ins_away")
    print("50 fouls_home")
    print("51 fouls_away")
    print("52 prematch_strength_home")
    print("53 prematch_strength_away")
    print("54 prev_odds_home")
    print("55 prev_odds_draw")
    print("56 prev_odds_away")
    print("57 elo_home")
    print("58 elo_away")
    print("59 keypasses_home")
    print("60 keypasses_away")
    print("61 crosses_home")
    print("62 crosses_away")
    print("63 tackles_home_extra")
    print("64 tackles_away_extra")
    print("65 interceptions_home_extra")
    print("66 interceptions_away_extra")
    print("67 clearances_home_extra")
    print("68 clearances_away_extra")
    print("69 duels_home_extra")
    print("70 duels_away_extra")
    print("71 aerials_home")
    print("72 aerials_away")
    print("73 dribbles_home")
    print("74 dribbles_away")
    print("75 throw_ins_home_extra")
    print("76 throw_ins_away_extra")
    print("77 final_third_entries_home")
    print("78 final_third_entries_away")
    print("79 long_balls_home")
    print("80 long_balls_away")
    print("81 gk_saves_home_extra")
    print("82 gk_saves_away_extra")
    print("83 big_chances_created_home")
    print("84 big_chances_created_away")
    print("85 action_left")
    print("86 action_middle")
    print("87 action_right")
    print("88 pass_accuracy_home_extra")
    print("89 pass_accuracy_away_extra")
    print("")
    print("Če daš manj podatkov, manjkajoči bodo avtomatsko 0.")
    print("Če daš več FotMob podatkov, jih bo PRO 75 uporabil.")
    print("")

    line = safe_input("Prilepi CSV:\n").strip()
    data = parse_csv_line(line)

    try:
        rezultat = izracunaj_model(data)
    except Exception as e:
        print(f"\nCFOS je ustavil izračun zaradi napake v CSV vrstici ali validatorju: {e}")
        return

    if rezultat is None:
        print("\nCFOS je ustavil izračun zaradi napake v CSV vrstici ali validatorju.")
        return

    print("")
    print("--------------- EXTRA STATS ----------------")

    print_stat("PASSES", rezultat.get("passes_h"), rezultat.get("passes_a"))
    print_stat("DUELS", rezultat.get("duels_h"), rezultat.get("duels_a"))
    print_stat("FOULS", rezultat.get("fouls_h"), rezultat.get("fouls_a"))
    print_stat("OFFSIDES", rezultat.get("offsides_h"), rezultat.get("offsides_a"))

    print_stat("KEY PASSES", rezultat.get("keypasses_h"), rezultat.get("keypasses_a"))
    print_stat("CROSSES", rezultat.get("crosses_h"), rezultat.get("crosses_a"))
    print_stat("LONG BALLS", rezultat.get("long_balls_h"), rezultat.get("long_balls_a"))

    print_stat("TACKLES", rezultat.get("tackles_h"), rezultat.get("tackles_a"))
    print_stat("INTERCEPT", rezultat.get("inter_h"), rezultat.get("inter_a"))
    print_stat("CLEARANCES", rezultat.get("clear_h"), rezultat.get("clear_a"))

    print_stat("AERIALS", rezultat.get("aerials_h"), rezultat.get("aerials_a"))
    print_stat("DRIBBLES", rezultat.get("dribbles_h"), rezultat.get("dribbles_a"))
    print_stat("FINAL THIRD", rezultat.get("final_third_h"), rezultat.get("final_third_a"))

    print_dominance(rezultat)
    print_match_direction(rezultat)

    izpis_rezultata(rezultat)

    bet_decision(rezultat)


    ans = safe_input("\nKončni rezultat (enter za skip) format H-A, npr. 2-1 : ").strip()

    if ans:
        try:

            fh, fa = ans.replace(" ", "").split("-")
            final_h = int(fh)
            final_a = int(fa)
            # ==========================================
            # LOG ZA ACCURACY ANALIZO
            # ==========================================

            prediction = str(rezultat["napoved_izida"]).strip().upper()

            if prediction in ["HOME", "1", "DOMAČI", "DOMACI"]:
                prediction = "DOMAČI"
                prediction_norm = "HOME"
            elif prediction in ["AWAY", "2", "GOST"]:
                prediction = "GOST"
                prediction_norm = "AWAY"
            elif prediction in ["DRAW", "X", "REMI"]:
                prediction = "REMI"
                prediction_norm = "DRAW"
            else:
                prediction_norm = normalize_outcome_label(prediction)

            if final_h > final_a:
                final_result = "DOMAČI"
                final_result_norm = "HOME"
            elif final_a > final_h:
                final_result = "GOST"
                final_result_norm = "AWAY"
            else:
                final_result = "REMI"
                final_result_norm = "DRAW"

            correct = 1 if prediction == final_result else 0

            try:
                with open("cfos75_accuracy_log.csv", "a", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)

                    if f.tell() == 0:
                        writer.writerow([
                            "home",
                            "away",
                            "minute",
                            "prediction",
                            "final_result",
                            "correct"
                        ])

                    writer.writerow([
                        rezultat["home"],
                        rezultat["away"],
                        rezultat["minute"],
                        prediction,
                        final_result,
                        correct
                    ])
            except Exception as e:
                print("Napaka pri pisanju accuracy log:", e)

            save_match_result(
                home=rezultat["home"],
                away=rezultat["away"],
                minute=rezultat["minute"],
                prediction_1x2=prediction_norm,
                prediction_score=rezultat["top_scores"][0][0] if rezultat.get("top_scores") else "",
                result_1x2=final_result_norm,
                result_score=f"{final_h}-{final_a}",
                history_pred=rezultat.get("history_pred", "")
            )

            finalize_snapshots(final_h, final_a, rezultat["home"], rezultat["away"])
            clear_match_memory(rezultat["home"], rezultat["away"])
            cfos_accuracy()
            history_accuracy()

        except Exception as e:
            print("Napaka pri branju končnega rezultata:", e)

    else:
        snap = safe_input("Shrani snapshot? (y/n): ").strip().lower()
        if snap == "y":
            save_snapshot(
                home=rezultat["home"],
                away=rezultat["away"],
                minute=rezultat["minute"],
                xg_total=rezultat["xg_total"],
                sot_total=rezultat["sot_total"],
                shots_total=rezultat["shots_total"],
                score_diff=rezultat["score_diff"],
                odds_home=rezultat["odds_home"],
                odds_draw=rezultat["odds_draw"],
                odds_away=rezultat["odds_away"],
                lam_total_raw=rezultat["lam_total_raw"],
                p_goal_raw=rezultat["p_goal_raw"],
                mc_h_raw=rezultat["mc_h_raw"],
                mc_x_raw=rezultat["mc_x_raw"],
                mc_a_raw=rezultat["mc_a_raw"],
                score_home=rezultat["score_home"],
                score_away=rezultat["score_away"],
                game_type=rezultat["game_type"],
                danger_total=rezultat["danger_total"]
            )


if __name__ == "__main__":
    main()

# ============================================================
# KONEC DELA 8 / 8
# ============================================================
