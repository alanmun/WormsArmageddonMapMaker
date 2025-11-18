"""
Simple helper to convert regular images into Worms Armageddon‑compatible colour maps.

Worms Armageddon (W:A) expects colour maps to be PNG files in 8‑bit indexed
colour mode.  The image dimensions must be divisible by 8 and the palette
cannot exceed 112 unique colours (a 113th entry can be reserved for
transparency).  The game also stores extra landscape settings (water level,
object placement holes, texture choice, etc.) in a custom PNG chunk called
``w2lv`` or ``waLV``.  If you have an existing W:A map, its chunk can be
copied into new maps to preserve those settings.

This script performs the following steps:

* opens the source image (any format supported by Pillow) and converts it to
  RGBA to ensure a consistent working format;
* rescales the image so that its width and height are multiples of 8.  If
  rounding up is required, the image is enlarged; rounding down results in a
  crop.  You can override this behaviour by resizing the input image
  yourself before conversion;
* quantises the image to a maximum number of colours (default 112) using
  Pillow’s median‑cut algorithm.  This step converts the image into 8‑bit
  indexed mode and optionally designates a single palette entry as
  transparent.  Any pixels matching the specified transparent colour will
  become see‑through in the final map;
* writes the result as a PNG file and optionally copies the ``w2lv``/``waLV``
  chunk from a template map into the output.  This chunk is inserted
  immediately before the final ``IEND`` chunk.

The generated file should load directly in W:A.  Advanced users may wish to
modify the template’s settings (e.g. water height or border type) by editing
the template map inside W:A’s built‑in map editor before using it as a
source for future conversions.

Example usage::

    python wa_map_maker.py source.png output.png \
        --template reference_map.png --maxcolours 96 \
        --transparent-colour 0 0 0

The above command reads ``source.png``, quantises it to 96 colours plus
transparency, copies the ``w2lv`` chunk from ``reference_map.png`` and
produces ``output.png``.

Author: OpenAI Assistant
"""

from __future__ import annotations

import argparse
import io
import os
import struct
from typing import Iterable, Optional, Tuple

from PIL import Image, ImageChops  # type: ignore


def find_custom_chunk(data: bytes, names: Iterable[str]) -> Optional[bytes]:
    """Return the raw PNG chunk (including length, type, data and CRC) whose
    type matches one of ``names`` (case‑insensitive).

    The PNG file format consists of a signature followed by a sequence of
    chunks.  Each chunk has a 4‑byte length, 4‑byte type code, the chunk
    data and a 4‑byte CRC.  This helper walks the file and returns the first
    chunk matching any of the specified names.  If no such chunk is found,
    ``None`` is returned.
    """
    offset = 8  # skip PNG signature
    lower_names = {name.lower() for name in names}
    while offset + 8 <= len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        type_code = data[offset + 4 : offset + 8].decode("latin-1")
        chunk_start = offset
        chunk_end = offset + 8 + length + 4
        if type_code.lower() in lower_names:
            return data[chunk_start:chunk_end]
        offset = chunk_end
    return None


def insert_chunk_before_iend(png_data: bytes, chunk: bytes) -> bytes:
    """Insert ``chunk`` into the PNG data immediately before the IEND chunk.

    PNG files always end with a single ``IEND`` chunk.  This function searches
    for that chunk and inserts the new chunk just before it.  If the file
    does not contain an ``IEND`` chunk, the original data is returned
    unchanged.
    """
    offset = 8  # skip the signature
    while offset + 8 <= len(png_data):
        length = struct.unpack(">I", png_data[offset : offset + 4])[0]
        type_code = png_data[offset + 4 : offset + 8]
        if type_code == b"IEND":
            # insert chunk before this one
            return png_data[:offset] + chunk + png_data[offset:]
        offset += 8 + length + 4
    # Fallback: append chunk at the end
    return png_data + chunk


def ensure_divisible_by_8(size: Tuple[int, int]) -> Tuple[int, int]:
    """Return a new (width, height) tuple where each dimension is divisible
    by 8.  The new dimensions are computed by rounding the input dimensions
    *down* to the nearest multiple of eight.  If rounding down results in
    zero, the dimension is rounded up instead.  This behaviour avoids
    unexpectedly enlarging the map while preserving most of the original
    content.
    """
    w, h = size
    new_w = (w // 8) * 8 or 8
    new_h = (h // 8) * 8 or 8
    return new_w, new_h


def convert_image(
    input_path: str,
    output_path: str,
    *,
    template_path: Optional[str] = None,
    max_colours: int = 112,
    transparent_colour: Optional[Tuple[int, int, int]] = (0, 0, 0),
    dither: bool = False,
) -> None:
    """Convert ``input_path`` into a W:A‑compatible colour map written to
    ``output_path``.

    Parameters
    ----------
    input_path: str
        The path to the source image.
    output_path: str
        The file to write.  Any existing file will be overwritten.
    template_path: str, optional
        If supplied, the script will attempt to read the custom ``w2lv``/``waLV``
        chunk from this map and copy it into the output.  If the template does
        not contain such a chunk, no chunk is added.
    max_colours: int, optional
        The maximum number of colours in the resulting palette (excluding
        transparency).  Must be between 1 and 112.  More colours can produce
        nicer images but may cause glitches or background removal in the game.
    transparent_colour: tuple of three ints, optional
        RGB triplet designating which colour in the input should be treated as
        transparent.  Pixels matching this colour (exact match) will become
        completely transparent in the output.  If ``None``, the image is
        treated as fully solid and no transparency entry is added to the
        palette.
    dither: bool, optional
        If true, enable Floyd–Steinberg dithering when reducing colours.  This
        can help reduce banding but may increase the number of colours used.
    """

    if max_colours < 1 or max_colours > 112:
        raise ValueError("max_colours must be between 1 and 112")

    # Load and normalise the image
    src = Image.open(input_path).convert("RGBA")
    # Resize so that width and height are multiples of eight
    new_size = ensure_divisible_by_8(src.size)
    if new_size != src.size:
        # Use nearest neighbour to avoid introducing new colours
        src = src.resize(new_size, Image.NEAREST)

    # Prepare transparency by assigning an alpha channel when a specific colour
    # should be invisible.  We avoid external dependencies by using logical
    # operations on image bands.
    if transparent_colour is not None:
        r, g, b = transparent_colour
        # Split into RGB channels
        r_band, g_band, b_band, _ = src.split()
        # Create binary masks for each channel: 255 where the channel value
        # matches the transparent component, otherwise 0
        mask_r = r_band.point(lambda v: 255 if v == r else 0)
        mask_g = g_band.point(lambda v: 255 if v == g else 0)
        mask_b = b_band.point(lambda v: 255 if v == b else 0)
        # A pixel is transparent only if all three channels match
        trans_mask = ImageChops.logical_and(mask_r, ImageChops.logical_and(mask_g, mask_b))
        # Build an alpha layer: start opaque and paste zeros where the mask is 255
        alpha = Image.new("L", src.size, color=255)
        alpha.paste(0, mask=trans_mask)
        src.putalpha(alpha)

    # Quantise to an 8‑bit palette
    # Use median cut to minimise perceptual error; quantize returns a 'P' mode image
    quantized = src.convert("RGB").quantize(
        colors=max_colours, method=Image.MEDIANCUT, dither=Image.FLOYDSTEINBERG if dither else Image.NONE
    )

    # If we used transparency, we need to add a transparent palette entry and
    # set up the tRNS chunk accordingly.  Pillow can do this if we pass the
    # transparency index when saving.  To avoid losing colours, we add one
    # extra colour at the end of the palette.
    transparency_index: Optional[int] = None
    if transparent_colour is not None:
        # Append the transparent colour to the palette
        palette = quantized.getpalette()  # list of ints
        # Ensure palette has room for extra colour
        if len(palette) // 3 < 256:
            palette += list(transparent_colour)  # add RGB
            quantized.putpalette(palette)
            transparency_index = (len(palette) // 3) - 1
        else:
            # Palette full; use index 0 for transparency and shift colours down
            transparency_index = 0

    # Save to a bytes buffer so we can insert our custom chunk
    buffer = io.BytesIO()
    save_kwargs = {}
    if transparency_index is not None:
        save_kwargs["transparency"] = transparency_index
    quantized.save(buffer, format="PNG", **save_kwargs)
    png_data = buffer.getvalue()

    # If a template is provided, extract its w2lv/waLV chunk
    if template_path is not None and os.path.isfile(template_path):
        with open(template_path, "rb") as tfile:
            template_bytes = tfile.read()
        custom_chunk = find_custom_chunk(template_bytes, ["w2lv", "walv"])
        if custom_chunk:
            png_data = insert_chunk_before_iend(png_data, custom_chunk)

    # Write the final output
    with open(output_path, "wb") as outfile:
        outfile.write(png_data)
    print(f"Created W:A map: {output_path}")


def parse_colour(values: Iterable[str]) -> Tuple[int, int, int]:
    """Parse three integers into an RGB tuple, ensuring values are between 0 and 255."""
    try:
        r, g, b = [int(v) for v in values]
    except Exception:
        raise argparse.ArgumentTypeError("colour must be three integers")
    for v in (r, g, b):
        if v < 0 or v > 255:
            raise argparse.ArgumentTypeError("colour values must be between 0 and 255")
    return (r, g, b)


def main(argv: Optional[Iterable[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="Convert any normal image into a Worms Armageddon map (explained for beginners).",
        epilog=(
            """        This tool turns a regular picture into a playable Worms Armageddon colour map.

            

            HOW IT WORKS (simple explanation):

              • Worms Armageddon can only load special PNG files called colour maps.

              • These maps must use an 8‑bit palette (max 112 colours).

              • One colour can be marked as 'transparent' — this becomes empty space in‑game.

              • The game also stores map settings (like water height) inside a hidden PNG chunk.

            

            WHAT THIS SCRIPT DOES FOR YOU:

              • Takes any image and reshapes it to a legal W:A map size.

              • Reduces colours so the game can display it correctly.

              • Makes part of the image transparent (optional).

              • Copies map settings from an existing map if you want.

            

            BASIC USAGE EXAMPLES:

              Make a simple map:      python wa_map_maker.py input.png output.png

              Make a map with holes:  python wa_map_maker.py input.png output.png -c 0 0 0

              Copy settings (water, etc.) from another map:

                    python wa_map_maker.py input.png output.png --template my_map.png

            

            After saving, put your new PNG into the W:A folder:

                User/SavedLevels/   (or a subfolder).

            Then open W:A → Map Editor → choose your map from the list.
"""
        ),
    )
    parser.add_argument("input", help="input image file")
    parser.add_argument("output", help="output PNG file for W:A")
    parser.add_argument("-t", "--template", help="template W:A map to copy w2lv/waLV chunk from")
    parser.add_argument(
        "-m", "--maxcolours", type=int, default=112, help="maximum number of colours (1‑112, default: 112)"
    )
    parser.add_argument(
        "-c",
        "--transparent-colour",
        type=parse_colour,
        nargs=3,
        metavar=("R", "G", "B"),
        default=(0, 0, 0),
        help="colour to treat as transparent (default: 0 0 0)",
    )
    parser.add_argument("--no-transparency", action="store_true", help="do not add a transparent palette entry")
    parser.add_argument("--dither", action="store_true", help="enable dithering when reducing colours")
    args = parser.parse_args(argv)

    transparent_colour = None if args.no_transparency else args.transparent_colour
    convert_image(
        args.input,
        args.output,
        template_path=args.template,
        max_colours=args.maxcolours,
        transparent_colour=transparent_colour,
        dither=args.dither,
    )


if __name__ == "__main__":
    main()
