"""Save a map: .jpg -> RGB JPEG, 4:4:4 chroma, optimized, progressive (default quality 92); other extensions as-is."""
import os

JPEG_KW = dict(quality=92, subsampling=0, optimize=True, progressive=True)


def is_jpeg(path):
    return os.path.splitext(str(path))[1].lower() in (".jpg", ".jpeg")


def save_final(im, path, quality=None):
    if is_jpeg(path):
        if im.mode in ("RGBA", "LA", "P"):
            from PIL import Image
            im = im.convert("RGBA"); bg = Image.new("RGB", im.size, (0, 0, 0)); bg.paste(im, mask=im.getchannel("A")); im = bg
        im.convert("RGB").save(path, "JPEG", **(dict(JPEG_KW, quality=int(quality)) if quality else JPEG_KW))
    else:
        im.save(path)
    return path
