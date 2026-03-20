"""Block-character image renderer"""

from PIL import Image


def image_to_blocks(img: Image.Image, columns: int) -> str:
    """Render image using half-block characters with ANSI true-color."""
    ratio = columns / img.width
    height = int(img.height * ratio)
    if height % 2 != 0:
        height += 1
    img = img.resize((columns, height), Image.LANCZOS).convert("RGB")

    px = img.load() 
    width = columns
    lines = []

    for y in range(0, height, 2):
        row_parts = []
        prev_fg = None
        prev_bg = None

        for x in range(width):
            top = px[x, y]
            bottom = px[x, y + 1] if y + 1 < height else (0, 0, 0)

            # Only emit ANSI codes when colors actually change
            fg_changed = top != prev_fg
            bg_changed = bottom != prev_bg

            if fg_changed and bg_changed:
                row_parts.append(
                    f"\x1b[38;2;{top[0]};{top[1]};{top[2]};48;2;{bottom[0]};{bottom[1]};{bottom[2]}m\u2580"
                )
            elif fg_changed:
                row_parts.append(f"\x1b[38;2;{top[0]};{top[1]};{top[2]}m\u2580")
            elif bg_changed:
                row_parts.append(
                    f"\x1b[48;2;{bottom[0]};{bottom[1]};{bottom[2]}m\u2580"
                )
            else:
                row_parts.append("\u2580")

            prev_fg = top
            prev_bg = bottom

        lines.append("".join(row_parts) + "\x1b[0m")

    return "\n".join(lines)
