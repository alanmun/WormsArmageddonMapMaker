Worms Armageddon colour map helper
==================================

This script converts a normal image into a Worms Armageddon colour map (8-bit indexed PNG). It reshapes the image so its dimensions are divisible by 8, reduces the palette to a game-safe size, optionally makes one colour transparent, and can copy map settings (w2lv/waLV chunk) from an existing map.

Requirements
------------
- Python 3.12+
- Tkinter runtime (bundled on Windows; on Debian/Ubuntu install a matching tk package, e.g. `sudo apt-get install python3.12-tk` or `python3-tk`)

Install dependencies:
```
python -m venv .venv
. .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt  # or pip install pillow
```

Command-line usage (for power users)
------------------------------------
Run the converter:
```
python make_map.py INPUT_IMAGE OUTPUT_MAP [options]
```

Options:
- `-t, --template PATH` copy the w2lv/waLV chunk from an existing W:A map.
- `-m, --maxcolours N` limit palette to N colours (1-112, default 112).
- `-c, --transparent-colour R G B` treat this RGB colour as transparent (default 0 0 0). Exact matches become holes in-game.
- `--no-transparency` disable transparency handling entirely.
- `--dither` enable Floyd-Steinberg dithering when reducing colours.

Common examples:
- Simple conversion: `python make_map.py input.png output.png`
- Keep a hole colour: `python make_map.py input.png output.png -c 0 0 0`
- Reuse map settings: `python make_map.py input.png output.png --template reference_map.png`
- Reduce colours: `python make_map.py input.png output.png -m 96 --dither`

Output placement: save the resulting PNG into your W:A `User/SavedLevels/` folder (or a subfolder) and pick it in the in-game map editor.

Windows GUI (primary distribution)
----------------------------------
The included Tkinter GUI (`gui.py`) mirrors all CLI options for non-technical Windows users:
1) Click "Open image" to choose the source PNG.
2) Optional: click "Template map" to select an existing W:A map to copy settings from.
3) Optional: adjust max colours, transparent colour, and toggle dithering/transparency.
4) Click "Save as..." to pick where the converted PNG should go.
5) Click "Convert" to run; a success message points to the chosen output. Put that PNG into `User/SavedLevels/` to use it in-game.

The GUI attempts to auto-target the W:A `User/SavedLevels/` folder for the output (Steam, Team17, or GOG installs, including WSL mounts like `/mnt/c/...`). If it cannot find your install, it will ask where to save.

Building the Windows executable yourself:
```
pip install pyinstaller
pyinstaller --onefile --noconsole gui.py
```

Or with uv:
```
uvx pyinstaller --onefile --noconsole gui.py
```

The generated `dist/gui.exe` is the file to share. The GUI is Windows-focused; Linux users can run the CLI via `uv run` or try the .exe with Wine/Proton if they wish. You can also try building, PyInstaller most likely works fine to make elf binaries, it is cross platform.
