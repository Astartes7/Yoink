from io import BytesIO
from pathlib import Path
from threading import Lock, Thread
from urllib.request import Request, urlopen

import customtkinter as ctk

try:
    from PIL import Image, ImageDraw
except ImportError:  # Image support is optional at runtime.
    Image = None
    ImageDraw = None


ASSET_ROOT = Path(__file__).parents[1] / "assets"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def asset_path(*parts: str) -> Path:
    return ASSET_ROOT.joinpath(*parts)


def local_image(path: Path, size: tuple[int, int]) -> ctk.CTkImage | None:
    if Image is None:
        return None
    try:
        image = Image.open(path).convert("RGBA")
        return ctk.CTkImage(light_image=image, dark_image=image, size=size)
    except OSError:
        return None


def placeholder(
    size: tuple[int, int], surface: str, accent: str
) -> ctk.CTkImage | None:
    if Image is None:
        return None
    image = Image.new("RGB", size, surface)  # type: ignore[union-attr]
    draw = ImageDraw.Draw(image)  # type: ignore[union-attr]
    width, height = size
    draw.ellipse(
        (width * 0.28, height * 0.18, width * 0.72, height * 0.82), fill=accent
    )
    draw.ellipse(
        (width * 0.39, height * 0.12, width * 0.76, height * 0.72), fill=surface
    )
    return ctk.CTkImage(light_image=image, dark_image=image, size=size)


class ThumbnailCache:
    def __init__(self):
        self._images: dict[tuple[str, tuple[int, int]], ctk.CTkImage] = {}
        self._lock = Lock()

    def load(self, owner, url: str, size: tuple[int, int], fallback, callback) -> None:
        key = (url, size)
        with self._lock:
            cached = self._images.get(key)
        if cached:
            callback(cached)
            return
        if not url or Image is None:
            callback(fallback)
            return

        def worker():
            try:
                request = Request(url, headers={"User-Agent": "YOINK/1.1"})
                with urlopen(request, timeout=10) as response:
                    image = Image.open(BytesIO(response.read())).convert("RGB")  # type: ignore[union-attr]
                image.thumbnail(size)
                result = ctk.CTkImage(light_image=image, dark_image=image, size=size)
                with self._lock:
                    self._images[key] = result
            except (OSError, ValueError):
                result = fallback
            try:
                owner.after(0, lambda: callback(result))
            except RuntimeError:
                pass

        Thread(target=worker, daemon=True, name="yoink-thumbnail").start()
