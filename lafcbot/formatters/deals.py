"""Formatters for LA sports deal notifications."""

from lafcbot.clients.lahomewin_client import Deal
from lafcbot.formatters.base import BaseFormatter


class DealsFormatter(BaseFormatter):
    """Formats LA sports deal notifications."""

    def format_deal_activation(self, deal: Deal) -> str:
        """Format a deal activation notification.

        Args:
            deal: The deal that is active

        Returns:
            Formatted message with deal info and redemption instructions
        """
        # Build the main message
        # Restaurant name may already contain Discord markdown link
        parts = [
            f"{deal.restaurant_name} deal is active!",
            deal.description,
        ]

        # Add trigger conditions with team name prefix
        if deal.trigger_conditions:
            parts.append(f"{deal.team_name}: {deal.trigger_conditions}")

        # Add redemption instructions (link already embedded in Discord markdown)
        if (
            deal.redemption_instructions
            and deal.redemption_instructions
            != "Check lahomewin.com for redemption details"
        ):
            parts.append(f"**How to redeem**: {deal.redemption_instructions}")

        return "\n".join(parts)

    def format_active_deals_with_redemption(self, active_deals: list[Deal]) -> str:
        """Format active deals with full redemption information.

        Args:
            active_deals: List of active deals

        Returns:
            Formatted message with active deals and redemption instructions
        """
        if not active_deals:
            return "No deals are active today"

        parts = [f"**Active Deals Today ({len(active_deals)})**"]

        for deal in active_deals:
            # Restaurant name may already contain Discord markdown link
            parts.append(f"{deal.restaurant_name} - {deal.description}")

            # Add trigger conditions with team name prefix
            if deal.trigger_conditions:
                parts.append(f"{deal.team_name}: {deal.trigger_conditions}")

            # Add redemption instructions (link already embedded in Discord markdown)
            if (
                deal.redemption_instructions
                and deal.redemption_instructions
                != "Check lahomewin.com for redemption details"
            ):
                parts.append(f"*How to redeem*: {deal.redemption_instructions}")

            parts.append("")  # Blank line between deals

        return "\n".join(parts)

    def format_deal_list(self, deals: list[Deal]) -> str:
        """Format a list of deals for the !deals list command.

        Args:
            deals: List of deals to format

        Returns:
            Formatted message listing all deals
        """
        if not deals:
            return "No deals found on lahomewin.com"

        # Group deals by status
        active_deals = [d for d in deals if d.status == "active"]
        inactive_deals = [d for d in deals if d.status == "inactive"]
        offseason_deals = [d for d in deals if d.status == "off-season"]

        parts = ["**LA Sports Deals from lahomewin.com**", ""]

        if active_deals:
            parts.append("**Active Today:**")
            for deal in active_deals:
                parts.append(f"• {deal.restaurant_name} - {deal.team_name}")
            parts.append("")

        if inactive_deals:
            parts.append("**Not Active:**")
            # Limit to first 5 to keep message short
            for deal in inactive_deals[:5]:
                parts.append(f"• {deal.restaurant_name} - {deal.team_name}")
            if len(inactive_deals) > 5:
                parts.append(f"  ... and {len(inactive_deals) - 5} more")
            parts.append("")

        if offseason_deals:
            parts.append("**Off-Season:**")
            for deal in offseason_deals[:5]:
                parts.append(f"• {deal.restaurant_name} - {deal.team_name}")
            if len(offseason_deals) > 5:
                parts.append(f"  ... and {len(offseason_deals) - 5} more")

        return "\n".join(parts)
