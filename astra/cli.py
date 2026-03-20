"""Astra — Fetch NASA's Astronomy Picture of the Day"""

import datetime
import os
import re
import sys
from io import BytesIO

import typer
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.text import Text

from astra.config import (
    load_config,
    save_config,
    get_config_path,
    save_last_apod,
    load_last_apod,
    validate_shell,
    install_greeter,
    uninstall_greeter,
    get_cached_image,
    save_cached_image,
    cleanup_expired_cache,
    clear_cache,
    search_archive,
    VALID_SHELLS,
)

APOD_URL = "https://api.nasa.gov/planetary/apod"

app = typer.Typer()
console = Console()


def _get_api_key() -> str:
    """Get NASA API key. Falls back to DEMO_KEY."""
    config = load_config()

    stored_key = config.get("api_key")
    if stored_key and stored_key.strip() and " " not in stored_key:
        return stored_key

    env_key = os.getenv("NASA_API_KEY")
    if env_key:
        return env_key

    return "DEMO_KEY"


def fetch_apod(api_key: str, **params) -> dict:
    """Fetch APOD data from NASA API"""
    import requests 

    response = requests.get(
        APOD_URL, params={"api_key": api_key, "thumbs": True, **params}, timeout=20
    )
    if response.status_code == 429:
        console.print("[bold red]Error:[/bold red] API rate limit exceeded.")
        console.print("Set your own key: [cyan]astra config --api-key <key>[/cyan]")
        console.print(
            "Get a free key at: [underline blue]https://api.nasa.gov[/underline blue]"
        )
        raise typer.Exit(code=1)
    response.raise_for_status()
    return response.json()


def _get_ext_from_url(url: str) -> str:
    """Get file extension from URL"""
    if url.lower().endswith(".png"):
        return "png"
    return "jpg"


def _download_image(url: str, date: str, use_cache: bool = True) -> bytes:
    """Download image with caching. Returns raw image bytes"""
    import requests  

    ext = _get_ext_from_url(url)

    if use_cache:
        cached = get_cached_image(date, ext)
        if cached:
            return cached

    response = requests.get(url, timeout=30)
    response.raise_for_status()
    data = response.content

    if use_cache:
        save_cached_image(date, ext, data)

    return data


def _detect_renderer() -> str:
    """Auto-detect the best graphics protocol for current terminal"""
    term_program = os.environ.get("TERM_PROGRAM", "").lower()
    if term_program in ("ghostty", "kitty", "wezterm"):
        return "kitty"

    if sys.platform == "win32":
        return "sixel"

    from astra.sixel import supports_sixel 

    if supports_sixel():
        return "sixel"

    return "block"


def render_image(img, size: str, term_width: int, bg: str) -> bool:
    """Render a PIL Image to the terminal"""
    from astra.sixel import hex_to_rgb  

    render_width = term_width if size == "full" else int(term_width * 0.6)
    bg_color = hex_to_rgb(bg) if bg else None
    renderer = _detect_renderer()

    console.print()

    # Path 1: Kitty protocol
    if renderer == "kitty":
        try:
            from astra.kitty import image_to_kitty  # Lazy

            kitty_data = image_to_kitty(img, render_width, term_width)
            sys.stdout.write("\r" + kitty_data)
            sys.stdout.flush()
            return True
        except Exception:
            pass  # Fall through to SIXEL

    # Path 2: SIXEL protocol
    if renderer in ("kitty", "sixel"):
        try:
            from astra.sixel import image_to_sixel  # Lazy

            sixel_data = image_to_sixel(img, render_width, term_width, bg_color)
            sys.stdout.write("\r" + sixel_data)
            sys.stdout.flush()
            return True
        except Exception:
            pass  # Fall through to block

    # Path 3: Block characters
    from astra.blockimg import image_to_blocks  # Lazy

    output = image_to_blocks(img, render_width)
    padding = " " * ((term_width - render_width) // 2)
    centered = "\n".join(padding + line for line in output.split("\n"))
    sys.stdout.write(centered + "\n")
    sys.stdout.flush()
    return False


def display_apod(data: dict, size: str, bg: str) -> None:
    """Display an APOD data dictionary"""
    from PIL import Image  # Lazy: only needed when displaying images

    title = data.get("title", "No Title")
    date = data.get("date", "Unknown Date")
    header = Text(justify="center")
    header.append(f"{title}\n", style="bold cyan")
    header.append(date, style="dim italic")
    console.print()
    console.print(Panel(header, border_style="blue"))

    term_width = console.width
    date = data.get("date", "")

    if data.get("media_type") == "video":
        video_url = data.get("url", "")
        thumb_url = data.get("thumbnail_url", "")

        if thumb_url:
            try:
                img_data = _download_image(thumb_url, date, use_cache=False)
                img = Image.open(BytesIO(img_data))
                fallback = not render_image(img, size, term_width, bg)
            except Exception:
                fallback = True
        else:
            fallback = True

        console.print()
        console.print(f"  Watch: [underline blue]{video_url}[/underline blue]")
        if fallback and thumb_url:
            console.print(f"\n  Thumbnail unavailable.")
    else:
        image_url = data.get("hdurl") or data.get("url", "")
        try:
            img_data = _download_image(image_url, date)
        except Exception:
            console.print(
                f"\n  Could not download image: [underline blue]{image_url}[/underline blue]"
            )
            save_last_apod(data)
            return

        img = Image.open(BytesIO(img_data))
        fallback = not render_image(img, size, term_width, bg)

        if fallback:
            console.print(f"\n  View HD: [underline blue]{image_url}[/underline blue]")

    if copyright_text := data.get("copyright"):
        clean_text = re.sub(r"\s+", " ", copyright_text).strip()
        safe_text = escape(clean_text)
        console.print()
        console.print(f"[dim italic](c) {safe_text}[/dim italic]", justify="right")

    console.print()

    save_last_apod(data)


def run_apod(size: str | None, bg: str | None, **api_params) -> None:
    """Logic for fetching and displaying an APOD"""
    # Clean up expired cache entries
    cleanup_expired_cache(max_age_days=14)

    config = load_config()
    size = size or config.get("size", "default")
    bg = bg or config.get("bg")

    api_key = _get_api_key()

    try:
        data = fetch_apod(api_key, **api_params)
    except Exception:
        console.print(
            "[bold red]Error:[/bold red] Could not reach NASA API. Check your connection."
        )
        raise typer.Exit(code=1)

    display_apod(data, size, bg)


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    version: bool = typer.Option(None, "--version", "-v", help="Show version."),
) -> None:
    """Default: show today's APOD"""
    if version:
        from astra import __version__

        console.print(f"astra {__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        run_apod(None, None)


@app.command()
def today(
    size: str = typer.Option(
        None, "--size", "-s", help="Image size: 'default' (60%) or 'full'."
    ),
    bg: str = typer.Option(
        None, "--bg", help="Background color in hex (e.g., '#0c0c0c')."
    ),
) -> None:
    """Fetch and display today's APOD"""
    run_apod(size, bg)


@app.command()
def date(
    date: str = typer.Argument(..., help="Date in YYYY-MM-DD format."),
    size: str = typer.Option(
        None, "--size", "-s", help="Image size: 'default' (60%) or 'full'."
    ),
    bg: str = typer.Option(
        None, "--bg", help="Background color in hex (e.g., '#0c0c0c')."
    ),
) -> None:
    """Fetch APOD for a specific date"""
    # Validate date format
    try:
        datetime.datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        console.print(
            "[bold red]Error:[/bold red] Invalid date format. Use YYYY-MM-DD (e.g., 2021-08-14)."
        )
        raise typer.Exit(code=1)
    run_apod(size, bg, date=date)


@app.command()
def random(
    size: str = typer.Option(
        None, "--size", "-s", help="Image size: 'default' (60%) or 'full'."
    ),
    bg: str = typer.Option(
        None, "--bg", help="Background color in hex (e.g., '#0c0c0c')."
    ),
) -> None:
    """Fetch a random APOD image"""
    config = load_config()
    size = size or config.get("size", "default")
    bg = bg or config.get("bg")

    api_key = _get_api_key()

    try:
        results = fetch_apod(api_key, count=5)
    except Exception:
        console.print(
            "[bold red]Error:[/bold red] Could not reach NASA API. Check your connection."
        )
        raise typer.Exit(code=1)

    if isinstance(results, dict):
        results = [results]

    for item in results:
        if item.get("media_type") == "image":
            display_apod(item, size, bg)
            break
    else:
        console.print(
            "[bold yellow]Warning:[/bold yellow] Could not find an image in random results."
        )


@app.command()
def info() -> None:
    """Show explanation for the last viewed APOD"""
    data = load_last_apod()
    if not data:
        console.print(
            "[bold yellow]No APOD viewed yet.[/bold yellow] Run `astra` first."
        )
        raise typer.Exit(code=1)

    title = data.get("title", "No Title")
    date = data.get("date", "Unknown Date")
    explanation = data.get("explanation", "")

    if not explanation:
        console.print("[yellow]No description available for this APOD.[/yellow]")
        return

    header = Text(justify="center")
    header.append(f"{title}\n", style="bold cyan")
    header.append(date, style="dim italic")
    console.print()
    console.print(Panel(header, border_style="blue"))
    console.print()
    console.print(explanation)
    console.print()


@app.command()
def greet() -> None:
    """Show today's APOD on terminal startup"""
    config = load_config()

    # Exit silently if greeter is disabled
    if not config.get("greeter"):
        return

    freq = config.get("greeter_freq", "daily")
    today = datetime.date.today().isoformat()

    if freq == "daily":
        if config.get("greeter_last_run") == today:
            return  # Already run today.

    # Show today's APOD
    try:
        api_key = _get_api_key()

        config = load_config()
        size = config.get("size", "default")
        bg = config.get("bg")

        data = fetch_apod(api_key)
        display_apod(data, size, bg)

        # Record that greeter ran today
        config["greeter_last_run"] = today
        save_config(config)
    except Exception:
        pass  # Fail silently in greeter


@app.command()
def save() -> None:
    """Save the last viewed APOD"""
    last = load_last_apod()
    if not last:
        console.print(
            "[bold yellow]No APOD viewed yet.[/bold yellow] Run `astra` first."
        )
        raise typer.Exit(code=1)

    config = load_config()
    save_dir = config.get("save_dir")

    if not save_dir:
        console.print()
        console.print("[yellow]No save directory configured.[/yellow]")
        save_dir = typer.prompt(
            "Where should Astra save images? (e.g., ~/Pictures/Astra)"
        )
        save_dir = os.path.expanduser(save_dir)
        config["save_dir"] = save_dir
        save_config(config)
        console.print(f"[green]Save directory set to: {save_dir}[/green]")

    date = last.get("date", "")
    if not date:
        console.print("[bold red]Error:[/bold red] No date found in last APOD.")
        raise typer.Exit(code=1)

    image_url = last.get("hdurl") or last.get("url", "")
    if not image_url:
        console.print("[bold red]Error:[/bold red] No image URL found in last APOD.")
        raise typer.Exit(code=1)

    ext = _get_ext_from_url(image_url)
    filename = f"{date}.{ext}"
    filepath = os.path.join(save_dir, filename)

    if os.path.exists(filepath):
        console.print(f"[yellow]Already saved: {filepath}[/yellow]")
        return

    try:
        img_data = _download_image(image_url, date)
    except Exception:
        console.print(
            "[bold red]Error:[/bold red] Could not download image. Check your connection."
        )
        raise typer.Exit(code=1)

    os.makedirs(save_dir, exist_ok=True)
    with open(filepath, "wb") as f:
        f.write(img_data)

    console.print(f"[green]Saved: {filepath}[/green]")


def _parse_archive_date(date_str: str) -> str:
    try:
        dt = datetime.datetime.strptime(date_str, "%Y %B %d")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return date_str


@app.command()
def search(
    query: str = typer.Argument(..., help="Search APOD titles."),
    size: str = typer.Option(
        None, "--size", "-s", help="Image size: 'default' (60%) or 'full'."
    ),
    bg: str = typer.Option(
        None, "--bg", help="Background color in hex (e.g., '#0c0c0c')."
    ),
) -> None:
    """Search the APOD archive by title"""
    try:
        with console.status(f"[cyan]Searching for '{query}'..."):
            results = search_archive(query)
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] Could not fetch archive: {e}")
        raise typer.Exit(code=1)

    if not results:
        console.print(f"[yellow]No results found for '{query}'.[/yellow]")
        return

    total = len(results)
    shown = results[:10]

    console.print()
    console.print(f"  [bold]Found {total} matches for '{query}':[/bold]")
    console.print()

    for i, (date_str, title) in enumerate(shown, 1):
        api_date = _parse_archive_date(date_str)
        console.print(
            f"  [cyan]{i:>2}.[/cyan] [bold]{title:<40}[/bold] [dim]{api_date}[/dim]"
        )

    if total > 10:
        console.print(f"\n  [dim]... and {total - 10} more matches.[/dim]")

    console.print()
    choice = typer.prompt("Enter number to view (or 'q' to quit)", default="q")

    if choice.lower() == "q":
        return

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(shown):
            date_str, _ = shown[idx]
            api_date = _parse_archive_date(date_str)
            run_apod(size, bg, date=api_date)
        else:
            console.print("[red]Invalid selection.[/red]")
    except ValueError:
        console.print("[red]Please enter a valid number.[/red]")


@app.command("config")
def config_cmd(
    size: str = typer.Option(
        None, "--size", "-s", help="Set default size: 'default' or 'full'."
    ),
    bg: str = typer.Option(
        None, "--bg", help="Set default background color (e.g., '#0c0c0c')."
    ),
    api_key: str = typer.Option(None, "--api-key", help="Set NASA API key."),
    greeter: str = typer.Option(
        None, "--greeter", help="Enable or disable greeter: 'on' or 'off'."
    ),
    greeter_freq: str = typer.Option(
        None, "--greeter-freq", help="Greeter frequency: 'daily' or 'always'."
    ),
    shell: str = typer.Option(
        None,
        "--shell",
        help=f"Shell to install/uninstall greeter: {', '.join(VALID_SHELLS)}.",
    ),
    save_dir: str = typer.Option(
        None, "--save-dir", help="Set default save directory for images."
    ),
    do_clear_cache: bool = typer.Option(
        False, "--clear-cache", help="Clear all cached images."
    ),
    reset: bool = typer.Option(False, "--reset", help="Reset config to defaults."),
    show: bool = typer.Option(False, "--show", help="Show current config."),
) -> None:
    """Manage Astra configuration"""
    if reset:
        config = load_config()
        save_config(
            {
                "size": "default",
                "bg": None,
                "greeter": False,
                "greeter_freq": "daily",
                "api_key": config.get("api_key"),
                "greeter_last_run": config.get("greeter_last_run"),
                "save_dir": config.get("save_dir"),
            }
        )
        console.print("[green]Config reset to defaults.[/green]")
        return

    if do_clear_cache:
        deleted, freed = clear_cache()
        freed_mb = freed / (1024 * 1024)
        console.print(
            f"[green]Cleared {deleted} cached images ({freed_mb:.2f} MB).[/green]"
        )
        return

    if show:
        config = load_config()
        config_path = get_config_path()
        stored_key = config.get("api_key")
        if stored_key:
            masked = f"****...{stored_key[-4:]}"
        else:
            env_key = os.getenv("NASA_API_KEY")
            masked = f"****...{env_key[-4:]} (from env)" if env_key else "not set"
        console.print(f"[dim]Config file: {config_path}[/dim]")
        console.print(f"  api_key: {masked}")
        console.print(f"  size: {config.get('size', 'default')}")
        console.print(f"  bg: {config.get('bg') or 'auto-detect'}")
        console.print(f"  greeter: {'on' if config.get('greeter') else 'off'}")
        console.print(f"  greeter_freq: {config.get('greeter_freq', 'daily')}")
        console.print(f"  save_dir: {config.get('save_dir') or 'not set'}")
        return

    config = load_config()
    changed = False

    if api_key is not None:
        config["api_key"] = api_key
        changed = True
        console.print("[green]API key updated.[/green]")

    if size is not None:
        if size not in ("default", "full"):
            console.print("[red]Error: size must be 'default' or 'full'[/red]")
            raise typer.Exit(code=1)
        config["size"] = size
        changed = True
        console.print(f"[green]Set size = {size}[/green]")

    if bg is not None:
        config["bg"] = bg
        changed = True
        console.print(f"[green]Set bg = {bg}[/green]")

    if greeter_freq is not None:
        if greeter_freq not in ("daily", "always"):
            console.print("[red]Error: greeter-freq must be 'daily' or 'always'[/red]")
            raise typer.Exit(code=1)
        config["greeter_freq"] = greeter_freq
        changed = True
        console.print(f"[green]Set greeter_freq = {greeter_freq}[/green]")

    if save_dir is not None:
        save_dir = os.path.expanduser(save_dir)
        config["save_dir"] = save_dir
        changed = True
        console.print(f"[green]Set save_dir = {save_dir}[/green]")

    if greeter is not None:
        if greeter not in ("on", "off"):
            console.print("[red]Error: greeter must be 'on' or 'off'[/red]")
            raise typer.Exit(code=1)

        if shell is None:
            console.print(f"[red]Error: --shell is required with --greeter[/red]")
            console.print(f"[dim]Valid shells: {', '.join(VALID_SHELLS)}[/dim]")
            raise typer.Exit(code=1)

        error = validate_shell(shell)
        if error:
            console.print(f"[red]Error: {error}[/red]")
            raise typer.Exit(code=1)

        if greeter == "on":
            install_greeter(shell)
            config["greeter"] = True
            console.print(f"[green]Greeter enabled for {shell}.[/green]")
        else:
            uninstall_greeter(shell)
            config["greeter"] = False
            console.print(f"[green]Greeter disabled for {shell}.[/green]")

        changed = True

    if not changed:
        console.print("Usage: astra config --api-key <key>")
        console.print("       astra config --size <default|full> --bg <hex_color>")
        console.print("       astra config --save-dir <path>")
        console.print("       astra config --greeter <on|off> --shell <shell>")
        console.print("       astra config --greeter-freq <daily|always>")
        console.print("       astra config --clear-cache")
        console.print("       astra config --show")
        console.print("       astra config --reset")
    else:
        save_config(config)


if __name__ == "__main__":
    app()
