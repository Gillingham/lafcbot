"""Client for scraping LA home win deals from lahomewin.com."""

import logging
from dataclasses import dataclass
from datetime import datetime

import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class Deal:
    """Represents a single LA sports deal."""

    deal_id: str
    restaurant_name: str
    team_name: str
    description: str
    status: str
    redemption_instructions: str
    trigger_conditions: str  # Why the deal is active (e.g., "Home game yesterday")
    redemption_link: str | None = None


class LaHomeWinClient:
    """Async client for scraping lahomewin.com deals."""

    BASE_URL = "https://lahomewin.com/"
    CACHE_TTL_SECONDS = 900  # 15 minutes

    def __init__(self, session: aiohttp.ClientSession | None = None):
        """Initialize the client.

        Args:
            session: Optional existing aiohttp session. If not provided, a new one will be created.
        """
        self._session = session
        self._owns_session = session is None
        self._cached_deals: list[Deal] | None = None
        self._cache_time: datetime | None = None

    async def __aenter__(self):
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def close(self):
        """Close the HTTP session if we own it."""
        if self._owns_session and self._session:
            await self._session.close()
            self._session = None

    async def get_all_deals(self) -> list[Deal]:
        """Fetch and parse all deals from lahomewin.com.

        Returns:
            List of Deal objects

        Raises:
            aiohttp.ClientError: If the HTTP request fails
            Exception: If parsing fails
        """
        # Check cache
        if self._cached_deals and self._cache_time:
            age = datetime.now() - self._cache_time
            if age.total_seconds() < self.CACHE_TTL_SECONDS:
                logger.debug(f"Returning cached deals (age: {age.total_seconds()}s)")
                return self._cached_deals

        # Fetch fresh data
        if self._session is None:
            self._session = aiohttp.ClientSession()

        try:
            async with self._session.get(self.BASE_URL) as response:
                if response.status != 200:
                    logger.warning(f"lahomewin.com returned status {response.status}")
                    # Return cached data if available
                    if self._cached_deals:
                        logger.info("Returning stale cached deals due to fetch failure")
                        return self._cached_deals
                    return []

                html = await response.text()
                deals = self._parse_html(html)

                # Update cache
                self._cached_deals = deals
                self._cache_time = datetime.now()

                logger.info(f"Successfully scraped {len(deals)} deals")
                return deals

        except aiohttp.ClientError as e:
            logger.error(f"HTTP request to lahomewin.com failed: {e}")
            # Return cached data if available
            if self._cached_deals:
                logger.info("Returning stale cached deals due to error")
                return self._cached_deals
            return []
        except Exception as e:
            logger.error(f"Unexpected error scraping lahomewin.com: {e}", exc_info=True)
            if self._cached_deals:
                return self._cached_deals
            return []

    def _parse_html(self, html: str) -> list[Deal]:
        """Parse HTML and extract all deals.

        Args:
            html: Raw HTML from lahomewin.com

        Returns:
            List of Deal objects
        """
        try:
            soup = BeautifulSoup(html, "lxml")
            # Find all <details> elements with IDs (these are the deals)
            deal_elements = soup.find_all("details", id=True)

            deals = []
            for element in deal_elements:
                try:
                    deal = self._parse_deal(element)
                    if deal:
                        deals.append(deal)
                except Exception as e:
                    logger.warning(f"Failed to parse deal element: {e}")
                    # Log HTML snippet for debugging
                    logger.debug(f"Problematic HTML: {str(element)[:200]}")

            return deals

        except Exception as e:
            logger.error(f"Failed to parse HTML: {e}", exc_info=True)
            return []

    def _parse_deal(self, element) -> Deal | None:
        """Parse a single deal element.

        Args:
            element: BeautifulSoup element for a single deal (<details> tag)

        Returns:
            Deal object or None if parsing fails
        """
        try:
            # Get the deal ID from the element ID attribute
            deal_id = element.get("id")
            if not deal_id:
                logger.debug("No ID found on details element")
                return None

            # Extract CSS classes to identify status
            classes = element.get("class", [])

            # Extract all text content
            text_content = element.get_text(separator=" ", strip=True)

            # Extract status - check for opacity-50 class (off-season) or text content
            status = "inactive"
            if "opacity-50" in classes:
                status = "off-season"
            elif "Active Today" in text_content:
                status = "active"
            elif "Not Active" in text_content:
                status = "inactive"

            # Parse deal_id to extract restaurant and team
            # Format: "restaurant-name-team" or "restaurant-name-team1-team2"
            parts = deal_id.split("-")
            if len(parts) < 2:
                logger.debug(f"Could not parse deal_id: {deal_id}")
                return None

            # Last part is always the team
            team_slug = parts[-1]
            # Everything before last hyphen is restaurant name
            restaurant_slug = "-".join(parts[:-1])

            # Convert slugs to readable names (but we'll try to get the real name with link from HTML)
            restaurant_name_fallback = self._slug_to_restaurant_name(restaurant_slug)
            team_name = self._slug_to_team_name(team_slug)

            # Extract description/conditions from summary
            summary = element.find("summary")
            description = self._extract_description_from_summary(summary, text_content)

            # Extract restaurant name with link from summary
            restaurant_name = self._extract_restaurant_name_with_link(
                summary, restaurant_name_fallback
            )

            # Extract redemption instructions and link
            redemption_instructions, redemption_link = self._extract_redemption_info(
                element, text_content
            )

            # Extract trigger conditions (why the deal is active)
            trigger_conditions = self._extract_trigger_conditions(summary)

            return Deal(
                deal_id=deal_id,
                restaurant_name=restaurant_name,
                team_name=team_name,
                description=description,
                status=status,
                redemption_instructions=redemption_instructions,
                trigger_conditions=trigger_conditions,
                redemption_link=redemption_link,
            )

        except Exception as e:
            logger.warning(f"Error parsing deal element: {e}", exc_info=True)
            return None

    def _extract_team_name(self, text: str) -> str | None:
        """Extract team name from text content.

        Args:
            text: Text content of the deal element

        Returns:
            Team name or None
        """
        # Common LA team names
        teams = [
            "Dodgers",
            "Lakers",
            "Clippers",
            "Kings",
            "Ducks",
            "Angels",
            "Rams",
            "Chargers",
            "LAFC",
            "Galaxy",
            "Sparks",
        ]

        for team in teams:
            if team in text:
                return team

        return None

    def _extract_restaurant_name(self, class_name: str, element) -> str:
        """Extract restaurant name from class or element.

        Args:
            class_name: CSS class name (e.g., "panda", "jack-in-the-box")
            element: BeautifulSoup element

        Returns:
            Cleaned restaurant name
        """
        # Map common class names to full restaurant names
        class_to_name = {
            "panda": "Panda Express",
            "mcdonalds": "McDonald's",
            "jack-in-the-box": "Jack in the Box",
            "habit-burger": "The Habit Burger Grill",
            "ampm": "ampm",
            "el-portal": "El Portal Restaurant",
            "con-azucar-cafe": "Con Azúcar Café",
            "sunright-tea-studio": "Sunright Tea Studio",
            "uber-eats": "Uber Eats",
            "mountain-dew": "Mountain Dew",
            "firehouse-subs": "Firehouse Subs",
            "ono-hawaiian-bbq": "Ono Hawaiian BBQ",
            "doordash": "DoorDash",
            "norms": "Norms",
            "carls-jr": "Carl's Jr",
            "mcdonald-ducks": "McDonald's",
            "mcdonald-kings": "McDonald's",
            "jack-in-the-box-lakers": "Jack in the Box",
        }

        return class_to_name.get(class_name, class_name.replace("-", " ").title())

    def _slug_to_restaurant_name(self, slug: str) -> str:
        """Convert restaurant slug to readable name.

        Args:
            slug: Restaurant slug (e.g., "panda-express", "jack-in-the-box")

        Returns:
            Readable restaurant name
        """
        # Map known slugs to proper names
        slug_map = {
            "panda-express": "Panda Express",
            "mc-donald-s": "McDonald's",
            "the-habit-burger-grill": "The Habit Burger Grill",
            "jack-in-the-box": "Jack in the Box",
            "ampm": "ampm",
            "el-portal-restaurant": "El Portal Restaurant",
            "con-az-car-caf": "Con Azúcar Café",
            "sunright-tea-studio": "Sunright Tea Studio",
            "uber-eats": "Uber Eats",
            "mcdonald-s": "McDonald's",
            "mountain-dew": "Mountain Dew",
            "firehouse-subs": "Firehouse Subs",
            "ono-hawaiian-bbq": "Ono Hawaiian BBQ",
            "doordash": "DoorDash",
            "norms": "Norms",
            "carl-s-jr": "Carl's Jr",
        }

        return slug_map.get(slug, slug.replace("-", " ").title())

    def _slug_to_team_name(self, slug: str) -> str:
        """Convert team slug to readable name.

        Args:
            slug: Team slug (e.g., "dodgers", "lakers", "lafc")

        Returns:
            Readable team name
        """
        slug_map = {
            "dodgers": "Dodgers",
            "lakers": "Lakers",
            "clippers": "Clippers",
            "kings": "Kings",
            "ducks": "Ducks",
            "angels": "Angels",
            "rams": "Rams",
            "chargers": "Chargers",
            "lafc": "LAFC",
            "galaxy": "Galaxy",
            "sparks": "Sparks",
            "mlb": "MLB",
            "fc": "SD FC",  # This handles both "fc" and composite team names
        }

        return slug_map.get(slug, slug.upper())

    def _extract_restaurant_name_with_link(self, summary, fallback_name: str) -> str:
        """Extract restaurant name with link from summary element.

        Args:
            summary: BeautifulSoup summary element
            fallback_name: Fallback name if link not found

        Returns:
            Restaurant name with Discord markdown link if available
        """
        if not summary:
            return fallback_name

        # Look for the link in the summary (usually the restaurant name)
        link = summary.find("a")
        if link:
            link_text = link.get_text(strip=True)
            href = link.get("href", "")
            if href and link_text:
                # Wrap URL in angle brackets to suppress Discord embed preview
                return f"[{link_text}](<{href}>)"

        return fallback_name

    def _extract_description_from_summary(self, summary, text: str) -> str:
        """Extract deal description from summary element.

        Args:
            summary: BeautifulSoup summary element
            text: Full text content

        Returns:
            Deal description
        """
        if summary:
            # Look for the description div within summary
            # Usually in a div with class containing "text-sm" or "text-gray-500"
            desc_div = summary.find("div", class_=lambda c: c and "text-sm" in c)
            if desc_div:
                desc = desc_div.get_text(strip=True)
                if desc and len(desc) > 5:
                    return desc

        # Fallback: extract first meaningful sentence
        sentences = text.split(".")
        for sentence in sentences:
            if (
                "Active Today" not in sentence
                and "Off-season" not in sentence
                and "Not Active" not in sentence
                and len(sentence.strip()) > 10
            ):
                return sentence.strip()

        return text[:200].strip()

    def _extract_description_from_body(self, body, text: str) -> str:
        """Extract deal description/conditions from body element.

        Args:
            body: BeautifulSoup body element
            text: Full text content

        Returns:
            Deal description
        """
        if body:
            # Get first <p> tag which usually contains the deal description
            first_p = body.find("p")
            if first_p:
                desc = first_p.get_text(strip=True)
                # Skip if it's just status text
                if desc not in ["Active Today", "Not Active", "Off-season"]:
                    return desc

        # Fallback: extract first meaningful sentence
        sentences = text.split(".")
        for sentence in sentences:
            if (
                "Active Today" not in sentence
                and "Off-season" not in sentence
                and "Not Active" not in sentence
                and len(sentence.strip()) > 10
            ):
                return sentence.strip()

        return text[:200].strip()

    def _extract_trigger_conditions(self, summary) -> str:
        """Extract trigger conditions from the 3rd column of the summary grid.

        The summary element uses a 5-column grid layout:
        1. Restaurant name + description
        2. Team name
        3. Trigger conditions ← We want this one
        4. Redemption instructions
        5. Status badge

        Args:
            summary: BeautifulSoup summary element

        Returns:
            Trigger conditions text (e.g., "Home game yesterday", "Struck out 7 opponents yesterday")
        """
        if not summary:
            return ""

        # Get all direct child divs from summary
        grid_divs = [
            child
            for child in summary.children
            if hasattr(child, "name") and child.name == "div"
        ]

        # Look for the trigger conditions div - it's hidden on mobile, shown on md+ screens
        # and contains checkmarks (✅ or ❌) indicating which conditions are met
        for div in grid_divs:
            classes = div.get("class", [])
            if "hidden" in classes and "md:block" in classes:
                div_text = div.get_text(strip=True)
                # The trigger div has checkmarks
                if "✅" in div_text or "❌" in div_text:
                    # Extract only the conditions that are met (✅)
                    conditions = []
                    inner_divs = div.find_all("div", class_="flex items-center mb-1")
                    for inner_div in inner_divs:
                        text = inner_div.get_text(strip=True)
                        if text.startswith("✅"):
                            # Remove the checkmark and add to conditions
                            condition = text[1:].strip()
                            if condition:
                                conditions.append(condition)

                    if conditions:
                        return ", ".join(conditions)

                    # No conditions met (all ❌)
                    return ""

        return ""

    def _extract_redemption_info(self, element, text: str) -> tuple[str, str | None]:
        """Extract redemption instructions from the 4th column of the summary grid.

        The summary element uses a 5-column grid layout:
        1. Restaurant name + description
        2. Team name
        3. Trigger conditions
        4. Redemption instructions ← We want this one
        5. Status badge

        Args:
            element: BeautifulSoup element (the <details> tag)
            text: Text content (unused but kept for signature compatibility)

        Returns:
            Tuple of (instructions with Discord markdown, None - link is embedded)
        """
        instructions = "Check lahomewin.com for redemption details"

        # Find the summary element
        summary = element.find("summary")
        if not summary:
            return instructions, None

        # The summary has a grid layout with direct child divs
        # Get all direct child divs (not nested ones)
        grid_divs = [
            child
            for child in summary.children
            if hasattr(child, "name") and child.name == "div"
        ]

        # The 4th div (index 3) contains redemption instructions
        # But on mobile it's a different layout, so we look for the div with class "hidden md:block"
        # that contains redemption-related content
        redemption_div = None
        for div in grid_divs:
            classes = div.get("class", [])
            # Look for the redemption column - it's hidden on mobile, shown on md+ screens
            # and contains redemption info (not trigger conditions)
            if "hidden" in classes and "md:block" in classes:
                div_text = div.get_text(strip=True)
                # Skip the trigger conditions div - it has checkmarks and condition text
                if "✅" not in div_text and "❌" not in div_text and len(div_text) > 10:
                    redemption_div = div
                    break

        if redemption_div:
            # Convert HTML to Discord markdown
            instructions = self._html_to_discord_markdown(redemption_div)
            # Clean up extra whitespace
            instructions = " ".join(instructions.split())

        # Return with None for link since it's embedded in instructions
        return instructions, None

    def _html_to_discord_markdown(self, element) -> str:
        """Convert HTML element to Discord markdown format.

        Converts:
        - <a href="url">text</a> → [text](url)
        - <button>text</button> → `text`
        - Preserves other text
        - Filters out reference links (Source, Official terms, etc.)

        Args:
            element: BeautifulSoup element

        Returns:
            Discord markdown formatted string
        """
        from bs4 import Comment, NavigableString

        # Links to ignore in redemption instructions (just reference/source links)
        IGNORED_LINK_TEXT = {
            "source",
            "official terms",
            "terms",
            "view deal history",
            "details",
        }

        result = []

        # Process all descendants recursively
        def process_element(elem):
            for child in elem.children:
                # Skip HTML comments
                if isinstance(child, Comment):
                    continue

                if isinstance(child, NavigableString):
                    # Plain text - add if not just whitespace
                    text = str(child).strip()
                    if text and text not in ["", "<!--[!-->", "<!--]-->"]:
                        result.append(text)
                elif hasattr(child, "name"):
                    if child.name == "a":
                        # Convert link to Discord markdown
                        link_text = child.get_text(strip=True)
                        href = child.get("href", "")

                        # Skip ignored reference links
                        if link_text.lower() in IGNORED_LINK_TEXT:
                            continue

                        if href and link_text:
                            # Wrap URL in angle brackets to suppress Discord embed preview
                            result.append(f"[{link_text}](<{href}>)")
                        elif link_text:
                            result.append(link_text)
                    elif child.name == "button":
                        # Extract button text (usually promo code)
                        button_text = child.get_text(strip=True)
                        if button_text:
                            result.append(f"`{button_text}`")
                    elif child.name in ["div", "span", "p"]:
                        # Recursively process containers
                        process_element(child)
                    else:
                        # For other elements, just get text
                        text = child.get_text(strip=True)
                        if text:
                            result.append(text)

        process_element(element)

        # Join with spaces and clean up
        text = " ".join(result)
        # Remove multiple spaces
        text = " ".join(text.split())
        # Remove any remaining HTML comment markers
        text = (
            text.replace("<!--[!-->", "")
            .replace("<!--]-->", "")
            .replace("[!]", "")
            .replace("[]", "")
        )
        return text.strip()

    def _construct_deal_id(self, restaurant_name: str, team_name: str) -> str:
        """Construct a consistent deal ID.

        Args:
            restaurant_name: Restaurant name
            team_name: Team name

        Returns:
            Deal ID in format "restaurant-slug-team-slug"
        """
        # Convert restaurant name to slug
        restaurant_slug = (
            restaurant_name.lower().replace(" ", "-").replace("'", "").replace(".", "")
        )

        # Convert team name to slug
        team_slug = team_name.lower().replace(" ", "-")

        return f"{restaurant_slug}-{team_slug}"

    async def get_deal_status(self, deal_id: str) -> str | None:
        """Get the status of a specific deal.

        Args:
            deal_id: The deal ID to check

        Returns:
            Status string ("active", "inactive", "off-season") or None if not found
        """
        deals = await self.get_all_deals()
        for deal in deals:
            if deal.deal_id == deal_id:
                return deal.status
        return None
