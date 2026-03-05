"""Block-character image renderer"""

from PIL import Image

def image_to_blocks(img: Image.Image, columns: int) -> str:
    
    ratio = columns / img.width
    height = int(img.height * ratio)
    if height % 2 != 0:
        height += 1
    img = img.resize((columns, height), Image.LANCZOS).convert("RGB")

    pixels = list(img.getdata())
    width = columns
    lines = []

    for y in range(0, height, 2):
        row_parts = []
        for x in range(width):
            top = pixels[y * width + x]
            if y + 1 < height:
                bottom = pixels[(y + 1) * width + x]
            else:
                bottom = (0, 0, 0)

            fg = f"\x1b[38;2;{top[0]};{top[1]};{top[2]}m"
            bg = f"\x1b[48;2;{bottom[0]};{bottom[1]};{bottom[2]}m"
            row_parts.append(f"{fg}{bg}\u2580")

        lines.append("".join(row_parts) + "\x1b[0m")

    return "\n".join(lines)
