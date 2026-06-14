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
