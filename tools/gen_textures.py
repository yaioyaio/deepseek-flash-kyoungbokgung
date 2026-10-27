#!/usr/bin/env python3
"""Procedural texture generator for the Gyeongbokgung 3D scene.

Outputs seamless albedo / normal maps used by the Blender model, plus a few
assets consumed directly by the web viewer. Everything is generated locally so
the project has no external texture dependencies.
"""

from __future__ import annotations

import math
import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "blender" / "textures"
PUBLIC = ROOT / "public" / "textures"
OUT.mkdir(parents=True, exist_ok=True)
PUBLIC.mkdir(parents=True, exist_ok=True)

S = 512


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def fft_noise(size: int, beta: float = 2.0, seed: int = 0) -> np.ndarray:
    """Periodic (tileable) fractal noise via FFT filtering, values ~0..1."""
    rng = np.random.default_rng(seed)
    white = rng.normal(size=(size, size))
    fy = np.fft.fftfreq(size)[:, None]
    fx = np.fft.fftfreq(size)[None, :]
    radius = np.sqrt(fx * fx + fy * fy)
    radius[0, 0] = 1.0
    filt = 1.0 / (radius**beta)
    filt[0, 0] = 0
    out = np.real(np.fft.ifft2(np.fft.fft2(white) * filt))
    out -= out.min()
    out /= max(out.max(), 1e-9)
    return out


def fbm(size: int, seed: int = 1, octaves=(0.12, 0.3, 0.8), weights=(0.6, 0.3, 0.15)) -> np.ndarray:
    acc = np.zeros((size, size), dtype=np.float64)
    for i, (beta, w) in enumerate(zip(octaves, weights)):
        acc += fft_noise(size, beta, seed + i * 11) * w
    acc -= acc.min()
    acc /= max(acc.max(), 1e-9)
    return acc


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a + 1e-9), 0, 1)
    return t * t * (3 - 2 * t)


def normal_from_height(height: np.ndarray, strength: float = 2.0) -> np.ndarray:
    """Convert a tileable height field to a tangent space normal map."""
    dx = (np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1)) * 0.5
    dy = (np.roll(height, -1, axis=0) - np.roll(height, 1, axis=0)) * 0.5
    nx = np.clip(-dx * strength * S, -0.62, 0.62)
    ny = np.clip(-dy * strength * S, -0.62, 0.62)
    nz = np.ones_like(height)
    ln = np.sqrt(nx * nx + ny * ny + nz * nz)
    n = np.stack([nx / ln, ny / ln, nz / ln], axis=-1)
    return ((n * 0.5 + 0.5) * 255).astype(np.uint8)


def save_rgb(path: Path, arr: np.ndarray, quality: int = 92):
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    Image.fromarray(arr, "RGB").save(path, quality=quality, subsampling=1)
    print("  wrote", path.relative_to(ROOT), arr.shape)


def tint(src: str, dst: str, mul, quality: int = 92):
    """Write a pre-tinted copy of an existing albedo (glTF has no tint node)."""
    im = np.asarray(Image.open(OUT / src).convert("RGB")).astype(np.float64)
    im *= np.array(mul, dtype=np.float64)
    save_rgb(OUT / dst, im, quality)


def save_normal(path: Path, arr: np.ndarray):
    Image.fromarray(arr, "RGB").save(path, quality=95, subsampling=0)
    print("  wrote", path.relative_to(ROOT), arr.shape)


def colorize(shade: np.ndarray, stops) -> np.ndarray:
    """Map a 0..1 shade field through (position, rgb) stops."""
    shade = np.clip(shade, 0, 1)
    out = np.zeros(shade.shape + (3,), dtype=np.float64)
    for i in range(len(stops) - 1):
        p0, c0 = stops[i]
        p1, c1 = stops[i + 1]
        t = smoothstep(p0, p1, shade)
        for ch in range(3):
            out[..., ch] = out[..., ch] * (1 - t) + c1[ch] * t
    return out


# --------------------------------------------------------------------------
# roof tiles (기와)
# --------------------------------------------------------------------------
def gen_roof():
    print("roof tiles")
    y, x = np.mgrid[0:S, 0:S]
    u = x / S
    v = y / S

    cols = 8          # convex tile runs per texture tile
    rows = 4          # overlapping tile courses

    # convex cylindrical tiles (수키와) with rounded valleys
    cu = (u * cols) % 1.0
    hump = (0.5 + 0.5 * np.cos(cu * 2 * np.pi)) ** 0.55

    # pan tiles (암키와) sit lower, visible in the valleys
    rv = (v * rows) % 1.0
    course = smoothstep(0.0, 0.055, rv) * 0.18 + 0.82
    course *= 1.0 - 0.10 * (1 - smoothstep(0.0, 0.09, rv))

    # fine surface breakdown + weather streaks running down the slope
    grain = fbm(S, 4, (0.35, 0.9, 2.4), (0.55, 0.3, 0.15))
    streak = fft_noise(S, 0.6, 9)
    height = hump * 0.62 + course * 0.28 + grain * 0.07 + streak * 0.03

    base = colorize(hump, [
        (0.00, (26, 30, 34)),
        (0.32, (37, 43, 48)),
        (0.70, (54, 61, 67)),
        (1.00, (72, 79, 86)),
    ])
    tone = (grain - 0.5) * 14 + (streak - 0.5) * 8
    # glazed sheen along tile crowns
    tone += (hump**3) * 8
    # darker gaps between courses
    tone -= (1 - smoothstep(0.0, 0.10, rv)) * 16
    # random weathering patches
    patch = fbm(S, 21, (0.18, 0.5), (0.7, 0.3))
    tone -= smoothstep(0.55, 0.85, patch) * 14
    base = base + tone[..., None]

    save_rgb(OUT / "roof_tile.jpg", base)
    save_normal(OUT / "roof_tile_normal.jpg", normal_from_height(height, 0.9))


# --------------------------------------------------------------------------
# granite (화강암)
# --------------------------------------------------------------------------
def gen_granite():
    print("granite")
    speck = fft_noise(S, 0.15, 31)
    coarse = fbm(S, 32, (0.35, 0.9), (0.6, 0.4))
    stain = fbm(S, 44, (0.18, 0.45), (0.7, 0.3))

    # sharp mineral speckles
    rng = np.random.default_rng(5)
    dots = np.zeros((S, S))
    ys = rng.integers(0, S, 9000)
    xs = rng.integers(0, S, 9000)
    vals = rng.uniform(-1, 1, 9000)
    np.add.at(dots, (ys, xs), vals)
    dots = np.clip(dots * 90, -55, 55)

    shade = 0.55 + (coarse - 0.5) * 0.28 + (speck - 0.5) * 0.16 + dots / 255 * 0.35
    shade -= smoothstep(0.6, 0.9, stain) * 0.10

    base = colorize(np.clip(shade, 0, 1), [
        (0.10, (96, 92, 84)),
        (0.45, (154, 149, 138)),
        (0.70, (182, 176, 164)),
        (0.92, (204, 198, 187)),
    ])
    save_rgb(OUT / "granite.jpg", base)

    height = coarse * 0.45 + speck * 0.35 + dots / 255 * 0.2
    save_normal(OUT / "granite_normal.jpg", normal_from_height(height, 0.55))


# --------------------------------------------------------------------------
# ashlar granite blocks (장대석) for platforms, walls and bridges
# --------------------------------------------------------------------------
def gen_granite_block():
    print("granite blocks")
    y, x = np.mgrid[0:S, 0:S]
    cols, rows = 2, 4
    cw, ch = S / cols, S / rows

    row = (y // ch).astype(int)
    xoff = (row % 2) * (cw * 0.5)
    col = ((x + xoff) // cw).astype(int)
    lx = ((x + xoff) % cw) / cw
    ly = (y % ch) / ch

    rng = np.random.default_rng(17)
    tone_lut = rng.uniform(-1.0, 1.0, (rows, cols))
    # blend a parallel copy so the tile stays seamless when it wraps
    tone = tone_lut[row % rows, col % cols]

    # recessed joints between blocks
    edge = np.minimum(np.minimum(lx, 1 - lx) * cw, np.minimum(ly, 1 - ly) * ch)
    bump = (fbm(S, 91, (0.28, 0.75), (0.65, 0.35)) - 0.5) * 3.2
    joint = 1.0 - smoothstep(1.2, 3.4, edge + bump)
    chamfer = 1.0 - smoothstep(3.0, 6.5, edge + bump)
    # bedding mortar sits slightly proud inside the joint
    mortar = joint * (0.55 + 0.45 * smoothstep(0.25, 0.75, fbm(S, 92, (0.5, 1.3), (0.6, 0.4))))

    stone = fbm(S, 93, (0.45, 1.2), (0.6, 0.4))
    fine = fft_noise(S, 0.16, 94)
    speck = fft_noise(S, 0.10, 95)

    shade = 0.60 + tone * 0.075 + (stone - 0.5) * 0.13 + (fine - 0.5) * 0.06
    shade += (speck - 0.5) * 0.10
    shade -= chamfer * 0.06
    shade = shade * (1 - joint) + (0.33 + mortar * 0.12) * joint

    base = colorize(np.clip(shade, 0, 1), [
        (0.06, (76, 75, 70)),
        (0.32, (112, 110, 103)),
        (0.58, (137, 133, 125)),
        (0.82, (158, 153, 143)),
    ])
    # warm lichen / damp staining in the lower half of the tile
    stain = smoothstep(0.55, 0.9, fbm(S, 96, (0.22, 0.55), (0.7, 0.3)))
    base[..., 0] -= stain * 10
    base[..., 1] -= stain * 4
    base[..., 2] -= stain * 12

    save_rgb(OUT / "granite_block.jpg", base)

    height = (1 - joint) * 0.62 + (1 - chamfer) * 0.10 + stone * 0.18 + fine * 0.10
    save_normal(OUT / "granite_block_normal.jpg", normal_from_height(height, 2.2))


# --------------------------------------------------------------------------
# paving (박석)
# --------------------------------------------------------------------------
def gen_paving():
    print("paving")
    y, x = np.mgrid[0:S, 0:S]
    cells = 3
    cw = S / cells
    row = (y // cw).astype(int)
    xoff = (row % 2) * (cw * 0.5)
    col = ((x + xoff) // cw).astype(int)
    lx = ((x + xoff) % cw) / cw
    ly = (y % cw) / cw

    rng = np.random.default_rng(12)
    tone_lut = rng.uniform(-1, 1, (cells, cells))
    tone = tone_lut[row % cells, col % cells]

    joint_w = 0.018
    edge = np.minimum(np.minimum(lx, 1 - lx), np.minimum(ly, 1 - ly))
    joint = 1 - smoothstep(joint_w, joint_w * 2.6, edge)

    # slightly irregular, chipped joints
    irregular = (fbm(S, 71, (0.25, 0.7), (0.7, 0.3)) - 0.5) * 0.02
    joint = 1 - smoothstep(joint_w, joint_w * 3.0, edge + irregular)

    stone = fbm(S, 72, (0.4, 1.1), (0.65, 0.35))
    fine = fft_noise(S, 0.2, 73)

    shade = 0.63 + tone * 0.055 + (stone - 0.5) * 0.16 + (fine - 0.5) * 0.05 - joint * 0.34
    base = colorize(np.clip(shade, 0, 1), [
        (0.08, (58, 57, 53)),
        (0.35, (101, 98, 91)),
        (0.60, (132, 128, 119)),
        (0.85, (156, 151, 141)),
    ])
    # faint moss between stones
    moss = smoothstep(0.55, 1.0, fbm(S, 74, (0.2, 0.5), (0.7, 0.3))) * joint
    base[..., 1] += moss * 16

    save_rgb(OUT / "paving.jpg", base)
    height = (1 - joint) * 0.7 + stone * 0.3
    save_normal(OUT / "paving_normal.jpg", normal_from_height(height, 0.9))


# --------------------------------------------------------------------------
# wood
# --------------------------------------------------------------------------
def gen_wood(name, dark, light, seed=0, rings=14.0):
    print("wood", name)
    y, x = np.mgrid[0:S, 0:S]
    u = x / S
    v = y / S

    warp = fft_noise(S, 1.0, seed) - 0.5
    grain = np.sin((u * rings * 2 * np.pi) + warp * 5.0) * 0.5 + 0.5
    fine = fft_noise(S, 0.15, seed + 2)
    patch = fbm(S, seed + 3, (0.25, 0.7), (0.7, 0.3))

    shade = grain * 0.55 + fine * 0.25 + patch * 0.2
    base = colorize(shade, [
        (0.0, dark),
        (0.5, tuple(int((dark[i] + light[i]) / 2) for i in range(3))),
        (1.0, light),
    ])
    # vertical streaks along the length of the member
    streak = fft_noise(S, 0.55, seed + 7)
    base = base + (streak[..., None] - 0.5) * 18
    save_rgb(OUT / f"{name}.jpg", base)


# --------------------------------------------------------------------------
# plaster / hanji walls
# --------------------------------------------------------------------------
def gen_plaster():
    print("plaster")
    noise = fbm(S, 91, (0.3, 0.8, 2.0), (0.55, 0.3, 0.15))
    stain = fbm(S, 92, (0.12, 0.4), (0.7, 0.3))
    shade = 0.78 + (noise - 0.5) * 0.14 - smoothstep(0.58, 0.92, stain) * 0.12
    base = colorize(np.clip(shade, 0, 1), [
        (0.3, (186, 178, 160)),
        (0.7, (218, 210, 193)),
        (1.0, (237, 231, 217)),
    ])
    save_rgb(OUT / "plaster.jpg", base)
    save_normal(OUT / "plaster_normal.jpg", normal_from_height(noise, 0.28))


# --------------------------------------------------------------------------
# lattice doors (창호)
# --------------------------------------------------------------------------
def gen_lattice():
    print("lattice")
    size = 512
    paper = np.zeros((size, size, 3), dtype=np.float64)
    base = fbm(size, 101, (0.25, 0.8, 2.2), (0.6, 0.28, 0.12))
    paper[..., 0] = 226 + (base - 0.5) * 22
    paper[..., 1] = 214 + (base - 0.5) * 20
    paper[..., 2] = 184 + (base - 0.5) * 18
    img = Image.fromarray(np.clip(paper, 0, 255).astype(np.uint8))
    draw = ImageDraw.Draw(img)

    # fine hanji fibres
    rng = np.random.default_rng(103)
    for _ in range(300):
        x0, y0 = rng.uniform(0, size, 2)
        ln = rng.uniform(8, 40)
        ang = rng.uniform(0, math.pi)
        draw.line(
            [(x0, y0), (x0 + math.cos(ang) * ln, y0 + math.sin(ang) * ln)],
            fill=(206, 196, 172, 255),
            width=1,
        )

    # wood lattice: 6 x 8 panes with an outer frame
    wood = (78, 44, 30)
    frame = 30
    draw.rectangle([0, 0, size - 1, size - 1], outline=wood, width=frame)
    cols, rows = 6, 8
    inner = size - frame * 2
    bar = 8
    for i in range(1, cols):
        x = frame + inner * i / cols
        draw.rectangle([x - bar / 2, frame, x + bar / 2, size - frame], fill=wood)
    for j in range(1, rows):
        y = frame + inner * j / rows
        draw.rectangle([frame, y - bar / 2, size - frame, y + bar / 2], fill=wood)
    # subtle shading on bars
    shadow = img.filter(ImageFilter.GaussianBlur(2))
    img = Image.blend(img, shadow, 0.18)
    img.save(OUT / "lattice.jpg", quality=92)
    print("  wrote", (OUT / "lattice.jpg").relative_to(ROOT))

    # emissive mask: warm paper glows through the lattice at night
    arr = np.asarray(img).astype(np.float64)
    lum = arr.mean(axis=2)
    mask = np.clip((lum - 70) / 120, 0, 1)
    em = np.stack([mask * 255 * 1.0, mask * 240 * 1.0, mask * 200 * 1.0], axis=-1)
    Image.fromarray(em.astype(np.uint8)).save(OUT / "lattice_emissive.jpg", quality=90)
    print("  wrote", (OUT / "lattice_emissive.jpg").relative_to(ROOT))


# --------------------------------------------------------------------------
# ground
# --------------------------------------------------------------------------
def gen_ground():
    print("ground")
    coarse = fbm(S, 121, (0.3, 0.8), (0.65, 0.35))
    fine = fft_noise(S, 0.12, 122)
    patch = fbm(S, 123, (0.12, 0.35), (0.7, 0.3))
    dry = smoothstep(0.48, 0.8, patch)

    shade = coarse * 0.65 + fine * 0.35
    base = colorize(shade, [
        (0.1, (54, 58, 40)),
        (0.45, (77, 82, 55)),
        (0.7, (101, 101, 68)),
        (0.95, (126, 118, 82)),
    ])
    base = base * (1 - dry[..., None] * 0.22) + dry[..., None] * np.array([132, 112, 79]) * 0.22
    # scattered pale grit
    rng = np.random.default_rng(124)
    grit = np.zeros((S, S))
    for _ in range(4500):
        px, py = rng.integers(0, S, 2)
        grit[py, px] = rng.uniform(0.4, 1.0)
    grit = np.array(Image.fromarray((grit * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.6))) / 255
    base = base + grit[..., None] * 16
    save_rgb(OUT / "ground.jpg", base)
    save_normal(OUT / "ground_normal.jpg", normal_from_height(coarse * 0.6 + fine * 0.4, 0.5))


# --------------------------------------------------------------------------
# water normal (used in three.js)
# --------------------------------------------------------------------------
def gen_water():
    print("water")
    y, x = np.mgrid[0:S, 0:S]
    u = x / S * 2 * np.pi
    v = y / S * 2 * np.pi
    h = (
        np.sin(u * 3 + v * 1.5) * 0.28
        + np.sin(u * 1.5 - v * 4) * 0.22
        + np.sin((u + v) * 7) * 0.10
        + (fft_noise(S, 0.4, 141) - 0.5) * 0.5
    )
    save_normal(PUBLIC / "water_normal.jpg", normal_from_height(h, 0.25))


# --------------------------------------------------------------------------
# signboards (현판)
# --------------------------------------------------------------------------
SIGNS = {
    "gwanghwamun": "光化門",
    "heungnyemun": "興禮門",
    "geunjeongmun": "勤政門",
    "geunjeongjeon": "勤政殿",
    "sajeongjeon": "思政殿",
    "gangnyeongjeon": "康寧殿",
    "gyotaejeon": "交泰殿",
    "gyeonghoeru": "慶會樓",
    "hyangwonjeong": "香遠亭",
    "jagyeongjeon": "慈慶殿",
    "sujeongjeon": "修政殿",
}


def gen_signs():
    print("signboards")
    font_path = "/System/Library/Fonts/Supplemental/AppleMyungjo.ttf"
    W, H = 1024, 256
    try:
        font = ImageFont.truetype(font_path, 118)
    except OSError:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/AppleGothic.ttf", 112)

    out_dir = OUT / "signs"
    out_dir.mkdir(exist_ok=True)
    for key, text in SIGNS.items():
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, W - 1, H - 1], fill=(22, 20, 18, 255))
        # gold double border
        d.rectangle([10, 10, W - 11, H - 11], outline=(176, 142, 82, 255), width=5)
        d.rectangle([24, 24, W - 25, H - 25], outline=(120, 94, 52, 255), width=2)
        # subtle lacquer sheen
        sheen = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        sd = ImageDraw.Draw(sheen)
        sd.ellipse([-W * 0.2, -H * 0.9, W * 0.9, H * 0.7], fill=(255, 240, 210, 16))
        img = Image.alpha_composite(img, sheen.filter(ImageFilter.GaussianBlur(18)))
        d = ImageDraw.Draw(img)

        # letters with a soft engraved shadow
        tracker = 34
        widths = [d.textlength(ch, font=font) for ch in text]
        total = sum(widths) + tracker * (len(text) - 1)
        x = (W - total) / 2
        for ch, cw in zip(text, widths):
            d.text((x + 3, 64 + 4), ch, font=font, fill=(0, 0, 0, 170))
            d.text((x, 62), ch, font=font, fill=(206, 170, 96, 255))
            d.text((x, 60), ch, font=font, fill=(232, 199, 128, 255))
            x += cw + tracker
        img.save(out_dir / f"{key}.png")
    print(f"  wrote {len(SIGNS)} signboards")


def gen_dancheong():
    """A repeating painted-beam strip (단청) used on lintels."""
    print("dancheong")
    W, H = 1024, 160
    base = np.zeros((H, W, 3))
    noise = np.array(Image.fromarray((fbm(128, 151, (0.4, 1.2), (0.7, 0.3)) * 255).astype(np.uint8)).resize((W, H))) / 255.0
    base[..., 0] = 26 + noise * 10
    base[..., 1] = 66 + noise * 14
    base[..., 2] = 54 + noise * 12
    img = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(img)

    cream = (222, 206, 172)
    red = (150, 46, 34)
    blue = (42, 78, 104)
    gold = (190, 152, 82)

    for k in range(8):
        x = k * 128
        d.rectangle([x, 0, x + 3, H], fill=(18, 38, 32))
        # top and bottom painted bands
        d.rectangle([x + 8, 6, x + 120, 16], fill=cream)
        d.rectangle([x + 8, H - 16, x + 120, H - 6], fill=cream)
        # lotus petal arc
        d.arc([x + 22, 18, x + 106, 132], 200, 340, fill=red, width=7)
        d.arc([x + 34, 30, x + 94, 120], 200, 340, fill=cream, width=5)
        d.arc([x + 46, 44, x + 82, 108], 200, 340, fill=blue, width=4)
        # central medallion
        cx, cy = x + 64, 80
        d.ellipse([cx - 13, cy - 13, cx + 13, cy + 13], outline=gold, width=4)
        d.ellipse([cx - 5, cy - 5, cx + 5, cy + 5], fill=red)
        # corner scrolls
        for sx in (0, 1):
            bx = x + 10 + sx * 100
            d.arc([bx, 26, bx + 18, 44], 90, 270, fill=cream, width=3)
            d.arc([bx, 116, bx + 18, 134], 90, 270, fill=cream, width=3)
    img = img.filter(ImageFilter.GaussianBlur(0.4))
    img.save(OUT / "dancheong_strip.jpg", quality=92)
    print("  wrote dancheong_strip.jpg")


def gen_screen():
    """Stylised Irworobongdo (일월오봉도) folding screen behind the throne."""
    print("throne screen")
    W, H = 1536, 768
    rng = np.random.default_rng(161)
    img = Image.new("RGB", (W, H), (196, 168, 112))
    px = img.load()
    for y in range(H):
        for x in range(W):
            n = rng.integers(-4, 5)
            r, g, b = 196 + n, 168 + n, 112 + n
            px[x, y] = (max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)))
    d = ImageDraw.Draw(img, "RGBA")
    # water at the bottom
    d.rectangle([0, int(H * 0.76), W, H], fill=(38, 74, 86, 255))
    for i in range(26):
        yy = int(H * 0.77) + i * 9
        d.line([(0, yy), (W, yy + rng.integers(-3, 4))], fill=(70, 112, 122, 150), width=2)
    # five peaks
    peaks = [(0.12, 0.68), (0.30, 0.48), (0.5, 0.33), (0.70, 0.47), (0.88, 0.66)]
    for i, (fx, fy) in enumerate(peaks):
        cx = int(W * fx)
        top = int(H * fy)
        half = int(W * (0.13 if i == 2 else 0.10))
        d.polygon([(cx - half, int(H * 0.78)), (cx, top), (cx + half, int(H * 0.78))],
                  fill=(44, 82, 72, 255) if i % 2 == 0 else (53, 92, 78, 255))
        # rocky face strokes
        for k in range(9):
            x0 = cx + rng.integers(-half, half)
            y0 = rng.integers(top + 20, int(H * 0.76))
            d.line([(x0, y0), (x0 + rng.integers(-18, 18), y0 + rng.integers(24, 90))],
                   fill=(30, 60, 54, 120), width=rng.integers(2, 5))
        # snow-ish highlight
        d.line([(cx, top), (cx - half * 0.45, int(H * 0.73))], fill=(86, 120, 100, 120), width=4)
    # sun and moon
    d.ellipse([120, 80, 240, 200], fill=(188, 62, 42, 255))
    d.ellipse([W - 260, 96, W - 160, 196], fill=(232, 224, 198, 255))
    # pines
    for cx in (int(W * 0.18), int(W * 0.82)):
        d.rectangle([cx - 5, int(H * 0.55), cx + 5, int(H * 0.78)], fill=(58, 44, 30, 255))
        for k in range(6):
            yy = int(H * 0.50) + k * 28
            ww = 70 - k * 9
            d.ellipse([cx - ww, yy, cx + ww, yy + 32], fill=(36, 68, 46, 230))
    # gold frame + panel seams
    d.rectangle([0, 0, W - 1, H - 1], outline=(120, 92, 48, 255), width=14)
    for i in range(1, 6):
        d.line([(W * i / 6, 0), (W * i / 6, H)], fill=(120, 92, 48, 170), width=6)
    img.save(OUT / "throne_screen.jpg", quality=90)
    print("  wrote throne_screen.jpg")


def main():
    gen_roof()
    gen_granite()
    gen_granite_block()
    gen_paving()
    gen_wood("wood_red", (74, 33, 28), (126, 63, 47), seed=201, rings=18)
    gen_wood("wood_dark", (43, 27, 20), (88, 58, 38), seed=202, rings=9)
    gen_plaster()
    gen_lattice()
    gen_ground()
    gen_water()
    gen_dancheong()
    gen_screen()
    gen_signs()

    # material variants (multiplying a texture is not exported to glTF, so bake it)
    tint("granite.jpg", "granite_dark.jpg", (0.46, 0.47, 0.48))
    tint("granite.jpg", "granite_light.jpg", (1.10, 1.09, 1.05))
    tint("granite_block.jpg", "granite_block_dark.jpg", (0.55, 0.56, 0.57))
    tint("wood_dark.jpg", "wood_floor.jpg", (0.98, 0.84, 0.64))
    tint("plaster.jpg", "plaster_wall.jpg", (0.74, 0.40, 0.30))
    print("done")


if __name__ == "__main__":
    main()
