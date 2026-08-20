"""Test message splitting for deals command."""

from dataclasses import dataclass

from lafcbot.formatters.deals import DealsFormatter
from lafcbot.utils.config import load_timezone


@dataclass
class MockDeal:
    """Mock Deal for testing."""

    deal_id: str
    team_name: str
    restaurant_name: str
    description: str
    trigger_conditions: str | None
    redemption_instructions: str | None
    status: str
    redemption_link: str | None = None


def test_message_splitting_logic():
    """Test that deals can be split across messages when content is too long."""
    formatter = DealsFormatter(load_timezone())

    # Create many deals with long content to exceed 2000 character limit
    deals = []
    for i in range(20):
        deals.append(
            MockDeal(
                deal_id=f"deal-{i}",
                team_name=f"Team {i}",
                restaurant_name=f"Very Long Restaurant Name Number {i}" * 3,
                description="Get 50% off all menu items when our team wins! This is an amazing deal that you don't want to miss out on!"
                * 2,
                trigger_conditions="Team wins home game" * 3,
                redemption_instructions="Show this code at checkout: TEAMWIN123. Valid for 24 hours after the game ends. Cannot be combined with other offers."
                * 2,
                status="active",
            )
        )

    # Format the deals
    deal_blocks = formatter.format_active_deals_with_redemption(deals)

    # Verify we got blocks back (header + deals)
    assert len(deal_blocks) == 21  # Header + 20 deals

    # Simulate the splitting logic
    MAX_LENGTH = 2000
    header = deal_blocks[0]
    deal_items = deal_blocks[1:]

    chunks = []
    current_chunk = [header]
    current_length = len(header) + 2

    for deal_block in deal_items:
        block_length = len(deal_block) + 2

        if current_length + block_length > MAX_LENGTH and len(current_chunk) > 1:
            chunks.append("\n\n".join(current_chunk))
            current_chunk = []
            current_length = 0

        current_chunk.append(deal_block)
        current_length += block_length

    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    # Verify we needed to split
    assert len(chunks) > 1, "Content should have been split into multiple messages"

    # Verify no chunk exceeds the limit
    for i, chunk in enumerate(chunks):
        assert len(chunk) <= MAX_LENGTH, (
            f"Chunk {i} exceeds Discord's max length: {len(chunk)} > {MAX_LENGTH}"
        )

    # Print the split info for visual verification
    print(f"\n{'=' * 60}")
    print(f"Split {len(deals)} deals into {len(chunks)} messages")
    print(f"{'=' * 60}")
    for i, chunk in enumerate(chunks):
        print(f"\nMessage {i + 1} length: {len(chunk)} characters")
        print(f"First 100 chars: {chunk[:100]}...")


def test_short_message_not_split():
    """Test that short messages aren't unnecessarily split."""
    formatter = DealsFormatter(load_timezone())

    # Create just a few deals
    deals = [
        MockDeal(
            deal_id="deal-1",
            team_name="LAFC",
            restaurant_name="Test Restaurant",
            description="50% off",
            trigger_conditions="Team wins",
            redemption_instructions="Show code: TEST",
            status="active",
        ),
        MockDeal(
            deal_id="deal-2",
            team_name="Lakers",
            restaurant_name="Another Restaurant",
            description="Free fries",
            trigger_conditions="Team scores 100+ points",
            redemption_instructions="Show code: FRIES",
            status="active",
        ),
    ]

    deal_blocks = formatter.format_active_deals_with_redemption(deals)
    full_message = "\n\n".join(deal_blocks)

    # Verify it's under the limit
    assert len(full_message) < 2000

    # Verify we got the expected blocks
    assert len(deal_blocks) == 3  # Header + 2 deals
