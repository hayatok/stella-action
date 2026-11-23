#!/usr/bin/env python3
"""Stella v4 texture generation.

Sources: if Codex imagegen sheets exist at assets/textures/raw_skin_sheet.png
and raw_clothes_sheet.png they are sampled ONLY for soft color variation
(low-frequency tint) and blended under the procedural detail work.
Everything structural (blush placement, hair gradient/band, atlas seams)
is procedural so placement is exact. Run with system python3 (PIL+numpy).
"""
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.expanduser("~/workspace/stella-action")
TEX = os.path.join(ROOT, "assets", "textures")
os.makedirs(TEX, exist_ok=True)
rng = np.random.default_rng(7)


def save(arr, name):
    Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).save(os.path.join(TEX, name))
    print(name, arr.shape)


def gauss_blob(shape, cx, cy, sx, sy, amp):
    h, w = shape
    y, x = np.mgrid[0:h, 0:w]
    g = np.exp(-(((x - cx) / sx) ** 2 + ((y - cy) / sy) ** 2))
    return g * amp


def lowfreq_tint(path, strength=0.10):
    """Return an HxWx3 low-frequency tint multiplier from an imagegen sheet."""
    if not os.path.exists(path):
        return None
    im = Image.open(path).convert("RGB").resize((64, 64), Image.BILINEAR)
    a = np.asarray(im).astype(np.float32)
    mean = a.reshape(-1, 3).mean(axis=0)
    tint = (a / np.maximum(mean, 1.0) - 1.0) * strength + 1.0
    return tint  # 64x64x3


def apply_tint(arr, tint):
    if tint is None:
        return arr
    h, w, _ = arr.shape
    t = np.asarray(Image.fromarray(((tint) * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC)).astype(np.float32) / 255.0
    # tint stored as multiplier around 1.0 -> rescale
    mult = (t - 0.5) * 2 * 0.10 + 1.0
    return arr * mult


# ---------------------------------------------------------------- skin 1024
# UV space: Face planar projection u = x/(2*rx)+0.5, v = z/(2*rz)+0.5
# (v measured from bottom in UV; image row = (1-v)*H).
S = 512  # dropped from 1024: merged GLB replicates textures x4, size budget
skin = np.zeros((S, S, 3), np.float32)
base = np.array([255, 206, 164], np.float32)  # soft peach (sRGB)
for c in range(3):
    skin[:, :, c] = base[c]
# gentle centre-front lightening
skin += gauss_blob((S, S), S * 0.5, S * 0.52, S * 0.30, S * 0.34, 10.0)[:, :, None]
# under-chin / lower-face tone (v < 0.22 -> rows > 0.78*S)
yy = np.linspace(0, 1, S)[:, None, None]
chin = np.clip((yy - 0.74) / 0.26, 0, 1) ** 2 * np.array([-16, -22, -18])
skin += chin
# subtle shading above the eyelid area: eyes at u .32/.68, v .45 (row .55)
for ex in (0.32, 0.68):
    skin += gauss_blob((S, S), S * ex, S * 0.545, S * 0.075, S * 0.030, -13.0)[:, :, None] * np.array([1.0, 0.8, 0.7])
    # brow-area warmth slightly above
    skin += gauss_blob((S, S), S * ex, S * 0.50, S * 0.08, S * 0.02, 6.0)[:, :, None]
# cheek blush: geometry blush centres at u .205/.795, v .30 (row .70)
blush_col = np.array([255, 138, 128], np.float32)
for bx in (0.205, 0.795):
    g = gauss_blob((S, S), S * bx, S * 0.70, S * 0.085, S * 0.052, 1.0)
    skin = skin * (1 - g[:, :, None] * 0.45) + blush_col * (g[:, :, None] * 0.45)
    g2 = gauss_blob((S, S), S * bx, S * 0.70, S * 0.045, S * 0.028, 1.0)
    skin = skin * (1 - g2[:, :, None] * 0.25) + blush_col * (g2[:, :, None] * 0.25)
# nose-bridge soft shade + philtrum warmth (very subtle)
skin += gauss_blob((S, S), S * 0.5, S * 0.60, S * 0.012, S * 0.05, -6.0)[:, :, None]
skin = apply_tint(skin, lowfreq_tint(os.path.join(TEX, "raw_skin_sheet.png")))
save(skin, "skin.png")

# ---------------------------------------------------------------- iris 256
I = 256
iris = np.zeros((I, I, 3), np.float32)
vv = np.linspace(0, 1, I)[:, None]  # image top = v=1 (top of eye)
# vertical gradient: dark teal top -> bright teal -> pale aqua bottom
top = np.array([6, 62, 66], np.float32)
mid = np.array([16, 168, 160], np.float32)
bot = np.array([140, 235, 220], np.float32)
t1 = np.clip(vv / 0.55, 0, 1)
t2 = np.clip((vv - 0.55) / 0.45, 0, 1)
grad = top[None, None, :] * (1 - t1[:, :, None]) + mid[None, None, :] * t1[:, :, None]
grad = grad * (1 - t2[:, :, None]) + bot[None, None, :] * t2[:, :, None]
iris[:] = grad
# radial streaks
xx = np.linspace(0, 1, I)[None, :]
streak = (np.sin(xx * np.pi * 36) * 0.5 + 0.5) * 10 - 5
iris += streak[:, :, None] * np.array([0.4, 1.0, 0.95])
# highlight dots at both candidate front-u positions (0.25 / 0.75), v~0.68
for hx in (0.25, 0.75):
    g = gauss_blob((I, I), I * hx, I * 0.32, I * 0.055, I * 0.075, 1.0)
    iris = iris * (1 - g[:, :, None] * 0.9) + 255.0 * (g[:, :, None] * 0.9)
    g = gauss_blob((I, I), I * (hx + 0.05), I * 0.52, I * 0.03, I * 0.04, 1.0)
    iris = iris * (1 - g[:, :, None] * 0.55) + 255.0 * (g[:, :, None] * 0.55)
save(iris, "iris.png")

# ---------------------------------------------------------------- hair 512
def hair_texture(dark=False):
    H = 512
    img = np.zeros((H, H, 3), np.float32)
    # v: 0 root (image bottom) -> 1 tip (image top)
    v = np.linspace(1, 0, H)[:, None]  # row0 = top = v=1
    root = np.array([7, 96, 94], np.float32)
    midc = np.array([13, 138, 132], np.float32)
    tip = np.array([38, 178, 168], np.float32)
    if dark:
        root *= 0.62; midc *= 0.62; tip *= 0.62
    a = np.clip(v / 0.6, 0, 1); b = np.clip((v - 0.6) / 0.4, 0, 1)
    col = root[None, None, :] * (1 - a[:, :, None]) + midc[None, None, :] * a[:, :, None]
    col = col * (1 - b[:, :, None]) + tip[None, None, :] * b[:, :, None]
    img[:] = col
    # fine strand streaks along V (vertical in image)
    x = np.linspace(0, 1, H)[None, :]
    streak = np.sin(x * np.pi * 90 + np.sin(x * 40) * 2.0) * 6
    img += streak[:, :, None] * np.array([0.3, 1.0, 0.95])
    # highlight band: fixed V range 0.30..0.50, decays around U (front u=0.5)
    band_v = np.exp(-(((v - 0.40) / 0.085) ** 2))          # Hx1
    du = np.minimum(np.abs(x - 0.5), 1 - np.abs(x - 0.5))  # 1xH wrap distance
    band_u = np.exp(-((du / 0.17) ** 2))
    band = band_v * band_u                                  # HxH
    shine = np.array([150, 240, 228], np.float32) * (0.85 if not dark else 0.6)
    img = img * (1 - band[:, :, None] * 0.55) + shine[None, None, :] * (band[:, :, None] * 0.55)
    return img

save(hair_texture(False), "hair.png")
save(hair_texture(True), "hair_dark.png")

# ---------------------------------------------------------------- clothes atlas 1024
# 4x4 tiles of 256. Tile (col,row) with row measured from BOTTOM in UV.
TILES = {
    "Cream":  (0, 3, (250, 243, 230)),
    "Teal":   (1, 3, (22, 138, 134)),
    "TealDk": (2, 3, (24, 102, 102)),
    "Orange": (3, 3, (238, 164, 54)),
    "Dark":   (0, 2, (74, 79, 94)),
    "Bag":    (1, 2, (30, 96, 96)),
    "Glove":  (2, 2, (98, 98, 110)),
    "Sock":   (3, 2, (82, 87, 106)),
}
A = 1024; TS = 256
atlas = np.zeros((A, A, 3), np.float32)
atlas[:] = np.array([40, 40, 44], np.float32)  # unused tiles: neutral dark
clothes_tint = lowfreq_tint(os.path.join(TEX, "raw_clothes_sheet.png"), 0.06)
for name, (col, row, color) in TILES.items():
    r0 = A - (row + 1) * TS  # image row of tile top
    tile = np.zeros((TS, TS, 3), np.float32)
    tile[:] = np.array(color, np.float32)
    # soft panel shading: lighter upper-left, contact shade at bottom
    gx = np.linspace(0, 1, TS)[None, :, None]; gy = np.linspace(0, 1, TS)[:, None, None]
    tile += (gx * 6 - 3) + ((1 - gy) * 10 - 5)
    tile += np.clip((gy - 0.80) / 0.20, 0, 1) ** 2 * -22   # hem contact shading
    tile += np.clip((0.10 - gy) / 0.10, 0, 1) * 8          # top edge light
    tile += rng.normal(0, 1.0, tile.shape)                  # fabric grain
    tile = np.asarray(Image.fromarray(np.clip(tile, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.1))).astype(np.float32)
    atlas[r0:r0 + TS, col * TS:(col + 1) * TS] = tile
    # seams / trim drawn crisp on top
    ov = Image.fromarray(np.clip(atlas, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(ov, "RGBA")
    x0, y0 = col * TS, r0
    dark_line = (0, 0, 0, 90); light_line = (255, 255, 255, 70)
    # inset seam rectangle (trim near edges)
    d.rectangle([x0 + 14, y0 + 14, x0 + TS - 15, y0 + TS - 15], outline=dark_line, width=3)
    d.rectangle([x0 + 20, y0 + 20, x0 + TS - 21, y0 + TS - 21], outline=light_line, width=1)
    # stitch dashes along the seam
    for t in range(28, TS - 28, 18):
        d.line([x0 + t, y0 + 17, x0 + t + 9, y0 + 17], fill=(255, 255, 255, 110), width=2)
        d.line([x0 + t, y0 + TS - 18, x0 + t + 9, y0 + TS - 18], fill=(255, 255, 255, 110), width=2)
    # vertical panel seam
    d.line([x0 + TS // 2, y0 + 22, x0 + TS // 2, y0 + TS - 22], fill=dark_line, width=2)
    atlas = np.asarray(ov).astype(np.float32)
atlas = apply_tint(atlas, clothes_tint)
save(atlas, "clothes_atlas.png")
with open(os.path.join(TEX, "atlas_tiles.json"), "w") as fh:
    import json
    json.dump({k: [v[0], v[1]] for k, v in TILES.items()}, fh, indent=1)
print("TEXTURES DONE")
