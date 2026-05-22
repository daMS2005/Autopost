from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_TEMPLATE_PATH = PROJECT_ROOT / "official_image.png"
DEFAULT_FONT_PATH = Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf")
FALLBACK_FONT_PATHS = (
    PROJECT_ROOT / "resources" / "Arial.TTF",
)
TITLE_BOX = (58, 160, 802, 286)
MAX_TITLE_LINES = 4
MAX_TITLE_FONT_SIZE = 40
MIN_TITLE_FONT_SIZE = 23
TITLE_FILL = (20, 20, 20, 255)


def load_font(font_size):
    for font_path in (DEFAULT_FONT_PATH, *FALLBACK_FONT_PATHS):
        try:
            return ImageFont.truetype(str(font_path), font_size)
        except OSError:
            continue

    raise OSError("No usable font was found for rendering the title card.")


def text_width(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def text_bounds(draw, text, font):
    return draw.textbbox((0, 0), text, font=font)


def text_height(draw, text, font):
    bbox = text_bounds(draw, text, font)
    return bbox[3] - bbox[1]


def wrap_title(draw, title, font, max_width, max_lines):
    words = title.split()
    lines = []

    while words and len(lines) < max_lines:
        line_words = []

        while words:
            candidate = " ".join([*line_words, words[0]])
            if line_words and text_width(draw, candidate, font) > max_width:
                break

            line_words.append(words.pop(0))

        if not line_words and words:
            line_words.append(words.pop(0))

        lines.append(" ".join(line_words))

    if words and lines:
        while lines[-1] and text_width(draw, f"{lines[-1]}...", font) > max_width:
            lines[-1] = " ".join(lines[-1].split()[:-1])
        lines[-1] = f"{lines[-1]}..."

    return lines


def render_title_card(title, output_path, template_path=None):
    """
    Render a Reddit post title into the blank title card template.
    """
    template = Path(template_path or DEFAULT_TEMPLATE_PATH).expanduser().resolve()
    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    image = Image.open(template).convert("RGBA")
    draw = ImageDraw.Draw(image)

    left, top, right, bottom = TITLE_BOX
    max_width = right - left
    max_height = bottom - top
    font_size = MAX_TITLE_FONT_SIZE
    lines = []
    font = load_font(font_size)
    line_gap = 8

    while font_size >= MIN_TITLE_FONT_SIZE:
        font = load_font(font_size)
        line_gap = max(5, int(font_size * 0.18))
        lines = wrap_title(draw, title, font, max_width, MAX_TITLE_LINES)
        total_height = sum(text_height(draw, line, font) for line in lines)
        total_height += line_gap * max(0, len(lines) - 1)

        if total_height <= max_height and all(
            text_width(draw, line, font) <= max_width for line in lines
        ):
            break

        font_size -= 2

    line_heights = [text_height(draw, line, font) for line in lines]
    total_height = sum(line_heights) + line_gap * max(0, len(lines) - 1)
    y = top + max(0, (max_height - total_height) // 2)

    for line, line_height in zip(lines, line_heights):
        bbox = text_bounds(draw, line, font)
        line_width = bbox[2] - bbox[0]
        x = left + max(0, (max_width - line_width) // 2)
        draw.text((x, y - bbox[1]), line, fill=TITLE_FILL, font=font)
        y += line_height + line_gap

    image.save(output)
    return output
