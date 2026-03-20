# Astra

NASA's Astronomy Picture of the Day, rendered directly in your terminal.

<img width="1363" height="766" alt="APOD 2026-01-31" src="https://github.com/user-attachments/assets/ca981b3f-41a4-4af2-8aa3-2fd302efc13b" />


## Features

- Auto-detected graphics: Kitty protocol, SIXEL, or block-character fallback
- Cross-platform: Windows, Linux, macOS
- Works with Windows Terminal, Ghostty, Kitty, WezTerm, Alacritty, and more
- Terminal greeter — show today's APOD when you open your shell
- Browse by date, view random APODs, read full explanations
- Search all APOD titles from APOD Archive
- Save HD images of APODs
- Works out of the box with DEMO_KEY

## Install

```
pip install astra-apod
```

## Usage

```
astra                              # Today's APOD
astra today                        # Same as above
astra date 2021-08-14              # APOD for a specific date
astra random                       # Random APOD 
astra search <title>               # Search APOD archive by title 
astra info                         # Full explanation of last viewed APOD
astra save                         # Save last viewed APOD
```

## Configuration

```
astra config --show                # Show current configuration
astra config --api-key <key>       # Set NASA API key
astra config --size full           # Full terminal width image
astra config --size default        # 60% terminal width image 
astra config --bg "#0c0c0c"        # Set background color manually
astra config --save-dir <path>     # Set default save directory
astra config --clear-cache         # Clear cached images
astra config --reset               # Reset all settings to defaults
```

## Terminal Greeter

Auto-display today's APOD when you open your terminal:

```
astra config --greeter on --shell cmd          # CMD (Windows)
astra config --greeter on --shell powershell   # PowerShell (Windows)
astra config --greeter on --shell bash         # Bash (Linux/macOS)
astra config --greeter on --shell zsh          # Zsh (Linux/macOS)
astra config --greeter on --shell fish         # Fish (Linux/macOS)
```

Control how often it runs:

```
astra config --greeter-freq daily    # Once per day (default)
astra config --greeter-freq always   # Every terminal open
```

Disable it:

```
astra config --greeter off --shell <shell>
```

## Optimization

Astra v0.3.0 implements four optimization techniques that significantly reduce install size, startup time, memory usage, and network bandwidth.

### 1. Dependency Elimination — Dropped NumPy (~87% smaller install)

NumPy (~65 MB installed) was used only in the SIXEL encoder for pixel array reshaping, palette scaling, and bitwise encoding. All NumPy operations were replaced with pure Python equivalents (list slicing, `set()` comprehensions, bitwise OR loops).

| Metric | Before (v0.2.3) | After (v0.3.0) | Improvement |
|---|---|---|---|
| Dependency install size | ~75 MB | ~10 MB | **~87% smaller** |
| Number of dependencies | 5 | 4 | 1 fewer C-extension package |

### 2. Lazy Imports — Load Modules on Demand (~57% faster startup)

Heavy modules (`requests`, `Pillow`, SIXEL/Kitty/block renderers) were imported at the top of `cli.py`, meaning every command — even `astra --version` or `astra config --show` — paid the full import cost.

Now, these imports are deferred to the functions that actually use them. Lightweight commands only load `typer` and `rich`.

| Metric | Before (v0.2.3) | After (v0.3.0) | Improvement |
|---|---|---|---|
| `astra --version` import time | ~2400 ms | ~700 ms | **~71% faster** |
| `astra today` import time | ~2400 ms | ~1030 ms | **~57% faster** |

### 3. Efficient Block Renderer — Reduced Memory & ANSI Output

The block-character renderer (`blockimg.py`) was rewritten with two optimizations:

- **Direct pixel access**: Replaced `list(img.getdata())` (which copies every pixel into a Python list) with `img.load()` for O(1) direct access — no allocation, no copy.
- **Redundant ANSI code elimination**: Adjacent pixels that share foreground or background colors now skip the unchanged escape codes. For typical images, this reduces output size by ~30-40% since natural photos have many runs of similar colors.

### 4. HTTP Conditional Caching — Smarter Archive Fetches

The APOD archive index (~2 MB HTML) was previously re-downloaded unconditionally every 24 hours. Now, `ETag` and `Last-Modified` headers are cached locally. On subsequent fetches, conditional headers (`If-None-Match` / `If-Modified-Since`) are sent, and if the server responds with `304 Not Modified`, zero bytes are transferred.

| Metric | Before (v0.2.3) | After (v0.3.0) | Improvement |
|---|---|---|---|
| Archive refresh (unchanged) | ~2 MB download | 0 bytes (304) | **~100% bandwidth saved** |
| Archive refresh (changed) | ~2 MB download | ~2 MB download | Same (expected) |

## Built with

[Python](https://python.org) · [Typer](https://typer.tiangolo.com) · [Rich](https://rich.readthedocs.io) · [Pillow](https://python-pillow.org)

## License

MIT © 2026 Asutosh Shrestha
