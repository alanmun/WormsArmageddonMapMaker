"""
Simple Tkinter front-end for the Worms Armageddon map converter.

This GUI mirrors the CLI flags from make_map.py:
* input image
* output PNG
* optional template (to copy w2lv/waLV chunk)
* max colours (1-112)
* transparent colour triplet or disabled transparency
* optional dithering

The GUI tries to locate the W:A SavedLevels folder automatically (Steam and
typical non-Steam installs). If detection fails, users can choose any output
path manually.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Iterable, List, Optional
import tkinter as tk
from tkinter import filedialog, messagebox

from make_map import convert_image


def _is_wsl() -> bool:
    try:
        with open("/proc/sys/kernel/osrelease", "r", encoding="utf-8") as f:
            data = f.read().lower()
        return "microsoft" in data or "wsl" in data
    except Exception:
        return False


def _steam_install_paths() -> List[Path]:
    """Return candidate Steam install paths (Steam root, not app)."""
    candidates: List[Path] = []
    env_paths = [
        os.environ.get("PROGRAMFILES(X86)"),
        os.environ.get("PROGRAMFILES"),
        os.environ.get("PROGRAMW6432"),
    ]
    for base in env_paths:
        if base:
            candidates.append(Path(base) / "Steam")
    # WSL: check Windows C: drive
    if _is_wsl():
        win_c = Path("/mnt/c")
        candidates.extend(
            [
                win_c / "Program Files (x86)" / "Steam",
                win_c / "Program Files" / "Steam",
            ]
        )
    # Common Linux/Proton locations
    home = Path.home()
    candidates.extend(
        [
            home / ".steam" / "steam",
            home / ".local" / "share" / "Steam",
            home / "Steam",
        ]
    )
    # Registry lookup on Windows
    if os.name == "nt":
        try:
            import winreg

            for hive, subkey in (
                (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Wow6432Node\Valve\Steam"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam"),
            ):
                try:
                    with winreg.OpenKey(hive, subkey) as key:
                        path, _ = winreg.QueryValueEx(key, "InstallPath")
                        if path:
                            candidates.append(Path(path))
                except OSError:
                    continue
        except Exception:
            pass
    return [p for p in candidates if p]


def _steam_libraries() -> List[Path]:
    """Return steamapps paths from known Steam roots and libraryfolders.vdf."""
    libraries: List[Path] = []
    for steam_root in _steam_install_paths():
        steamapps = steam_root / "steamapps"
        if steamapps.is_dir():
            libraries.append(steamapps)
            vdf = steamapps / "libraryfolders.vdf"
            if vdf.is_file():
                try:
                    text = vdf.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    text = ""
                # Handle both legacy and new VDF formats by grabbing any "path" value
                for match in re.finditer(r'"path"\s*"([^"]+)"', text):
                    lib = Path(match.group(1)).expanduser()
                    lib_apps = lib / "steamapps"
                    if lib_apps.is_dir():
                        libraries.append(lib_apps)
    # Deduplicate while preserving order
    seen = set()
    unique: List[Path] = []
    for lib in libraries:
        if lib in seen:
            continue
        seen.add(lib)
        unique.append(lib)
    return unique


def find_wa_savedlevels() -> Optional[Path]:
    """Best-effort detection of the Worms Armageddon SavedLevels folder."""
    # Steam libraries
    for lib in _steam_libraries():
        candidate = lib / "common" / "Worms Armageddon"
        if candidate.is_dir():
            saved = candidate / "User" / "SavedLevels"
            if saved.is_dir():
                return saved
    # Common non-Steam installs on Windows
    potential_roots: Iterable[Path] = []
    if os.name == "nt" or _is_wsl():
        pf = os.environ.get("PROGRAMFILES(X86)")
        pf64 = os.environ.get("PROGRAMFILES")
        roots = [
            Path(pf) / "Team17" / "Worms Armageddon" if pf else None,
            Path(pf64) / "Team17" / "Worms Armageddon" if pf64 else None,
            Path("C:/Team17/Worms Armageddon"),
            Path("C:/Worms Armageddon"),
            Path("C:/GOG Games/Worms Armageddon"),
        ]
        if _is_wsl():
            win_c = Path("/mnt/c")
            roots.extend(
                [
                    win_c / "Team17" / "Worms Armageddon",
                    win_c / "Worms Armageddon",
                    win_c / "GOG Games" / "Worms Armageddon",
                ]
            )
        potential_roots = filter(None, roots)
        for root in potential_roots:
            saved = root / "User" / "SavedLevels"
            if saved.is_dir():
                return saved
    return None


class MapGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Worms Armageddon Map Converter")
        self.root.resizable(False, False)

        self.input_path = tk.StringVar()
        self.template_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.max_colours = tk.StringVar(value="112")
        self.transparent_r = tk.StringVar(value="0")
        self.transparent_g = tk.StringVar(value="0")
        self.transparent_b = tk.StringVar(value="0")
        self.no_transparency = tk.BooleanVar(value=False)
        self.dither = tk.BooleanVar(value=False)

        self.savedlevels_dir = find_wa_savedlevels()

        self._build_ui()

    def _build_ui(self) -> None:
        padding = {"padx": 8, "pady": 4}

        # Input
        tk.Label(self.root, text="Input image").grid(row=0, column=0, sticky="w", **padding)
        tk.Entry(self.root, textvariable=self.input_path, width=50).grid(row=0, column=1, **padding)
        tk.Button(self.root, text="Browse", command=self.browse_input).grid(row=0, column=2, **padding)

        # Template
        tk.Label(self.root, text="Template map (optional)").grid(row=1, column=0, sticky="w", **padding)
        tk.Entry(self.root, textvariable=self.template_path, width=50).grid(row=1, column=1, **padding)
        tk.Button(self.root, text="Browse", command=self.browse_template).grid(row=1, column=2, **padding)

        # Output
        tk.Label(self.root, text="Output PNG").grid(row=2, column=0, sticky="w", **padding)
        tk.Entry(self.root, textvariable=self.output_path, width=50).grid(row=2, column=1, **padding)
        tk.Button(self.root, text="Save as", command=self.choose_output).grid(row=2, column=2, **padding)

        # Max colours
        tk.Label(self.root, text="Max colours (1-112)").grid(row=3, column=0, sticky="w", **padding)
        tk.Entry(self.root, textvariable=self.max_colours, width=8).grid(row=3, column=1, sticky="w", **padding)

        # Transparency
        tk.Checkbutton(self.root, text="Disable transparency", variable=self.no_transparency).grid(
            row=4, column=0, sticky="w", **padding
        )
        tk.Label(self.root, text="Transparent colour (R G B)").grid(row=5, column=0, sticky="w", **padding)
        tk.Entry(self.root, textvariable=self.transparent_r, width=4).grid(row=5, column=1, sticky="w", **padding)
        tk.Entry(self.root, textvariable=self.transparent_g, width=4).grid(row=5, column=2, sticky="w", **padding)
        tk.Entry(self.root, textvariable=self.transparent_b, width=4).grid(row=5, column=3, sticky="w", **padding)

        # Dither
        tk.Checkbutton(self.root, text="Enable dithering", variable=self.dither).grid(
            row=6, column=0, sticky="w", **padding
        )

        # Convert button
        tk.Button(self.root, text="Convert", command=self.run_conversion, width=20).grid(
            row=7, column=0, columnspan=2, pady=12
        )
        tk.Button(self.root, text="Help", command=self.show_help, width=10).grid(
            row=7, column=2, columnspan=2, pady=12
        )

        # SavedLevels hint
        hint = (
            f"Detected SavedLevels: {self.savedlevels_dir}"
            if self.savedlevels_dir
            else "SavedLevels folder not detected (you can still choose any output)."
        )
        tk.Label(self.root, text=hint, fg="gray").grid(row=8, column=0, columnspan=4, sticky="w", **padding)

    def show_help(self) -> None:
        message = (
            "How to use:\n\n"
            "1) Pick an image. Transparent pixels become air/holes in-game.\n"
            "2) If the app finds your W:A SavedLevels folder, it will suggest an output there.\n"
            "3) Only choose an output manually if detection failed or you want a different location.\n"
            "4) Optional: pick a template map to copy settings, adjust max colours, toggle dithering/transparency.\n"
            "5) Click Convert. The PNG goes into SavedLevels and will appear in the W:A map list."
        )
        messagebox.showinfo("Help", message)

    def browse_input(self) -> None:
        path = filedialog.askopenfilename(
            title="Select input image",
            filetypes=[("Images", "*.png *.webp *.jpg *.jpeg *.bmp *.gif"), ("All files", "*.*")],
        )
        if path:
            self.input_path.set(path)
            # Suggest output name in SavedLevels if possible
            stem = Path(path).stem
            suggested = f"{stem}_wa.png"
            if self.savedlevels_dir:
                self.output_path.set(str(self.savedlevels_dir / suggested))
            else:
                self.output_path.set(str(Path(path).with_name(suggested)))

    def browse_template(self) -> None:
        path = filedialog.askopenfilename(
            title="Select template map (optional)",
            filetypes=[("PNG files", "*.png"), ("All files", "*.*")],
        )
        if path:
            self.template_path.set(path)

    def choose_output(self) -> None:
        initialdir = self.savedlevels_dir if self.savedlevels_dir else Path(self.input_path.get() or ".").parent
        path = filedialog.asksaveasfilename(
            title="Save output PNG",
            defaultextension=".png",
            filetypes=[("PNG files", "*.png")],
            initialdir=initialdir,
            initialfile=Path(self.output_path.get()).name or "converted.png",
        )
        if path:
            self.output_path.set(path)

    def _parse_colour(self) -> Optional[tuple[int, int, int]]:
        if self.no_transparency.get():
            return None
        try:
            values = [int(self.transparent_r.get()), int(self.transparent_g.get()), int(self.transparent_b.get())]
        except ValueError:
            messagebox.showerror("Invalid colour", "Transparent colour must be three integers (0-255).")
            return None
        for v in values:
            if v < 0 or v > 255:
                messagebox.showerror("Invalid colour", "Transparent colour values must be between 0 and 255.")
                return None
        return tuple(values)  # type: ignore[return-value]

    def run_conversion(self) -> None:
        input_path = self.input_path.get().strip()
        output_path = self.output_path.get().strip()
        template_path = self.template_path.get().strip() or None

        if not input_path:
            messagebox.showerror("Missing input", "Please choose an input image.")
            return
        if not output_path:
            if self.savedlevels_dir:
                output_path = str(self.savedlevels_dir / f"{Path(input_path).stem}_wa.png")
                self.output_path.set(output_path)
            else:
                messagebox.showerror("Missing output", "Please choose where to save the output PNG.")
                return

        try:
            max_cols = int(self.max_colours.get())
            if max_cols < 1 or max_cols > 112:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid max colours", "Max colours must be an integer between 1 and 112.")
            return

        transparent_colour = self._parse_colour()
        if transparent_colour is None and not self.no_transparency.get():
            return

        try:
            convert_image(
                input_path,
                output_path,
                template_path=template_path,
                max_colours=max_cols,
                transparent_colour=transparent_colour,
                dither=self.dither.get(),
            )
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Conversion failed", f"Could not create map:\n{exc}")
            return

        messagebox.showinfo("Success", f"Created map:\n{output_path}")


def main() -> None:
    root = tk.Tk()
    MapGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
