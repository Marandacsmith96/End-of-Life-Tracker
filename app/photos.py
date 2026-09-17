"""Saving uploaded photos to the data folder.

Images are resized so a phone photo does not fill the disk, and re-encoded so
whatever the browser sent, what we store is a known-good JPEG or PNG.
"""
import uuid
from pathlib import Path

from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
MAX_SIDE = 800  # pixels


class InvalidImage(ValueError):
    pass


def allowed_filename(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _open_and_shrink(file_storage) -> Image.Image:
    if not file_storage or not file_storage.filename:
        raise InvalidImage("No file was chosen.")
    if not allowed_filename(file_storage.filename):
        raise InvalidImage("Please choose a JPG, PNG, or WebP image.")
    try:
        image = Image.open(file_storage.stream)
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise InvalidImage("That file does not look like an image.") from exc
    image = ImageOps.exif_transpose(image)  # respect phone rotation
    image.thumbnail((MAX_SIDE, MAX_SIDE))
    return image


def _save(image: Image.Image, relative_dir: Path, stem: str, replace_same_stem: bool) -> str:
    has_alpha = image.mode in ("RGBA", "LA") or "transparency" in image.info
    ext = "png" if has_alpha else "jpg"
    if not has_alpha:
        image = image.convert("RGB")
    relative = relative_dir / f"{stem}.{ext}"
    target = Path(current_app.config["PHOTO_DIR"]) / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if replace_same_stem:
        for old in target.parent.glob(f"{stem}.*"):
            old.unlink()
    image.save(target, quality=85)
    return relative.as_posix()


def save_animal_photo(file_storage, animal_id: int) -> str:
    """Resize and save a profile photo. Returns the path relative to PHOTO_DIR."""
    image = _open_and_shrink(file_storage)
    return _save(image, Path("animals"), str(animal_id), replace_same_stem=True)


def save_entry_photo(file_storage, entry_id: int) -> str:
    """Resize and save a photo attached to a daily entry. Returns the relative path."""
    image = _open_and_shrink(file_storage)
    return _save(image, Path("entries") / str(entry_id), uuid.uuid4().hex[:12], False)


def delete_photo_file(relative_path: str | None) -> None:
    if not relative_path:
        return
    target = Path(current_app.config["PHOTO_DIR"]) / relative_path
    if target.is_file():
        target.unlink()


# Kept for the animal routes' existing import name.
delete_animal_photo = delete_photo_file
