"""Country flag utilities for soccer teams."""


def get_country_flag(country_name: str) -> str:
    """
    Convert a country name to its flag emoji.

    Supports all 48 World Cup 2026 teams plus additional countries.
    Handles UK subdivisions (England, Scotland, Wales) with proper flag emojis.
    Supports alternative spellings (e.g., Czechia/Czech Republic, Turkiye/Turkey).

    Args:
        country_name: Name of the country

    Returns:
        Flag emoji string, or empty string if country not found
    """
    # Map common country names to their ISO 3166-1 alpha-2 codes
    country_codes = {
        # UEFA
        "Germany": "DE",
        "Spain": "ES",
        "France": "FR",
        "Italy": "IT",
        "England": "GB-ENG",
        "Portugal": "PT",
        "Netherlands": "NL",
        "Belgium": "BE",
        "Croatia": "HR",
        "Denmark": "DK",
        "Switzerland": "CH",
        "Austria": "AT",
        "Poland": "PL",
        "Ukraine": "UA",
        "Sweden": "SE",
        "Norway": "NO",
        "Czech Republic": "CZ",
        "Czechia": "CZ",
        "Serbia": "RS",
        "Turkey": "TR",
        "Turkiye": "TR",
        "Greece": "GR",
        "Scotland": "GB-SCT",
        "Wales": "GB-WLS",
        "Ireland": "IE",
        "Northern Ireland": "GB-NIR",
        "Bosnia and Herzegovina": "BA",
        "Albania": "AL",
        "North Macedonia": "MK",
        "Slovenia": "SI",
        "Slovakia": "SK",
        "Romania": "RO",
        "Bulgaria": "BG",
        "Hungary": "HU",
        "Finland": "FI",
        "Iceland": "IS",
        "Israel": "IL",
        # CONMEBOL
        "Brazil": "BR",
        "Argentina": "AR",
        "Uruguay": "UY",
        "Colombia": "CO",
        "Chile": "CL",
        "Peru": "PE",
        "Ecuador": "EC",
        "Paraguay": "PY",
        "Venezuela": "VE",
        "Bolivia": "BO",
        # CONCACAF
        "USA": "US",
        "United States": "US",
        "Mexico": "MX",
        "Canada": "CA",
        "Costa Rica": "CR",
        "Jamaica": "JM",
        "Panama": "PA",
        "Honduras": "HN",
        "Haiti": "HT",
        "Curaçao": "CW",
        "Curacao": "CW",
        "Trinidad and Tobago": "TT",
        "El Salvador": "SV",
        "Guatemala": "GT",
        "Dominican Republic": "DO",
        "Suriname": "SR",
        # AFC
        "Japan": "JP",
        "South Korea": "KR",
        "Korea Republic": "KR",
        "Australia": "AU",
        "Iran": "IR",
        "Saudi Arabia": "SA",
        "Qatar": "QA",
        "UAE": "AE",
        "Iraq": "IQ",
        "China": "CN",
        "Thailand": "TH",
        "Jordan": "JO",
        "Uzbekistan": "UZ",
        # CAF
        "Nigeria": "NG",
        "Senegal": "SN",
        "Morocco": "MA",
        "Egypt": "EG",
        "Ghana": "GH",
        "Cameroon": "CM",
        "Algeria": "DZ",
        "Tunisia": "TN",
        "South Africa": "ZA",
        "Ivory Coast": "CI",
        "Côte d'Ivoire": "CI",
        "Cape Verde": "CV",
        "DR Congo": "CD",
        # OFC
        "New Zealand": "NZ",
    }

    code = country_codes.get(country_name, "")
    if not code:
        return ""

    # UK Subdivision flags to prevent bot from using UK flags for scotland, english and wales
    SUBDIVISION_FLAGS = {
        "GB-ENG": "\U0001f3f4\U000e0067\U000e0062\U000e0065\U000e006e\U000e0067\U000e007f",  # England
        "GB-SCT": "\U0001f3f4\U000e0067\U000e0062\U000e0073\U000e0063\U000e0074\U000e007f",  # Scotland
        "GB-WLS": "\U0001f3f4\U000e0067\U000e0062\U000e0077\U000e006c\U000e0073\U000e007f",  # Wales
    }
    if code in SUBDIVISION_FLAGS:
        return SUBDIVISION_FLAGS[code]
    # Northern Ireland has no official Unicode subdivision flag, plus they arent in the WC anyway.

    # Convert ISO code to flag emoji
    # Each letter becomes a regional indicator symbol (🇦 = U+1F1E6, etc.)
    flag = "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in code.upper())
    return flag


# FIFA World Rankings
FIFA_RANKINGS = {
    "Argentina": 1,
    "Spain": 2,
    "France": 3,
    "England": 4,
    "Portugal": 5,
    "Brazil": 6,
    "Morocco": 7,
    "Netherlands": 8,
    "Germany": 9,
    "Belgium": 10,
    "Croatia": 11,
    "Italy": 12,
    "Mexico": 13,
    "Colombia": 14,
    "USA": 15,
    "United States": 15,
    "Senegal": 16,
    "Uruguay": 17,
    "Japan": 18,
    "Switzerland": 19,
    "Iran": 20,
    "IR Iran": 20,
    "Denmark": 21,
    "South Korea": 22,
    "Korea Republic": 22,
    "Australia": 23,
    "Austria": 24,
    "Nigeria": 25,
    "Turkey": 26,
    "Turkiye": 26,
    "Türkiye": 26,
    "Algeria": 27,
    "Ecuador": 28,
    "Ivory Coast": 29,
    "Côte d'Ivoire": 29,
    "Egypt": 30,
    "Norway": 31,
    "Canada": 32,
    "Ukraine": 33,
    "Panama": 34,
    "Sweden": 35,
    "Poland": 37,
    "Scotland": 38,
    "Wales": 39,
    "Hungary": 40,
    "Serbia": 41,
    "Paraguay": 42,
    "Czech Republic": 43,
    "Czechia": 43,
    "Cameroon": 44,
    "DR Congo": 45,
    "Congo DR": 45,
    "Slovakia": 46,
    "Greece": 47,
    "Venezuela": 48,
    "Qatar": 49,
    "Uzbekistan": 50,
    "Chile": 51,
    "Peru": 52,
    "Costa Rica": 53,
    "Romania": 54,
    "Tunisia": 56,
    "Iraq": 57,
    "Ireland": 58,
    "Slovenia": 59,
    "Saudi Arabia": 60,
    "South Africa": 61,
    "Bosnia and Herzegovina": 63,
    "Jordan": 64,
    "Honduras": 65,
    "Albania": 66,
    "Cape Verde": 67,
    "Cabo Verde": 67,
    "UAE": 68,
    "United Arab Emirates": 68,
    "North Macedonia": 69,
    "Northern Ireland": 70,
    "Jamaica": 71,
    "Ghana": 73,
    "Iceland": 74,
    "Finland": 75,
    "Israel": 76,
    "Bolivia": 77,
    "Curaçao": 82,
    "Curacao": 82,
    "Haiti": 84,
    "New Zealand": 85,
    "Bulgaria": 87,
    "China": 91,
    "China PR": 91,
    "Thailand": 94,
    "Guatemala": 97,
    "El Salvador": 100,
    "Trinidad and Tobago": 102,
    "Suriname": 125,
    "Dominican Republic": 144,
}

def get_country_rank(country_name: str) -> int | None:
    """
    Get the FIFA men's ranking for a country.

    Returns:
        FIFA rank as an int, or None if country not found.
    """
    return FIFA_RANKINGS.get(country_name)

