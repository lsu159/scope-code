"""Generate a terminal-style demo GIF from Scope Code output."""

import subprocess, os, sys, time, textwrap
from PIL import Image, ImageDraw, ImageFont

DEMO_SCRIPT = "demo_gif.py"
OUTPUT = "demo.gif"

# Terminal colors
BG = (30, 30, 30)
FG = (200, 200, 200)
GREEN = (100, 220, 100)
YELLOW = (240, 200, 60)
RED = (240, 100, 100)
CYAN = (100, 200, 220)
GRAY = (120, 120, 120)
DIM = (80, 80, 80)

WIDTH = 720
HEIGHT = 520
FONT_SIZE = 15
LINE_HEIGHT = 20
PADDING = 20
FRAME_DELAY = 120  # ms between frames


def run_demo():
    """Run demo_gif.py and capture output."""
    env = os.environ.copy()
    result = subprocess.run(
        [sys.executable, DEMO_SCRIPT],
        capture_output=True, text=True, cwd=os.path.dirname(__file__),
        env=env, timeout=120, encoding="utf-8", errors="replace",
    )
    return result.stdout


def create_frame(lines, highlight_line=None, frame_num=0):
    """Create a single frame with terminal-style text."""
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("Consolas", FONT_SIZE)
    except Exception:
        font = ImageFont.load_default()

    # Title bar
    draw.rectangle([(0, 0), (WIDTH, 30)], fill=(50, 50, 50))
    draw.text((10, 6), "Scope Code Demo", fill=GRAY, font=font)

    y = PADDING + 20
    for i, line in enumerate(lines):
        if y > HEIGHT - 30:
            break

        # Choose color
        if "Scope Code" in line and i < 5:
            color = CYAN
        elif "Demo" in line and ":" in line:
            color = YELLOW
        elif "MUST MODIFY" in line:
            color = GREEN
        elif "MUST NOT" in line:
            color = RED
        elif line.startswith("  X "):
            color = RED
        elif line.startswith("    [modify]"):
            color = GREEN
        elif line.startswith("  Risks:") or line.startswith("  Evidence:"):
            color = CYAN
        elif line.startswith("  $"):  # command
            color = YELLOW
        elif "─" in line:
            color = GRAY
        else:
            color = FG

        # Highlight current "typing" line
        if highlight_line is not None and i == highlight_line:
            color = (255, 255, 255)

        draw.text((PADDING, y), line, fill=color, font=font)
        y += LINE_HEIGHT

    return img


def main():
    print("Running demo...")
    output = run_demo()
    lines = output.strip().split("\n")

    frames = []

    # Frame 1: Initial header
    header_lines = [l for l in lines if l.strip()][:8]
    frames.append(create_frame(header_lines))
    for _ in range(6):
        frames.append(frames[-1].copy())

    # Animate text appearing line by line
    visible = []
    for i, line in enumerate(lines):
        if not line.strip():
            visible.append(line)
            continue
        visible.append(line)
        if len(visible) > 18:
            visible = visible[-18:]
        if i % 2 == 0:  # Every other line to keep GIF short
            frame = create_frame(visible[-18:])
            frames.append(frame)
            frames.append(frame.copy())

    # Hold final frame
    final_frame = create_frame(lines[-18:])
    for _ in range(15):
        frames.append(final_frame.copy())

    # Save
    print(f"Generating {OUTPUT} ({len(frames)} frames)...")
    frames[0].save(
        OUTPUT,
        save_all=True,
        append_images=frames[1:],
        duration=FRAME_DELAY,
        loop=0,
        optimize=True,
    )
    print(f"Done: {OUTPUT} ({os.path.getsize(OUTPUT) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
