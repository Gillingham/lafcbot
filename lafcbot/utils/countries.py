"""Country flag, code, and ranking utilities for soccer teams."""

from functools import cache

from lafcbot.clients.fotmob.models import CountryInfo

# UK subdivision flags to prevent bot from using the generic UK flag
SUBDIVISION_FLAGS: dict[str, str] = {
    "GB-ENG": "\U0001f3f4\U000e0067\U000e0062\U000e0065\U000e006e\U000e0067\U000e007f",  # England
    "GB-SCT": "\U0001f3f4\U000e0067\U000e0062\U000e0073\U000e0063\U000e0074\U000e007f",  # Scotland
    "GB-WLS": "\U0001f3f4\U000e0067\U000e0062\U000e0077\U000e006c\U000e0073\U000e007f",  # Wales
}


# World Cup / international country info.
# This must be defined before COUNTRY_INFO_BY_NAME.
COUNTRIES: list[CountryInfo] = [
    # UEFA
    CountryInfo("Germany", "DE", "DEU", "GER", 9),
    CountryInfo("Spain", "ES", "ESP", "ESP", 2),
    CountryInfo("France", "FR", "FRA", "FRA", 3),
    CountryInfo("Italy", "IT", "ITA", "ITA", 12),
    CountryInfo("England", "GB-ENG", "GBR", "ENG", 4),
    CountryInfo("Portugal", "PT", "PRT", "POR", 5),
    CountryInfo("Netherlands", "NL", "NLD", "NED", 8),
    CountryInfo("Belgium", "BE", "BEL", "BEL", 10),
    CountryInfo("Croatia", "HR", "HRV", "CRO", 11),
    CountryInfo("Denmark", "DK", "DNK", "DEN", 21),
    CountryInfo("Switzerland", "CH", "CHE", "SUI", 19),
    CountryInfo("Austria", "AT", "AUT", "AUT", 24),
    CountryInfo("Poland", "PL", "POL", "POL", 37),
    CountryInfo("Ukraine", "UA", "UKR", "UKR", 33),
    CountryInfo("Sweden", "SE", "SWE", "SWE", 35),
    CountryInfo("Norway", "NO", "NOR", "NOR", 31),
    CountryInfo("Czech Republic", "CZ", "CZE", "CZE", 43),
    CountryInfo("Czechia", "CZ", "CZE", "CZE", 43),
    CountryInfo("Serbia", "RS", "SRB", "SRB", 41),
    CountryInfo("Turkey", "TR", "TUR", "TUR", 26),
    CountryInfo("Turkiye", "TR", "TUR", "TUR", 26),
    CountryInfo("Greece", "GR", "GRC", "GRE", 47),
    CountryInfo("Scotland", "GB-SCT", "GBR", "SCO", 38),
    CountryInfo("Wales", "GB-WLS", "GBR", "WAL", 39),
    CountryInfo("Ireland", "IE", "IRL", "IRL", 58),
    CountryInfo("Northern Ireland", "GB-NIR", "GBR", "NIR", 70),
    CountryInfo("Bosnia and Herzegovina", "BA", "BIH", "BIH", 63),
    CountryInfo("Albania", "AL", "ALB", "ALB", 66),
    CountryInfo("North Macedonia", "MK", "MKD", "MKD", 69),
    CountryInfo("Slovenia", "SI", "SVN", "SVN", 59),
    CountryInfo("Slovakia", "SK", "SVK", "SVK", 46),
    CountryInfo("Romania", "RO", "ROU", "ROU", 54),
    CountryInfo("Bulgaria", "BG", "BGR", "BUL", 87),
    CountryInfo("Hungary", "HU", "HUN", "HUN", 40),
    CountryInfo("Finland", "FI", "FIN", "FIN", 75),
    CountryInfo("Iceland", "IS", "ISL", "ISL", 74),
    CountryInfo("Israel", "IL", "ISR", "ISR", 76),
    # CONMEBOL
    CountryInfo("Brazil", "BR", "BRA", "BRA", 6),
    CountryInfo("Argentina", "AR", "ARG", "ARG", 1),
    CountryInfo("Uruguay", "UY", "URY", "URU", 17),
    CountryInfo("Colombia", "CO", "COL", "COL", 14),
    CountryInfo("Chile", "CL", "CHL", "CHI", 51),
    CountryInfo("Peru", "PE", "PER", "PER", 52),
    CountryInfo("Ecuador", "EC", "ECU", "ECU", 28),
    CountryInfo("Paraguay", "PY", "PRY", "PAR", 42),
    CountryInfo("Venezuela", "VE", "VEN", "VEN", 48),
    CountryInfo("Bolivia", "BO", "BOL", "BOL", 77),
    # CONCACAF
    CountryInfo("USA", "US", "USA", "USA", 15),
    CountryInfo("United States", "US", "USA", "USA", 15),
    CountryInfo("Mexico", "MX", "MEX", "MEX", 13),
    CountryInfo("Canada", "CA", "CAN", "CAN", 32),
    CountryInfo("Costa Rica", "CR", "CRI", "CRC", 53),
    CountryInfo("Jamaica", "JM", "JAM", "JAM", 71),
    CountryInfo("Panama", "PA", "PAN", "PAN", 34),
    CountryInfo("Honduras", "HN", "HND", "HON", 65),
    CountryInfo("Haiti", "HT", "HTI", "HAI", 84),
    CountryInfo("Curaçao", "CW", "CUW", "CUW", 82),
    CountryInfo("Curacao", "CW", "CUW", "CUW", 82),
    CountryInfo("Trinidad and Tobago", "TT", "TTO", "TRI", 102),
    CountryInfo("El Salvador", "SV", "SLV", "SLV", 100),
    CountryInfo("Guatemala", "GT", "GTM", "GUA", 97),
    CountryInfo("Dominican Republic", "DO", "DOM", "DOM", 144),
    CountryInfo("Suriname", "SR", "SUR", "SUR", 125),
    # AFC
    CountryInfo("Japan", "JP", "JPN", "JPN", 18),
    CountryInfo("South Korea", "KR", "KOR", "KOR", 22),
    CountryInfo("Korea Republic", "KR", "KOR", "KOR", 22),
    CountryInfo("Australia", "AU", "AUS", "AUS", 23),
    CountryInfo("Iran", "IR", "IRN", "IRN", 20),
    CountryInfo("Saudi Arabia", "SA", "SAU", "KSA", 60),
    CountryInfo("Qatar", "QA", "QAT", "QAT", 49),
    CountryInfo("UAE", "AE", "ARE", "UAE", 68),
    CountryInfo("Iraq", "IQ", "IRQ", "IRQ", 57),
    CountryInfo("China", "CN", "CHN", "CHN", 91),
    CountryInfo("Thailand", "TH", "THA", "THA", 94),
    CountryInfo("Jordan", "JO", "JOR", "JOR", 64),
    CountryInfo("Uzbekistan", "UZ", "UZB", "UZB", 50),
    # CAF
    CountryInfo("Nigeria", "NG", "NGA", "NGA", 25),
    CountryInfo("Senegal", "SN", "SEN", "SEN", 16),
    CountryInfo("Morocco", "MA", "MAR", "MAR", 7),
    CountryInfo("Egypt", "EG", "EGY", "EGY", 30),
    CountryInfo("Ghana", "GH", "GHA", "GHA", 73),
    CountryInfo("Cameroon", "CM", "CMR", "CMR", 44),
    CountryInfo("Algeria", "DZ", "DZA", "ALG", 27),
    CountryInfo("Tunisia", "TN", "TUN", "TUN", 56),
    CountryInfo("South Africa", "ZA", "ZAF", "RSA", 61),
    CountryInfo("Ivory Coast", "CI", "CIV", "CIV", 29),
    CountryInfo("Côte d'Ivoire", "CI", "CIV", "CIV", 29),
    CountryInfo("Cape Verde", "CV", "CPV", "CPV", 67),
    CountryInfo("DR Congo", "CD", "COD", "COD", 45),
    # OFC
    CountryInfo("New Zealand", "NZ", "NZL", "NZL", 85),
]


COUNTRY_INFO_BY_NAME: dict[str, CountryInfo] = {
    country.country_name.casefold(): country for country in COUNTRIES
}


@cache
def get_country_info(country_name: str) -> CountryInfo | None:
    """
    Get CountryInfo by country name.

    Args:
        country_name: Name or alias of the country.

    Returns:
        CountryInfo object, or None if country not found.
    """
    return COUNTRY_INFO_BY_NAME.get(country_name.strip().casefold())


@cache
def get_country_flag(country_name: str) -> str:
    """
    Convert a country name to its flag emoji.

    Uses CountryInfo.iso_alpha_2 as the source of truth.
    Handles UK subdivisions like England, Scotland, and Wales.

    Args:
        country_name: Name or alias of the country.

    Returns:
        Flag emoji string, or empty string if country not found.
    """
    country = get_country_info(country_name)
    if country is None:
        return ""

    code = country.iso_alpha_2
    if not code:
        return ""

    if code in SUBDIVISION_FLAGS:
        return SUBDIVISION_FLAGS[code]

    # Northern Ireland has no official Unicode subdivision flag.
    # Returning empty string avoids accidentally showing the generic UK flag.
    if code == "GB-NIR":
        return ""

    # Only standard two-letter ISO alpha-2 codes can be converted this way.
    if len(code) != 2:
        return ""

    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in code.upper())


@cache
def get_country_rank(country_name: str) -> int | None:
    """
    Get the FIFA men's ranking for a country.

    Uses CountryInfo.fifa_rank as the source of truth.

    Args:
        country_name: Name or alias of the country.

    Returns:
        FIFA rank as an int, or None if country not found or rank unknown.
    """
    country = get_country_info(country_name)
    if country is None:
        return None

    return country.fifa_rank


@cache
def get_fifa_trigram(country_name: str) -> str:
    """
    Get the FIFA-style three-letter country code.

    Args:
        country_name: Name or alias of the country.

    Returns:
        FIFA trigram string, or empty string if country not found.
    """
    country = get_country_info(country_name)
    if country is None:
        return ""

    return country.fifa_trigram


@cache
def get_iso_alpha_2(country_name: str) -> str:
    """
    Get the ISO alpha-2 code or subdivision code used for flags.

    Args:
        country_name: Name or alias of the country.

    Returns:
        ISO alpha-2 string, subdivision code, or empty string if country not found.
    """
    country = get_country_info(country_name)
    if country is None:
        return ""

    return country.iso_alpha_2


@cache
def get_iso_alpha_3(country_name: str) -> str:
    """
    Get the ISO alpha-3 code.

    Args:
        country_name: Name or alias of the country.

    Returns:
        ISO alpha-3 string, or empty string if country not found.
    """
    country = get_country_info(country_name)
    if country is None:
        return ""

    return country.iso_alpha_3
