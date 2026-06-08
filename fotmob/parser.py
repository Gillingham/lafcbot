"""HTML parser for extracting __NEXT_DATA__ from FotMob pages."""

import json
import re
from typing import Optional, List, Dict


def extract_next_data(html: str) -> Optional[dict]:
    """
    Extract the __NEXT_DATA__ JSON from a FotMob HTML page.

    FotMob uses Next.js server-side rendering, which embeds data in a
    <script id="__NEXT_DATA__"> tag. This function extracts and parses
    that JSON data.

    Args:
        html: The raw HTML content of a FotMob page

    Returns:
        The parsed pageProps dictionary, or None if extraction failed
    """
    marker = '__NEXT_DATA__'

    marker_idx = html.find(marker)
    if marker_idx == -1:
        return None

    start_idx = html.find('>', marker_idx)
    if start_idx == -1:
        return None
    start_idx += 1

    end_idx = html.find('</script>', start_idx)
    if end_idx == -1:
        return None

    json_str = html[start_idx:end_idx].strip()

    try:
        data = json.loads(json_str)
        page_props = data.get('props', {}).get('pageProps', {})
        return page_props
    except (json.JSONDecodeError, KeyError):
        return None


def extract_page_props(html: str) -> Optional[dict]:
    """
    Alias for extract_next_data for better semantic meaning.
    """
    return extract_next_data(html)


def extract_broadcast_channels(html: str) -> List[Dict[str, str]]:
    """
    Extract broadcast/TV channel information from FotMob HTML.

    This data is embedded in the HTML for SEO purposes and contains
    TV provider information by country.

    Args:
        html: The raw HTML content of a FotMob match page

    Returns:
        List of dictionaries with channelName and countryName, or empty list if not found
    """
    if 'broadcastChannels' not in html:
        return []

    try:
        # Extract the broadcastChannels array
        pattern = r'"broadcastChannels":\[(.*?)\]'
        matches = re.findall(pattern, html)

        if not matches:
            return []

        # Parse the JSON
        channels_json = '[' + matches[0] + ']'
        channels = json.loads(channels_json)

        return channels
    except (json.JSONDecodeError, IndexError):
        return []
