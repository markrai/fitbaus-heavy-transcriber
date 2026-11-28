import io
import sys
import warnings

from PIL import Image, ImageFile, ImageOps, __version__


MAX_INPUT = 4 * 1024 * 1024
MAX_OUTPUT = 1024 * 1024
MAX_PIXELS = 8_000_000
MAX_EDGE = 8192
OUTPUT_SIZE = (1024, 600)
FORMATS = {"image/png": "PNG", "image/jpeg": "JPEG", "image/gif": "GIF", "image/webp": "WEBP"}


def normalize(raw, media_type):
    if __version__ != "13.0.0":
        raise RuntimeError("Unqualified Pillow version")
    if not 0 < len(raw) <= MAX_INPUT or media_type not in FORMATS:
        raise ValueError("Invalid raster input")
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    ImageFile.LOAD_TRUNCATED_IMAGES = False
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(raw), formats=[FORMATS[media_type]]) as source:
            width, height = source.size
            if (source.format != FORMATS[media_type] or not 0 < width <= MAX_EDGE
                    or not 0 < height <= MAX_EDGE or width * height > MAX_PIXELS
                    or getattr(source, "n_frames", 1) != 1):
                raise ValueError("Unsupported dimensions or animation")
            source.verify()
        with Image.open(io.BytesIO(raw), formats=[FORMATS[media_type]]) as source:
            source.load()
            oriented = ImageOps.exif_transpose(source)
            rgba = oriented.convert("RGBA")
            rgba.thumbnail(OUTPUT_SIZE, Image.Resampling.LANCZOS)
            clean = Image.frombytes("RGBA", rgba.size, rgba.tobytes())
            output = io.BytesIO()
            clean.save(output, format="PNG", compress_level=6)
            data = output.getvalue()
            if len(data) > MAX_OUTPUT:
                raise ValueError("Normalized image exceeds size limit")
            return data


def main():
    try:
        if len(sys.argv) != 2:
            return 2
        data = normalize(sys.stdin.buffer.read(MAX_INPUT + 1), sys.argv[1])
        sys.stdout.buffer.write(data)
        return 0
    except (ValueError, OSError, SyntaxError, Image.DecompressionBombError,
            Image.DecompressionBombWarning, OverflowError, EOFError):
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
