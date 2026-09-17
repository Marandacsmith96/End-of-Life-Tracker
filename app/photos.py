"""Saving uploaded photos to the data folder.

Images are resized so a phone photo does not fill the disk, and re-encoded so
whatever the browser sent, what we store is a known-good JPEG or PNG.
"""
from pathlib import Path

from flask import current_app
from PIL import Image, UnidentifiedImageError

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
MAX_SIDE = 800  # pixels


class InvalidImage(ValueError):
    pass


def allowed_filename(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_animal_photo(file_storage, animal_id: int) -> str:
    """Resize and save an uploaded profile photo.

    Returns the path relative to PHOTO_DIR, which is what gets stored in the
    database and used to serve the image later.
    """
    if not file_storage or not file_storage.filename:
        raise InvalidImage("No file was chosen.")
    if not allowed_filename(file_storage.filename):
        raise InvalidImage("Please choose a JPG, PNG, or WebP image.")
    try:
        image = Image.open(file_storage.stream)
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise InvalidImage("That file does not look like an image.") from exc

    image.thumbnail((MAX_SIDE, MAX_SIDE))
    has_alpha = image.mode in ("RGBA", "LA") or "transparency" in image.info
    ext = "png" if has_alpha else "jpg"
    if not has_alpha:
        image = image.convert("RGB")

    relative = Path("animals") / f"{animal_id}.{ext}"
    target = Path(current_app.config["PHOTO_DIR"]) / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    # Remove a previous photo with the other extension, if any.
    for old in target.parent.glob(f"{animal_id}.*"):
        old.unlink()
    image.save(target, quality=85)
    return relative.as_posix()


def delete_animal_photo(relative_path: str | None) -> None:
    if not relative_path:
        return
    target = Path(current_app.config["PHOTO_DIR"]) / relative_path
    if target.is_file():
        target.unlink()
