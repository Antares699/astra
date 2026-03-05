"""Kitty graphics protocol image encoder"""

import base64
from io import BytesIO

from PIL import Image

from astra.sixel import get_cell_size


def image_to_kitty(img: Image.Image, columns: int, term_columns: int) -> str:

    cell_width, _ = get_cell_size()

    # Resize image to fit target column width
    img_pixel_width = columns * cell_width
    if img_pixel_width > 800:
        img_pixel_width = 800
    ratio = img_pixel_width / img.width
    img_pixel_height = int(img.height * ratio)
    img = img.resize((img_pixel_width, img_pixel_height), Image.LANCZOS).convert("RGB")

    # Encode as PNG in memory
    buf = BytesIO()
    img.save(buf, format="PNG")
    png_data = buf.getvalue()

    # Base64 encode the PNG data
    b64_data = base64.b64encode(png_data).decode("ascii")

    # Center the image 
    padding = " " * ((term_columns - columns) // 2)

    parts = [padding]

    # Chunk the base64 data
    chunk_size = 4000
    b64_chunks = [
        b64_data[i : i + chunk_size] for i in range(0, len(b64_data), chunk_size)
    ]

    for i, chunk in enumerate(b64_chunks):
        m = 1 if i < len(b64_chunks) - 1 else 0  # 1 = more chunks, 0 = last chunk
        if i == 0:
            parts.append(f"\x1b_Ga=T,f=100,t=d,m={m};{chunk}\x1b\\")
        else:
            parts.append(f"\x1b_Gm={m};{chunk}\x1b\\")

    parts.append("\n")
    return "".join(parts)
