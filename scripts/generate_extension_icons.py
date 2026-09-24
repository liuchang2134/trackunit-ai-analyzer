"""Derive sharp Chrome icon sizes from the existing official XCMG wordmark.

The logo's first 106 square pixels contain the mark in white.  The existing
favicon exports were enlarged from a tiny raster; this uses the 106 px mark as
the common source and keeps its geometry and alpha edges intact.
"""

from pathlib import Path
import sys

from PIL import Image, ImageDraw


SOURCE = Path(sys.argv[1])
DEST = Path(sys.argv[2])
BLUE = (0, 71, 157)
SIZES = (16, 32, 48, 128)


def main() -> None:
    logo = Image.open(SOURCE).convert("RGBA")
    if logo.size != (500, 110):
        raise ValueError(f"unexpected XCMG source size: {logo.size}")
    source_mark = logo.crop((0, 0, 106, 106))
    # Keep the white openings opaque so the symbol also works in dark Chrome.
    mark = Image.new("RGBA", source_mark.size, (0, 0, 0, 0))
    ImageDraw.Draw(mark).rounded_rectangle((0, 0, 105, 105), radius=9, fill="white")
    blue_mark = Image.new("RGBA", source_mark.size, (*BLUE, 0))
    blue_mark.putalpha(source_mark.getchannel("A"))
    mark.alpha_composite(blue_mark)
    DEST.mkdir(parents=True, exist_ok=True)
    for size in SIZES:
        icon = mark.resize((size, size), Image.Resampling.LANCZOS)
        icon.save(DEST / f"icon{size}.png", optimize=True)
        print(size, (DEST / f"icon{size}.png").stat().st_size)


if __name__ == "__main__":
    main()
