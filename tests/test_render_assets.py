from PIL import Image

from subtitle_editor import resolve_font_path
from title_card import DEFAULT_TEMPLATE_PATH, render_title_card


def test_bundled_fonts_resolve():
    assert resolve_font_path().endswith("BebasNeue-Regular.ttf")


def test_title_card_renders_with_bundled_assets(tmp_path):
    output = tmp_path / "title-card.png"
    result = render_title_card(
        "A recruiter-friendly title that wraps cleanly",
        output,
        template_path=DEFAULT_TEMPLATE_PATH,
    )

    assert result == output.resolve()
    assert output.exists()
    with Image.open(output) as image:
        assert image.size == (860, 320)
