"""Utilities for rendering formatted text into PNG images."""

import functools
import logging
import math
import pathlib
import re
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


@functools.lru_cache
def _load_mono_font(size: int):
    """
    Load a monospaced font.

    Tries a few common font locations/names, then falls back to Pillow's default font.
    """
    candidates = [
        "DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "C:/Windows/Fonts/consola.ttf",
        "C:/Windows/Fonts/consolab.ttf",
    ]

    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue

    logger.debug("Could not load a monospaced font. Using embedded default.")
    return ImageFont.truetype(
        str(pathlib.Path(__file__).parent.resolve()) + "/DejaVuSansMono.ttf", size
    )


def _parse_discord_table_message(
    message: str,
    default_title: str = "Table",
) -> tuple[str, list[str]]:
    """
    Parse a Discord markdown table message into a title and body lines.

    Example input:
        **Grp. A Standings:**
        ```
        #  Team ...
        ...
        ```
    """
    title = default_title
    body_lines: list[str] = []

    for raw_line in message.splitlines():
        stripped = raw_line.strip()

        # Skip Discord code block markers
        if stripped == "```":
            continue

        # First bold line becomes the title
        if stripped.startswith("**") and stripped.endswith("**") and len(stripped) >= 4:
            title = stripped[2:-2].strip()
            continue

        # Avoid leading blank lines
        if stripped == "" and not body_lines:
            continue

        body_lines.append(raw_line.rstrip())

    if not body_lines:
        body_lines = ["No data available."]

    return title, body_lines


def _extract_rank_from_line(line: str) -> int | None:
    """
    Extract the leading rank number from a standings row.

    Examples:
        '1  Mexico        3 3 0 0 +6   9' -> 1
        '#  Team          P W D L GD Pts' -> None
    """
    match = re.match(r"^\s*(\d+)\b", line)
    if not match:
        return None

    return int(match.group(1))


def _get_row_highlight_style(
    rank: int | None,
    highlight_rank_values: set[int] | None = None,
    highlight_top_n: int = 0,
) -> tuple[tuple[int, int, int], tuple[int, int, int]] | None:
    """
    Return a row highlight style as (fill_color, outline_color).

    Args:
        rank: Table row rank, usually 1, 2, 3, etc.
        highlight_rank_values: Explicit rank numbers to highlight green, such as {1, 2}.
        highlight_top_n: Highlight rows ranked 1 through N in gold.
    """
    if rank is None:
        return None

    highlight_rank_values = highlight_rank_values or set()

    # Automatic group qualifiers, usually ranks 1 and 2
    if rank in highlight_rank_values:
        return (
            (28, 66, 48),  # dark green fill
            (88, 176, 122),  # green outline
        )

    # Advancing best 3rd-place teams
    if highlight_top_n > 0 and rank <= highlight_top_n:
        return (
            (92, 72, 24),  # dark gold fill
            (212, 176, 72),  # gold outline
        )

    return None


def render_discord_table_to_png(
    message: str,
    default_title: str = "Player Stats",
    highlight_rank_values: set[int] | None = None,
    highlight_top_n: int = 0,
) -> BytesIO:
    """
    Convert a Discord-formatted markdown table into a PNG image.

    Useful for:
        - !stats output
        - single standings tables
        - Best 3rd placed teams table

    Args:
        message: Discord-formatted table text.
        default_title: Fallback title if the message does not contain a bold title.
        highlight_rank_values: Explicit row ranks to highlight green, such as {1, 2}.
        highlight_top_n: Highlight ranks 1 through N in gold.
    """
    title, lines = _parse_discord_table_message(
        message=message,
        default_title=default_title,
    )

    # Styling
    background_color = (22, 24, 28)
    panel_color = (28, 31, 36)
    border_color = (66, 72, 80)
    title_color = (255, 255, 255)
    text_color = (235, 237, 240)

    padding_x = 32
    padding_y = 28
    title_gap = 18
    line_spacing = 10
    min_width = 820

    row_pad_x = 10
    row_pad_y = 5

    title_font = _load_mono_font(30)
    body_font = _load_mono_font(22)

    # Measure text
    dummy_image = Image.new("RGB", (1, 1))
    draw = ImageDraw.Draw(dummy_image)

    def measure_text(text: str, font):
        sample = text if text else " "
        bbox = draw.textbbox((0, 0), sample, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]

    def measure_lines(text_lines: list[str], font):
        max_width = 0
        max_height = 0

        for line in text_lines:
            width, height = measure_text(line, font)
            max_width = max(max_width, width)
            max_height = max(max_height, height)

        return max_width, max_height

    title_width, title_height = measure_text(title, title_font)
    body_width, line_height = measure_lines(lines, body_font)

    body_height = len(lines) * line_height + max(0, len(lines) - 1) * line_spacing

    image_width = max(min_width, title_width, body_width) + (padding_x * 2)
    image_height = (padding_y * 2) + title_height + title_gap + body_height

    # Draw image
    image = Image.new("RGB", (image_width, image_height), background_color)
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle(
        (2, 2, image_width - 3, image_height - 3),
        radius=20,
        outline=border_color,
        width=2,
        fill=panel_color,
    )

    current_y = padding_y

    draw.text(
        (padding_x, current_y),
        title,
        font=title_font,
        fill=title_color,
    )
    current_y += title_height + title_gap

    for line in lines:
        rank = _extract_rank_from_line(line)
        highlight_style = _get_row_highlight_style(
            rank=rank,
            highlight_rank_values=highlight_rank_values,
            highlight_top_n=highlight_top_n,
        )

        if highlight_style:
            fill_color, outline_color = highlight_style

            draw.rounded_rectangle(
                (
                    padding_x - row_pad_x,
                    current_y - row_pad_y,
                    image_width - padding_x + row_pad_x,
                    current_y + line_height + row_pad_y,
                ),
                radius=10,
                fill=fill_color,
                outline=outline_color,
                width=2,
            )

        draw.text(
            (padding_x, current_y),
            line,
            font=body_font,
            fill=text_color,
        )
        current_y += line_height + line_spacing

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def render_table_grid_to_png(
    table_messages: list[str],
    overall_title: str = "Standings",
    columns: int = 2,
    advancing_third_place_count: int = 8,
) -> BytesIO:
    """
    Render multiple Discord-formatted standings tables into a grid PNG.

    This is intended for World Cup group standings.

    It highlights:
        - ranks 1 and 2 in group tables
        - top N teams in "Best 3rd placed teams" tables

    Args:
        table_messages: List of formatted markdown table strings.
        overall_title: Main title shown at the top of the image.
        columns: Number of grid columns. Use 2 for a mobile-friendly 6x2 World Cup layout.
        advancing_third_place_count: Number of best 3rd-place teams that advance.
    """
    if not table_messages:
        raise ValueError("table_messages cannot be empty")

    if columns <= 0:
        raise ValueError("columns must be greater than 0")

    blocks = [
        _parse_discord_table_message(message, default_title="Standings")
        for message in table_messages
    ]

    # Styling
    background_color = (20, 22, 26)
    panel_color = (29, 32, 37)
    panel_border_color = (72, 78, 88)
    overall_title_color = (255, 255, 255)
    panel_title_color = (255, 255, 255)
    text_color = (236, 238, 242)

    outer_padding = 30
    top_gap = 22
    column_gap = 22
    row_gap = 22

    panel_padding_x = 20
    panel_padding_y = 18
    panel_title_gap = 12
    line_spacing = 8

    row_pad_x = 8
    row_pad_y = 4

    min_panel_width = 470

    overall_title_font = _load_mono_font(34)
    panel_title_font = _load_mono_font(22)
    body_font = _load_mono_font(18)

    # Measure text
    dummy_image = Image.new("RGB", (1, 1))
    draw = ImageDraw.Draw(dummy_image)

    def measure_text(text: str, font):
        sample = text if text else " "
        bbox = draw.textbbox((0, 0), sample, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]

    def measure_lines(text_lines: list[str], font):
        max_width = 0
        max_height = 0

        for line in text_lines:
            width, height = measure_text(line, font)
            max_width = max(max_width, width)
            max_height = max(max_height, height)

        return max_width, max_height

    overall_title_width, overall_title_height = measure_text(
        overall_title,
        overall_title_font,
    )

    panel_title_height = measure_text("Ag", panel_title_font)[1]
    body_line_height = measure_text("Ag", body_font)[1]

    max_panel_title_width = 0
    max_panel_body_width = 0
    max_panel_line_count = 0

    for title, lines in blocks:
        title_width, _ = measure_text(title, panel_title_font)
        body_width, _ = measure_lines(lines, body_font)

        max_panel_title_width = max(max_panel_title_width, title_width)
        max_panel_body_width = max(max_panel_body_width, body_width)
        max_panel_line_count = max(max_panel_line_count, len(lines))

    panel_width = max(
        min_panel_width,
        max(max_panel_title_width, max_panel_body_width) + (panel_padding_x * 2),
    )

    panel_height = (
        (panel_padding_y * 2)
        + panel_title_height
        + panel_title_gap
        + (max_panel_line_count * body_line_height)
        + (max(0, max_panel_line_count - 1) * line_spacing)
    )

    rows = math.ceil(len(blocks) / columns)

    image_width = (
        (outer_padding * 2)
        + (columns * panel_width)
        + (max(0, columns - 1) * column_gap)
    )

    image_height = (
        (outer_padding * 2)
        + overall_title_height
        + top_gap
        + (rows * panel_height)
        + (max(0, rows - 1) * row_gap)
    )

    # Draw image
    image = Image.new("RGB", (image_width, image_height), background_color)
    draw = ImageDraw.Draw(image)

    current_y = outer_padding

    draw.text(
        (outer_padding, current_y),
        overall_title,
        font=overall_title_font,
        fill=overall_title_color,
    )
    current_y += overall_title_height + top_gap

    for index, (title, lines) in enumerate(blocks):
        row = index // columns
        col = index % columns

        x = outer_padding + col * (panel_width + column_gap)
        y = current_y + row * (panel_height + row_gap)

        draw.rounded_rectangle(
            (x, y, x + panel_width, y + panel_height),
            radius=18,
            outline=panel_border_color,
            width=2,
            fill=panel_color,
        )

        text_x = x + panel_padding_x
        text_y = y + panel_padding_y

        draw.text(
            (text_x, text_y),
            title,
            font=panel_title_font,
            fill=panel_title_color,
        )
        text_y += panel_title_height + panel_title_gap

        title_lower = title.lower()

        highlight_rank_values: set[int] | None = None
        highlight_top_n = 0

        if title_lower.startswith("grp."):
            highlight_rank_values = {1, 2}
        elif title_lower.startswith("best 3rd"):
            highlight_top_n = advancing_third_place_count

        for line in lines:
            rank = _extract_rank_from_line(line)
            highlight_style = _get_row_highlight_style(
                rank=rank,
                highlight_rank_values=highlight_rank_values,
                highlight_top_n=highlight_top_n,
            )

            if highlight_style:
                fill_color, outline_color = highlight_style

                draw.rounded_rectangle(
                    (
                        text_x - row_pad_x,
                        text_y - row_pad_y,
                        x + panel_width - panel_padding_x + row_pad_x,
                        text_y + body_line_height + row_pad_y,
                    ),
                    radius=9,
                    fill=fill_color,
                    outline=outline_color,
                    width=2,
                )

            draw.text(
                (text_x, text_y),
                line,
                font=body_font,
                fill=text_color,
            )
            text_y += body_line_height + line_spacing

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer
