"""SIXEL image encoder"""

import re
import sys
import time

import numpy as np
from PIL import Image


def _query_terminal(query: str, timeout: float = 0.5) -> str:
    if not sys.stdout.isatty():
        return ""

    if sys.platform == "win32":
        import ctypes
        import msvcrt

        kernel32 = ctypes.windll.kernel32
        h_stdin = kernel32.GetStdHandle(-10)
        old_mode = ctypes.c_ulong()
        kernel32.GetConsoleMode(h_stdin, ctypes.byref(old_mode))
        try:
            kernel32.SetConsoleMode(h_stdin, old_mode.value | 0x0200)
            sys.stdout.write(query)
            sys.stdout.flush()
            response = ""
            start = time.time()
            while time.time() - start < timeout:
                if msvcrt.kbhit():
                    char = msvcrt.getch().decode("latin-1", errors="ignore")
                    response += char
                    if char == "\\" or len(response) > 100:
                        break
                time.sleep(0.01)
            return response
        except Exception:
            return ""
        finally:
            kernel32.SetConsoleMode(h_stdin, old_mode)
    else:
        import select
        import termios
        import tty

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            sys.stdout.write(query)
            sys.stdout.flush()
            response = ""
            start = time.time()
            while time.time() - start < timeout:
                if select.select([fd], [], [], 0.01)[0]:
                    char = sys.stdin.read(1)
                    response += char
                    if char == "\\" or len(response) > 100:
                        break
            return response
        except Exception:
            return ""
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def supports_sixel() -> bool:
    """Check if the terminal supports SIXEL via DA1"""
    response = _query_terminal("\x1b[c")
    match = re.search(r"\x1b\[\?([0-9;]+)c", response)
    if match:
        params = match.group(1).split(";")
        return "4" in params
    return False


def get_cell_size() -> tuple[int, int]:
    """Query terminal for cell pixel dimensions"""
    response = _query_terminal("\x1b[16t")
    match = re.search(r"\x1b\[6;(\d+);(\d+)t", response)
    if match:
        return (int(match.group(2)), int(match.group(1)))
    return (8, 16)


def get_background_color() -> tuple[int, int, int]:
    """Query terminal background color"""
    response = _query_terminal("\x1b]11;?\x1b\\")
    match = re.search(
        r"\x1b\]11;rgb:([0-9a-fA-F]+)/([0-9a-fA-F]+)/([0-9a-fA-F]+)", response
    )
    if match:
        r_hex, g_hex, b_hex = match.group(1), match.group(2), match.group(3)
        # Handle 16-bit (4 chars) vs 8-bit (2 chars) values.
        if len(r_hex) == 4:
            return (
                int(r_hex, 16) // 257,
                int(g_hex, 16) // 257,
                int(b_hex, 16) // 257,
            )
        return (int(r_hex, 16), int(g_hex, 16), int(b_hex, 16))
    return (12, 12, 12)


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert hex color string to RGB tuple"""
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def image_to_sixel(
    img: Image.Image,
    columns: int,
    term_columns: int,
    bg_color: tuple[int, int, int] | None = None,
) -> str:
   
    cell_width, _ = get_cell_size()
    if bg_color is None:
        bg_color = get_background_color()

    # Resize image to fit target column width
    img_pixel_width = columns * cell_width
    ratio = img_pixel_width / img.width
    img_pixel_height = int(img.height * ratio)
    img = img.resize((img_pixel_width, img_pixel_height), Image.LANCZOS).convert("RGB")

    # Create canvas at full terminal width with background color
    canvas_width = term_columns * cell_width
    canvas_height = img_pixel_height
    if canvas_height % 6 != 0:
        canvas_height += 6 - (canvas_height % 6)

    canvas = Image.new("RGB", (canvas_width, canvas_height), bg_color)
    x_offset = (canvas_width - img_pixel_width) // 2
    canvas.paste(img, (x_offset, 0))

    # Quantize to 256 colors
    quantized = canvas.quantize(colors=256, method=Image.MEDIANCUT)
    palette = quantized.getpalette()
    width, height = quantized.size
    pixels = np.array(quantized.getdata(), dtype=np.uint8).reshape(height, width)

    # Force exact background color in palette to avoid quantization drift
    bg_pixel_index = int(pixels[0, 0])
    palette[bg_pixel_index * 3] = bg_color[0]
    palette[bg_pixel_index * 3 + 1] = bg_color[1]
    palette[bg_pixel_index * 3 + 2] = bg_color[2]

    parts = ["\x1bPq", f'"1;1;{width};{height}']

    # Define palette — round to nearest SIXEL value (0-100 scale)
    num_colors = len(palette) // 3
    pal_array = np.array(palette[: num_colors * 3], dtype=np.int16).reshape(-1, 3)
    pal_scaled = np.round(pal_array * 100 / 255).astype(np.int16)
    for i in range(num_colors):
        parts.append(f"#{i};2;{pal_scaled[i, 0]};{pal_scaled[i, 1]};{pal_scaled[i, 2]}")

    # Precompute powers for SIXEL bit encoding: [1, 2, 4, 8, 16, 32]
    powers = np.array([1, 2, 4, 8, 16, 32], dtype=np.uint8)

    # Encode pixel data in 6-row bands
    for band_top in range(0, height, 6):
        band = pixels[band_top : band_top + 6, :]  

        if band.shape[0] < 6:
            pad = np.zeros((6 - band.shape[0], width), dtype=np.uint8)
            band = np.vstack([band, pad])

        colors_in_band = np.unique(band)

        first = True
        for color_idx in colors_in_band:
            if not first:
                parts.append("$")
            first = False
            parts.append(f"#{color_idx}")

            mask = band == color_idx
            vals = (mask * powers[:, np.newaxis]).sum(axis=0) + 63
            chars = vals.astype(np.uint8).tobytes().decode("ascii")

            # RLE compression
            i = 0
            n = len(chars)
            while i < n:
                ch = chars[i]
                count = 1
                while i + count < n and chars[i + count] == ch:
                    count += 1
                parts.append(f"!{count}{ch}" if count > 3 else ch * count)
                i += count

        if band_top + 6 < height:
            parts.append("-")

    parts.append("\x1b\\")
    return "".join(parts)
