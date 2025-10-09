from __future__ import annotations

from collections import defaultdict

# Our team name as exposed by /name
TEAM_NAME = "Equipe3MaGueule"

# ----- buying thresholds (avoid magic numbers) -----
BUY_PROVINCE_COINS = 8
BUY_GOLD_COINS = 6
BUY_5_COST_COINS = 5
BUY_4_COST_COINS = 4
BUY_SILVER_COINS = 3

# --- phase thresholds & caps ---
ENDGAME_PROVINCE_THRESHOLD = 2
MIDGAME_PROVINCE_THRESHOLD = 4

# --- turn-limit related knobs ---
MAX_TURN = 155
RUSH_TURN = 145
MIN_GREEN_TURN = 14
PROVINCE_SOFT_CAP_BEFORE_TURN = 20
PROVINCES_ALLOWED_BEFORE_CAP = 2

MAX_LABS = 3
MAX_SMITHIES = 2

# --- lint-friendly thresholds ---
ENGINE_GOLD_THRESHOLD = 2
ENGINE_LAB_THRESHOLD = 2
ENGINE_MF_SUM_THRESHOLD = 2
MIN_COPPER_TRASH = 2
OPENING_TURN_LIMIT = 3
COINS_EQ_3 = 3
COINS_EQ_4 = 4
COINS_EQ_5 = 5

# --- additional thresholds ---
BEHIND_DUCHY_DEFICIT = 6
EARLY_PROVINCE_STOCK = 6
GARDENS_EARLY_STOCK = 8
# When it's still worth buying Hireling early
EARLY_HIRELING_TURN = 10
# Minimum Provinces left to even consider pivoting to Gardens
GARDENS_PIVOT_MIN_PROVINCES = 10

# --- costs & per-action bonuses ---
COSTS: dict[str, int] = {
    "province": 8,
    "duchy": 5,
    "estate": 2,
    "gold": 6,
    "silver": 3,
    "copper": 0,
    # core engine & economy
    "laboratory": 5,
    "market": 5,
    "festival": 5,
    "village": 3,
    "smithy": 4,
    "woodcutter": 3,
    "port": 4,
    "poacher": 4,
    "cellar": 2,
    "farmingvillage": 4,
    # alt-vp / payload helpers
    "gardens": 4,
    # trashers / gainers / attacks
    "chapel": 2,
    "moneylender": 4,
    "remodel": 4,
    "remake": 4,
    "workshop": 3,
    "feast": 4,
    "mine": 5,
    "witch": 5,
    "militia": 4,
    "bandit": 5,
    "bureaucrat": 4,
    # drawers / others
    "councilroom": 5,
    "library": 5,
    "adventurer": 6,
    "magpie": 4,
    "hireling": 6,
    "distantshore": 6,
    "marquis": 6,
}

ACTION_COIN_BONUS: dict[str, int] = {
    "market": 1,
    "festival": 2,
    "woodcutter": 2,
    "moneylender": 3,
    "chancellor": 2,
    "poacher": 1,
    "farmingvillage": 2,
}

ACTION_PLUS_ACTIONS: dict[str, int] = {
    "village": 2,
    "market": 1,
    "laboratory": 1,
    "festival": 2,
    "port": 2,
    "cellar": 1,
    "farmingvillage": 2,
    "distantshore": 1,
    "magpie": 1,
    "poacher": 1,
}

ACTION_BUY_BONUS: dict[str, int] = {
    "market": 1,
    "woodcutter": 1,
    "festival": 1,
    "councilroom": 1,
}

ENGINE_ACTIONS = {"village", "market", "laboratory", "festival"}
TERMINAL_ACTIONS = {"smithy", "woodcutter"}

FIVE_COST_PREFER = ["laboratory", "market", "festival"]
FOUR_COST_PREFER = ["village", "smithy"]

CARD_PRIORITY = defaultdict(
    lambda: 0,
    {
        "province": 100,
        "gold": 80,
        "laboratory": 70,
        "market": 62,
        "festival": 58,
        "smithy": 55,
        "village": 40,
        "duchy": 35,
        "gardens": 32,
        "silver": 30,
        "estate": 10,
        "copper": 5,
    },
)

JUNK = {"estate", "curse"}
