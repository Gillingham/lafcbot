"""Constants for FotMob API access."""

BASE_URL = "https://www.fotmob.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

LEAGUE_IDS = {
    "mls": 130,
    "nwsl": 9134,  # To be verified
    "world_cup": 77,
    "premier_league": 47,
    "champions_league": 42,
}

# Aliases for league names - maps alternative names to canonical keys
LEAGUE_ALIASES = {
    # MLS aliases
    "major league soccer": "mls",
    "major_league_soccer": "mls",
    # NWSL aliases
    "national womens soccer league": "nwsl",
    "womens": "nwsl",
    # World Cup aliases
    "world cup": "world_cup",
    "worldcup": "world_cup",
    "wc": "world_cup",
    # Premier League aliases
    "premier league": "premier_league",
    "premier": "premier_league",
    "epl": "premier_league",
    "english premier league": "premier_league",
    # Champions League aliases
    "champions league": "champions_league",
    "champions": "champions_league",
    "ucl": "champions_league",
    "uefa": "champions_league",
}

REQUEST_DELAY = 0.5
MAX_RETRIES = 3
RETRY_DELAY = 1.0
