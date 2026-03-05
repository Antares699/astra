"""Astra — Fetch NASA's Astronomy Picture of the Day"""

import datetime
import os
import re
import sys
from io import BytesIO

import requests
import typer
from PIL import Image
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
    VALID_SHELLS,
)
from astra.sixel import image_to_sixel, hex_to_rgb, supports_sixel
from astra.blockimg import image_to_blocks
from astra.kitty import image_to_kitty

APOD_URL = "https://api.nasa.gov/planetary/apod"

app = typer.Typer()
console = Console()


def _get_api_key(interactive: bool = True) -> str | None:
    """Get NASA API key"""
    config = load_config()

    if config.get("api_key"):
        return config["api_key"]

    env_key = os.getenv("NASA_API_KEY")
    if env_key:
        return env_key

    if not interactive:
        return None

    console.print()
    console.print("[yellow]No NASA API key found.[/yellow]")
    console.print(
        "Get a free key at: [underline blue]https://api.nasa.gov[/underline blue]"
    )
    console.print()
    api_key = typer.prompt("Enter your API key")

    config["api_key"] = api_key
    save_config(config)
    console.print("[green]API key saved successfully![/green]")
    console.print()
    return api_key


def fetch_apod(api_key: str, **params) -> dict:
    """Fetch APOD data from NASA API"""
    response = requests.get(
        APOD_URL, params={"api_key": api_key, "thumbs": True, **params}, timeout=10
    )
    response.raise_for_status()
    return response.json()


def _detect_renderer() -> str:
    """Auto-detect the best graphics protocol for current terminal"""
    term_program = os.environ.get("TERM_PROGRAM", "").lower()
    if term_program in ("ghostty", "kitty", "wezterm"):
        return "kitty"

    if sys.platform == "win32":
        return "sixel"

    if supports_sixel():
        return "sixel"

    return "block"


def render_image(img: Image.Image, size: str, term_width: int, bg: str) -> bool:
    """Render a PIL Image to the terminal."""
    render_width = term_width if size == "full" else int(term_width * 0.6)
    bg_color = hex_to_rgb(bg) if bg else None
    renderer = _detect_renderer()

    console.print()

    # Path 1: Kitty protocol
    if renderer == "kitty":
        try:
            kitty_data = image_to_kitty(img, render_width, term_width)
            sys.stdout.write("\r" + kitty_data)
            sys.stdout.flush()
            return True
        except Exception:
            pass  # Fall through to SIXEL

    # Path 2: SIXEL protocol
    if renderer in ("kitty", "sixel"):
        try:
            sixel_data = image_to_sixel(img, render_width, term_width, bg_color)
            sys.stdout.write("\r" + sixel_data)
            sys.stdout.flush()
            return True
        except Exception:
            pass  # Fall through to block

    # Path 3: Block characters
    output = image_to_blocks(img, render_width)
    padding = " " * ((term_width - render_width) // 2)
    centered = "\n".join(padding + line for line in output.split("\n"))
    sys.stdout.write(centered + "\n")
    sys.stdout.flush()
    return False


def display_apod(data: dict, size: str, bg: str) -> None:
    """Display an APOD data dictionary."""
    title = data.get("title", "No Title")
    date = data.get("date", "Unknown Date")
    header = Text(justify="center")
    header.append(f"{title}\n", style="bold cyan")
    header.append(date, style="dim italic")
    console.print()
    console.print(Panel(header, border_style="blue"))

    term_width = console.width

    if data.get("media_type") == "video":
        video_url = data.get("url", "")
        thumb_url = data.get("thumbnail_url", "")

        if thumb_url:
            try:
                img_response = requests.get(thumb_url, timeout=30)
                img_response.raise_for_status()
                img = Image.open(BytesIO(img_response.content))
                fallback = not render_image(img, size, term_width, bg)
            except requests.RequestException:
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
            img_response = requests.get(image_url, timeout=30)
            img_response.raise_for_status()
        except requests.RequestException:
            console.print(
                f"\n  Could not download image: [underline blue]{image_url}[/underline blue]"
            )
            save_last_apod(data)
            return

        img = Image.open(BytesIO(img_response.content))
        fallback = not render_image(img, size, term_width, bg)

        if fallback:
            console.print(f"\n  View HD: [underline blue]{image_url}[/underline blue]")

    if copyright_text := data.get("copyright"):
        clean_text = re.sub(r"\s+", " ", copyright_text).strip()
        safe_text = escape(clean_text)
        console.print()
        console.print(f"[dim italic]© {safe_text}[/dim italic]", justify="right")

    console.print()

    save_last_apod(data)


def run_apod(size: str | None, bg: str | None, **api_params) -> None:
    """Logic for fetching and displaying an APOD"""
    config = load_config()
    size = size or config.get("size", "default")
    bg = bg or config.get("bg")

    api_key = _get_api_key(interactive=True)
    if not api_key:
        raise typer.Exit(code=1)

    try:
        data = fetch_apod(api_key, **api_params)
    except requests.RequestException as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1)

    display_apod(data, size, bg)


@app.callback(invoke_without_command=True)
def main_callback(ctx: typer.Context) -> None:
    """Default: show today's APOD"""
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
    """Fetch a random APOD imagE"""
    config = load_config()
    size = size or config.get("size", "default")
    bg = bg or config.get("bg")

    api_key = _get_api_key(interactive=True)
    if not api_key:
        raise typer.Exit(code=1)

    try:
        results = fetch_apod(api_key, count=5)
    except requests.RequestException as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
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
        api_key = _get_api_key(interactive=False)
        if not api_key:
            return

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
    reset: bool = typer.Option(False, "--reset", help="Reset config to defaults."),
    show: bool = typer.Option(False, "--show", help="Show current config."),
) -> None:
    """Manage Astra configuration."""
    if reset:
        config = load_config()
        save_config(
            {
                "size": "default",
                "bg": None,
                "greeter": False,
                "greeter_freq": "daily",
                "api_key": config.get("api_key"),  # preserve existing key
                "greeter_last_run": config.get("greeter_last_run"),
            }
        )
        console.print("[green]Config reset to defaults.[/green]")
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
        console.print("       astra config --greeter <on|off> --shell <shell>")
        console.print("       astra config --greeter-freq <daily|always>")
        console.print("       astra config --show")
        console.print("       astra config --reset")
    else:
        save_config(config)


if __name__ == "__main__":
    app()
