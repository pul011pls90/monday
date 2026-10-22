"""Uploaded pictures are shrunk before they are stored.

A phone photo of a solution is ~3 MB; at 1600 px on the long side and JPEG quality 78 it is ~150–300 KB and
still easy to read. Figures for questions stay PNG (sharp lines), only resized when huge. Avatars become small JPEGs.
Anything Pillow cannot open (e.g. HEIC without a plugin) is stored as it came.
"""
import os

from flask import current_app

LIMITS = {"photo": 1600, "figure": 1600, "avatar": 400}


def store_image(upload, stem, kind="photo"):
    """Save an uploaded image under UPLOAD_FOLDER as <stem>.<ext>; returns the stored relative name."""
    folder = current_app.config["UPLOAD_FOLDER"]
    ext = upload.filename.rsplit(".", 1)[-1].lower() if "." in (upload.filename or "") else "bin"
    try:
        from PIL import Image, ImageOps
        try:  # iPhone photos (HEIC) become ordinary JPEGs
            from pillow_heif import register_heif_opener
            register_heif_opener()
        except ImportError:
            pass
        img = Image.open(upload.stream)
        img = ImageOps.exif_transpose(img)  # phones store the rotation separately
        side = current_app.config.get("PHOTO_MAX_SIDE", 1600) if kind != "avatar" else LIMITS["avatar"]
        img.thumbnail((side, side))
        keep_png = kind == "figure" and (ext == "png" or img.mode in ("RGBA", "LA", "P"))
        name = f"{stem}.{'png' if keep_png else 'jpg'}"
        path = os.path.join(folder, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if keep_png:
            img.save(path, "PNG", optimize=True)
        else:
            if img.mode not in ("RGB", "L"):
                bg = Image.new("RGB", img.size, (255, 255, 255))  # transparent parts become white, not black
                bg.paste(img, mask=img.convert("RGBA").split()[-1])
                img = bg
            img.save(path, "JPEG", quality=current_app.config.get("PHOTO_QUALITY", 78), optimize=True, progressive=True)
        return name
    except Exception:  # not an image Pillow understands: keep the original file
        upload.stream.seek(0)
        name = f"{stem}.{ext}"
        path = os.path.join(folder, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        upload.save(path)
        return name
