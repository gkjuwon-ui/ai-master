"""Generate all PNG assets for the Ogenti verification email.
- Static text images (logo, subtitle, etc.)
- Digit images 0-9 for dynamic code composition
All rendered with Press Start 2P font on transparent/dark backgrounds.
"""

import os
import io
import zipfile
import httpx
from PIL import Image, ImageDraw, ImageFont

OUT_DIR = r"C:\Users\gkjuw\Downloads\ogentilanding\email"
FONT_DIR = r"C:\Users\gkjuw\Downloads\ai_master\_fonts"

# Colors
CYAN = (0, 240, 255)
PURPLE = (176, 96, 255)
DIM = (58, 58, 90)
MUTED = (42, 42, 74)
TEXT = (106, 106, 138)
BG = (10, 10, 26)
SURFACE = (15, 15, 42)
GREEN = (0, 255, 136)
RED = (255, 64, 96)
YELLOW = (255, 224, 64)
TRANSPARENT = (0, 0, 0, 0)

# ---- Download Press Start 2P font ----
def download_font():
    os.makedirs(FONT_DIR, exist_ok=True)
    font_path = os.path.join(FONT_DIR, "PressStart2P-Regular.ttf")
    if os.path.exists(font_path):
        print(f"Font already exists: {font_path}")
        return font_path

    print("Downloading Press Start 2P font...")
    # Direct TTF from GitHub google/fonts repo
    url = "https://github.com/google/fonts/raw/main/ofl/pressstart2p/PressStart2P-Regular.ttf"
    r = httpx.get(url, follow_redirects=True, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"Failed to download font: {r.status_code}")
    with open(font_path, "wb") as f:
        f.write(r.content)
    print(f"Font saved: {font_path}")
    return font_path


def make_text_image(text, font, color, bg_color=None, padding=(0, 0, 0, 0), scale=2):
    """Render text to a PNG image.
    padding = (left, top, right, bottom)
    """
    # Measure text
    dummy = Image.new("RGBA", (1, 1))
    draw = ImageDraw.Draw(dummy)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    pl, pt, pr, pb = padding
    w = tw + pl + pr
    h = th + pt + pb

    if bg_color:
        img = Image.new("RGBA", (w, h), bg_color)
    else:
        img = Image.new("RGBA", (w, h), TRANSPARENT)

    draw = ImageDraw.Draw(img)
    # Center text vertically, offset by padding
    x = pl
    y = pt - bbox[1]  # compensate for font baseline offset
    draw.text((x, y), text, fill=color, font=font)

    return img


def generate_all():
    font_path = download_font()
    os.makedirs(OUT_DIR, exist_ok=True)

    # Load fonts at various sizes (doubled for retina)
    f_logo = ImageFont.truetype(font_path, 40)      # Logo: ◆ OGENTI ◆
    f_sub = ImageFont.truetype(font_path, 14)        # Subtitle
    f_verify = ImageFont.truetype(font_path, 22)     # "ENTER THIS CODE"
    f_digit = ImageFont.truetype(font_path, 72)      # Code digits
    f_small = ImageFont.truetype(font_path, 14)      # Timer, footer
    f_tiny = ImageFont.truetype(font_path, 12)       # System, bottom
    f_header = ImageFont.truetype(font_path, 14)     # Header bar text

    # 1. Logo: OGENTI (without diamonds - use text)
    print("Generating logo...")
    img = make_text_image("OGENTI", f_logo, CYAN, padding=(20, 16, 20, 16))
    img.save(os.path.join(OUT_DIR, "logo.png"), "PNG")

    # 2. Diamonds (separate small decorative element)
    img_d = make_text_image("◆          ◆", f_sub, CYAN, padding=(4, 4, 4, 4))
    img_d.save(os.path.join(OUT_DIR, "diamonds.png"), "PNG")

    # 3. Subtitle
    print("Generating subtitle...")
    img = make_text_image("AI-TO-AI COMMUNICATION PROTOCOL", f_tiny, DIM, padding=(8, 6, 8, 6))
    img.save(os.path.join(OUT_DIR, "subtitle.png"), "PNG")

    # 4. "ENTER THIS CODE TO VERIFY"
    print("Generating verify text...")
    img = make_text_image("ENTER THIS CODE TO VERIFY", f_sub, TEXT, padding=(8, 8, 8, 8))
    img.save(os.path.join(OUT_DIR, "verify_text.png"), "PNG")

    # 5. Timer text
    print("Generating timer...")
    img = make_text_image("EXPIRES IN 10 MIN", f_tiny, DIM, padding=(8, 6, 8, 6))
    img.save(os.path.join(OUT_DIR, "expires.png"), "PNG")

    # 6. Footer text
    print("Generating footer...")
    img = make_text_image("PRESS START TO CONTINUE_", f_tiny, MUTED, padding=(8, 6, 8, 6))
    img.save(os.path.join(OUT_DIR, "footer.png"), "PNG")

    # 7. Bottom text
    print("Generating bottom...")
    img = make_text_image("OGENTI.COM", f_tiny, MUTED, padding=(8, 6, 8, 6))
    img.save(os.path.join(OUT_DIR, "bottom.png"), "PNG")

    # 8. Header bar text
    print("Generating header...")
    img = make_text_image("SYSTEM://VERIFY", f_tiny, DIM, padding=(4, 4, 4, 4))
    img.save(os.path.join(OUT_DIR, "header.png"), "PNG")

    # 9. Window dots (red, yellow, green)
    print("Generating window dots...")
    dot_size = 16
    dot_spacing = 6
    dots_w = dot_size * 3 + dot_spacing * 2 + 8
    dots_h = dot_size + 8
    dots_img = Image.new("RGBA", (dots_w, dots_h), TRANSPARENT)
    draw = ImageDraw.Draw(dots_img)
    colors = [RED, YELLOW, GREEN]
    for i, c in enumerate(colors):
        x = 4 + i * (dot_size + dot_spacing)
        draw.rectangle([x, 4, x + dot_size, 4 + dot_size], fill=c)
    dots_img.save(os.path.join(OUT_DIR, "dots.png"), "PNG")

    # 10. Digit images 0-9
    print("Generating digits 0-9...")
    for d in range(10):
        img = make_text_image(str(d), f_digit, CYAN, padding=(16, 12, 16, 12))
        img.save(os.path.join(OUT_DIR, f"d{d}.png"), "PNG")

    print(f"\nAll images generated in {OUT_DIR}")
    # List files
    for f in sorted(os.listdir(OUT_DIR)):
        size = os.path.getsize(os.path.join(OUT_DIR, f))
        print(f"  {f:20s} {size:>6d} bytes")


if __name__ == "__main__":
    generate_all()
