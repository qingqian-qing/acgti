from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "public" / "images" / "characters"
THUMBS_DIR = SOURCE_DIR / "thumbs"
FULL_QUALITY = 85
THUMB_WIDTH = 400
THUMB_QUALITY = 80


def build_webp(source_path: Path, output_path: Path, max_width: int | None = None, quality: int = 85) -> None:
    with Image.open(source_path) as image:
        converted = image.convert("RGBA")
        if max_width and converted.width > max_width:
            ratio = max_width / converted.width
            new_size = (max_width, int(converted.height * ratio))
            converted = converted.resize(new_size, Image.Resampling.LANCZOS)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        converted.save(output_path, format="WEBP", quality=quality, method=6)


def main() -> None:
    png_files = sorted(path for path in SOURCE_DIR.glob("*.png") if path.is_file())
    if not png_files:
        raise FileNotFoundError(f"No PNG files found in {SOURCE_DIR}")

    THUMBS_DIR.mkdir(parents=True, exist_ok=True)

    for source_path in png_files:
        webp_name = f"{source_path.stem}.webp"

        # 全尺寸 WebP
        full_output = SOURCE_DIR / webp_name
        build_webp(source_path, full_output, quality=FULL_QUALITY)
        print(f"Full: {full_output.relative_to(ROOT)}")

        # 缩略图 WebP（400px 宽）
        thumb_output = THUMBS_DIR / webp_name
        build_webp(source_path, thumb_output, max_width=THUMB_WIDTH, quality=THUMB_QUALITY)
        print(f"Thumb: {thumb_output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
