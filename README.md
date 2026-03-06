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

## Built with

[Python](https://python.org) · [Typer](https://typer.tiangolo.com) · [Rich](https://rich.readthedocs.io) · [Pillow](https://python-pillow.org) · [NumPy](https://numpy.org)

## License

MIT © 2026 Asutosh Shrestha
