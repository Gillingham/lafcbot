"""Tests for LaHomeWinClient."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from lafcbot.clients.lahomewin_client import LaHomeWinClient


@pytest.fixture
def mock_html():
    """Mock HTML response from lahomewin.com with grid structure."""
    return """
    <html>
        <body>
            <details id="panda-express-dodgers" class="group transition-all">
                <summary class="deal-summary grid">
                    <div>
                        <div><a href="https://pandaexpress.com/app">Panda Express</a></div>
                        <div class="text-sm text-gray-500">$7 Panda Plate</div>
                    </div>
                    <div class="hidden lg:block">Dodgers</div>
                    <div class="hidden md:block">
                        <div class="flex items-center mb-1"><span>✅</span><span>Home game yesterday</span></div>
                    </div>
                    <div class="hidden md:block">
                        Code: <button>DODGERSWIN</button>
                    </div>
                    <div class="hidden md:flex">Active Today</div>
                </summary>
            </details>
            <details id="jack-in-the-box-dodgers" class="group transition-all">
                <summary class="deal-summary grid">
                    <div>
                        <div><a href="https://jackinthebox.com">Jack in the Box</a></div>
                        <div class="text-sm text-gray-500">Free Jumbo Jack</div>
                    </div>
                    <div class="hidden lg:block">Dodgers</div>
                    <div class="hidden md:block">
                        <div class="flex items-center mb-1"><span>✅</span><span>Struck out 7 yesterday</span></div>
                    </div>
                    <div class="hidden md:block">
                        Mobile app - Code: <button>GODODGERS26</button>
                    </div>
                    <div class="hidden md:flex">Not Active</div>
                </summary>
            </details>
            <details id="mcdonald-s-kings" class="group opacity-50 transition-all">
                <summary class="deal-summary grid">
                    <div>
                        <div><a href="https://mcdonalds.com">McDonald's</a></div>
                        <div class="text-sm text-gray-500">Free McFlurry</div>
                    </div>
                    <div class="hidden lg:block">Kings</div>
                    <div class="hidden md:block">
                        <div class="flex items-center mb-1"><span>❌</span><span>Won game yesterday</span></div>
                        <div class="flex items-center mb-1"><span>❌</span><span>Scored 3+ goals</span></div>
                    </div>
                    <div class="hidden md:block">
                        McDonald's App
                    </div>
                    <div class="hidden md:flex">Off-season</div>
                </summary>
            </details>
        </body>
    </html>
    """


@pytest.mark.asyncio
async def test_get_all_deals_success(mock_html):
    """Test successful scraping of deals."""
    # Create mock response context manager
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.text = AsyncMock(return_value=mock_html)
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock()

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_response)

    async with LaHomeWinClient(session=mock_session) as client:
        deals = await client.get_all_deals()

    assert len(deals) == 3

    # Check first deal (Panda Express - active)
    panda_deal = next(d for d in deals if d.deal_id == "panda-express-dodgers")
    assert (
        panda_deal.restaurant_name == "[Panda Express](<https://pandaexpress.com/app>)"
    )
    assert panda_deal.team_name == "Dodgers"
    assert panda_deal.status == "active"
    assert panda_deal.deal_id == "panda-express-dodgers"
    assert "DODGERSWIN" in panda_deal.redemption_instructions
    assert "`DODGERSWIN`" in panda_deal.redemption_instructions
    assert panda_deal.redemption_link is None  # Link is embedded in instructions now
    assert panda_deal.trigger_conditions == "Home game yesterday"

    # Check second deal (Jack in the Box - inactive)
    jitb_deal = next(d for d in deals if d.deal_id == "jack-in-the-box-dodgers")
    assert jitb_deal.restaurant_name == "[Jack in the Box](<https://jackinthebox.com>)"
    assert jitb_deal.team_name == "Dodgers"
    assert jitb_deal.status == "inactive"
    assert jitb_deal.deal_id == "jack-in-the-box-dodgers"
    assert "Mobile app - Code:" in jitb_deal.redemption_instructions
    assert "`GODODGERS26`" in jitb_deal.redemption_instructions
    assert jitb_deal.trigger_conditions == "Struck out 7 yesterday"

    # Check third deal (McDonald's - off-season)
    mcdonalds_deal = next(d for d in deals if d.deal_id == "mcdonald-s-kings")
    assert mcdonalds_deal.restaurant_name == "[McDonald's](<https://mcdonalds.com>)"
    assert mcdonalds_deal.team_name == "Kings"
    assert mcdonalds_deal.status == "off-season"
    assert mcdonalds_deal.trigger_conditions == ""  # No conditions met (❌)


@pytest.mark.asyncio
async def test_get_all_deals_http_error():
    """Test handling of HTTP errors."""
    mock_response = MagicMock()
    mock_response.status = 500
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock()

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_response)

    async with LaHomeWinClient(session=mock_session) as client:
        deals = await client.get_all_deals()

    # Should return empty list on error
    assert deals == []


@pytest.mark.asyncio
async def test_caching():
    """Test that deals are cached for 15 minutes."""
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.text = AsyncMock(
        return_value='<html><body><details id="panda-express-dodgers"><summary>Panda Express</summary><div>Active Today</div><div>Dodgers</div></details></body></html>'
    )
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock()

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_response)

    async with LaHomeWinClient(session=mock_session) as client:
        # First call should hit the network
        await client.get_all_deals()
        assert mock_session.get.call_count == 1

        # Second call should use cache
        await client.get_all_deals()
        assert mock_session.get.call_count == 1  # Still 1


@pytest.mark.asyncio
async def test_get_deal_status(mock_html):
    """Test getting status of a specific deal."""
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.text = AsyncMock(return_value=mock_html)
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock()

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_response)

    async with LaHomeWinClient(session=mock_session) as client:
        status = await client.get_deal_status("panda-express-dodgers")
        assert status == "active"

        status = await client.get_deal_status("jack-in-the-box-dodgers")
        assert status == "inactive"

        status = await client.get_deal_status("nonexistent-deal")
        assert status is None


def test_construct_deal_id():
    """Test deal ID construction."""
    client = LaHomeWinClient()

    assert (
        client._construct_deal_id("Panda Express", "Dodgers") == "panda-express-dodgers"
    )
    assert (
        client._construct_deal_id("Jack in the Box", "Lakers")
        == "jack-in-the-box-lakers"
    )
    assert client._construct_deal_id("McDonald's", "Kings") == "mcdonalds-kings"


def test_extract_team_name():
    """Test team name extraction from text."""
    client = LaHomeWinClient()

    assert client._extract_team_name("Free food when Dodgers win") == "Dodgers"
    assert client._extract_team_name("Lakers deal available") == "Lakers"
    assert client._extract_team_name("LAFC scored first") == "LAFC"
    assert client._extract_team_name("No team mentioned here") is None


def test_slug_to_names():
    """Test slug to name conversion."""
    client = LaHomeWinClient()

    assert client._slug_to_restaurant_name("panda-express") == "Panda Express"
    assert client._slug_to_restaurant_name("jack-in-the-box") == "Jack in the Box"
    assert client._slug_to_restaurant_name("unknown-restaurant") == "Unknown Restaurant"

    assert client._slug_to_team_name("dodgers") == "Dodgers"
    assert client._slug_to_team_name("lakers") == "Lakers"
    assert client._slug_to_team_name("mlb") == "MLB"
