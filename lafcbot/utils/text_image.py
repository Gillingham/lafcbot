"""Utilities for rendering formatted text into PNG images."""

import math

from io import BytesIO

from PIL import Image, ImageDraw, ImageFont


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

    return ImageFont.load_default()


def render_discord_table_to_png(
        message: str,
        default_title: str = "Player Stats",
) -> BytesIO:
    """
    Convert a Discord-formatted markdown table into a PNG image.

    Expected input looks like:
        **World Cup - Top Goals:**
        ```
        #  Player      Team  Goals
        --------------------------
        1  Messi       ARG   3
        ```
    """
    title = default_title
    body_lines: list[str] = []

    for raw_line in message.splitlines():
        stripped = raw_line.strip()

        # Skip code fences
        if stripped == "```":
            continue

        # First bold line becomes the title
        if stripped.startswith("**") and stripped.endswith("**") and len(stripped) >= 4:
            title = stripped[2:-2].strip()
            continue

        body_lines.append(raw_line.rstrip())

    body_text = "\n".join(body_lines).strip() or "No data available."
    lines = body_text.splitlines() or [""]

    # Styling
    background_color = (24, 26, 27)
    border_color = (60, 63, 65)
    title_color = (255, 255, 255)
    text_color = (230, 230, 230)

    padding_x = 28
    padding_y = 24
    title_gap = 16
    line_spacing = 8
    min_width = 700

    title_font = _load_mono_font(26)
    body_font = _load_mono_font(22)

    # Measure text
    dummy_image = Image.new("RGB", (1, 1))
    draw = ImageDraw.Draw(dummy_image)

    def measure_text_block(text_lines: list[str], font):
        max_width = 0
        max_height = 0

        for line in text_lines:
            sample = line if line else " "
            bbox = draw.textbbox((0, 0), sample, font=font)
            width = bbox[2] - bbox[0]
            height = bbox[3] - bbox[1]
            max_width = max(max_width, width)
            max_height = max(max_height, height)

        return max_width, max_height

    title_bbox = draw.textbbox((0, 0), title or " ", font=title_font)
    title_width = title_bbox[2] - title_bbox[0]
    title_height = title_bbox[3] - title_bbox[1]

    body_width, line_height = measure_text_block(lines, body_font)
    body_height = len(lines) * line_height + max(0, len(lines) - 1) * line_spacing

    image_width = max(min_width, title_width, body_width) + (padding_x * 2)
    image_height = (padding_y * 2) + title_height + title_gap + body_height

    # Draw image
    image = Image.new("RGB", (image_width, image_height), background_color)
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle(
        (2, 2, image_width - 3, image_height - 3),
        radius=18,
        outline=border_color,
        width=2,
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

        if stripped == "```":
            continue

        if stripped.startswith("**") and stripped.endswith("**") and len(stripped) >= 4:
            title = stripped[2:-2].strip()
            continue

        if stripped == "" and not body_lines:
            continue

        body_lines.append(raw_line.rstrip())

    if not body_lines:
        body_lines = ["No data available."]

    return title, body_lines


def render_table_grid_to_png(
        table_messages: list[str],
        overall_title: str = "Standings",
        columns: int = 4,
) -> BytesIO:
    """
    Render multiple Discord-formatted table messages into a grid PNG.

    Args:
        table_messages: List of formatted markdown table strings
        overall_title: Title shown at the top of the image
        columns: Number of columns in the grid
    """
    if not table_messages:
        raise ValueError("table_messages cannot be empty")

    blocks = [
        _parse_discord_table_message(message, default_title="Standings")
        for message in table_messages
    ]

    # Styling
    background_color = (24, 26, 27)
    panel_color = (30, 33, 36)
    border_color = (60, 63, 65)
    overall_title_color = (255, 255, 255)
    panel_title_color = (255, 255, 255)
    text_color = (230, 230, 230)

    outer_padding = 28
    top_gap = 20
    column_gap = 20
    row_gap = 20

    panel_padding_x = 18
    panel_padding_y = 16
    panel_title_gap = 10
    line_spacing = 6

    min_panel_width = 300

    overall_title_font = _load_mono_font(28)
    panel_title_font = _load_mono_font(20)
    body_font = _load_mono_font(16)

    dummy_image = Image.new("RGB", (1, 1))
    draw = ImageDraw.Draw(dummy_image)

    def text_size(text: str, font):
        sample = text if text else " "
        bbox = draw.textbbox((0, 0), sample, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]

    def lines_size(lines: list[str], font):
        max_width = 0
        max_height = 0
        for line in lines:
            width, height = text_size(line, font)
            max_width = max(max_width, width)
            max_height = max(max_height, height)
        return max_width, max_height

    overall_title_width, overall_title_height = text_size(
        overall_title, overall_title_font
    )
    panel_title_height = text_size("Ag", panel_title_font)[1]
    body_line_height = text_size("Ag", body_font)[1]

    max_panel_title_width = 0
    max_panel_body_width = 0
    max_panel_body_lines = 0

    for title, lines in blocks:
        title_width, _ = text_size(title, panel_title_font)
        body_width, _ = lines_size(lines, body_font)

        max_panel_title_width = max(max_panel_title_width, title_width)
        max_panel_body_width = max(max_panel_body_width, body_width)
        max_panel_body_lines = max(max_panel_body_lines, len(lines))

    panel_width = max(
        min_panel_width,
        max(max_panel_title_width, max_panel_body_width) + (panel_padding_x * 2),
        )

    panel_height = (
            (panel_padding_y * 2)
            + panel_title_height
            + panel_title_gap
            + (max_panel_body_lines * body_line_height)
            + (max(0, max_panel_body_lines - 1) * line_spacing)
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

    image = Image.new("RGB", (image_width, image_height), background_color)
    draw = ImageDraw.Draw(image)

    # Main title
    current_y = outer_padding
    draw.text(
        (outer_padding, current_y),
        overall_title,
        font=overall_title_font,
        fill=overall_title_color,
    )
    current_y += overall_title_height + top_gap

    # Panels
    for index, (title, lines) in enumerate(blocks):
        row = index // columns
        col = index % columns

        x = outer_padding + col * (panel_width + column_gap)
        y = current_y + row * (panel_height + row_gap)

        draw.rounded_rectangle(
            (x, y, x + panel_width, y + panel_height),
            radius=16,
            outline=border_color,
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

        for line in lines:
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