"""Build the Gyeongbokgung palace scene in Blender and export a GLB.

Run headless:
    blender -b --factory-startup -P blender/scripts/build_scene.py

The model is deliberately stylised but architecturally literate: stone
platforms (기단/월대), timber columns, dancheong lintels, bracket sets (공포),
tiled hip roofs with upturned eaves, ridges and rafters.  Each building is split
into member layers — following the member names of Korean palace carpentry
(초석, 기둥, 창방, 평방, 대들보, 대공, 공포, 도리, 장혀, 서까래, 부연, 추녀,
지붕, 기와, 막새, 용마루) — so the web viewer can take it apart piece by piece.

Two-storey buildings (광화문, 근정전, 경회루, 향원정) repeat the same member
sequence for the upper storey, which sits inside the lower skirt roof: 상층
마루 → 상층 기둥 → 상층 벽체/창호 → 상층 창방·평방 → 상층 공포 → 상층 도리 →
상층 서까래 → 상층 부연 → 상층 추녀 → 상층 지붕 → 상층 기와 → 상층 막새.
Single-storey halls leave those slots empty.
"""

from __future__ import annotations

import json
import math
import os
import random
import sys
from pathlib import Path

import bpy
from mathutils import Vector

sys.path.append(str(Path(__file__).resolve().parent))
from geo import (  # noqa: E402
    MAT, TILE_PITCH, Builder, add_box, add_cyl, add_lantern, add_lattice_panel,
    add_maksae, add_plane, add_prism, add_rail, add_roof, add_roof_ridges,
    add_roof_tiles, add_rock, add_sign, add_skirt_roof, add_skirt_roof_tiles,
    add_sphere, add_tile_field, add_tile_ridges, add_tree, add_tube,
    build_materials, reset_scene, roof_height,
)

ROOT = Path(__file__).resolve().parents[2]
OUT_GLB = ROOT / "public" / "models" / "gyeongbokgung.glb"
OUT_GLB.parent.mkdir(parents=True, exist_ok=True)

# Order runs bottom-up through the structure, which is also the order the
# exploded stack uses: 기단 -> 마루 -> 초석 -> 기둥 -> 벽체/창호 -> 창방/평방 ->
# 가구 -> 공포 -> 도리/장혀 -> 서까래 -> 부연/평고대 -> 추녀/사래 -> 지붕 ->
# (상층의 같은 순서) -> 용마루.
#
# ``group`` tells the viewer which tier a member belongs to: "lower" parts are
# used by every building, "upper" parts only by the four two-storey buildings,
# and "cap" closes the stack at the topmost ridge.
LAYERS = [
    ("base", "기단·월대", "lower"),
    ("floor", "마루", "lower"),
    ("plinth", "초석", "lower"),
    ("column", "기둥", "lower"),
    ("wall", "벽체", "lower"),
    ("door", "창호·난간", "lower"),
    ("lintel", "창방·평방", "lower"),
    ("frame", "가구·천장", "lower"),
    ("bracket", "공포", "lower"),
    ("purlin", "도리·장혀", "lower"),
    ("rafter", "서까래", "lower"),
    ("eave", "부연·평고대", "lower"),
    ("hip", "추녀·사래", "lower"),
    ("roof", "지붕 골조", "lower"),
    ("tile", "기와", "lower"),
    ("maksae", "막새·와당", "lower"),
    ("upper_floor", "상층 마루", "upper"),
    ("upper_column", "상층 기둥", "upper"),
    ("upper_wall", "상층 벽체", "upper"),
    ("upper_door", "상층 창호·난간", "upper"),
    ("upper_lintel", "상층 창방·평방", "upper"),
    ("upper_bracket", "상층 공포", "upper"),
    ("upper_purlin", "상층 도리·장혀", "upper"),
    ("upper_rafter", "상층 서까래", "upper"),
    ("upper_eave", "상층 부연·평고대", "upper"),
    ("upper_hip", "상층 추녀·사래", "upper"),
    ("upper_roof", "상층 지붕 골조", "upper"),
    ("upper_tile", "상층 기와", "upper"),
    ("upper_maksae", "상층 막새·와당", "upper"),
    ("ridge", "용마루·취두", "cap"),
]

# index ranges used by the builders below
LOWER = slice(0, 16)          # 기단 … 하층 막새
UPPER = slice(16, 29)         # 상층 마루 … 상층 막새
RIDGE_INDEX = 29              # 용마루 (topmost roof)

# A 막새 ring is a thin strip along the eave, so stacking it on top of the tall
# tile shell would fling it up to the ridge.  It rides with its own 기와 layer
# instead and only takes a small extra step.
RIDE_WITH = {"maksae": "tile", "upper_maksae": "upper_tile"}
RIDE_INDEX = {i: next(j for j, (k, _l, _g) in enumerate(LAYERS) if k == parent)
              for i, (key, _l, _g) in enumerate(LAYERS)
              if (parent := RIDE_WITH.get(key))}

bpy.context.scene.unit_settings.system = "METRIC"
reset_scene()
build_materials()

COLL = bpy.data.collections.new("GYEONGBOKGUNG")
bpy.context.scene.collection.children.link(COLL)


# --------------------------------------------------------------------------
# scene graph helpers
# --------------------------------------------------------------------------
def empty(name, loc=(0, 0, 0), rot_z=0.0, parent=None, extras=None):
    ob = bpy.data.objects.new(name, None)
    ob.empty_display_type = "PLAIN_AXES"
    ob.empty_display_size = 4
    ob.location = loc
    ob.rotation_euler = (0, 0, rot_z)
    COLL.objects.link(ob)
    if parent:
        ob.parent = parent
    if extras:
        for k, v in extras.items():
            ob[k] = v
    return ob


class Building:
    def __init__(self, bid, ko, hanja, loc, kind="hall", year="", rot_z=0.0, **extra):
        self.bid = bid
        self.ko = ko
        self.meta = {
            "building_id": bid,
            "ko": ko,
            "hanja": hanja,
            "kind": kind,
            "year": year,
            "tiers": 1,
            "x": loc[0],
            "y": loc[1],
            **extra,
        }
        self.root = empty(f"B_{bid}", loc, rot_z, extras=self.meta)
        self.layer_nodes = []
        self.bx = []
        for i, (key, label, group) in enumerate(LAYERS):
            extras = {"layer": i, "layer_key": key, "layer_ko": label,
                      "layer_group": group}
            if i in RIDE_INDEX:
                extras["layer_ride"] = RIDE_INDEX[i]
            node = empty(f"{bid}_L{i}_{key}", parent=self.root, extras=extras)
            self.layer_nodes.append(node)
            self.bx.append(Builder(f"{bid}_L{i}"))
        # convenience slices: (lower…), (upper…), ridge
        self.lower = self.bx[LOWER]
        self.upper = self.bx[UPPER]
        self.ridge = self.bx[RIDGE_INDEX]

    def emit(self):
        for builder, node in zip(self.bx, self.layer_nodes):
            builder.emit(node, COLL)


site_root = empty("SITE", extras={"kind": "site"})
site = Builder("site")


# --------------------------------------------------------------------------
# shared architectural elements
# --------------------------------------------------------------------------
def stairs(b, cx, y_edge, z_base, z_top, width, n=4, mat="stone"):
    depth = 0.44
    for i in range(n):
        h = z_top - (z_top - z_base) * (i + 1) / n
        y = y_edge - depth * (i + 0.5)
        add_box(b, mat, (width, depth, h - z_base), (cx, y, (h + z_base) / 2), uv_scale=2.0)


def bracket(b, x, y, z, along="x", s=1.0):
    rot = (0, 0, math.pi / 2) if along == "y" else (0, 0, 0)
    add_box(b, "green", (1.55 * s, 0.8 * s, 0.3 * s), (x, y, z), rot=rot, uv_scale=0.9)
    add_box(b, "red", (1.95 * s, 0.55 * s, 0.22 * s), (x, y, z + 0.3 * s), rot=rot, uv_scale=0.9)
    add_box(b, "green_light", (1.15 * s, 1.0 * s, 0.3 * s), (x, y, z + 0.56 * s), rot=rot, uv_scale=0.9)
    add_box(b, "white", (0.3 * s, 1.12 * s, 0.14 * s), (x, y, z + 0.44 * s), rot=rot, uv_scale=0.8)
    add_box(b, "green", (0.5 * s, 1.28 * s, 0.24 * s), (x, y, z + 0.76 * s), rot=rot, uv_scale=0.8)
    add_box(b, "gold", (0.18 * s, 1.34 * s, 0.06 * s), (x, y, z + 0.88 * s), rot=rot, uv_scale=0.5)


def bracket_ring(b, xs, ys, z, scale=1.0):
    """Bracket sets on every column line and between the bays, all four sides."""
    for x in xs:
        bracket(b, x, ys[0], z, "x", scale)
        bracket(b, x, ys[-1], z, "x", scale)
    for i in range(len(xs) - 1):
        xm = (xs[i] + xs[i + 1]) / 2
        bracket(b, xm, ys[0], z, "x", scale * 0.8)
        bracket(b, xm, ys[-1], z, "x", scale * 0.8)
    for y in ys:
        bracket(b, xs[0], y, z, "y", scale)
        bracket(b, xs[-1], y, z, "y", scale)
    for j in range(len(ys) - 1):
        ym = (ys[j] + ys[j + 1]) / 2
        bracket(b, xs[0], ym, z, "y", scale * 0.8)
        bracket(b, xs[-1], ym, z, "y", scale * 0.8)


def wall_panel(b_body, b_door, cx, cy, z0, width, height, axis="x", facing=-1,
               door=True, mat="plaster"):
    """A bay infill: 벽체 body in one builder, 창호 in another.

    The plaster/wood body belongs to 벽체, the lattice doors and the transom
    above them to 창호 — the two are separate parts in the exploded view.
    """
    b = b_body
    if axis == "x":
        add_box(b, mat, (width, 0.32, height), (cx, cy, z0 + height / 2), uv_scale=1.8)
        add_box(b, "wood_dark", (width + 0.05, 0.42, 0.75),
                (cx, cy, z0 + 0.375), uv_scale=1.4)
        lw, lh = width - 0.34, height * 0.53
        lz = z0 + 0.75 + lh / 2
        ly = cy + facing * 0.175
        if door:
            add_lattice_panel(b_door, cx, ly, lz, lw, lh, facing_south=(facing < 0))
            add_box(b_door, "wood_dark", (width + 0.08, 0.24, 0.14),
                    (cx, ly, z0 + 0.78), uv_scale=1.2)
            add_box(b_door, "wood_dark", (width + 0.08, 0.24, 0.14),
                    (cx, ly, z0 + 0.78 + lh + 0.07), uv_scale=1.2)
            for sx in (-1, 1):
                add_box(b_door, "wood_dark", (0.13, 0.22, lh + 0.2),
                        (cx + sx * (lw / 2 + 0.06), ly, lz), uv_scale=1.2)
        # transom
        tz = z0 + 0.75 + height * 0.53 + 0.25
        th = height * 0.16
        add_lattice_panel(b_door, cx, ly, tz + th / 2, width - 0.5, th,
                          facing_south=(facing < 0))
        add_box(b, "wood_dark", (width, 0.36, 0.16), (cx, cy, tz + th + 0.08),
                uv_scale=1.4)
    else:
        add_box(b, mat, (0.32, width, height), (cx, cy, z0 + height / 2), uv_scale=1.8)
        add_box(b, "wood_dark", (0.42, width + 0.05, 0.75),
                (cx, cy, z0 + 0.375), uv_scale=1.4)
        lw, lh = width - 0.34, height * 0.53
        lz = z0 + 0.75 + lh / 2
        lx = cx + facing * 0.175
        if door:
            add_lattice_panel(b_door, lx, cy, lz, lw, lh,
                              rot_z=math.pi / 2, facing_south=(facing > 0))
            add_box(b_door, "wood_dark", (0.24, width + 0.08, 0.14),
                    (lx, cy, z0 + 0.78), uv_scale=1.2)
            add_box(b_door, "wood_dark", (0.24, width + 0.08, 0.14),
                    (lx, cy, z0 + 0.78 + lh + 0.07), uv_scale=1.2)
            for sy in (-1, 1):
                add_box(b_door, "wood_dark", (0.22, 0.13, lh + 0.2),
                        (lx, cy + sy * (lw / 2 + 0.06), lz), uv_scale=1.2)
        tz = z0 + 0.75 + height * 0.53 + 0.25
        th = height * 0.16
        add_lattice_panel(b_door, lx, cy, tz + th / 2, width - 0.5, th,
                          rot_z=math.pi / 2, facing_south=(facing > 0))
        add_box(b, "wood_dark", (0.36, width, 0.16), (cx, cy, tz + th + 0.08),
                uv_scale=1.4)


def rafter_field(b, w, d, eave_z, spacing=0.62):
    # long sides
    n = max(4, int(w / spacing))
    for i in range(n + 1):
        x = -w / 2 + 0.3 + (w - 0.6) * i / n
        for s in (-1, 1):
            add_tube(b, "wood_dark",
                     [(x, s * (d / 2 - 2.6), eave_z - 0.02), (x, s * (d / 2 - 0.12), eave_z - 0.26)],
                     0.095, sides=5, uv_scale=0.8)
    m = max(3, int(d / spacing))
    for j in range(m + 1):
        y = -d / 2 + 0.3 + (d - 0.6) * j / m
        for s in (-1, 1):
            add_tube(b, "wood_dark",
                     [(s * (w / 2 - 2.6), y, eave_z - 0.02), (s * (w / 2 - 0.12), y, eave_z - 0.26)],
                     0.095, sides=5, uv_scale=0.8)


def eave_detail(b, w, d, eave_z, spacing=0.66):
    """부연 · 평고대 — the outer, flying tier of a 겹처마 eave."""
    n = max(4, int(w / spacing))
    for i in range(n + 1):
        x = -w / 2 + 0.3 + (w - 0.6) * i / n
        for s in (-1, 1):
            add_tube(b, "wood_red",
                     [(x, s * (d / 2 - 1.65), eave_z + 0.09),
                      (x, s * (d / 2 + 0.06), eave_z - 0.05)],
                     0.075, sides=5, uv_scale=0.8)
    m = max(3, int(d / spacing))
    for j in range(m + 1):
        y = -d / 2 + 0.3 + (d - 0.6) * j / m
        for s in (-1, 1):
            add_tube(b, "wood_red",
                     [(s * (w / 2 - 1.65), y, eave_z + 0.09),
                      (s * (w / 2 + 0.06), y, eave_z - 0.05)],
                     0.075, sides=5, uv_scale=0.8)
    # 평고대: the board that carries the tile edge, along all four eaves
    add_box(b, "wood_dark", (w + 0.24, 0.16, 0.22), (0, d / 2 - 0.02, eave_z - 0.15), uv_scale=1.4)
    add_box(b, "wood_dark", (w + 0.24, 0.16, 0.22), (0, -d / 2 + 0.02, eave_z - 0.15), uv_scale=1.4)
    add_box(b, "wood_dark", (0.16, d + 0.24, 0.22), (w / 2 - 0.02, 0, eave_z - 0.15), uv_scale=1.4)
    add_box(b, "wood_dark", (0.16, d + 0.24, 0.22), (-w / 2 + 0.02, 0, eave_z - 0.15), uv_scale=1.4)


def hip_rafters(b, w, d, eave_z, ix, iy, lift=0.9):
    """추녀 · 사래 — the corner rafters that turn the hip up at the eave."""
    for sx in (-1, 1):
        for sy in (-1, 1):
            x0, y0 = sx * ix, sy * iy
            x1, y1 = sx * (w / 2 - 0.18), sy * (d / 2 - 0.18)
            tip_z = eave_z + lift * 0.96
            add_tube(b, "wood_dark",
                     [(x0, y0, eave_z + 0.13),
                      (x0 + (x1 - x0) * 0.55, y0 + (y1 - y0) * 0.55, eave_z - 0.1),
                      (x1, y1, tip_z)],
                     0.17, sides=6, uv_scale=1.1)
            # 사래: the short flying rafter that lengthens the 추녀
            add_tube(b, "wood_red",
                     [(x0 + (x1 - x0) * 0.58, y0 + (y1 - y0) * 0.58, eave_z + 0.06),
                      (x1, y1, tip_z + 0.06)],
                     0.1, sides=5, uv_scale=0.9)


def add_throne(b, floor_z, back_y):
    # raised dais
    add_box(b, "stone_dark", (5.2, 3.4, 1.0), (0, back_y + 1.4, floor_z + 0.5), uv_scale=2.0)
    add_box(b, "red_deep", (4.4, 2.8, 0.35), (0, back_y + 1.4, floor_z + 1.17), uv_scale=1.5)
    # seat
    add_box(b, "gold", (2.4, 1.6, 0.55), (0, back_y + 1.8, floor_z + 1.55), uv_scale=1.2)
    add_box(b, "red", (2.0, 1.2, 0.28), (0, back_y + 1.85, floor_z + 1.9), uv_scale=1.0)
    add_box(b, "gold", (2.1, 0.24, 2.1), (0, back_y + 2.5, floor_z + 2.65), uv_scale=1.2)
    # canopy
    for sx in (-1.6, 1.6):
        for sy in (-1.0, 1.0):
            add_cyl(b, "red_deep", 0.14, 4.4, (sx, back_y + 1.4 + sy, floor_z + 2.9), segments=8)
    add_roof(b, "gold", "red_deep", 4.4, 3.6, 1.2, floor_z + 5.0, hip=True,
             lift=0.25, nx=10, ny=8, thickness=0.16, uv=(1.2, 1.2), overhang_trim=False)
    add_box(b, "gold", (4.6, 0.3, 0.28), (0, back_y + 1.4, floor_z + 5.06), uv_scale=1.0)
    # screen
    add_plane(b, "screen", (5.6, 3.1), (0, back_y + 0.15, floor_z + 2.75),
              rot=(math.pi / 2, 0, 0))


def build_hall(b, cfg, woldae=False):
    (L_base, L_floor, L_plinth, L_col, L_wall, L_door, L_lintel, L_frame,
     L_brack, L_purlin, L_raft, L_eave, L_hip, L_roof, L_tile,
     L_maksae) = b.lower
    (U_floor, U_col, U_wall, U_door, U_lintel, U_brack, U_purlin, U_raft,
     U_eave, U_hip, U_roof, U_tile, U_maksae) = b.upper
    L_ridge = b.ridge
    W, D = cfg["w"], cfg["d"]
    ch = cfg["col_h"]
    roof_h = cfg.get("roof_h", 5.0)
    over = cfg.get("overhang", 2.3)
    bays_x = cfg.get("bays_x", 5)
    bays_y = cfg.get("bays_y", 3)
    base = cfg.get("base", 0.0)
    walls = cfg.get("walls", True)
    open_bays = cfg.get("open_bays", 0)
    double = cfg.get("double", False)
    open_upper = cfg.get("open_upper", False)
    platform_h = cfg.get("platform_h", 1.15)
    sign = cfg.get("sign")
    interior = cfg.get("interior", False)
    railing = cfg.get("railing", False)
    col_r = cfg.get("col_r", max(0.28, min(0.42, W * 0.011)))

    # ---------------------------------------------------------------- base
    z = base
    if cfg.get("woldae"):
        z = build_woldae(b, cfg, z)
    if cfg.get("platform", True):
        pw, pd = W + 3.0, D + 3.0
        add_box(L_base, "stone", (pw, pd, platform_h), (0, 0, z + platform_h / 2), uv_scale=2.4)
        add_box(L_base, "stone_light", (pw + 0.45, pd + 0.45, 0.2),
                (0, 0, z + platform_h + 0.1), uv_scale=1.8)
        stairs(L_base, 0, -pd / 2, z, z + platform_h + 0.2, min(10.0, W * 0.42), n=4)
        z += platform_h + 0.2
    else:
        # a 누각 standing straight on stone still has a dressed terrace
        add_box(L_base, "stone", (W + 3.4, D + 3.4, 0.55), (0, 0, z - 0.28), uv_scale=2.4)
        add_box(L_base, "stone_light", (W + 3.9, D + 3.9, 0.16), (0, 0, z - 0.09), uv_scale=2.0)
    floor_z = z

    # ------------------------------------------------ 마루 (floor deck)
    add_box(L_floor, "wood_floor", (W + 0.5, D + 0.5, 0.22), (0, 0, floor_z + 0.05), uv_scale=1.6)
    # 귀틀: the joists the deck boards sit on, visible once the floor is lifted
    for i in range(bays_y + 1):
        jy = -(D - 2.4) / 2 + (D - 2.4) * i / bays_y
        add_box(L_floor, "wood_dark", (W + 0.3, 0.2, 0.2), (0, jy, floor_z - 0.02), uv_scale=1.3)
    floor_z += 0.16

    # ------------------------------------------------------------- columns
    inset = 1.25
    xs = [-(W / 2 - inset) + (W - 2 * inset) * i / bays_x for i in range(bays_x + 1)]
    ys = [-(D / 2 - inset) + (D - 2 * inset) * j / bays_y for j in range(bays_y + 1)]
    top_z = floor_z + ch
    for x in xs:
        for y in ys:
            # 초석: the dressed stone footing each column stands on
            add_cyl(L_plinth, "stone_light", col_r * 1.75, 0.34,
                    (x, y, floor_z + 0.17), segments=10, uv_scale=1.0)
            add_cyl(L_col, "wood_red", col_r, ch, (x, y, floor_z + 0.3 + ch / 2),
                    segments=12, taper=0.97, uv_scale=1.6)
            add_box(L_brack, "wood_dark", (col_r * 2.6, col_r * 2.6, 0.34),
                    (x, y, top_z - 0.1), uv_scale=1.0)
            add_box(L_brack, "green", (col_r * 2.9, col_r * 2.9, 0.18),
                    (x, y, top_z + 0.13), uv_scale=0.8)

    # --------------------------------------------------------------- walls
    if walls:
        wall_h = ch - 0.35
        # front (south, -Y)
        for i in range(bays_x):
            cx = (xs[i] + xs[i + 1]) / 2
            w = xs[i + 1] - xs[i] - col_r * 2.0
            central = abs(cx) < (W * 0.32)
            if open_bays and central:
                continue
            door = not (cfg.get("plain_walls") and abs(cx) > W * 0.3)
            wall_panel(L_wall, L_door, cx, ys[0], floor_z, w, wall_h, axis="x", facing=-1, door=door)
        # back
        for i in range(bays_x):
            cx = (xs[i] + xs[i + 1]) / 2
            w = xs[i + 1] - xs[i] - col_r * 2.0
            wall_panel(L_wall, L_door, cx, ys[-1], floor_z, w, wall_h, axis="x", facing=1, door=False)
        # sides
        for j in range(bays_y):
            cy = (ys[j] + ys[j + 1]) / 2
            w = ys[j + 1] - ys[j] - col_r * 2.0
            wall_panel(L_wall, L_door, xs[0], cy, floor_z, w, wall_h, axis="y", facing=-1, door=False)
            wall_panel(L_wall, L_door, xs[-1], cy, floor_z, w, wall_h, axis="y", facing=1, door=False)

        # dark interior ceiling + back so open doors read as a deep hall
        add_box(L_frame, "black", (W - 2.4, D - 2.4, 0.2), (0, 0, top_z - 0.35), uv_scale=2.0)

    if interior:
        add_throne(L_floor, floor_z, D / 2 - 3.6)

    if railing:
        add_rail(L_door, "wood_red", -W / 2 + 0.2, -D / 2 + 0.2, W / 2 - 0.2, -D / 2 + 0.2,
                 floor_z + 0.2, height=1.0, post_every=2.2)
        add_rail(L_door, "wood_red", -W / 2 + 0.2, D / 2 - 0.2, W / 2 - 0.2, D / 2 - 0.2,
                 floor_z + 0.2, height=1.0, post_every=2.2)
        add_rail(L_door, "wood_red", -W / 2 + 0.2, -D / 2 + 0.2, -W / 2 + 0.2, D / 2 - 0.2,
                 floor_z + 0.2, height=1.0, post_every=2.2)
        add_rail(L_door, "wood_red", W / 2 - 0.2, -D / 2 + 0.2, W / 2 - 0.2, D / 2 - 0.2,
                 floor_z + 0.2, height=1.0, post_every=2.2)

    # --------------------------------------------------------- 창방·평방
    bz = top_z + 0.3
    # 창방: the lintel that ties the column heads together
    add_box(L_lintel, "dancheong", (W + 0.5, 0.55, 0.9), (0, ys[0], bz + 0.1), uv_scale=2.2)
    add_box(L_lintel, "dancheong", (W + 0.5, 0.55, 0.9), (0, ys[-1], bz + 0.1), uv_scale=2.2)
    add_box(L_lintel, "dancheong", (0.55, D + 0.5, 0.9), (xs[0], 0, bz + 0.1), uv_scale=2.2)
    add_box(L_lintel, "dancheong", (0.55, D + 0.5, 0.9), (xs[-1], 0, bz + 0.1), uv_scale=2.2)
    # 평방: the ring above the lintel that carries the bracket sets
    pw, pd = W + 1.5, D + 1.5
    for s in (-1, 1):
        add_box(L_lintel, "red_deep", (pw, 0.6, 0.32), (0, s * (pd / 2 - 0.3), bz + 0.8), uv_scale=2.0)
        add_box(L_lintel, "red_deep", (0.6, pd - 1.2, 0.32), (s * (pw / 2 - 0.3), 0, bz + 0.8), uv_scale=2.0)
    add_box(L_lintel, "gold", (W + 0.7, 0.12, 0.08), (0, ys[0] - 0.3, bz + 0.62), uv_scale=1.0)
    add_box(L_lintel, "gold", (W + 0.7, 0.12, 0.08), (0, ys[-1] + 0.3, bz + 0.62), uv_scale=1.0)

    # ------------------------------------------------------- roof envelope
    eave_z = bz + 1.95
    eave_base = eave_z + 0.15
    roof_w = W + over * 2
    roof_d = D + over * 2
    up_w = cfg.get("upper_w", W - 2.0)
    up_d = cfg.get("upper_d", D - 2.0)
    skirt_h = cfg.get("skirt_h", roof_h * 0.46)
    # the frame of the lower storey stops under the lower (skirt) roof
    frame_h = skirt_h if double else roof_h
    frame_w = roof_w + 1.8 if double else roof_w
    frame_d = roof_d + 1.8 if double else roof_d
    eave_w = roof_w + 1.8 if double else roof_w
    eave_d = roof_d + 1.8 if double else roof_d
    z_frame_top = eave_base + frame_h

    # ------------------------------------------ 가구: 대들보 · 대공 · 천장
    beam_xs = [-W * 0.24, 0.0, W * 0.24] if W >= 18 else [0.0]
    beam_z = top_z + 1.12
    beam_h = 0.72
    for bxx in beam_xs:
        add_box(L_frame, "wood_dark", (0.58, ys[-1] - ys[0] + 0.7, beam_h),
                (bxx, (ys[0] + ys[-1]) / 2, beam_z), uv_scale=1.8)
        # 대공: the tapering king post that carries the ridge purlin
        post0 = beam_z + beam_h / 2
        post1 = z_frame_top - 0.74
        if post1 - post0 > 0.5:
            hgt = post1 - post0
            for k in range(3):
                add_box(L_frame, "wood_dark", (0.52 - k * 0.12, 0.52 - k * 0.12, hgt / 3),
                        (bxx, 0, post0 + hgt * (k + 0.5) / 3), uv_scale=1.1)

    # ------------------------------------------------------------ brackets
    bracket_ring(L_brack, xs, ys, bz + 1.02)

    # ------------------------------------------------------- 도리 · 장혀
    ey0, ey1 = ys[0] - 0.1, ys[-1] + 0.1
    ex0, ex1 = xs[0] - 0.1, xs[-1] + 0.1
    # 외목도리: the eave purlin the rafters sit on, tied by 장혀 below it
    add_box(L_purlin, "wood_dark", (W + 2.6, 0.42, 0.42), (0, ey0, eave_z), uv_scale=1.6)
    add_box(L_purlin, "wood_dark", (W + 2.6, 0.42, 0.42), (0, ey1, eave_z), uv_scale=1.6)
    add_box(L_purlin, "wood_dark", (0.42, D + 2.6, 0.42), (ex0, 0, eave_z), uv_scale=1.6)
    add_box(L_purlin, "wood_dark", (0.42, D + 2.6, 0.42), (ex1, 0, eave_z), uv_scale=1.6)
    add_box(L_purlin, "wood_dark", (W + 2.2, 0.3, 0.18), (0, ey0, eave_z - 0.31), uv_scale=1.4)
    add_box(L_purlin, "wood_dark", (W + 2.2, 0.3, 0.18), (0, ey1, eave_z - 0.31), uv_scale=1.4)
    add_box(L_purlin, "wood_dark", (0.3, D + 2.2, 0.18), (ex0, 0, eave_z - 0.31), uv_scale=1.4)
    add_box(L_purlin, "wood_dark", (0.3, D + 2.2, 0.18), (ex1, 0, eave_z - 0.31), uv_scale=1.4)
    if double:
        # inside the skirt the purlins ride on the flat inner rim
        add_box(L_purlin, "wood_dark", (up_w + 1.2, 0.4, 0.4),
                (0, 0, z_frame_top - 0.68), uv_scale=1.6)
        for sy in (-1, 1):
            add_box(L_purlin, "wood_dark", (up_w + 0.6, 0.32, 0.32),
                    (0, sy * up_d * 0.32, z_frame_top - 0.72), uv_scale=1.4)
    else:
        ridge_half = max(0.8, frame_w / 2 - frame_d / 2)
        # 종도리 at the ridge, 중도리 on the slopes between ridge and eave
        add_box(L_purlin, "wood_dark", (ridge_half * 2 + 0.6, 0.4, 0.4),
                (0, 0, z_frame_top - 0.72), uv_scale=1.6)
        for sy in (-1, 1):
            py = sy * frame_d * 0.26
            pz = eave_base + roof_height(0.0, py, frame_w, frame_d, frame_h) - 0.57
            add_box(L_purlin, "wood_dark", (frame_w * 0.58, 0.34, 0.34),
                    (0, py, pz), uv_scale=1.6)

    # ---------------------------------------------- 서까래 · 부연 · 추녀
    rafter_field(L_raft, roof_w, roof_d, eave_z)
    eave_detail(L_eave, eave_w, eave_d, eave_z)
    hip_rafters(L_hip, eave_w, eave_d, eave_z, abs(xs[0]), abs(ys[0]))

    if double:
        # ------------------------------------------------------ 하층 지붕
        # the skirt roof wraps the upper storey; it is its own member, so it
        # lifts away from the upper storey in the exploded view
        low_w, low_d = eave_w, eave_d
        up_z = add_skirt_roof(L_roof, "roof_base", "wood_dark", low_w, low_d,
                              up_w + 2.4, up_d + 2.4, skirt_h, eave_base - 0.05,
                              lift=1.0, thickness=0.42, nx=20, ny=16)
        add_skirt_roof_tiles(L_tile, L_maksae, low_w, low_d,
                             up_w + 2.4, up_d + 2.4, skirt_h, eave_base - 0.05,
                             lift=1.0)
        up_h = cfg.get("upper_col_h", 3.3)
        uxs = [-(up_w / 2) + up_w * i / max(2, bays_x) for i in range(max(2, bays_x) + 1)]
        uys = [-(up_d / 2) + up_d * j / 2 for j in range(3)]
        uz = up_z + 0.35

        # -------------------------------------------------- 상층 마루
        add_box(U_floor, "wood_dark", (up_w + 2.8, up_d + 2.8, 0.22),
                (0, 0, up_z - 0.02), uv_scale=1.4)
        add_box(U_floor, "wood_floor", (up_w + 2.4, up_d + 2.4, 0.3),
                (0, 0, up_z + 0.2), uv_scale=1.6)

        # -------------------------------------------------- 상층 기둥
        if open_upper:
            # 누마루: stone pads and an open grid of columns
            for x in uxs:
                for y in uys:
                    add_box(U_col, "stone_light", (0.6, 0.6, 0.18),
                            (x, y, uz + 0.09), uv_scale=0.8)
                    add_cyl(U_col, "wood_red", 0.26, up_h,
                            (x, y, uz + 0.18 + up_h / 2),
                            segments=10, taper=0.97, uv_scale=1.2)
            col_base = uz + 0.18
        else:
            # 겹처마 전각: perimeter posts frame plaster bays and lattice windows
            for x in uxs:
                for y in uys:
                    if not (x in (uxs[0], uxs[-1]) or y in (uys[0], uys[-1])):
                        continue
                    add_cyl(U_col, "wood_red", 0.26, up_h,
                            (x, y, uz + up_h / 2),
                            segments=10, taper=0.97, uv_scale=1.2)
            for i in range(len(uxs) - 1):
                cx_ = (uxs[i] + uxs[i + 1]) / 2
                w = uxs[i + 1] - uxs[i] - 0.52
                wall_panel(U_wall, U_door, cx_, uys[0], uz, w, up_h - 0.35,
                           axis="x", facing=-1, door=True)
                wall_panel(U_wall, U_door, cx_, uys[-1], uz, w, up_h - 0.35,
                           axis="x", facing=1, door=True)
            for j in range(len(uys) - 1):
                cy_ = (uys[j] + uys[j + 1]) / 2
                w = uys[j + 1] - uys[j] - 0.52
                wall_panel(U_wall, U_door, uxs[0], cy_, uz, w, up_h - 0.35,
                           axis="y", facing=-1, door=True)
                wall_panel(U_wall, U_door, uxs[-1], cy_, uz, w, up_h - 0.35,
                           axis="y", facing=1, door=True)
            col_base = uz

        # -------------------------------------------------- 상층 난간
        if open_upper:
            add_rail(U_door, "wood_red", -up_w / 2, -up_d / 2, up_w / 2, -up_d / 2,
                     uz + 0.1, height=0.95, post_every=1.9)
            add_rail(U_door, "wood_red", -up_w / 2, up_d / 2, up_w / 2, up_d / 2,
                     uz + 0.1, height=0.95, post_every=1.9)
            add_rail(U_door, "wood_red", -up_w / 2, -up_d / 2, -up_w / 2, up_d / 2,
                     uz + 0.1, height=0.95, post_every=1.9)
            add_rail(U_door, "wood_red", up_w / 2, -up_d / 2, up_w / 2, up_d / 2,
                     uz + 0.1, height=0.95, post_every=1.9)

        # -------------------------------------------- 상층 창방 · 평방
        ub = col_base + up_h
        for sy in (-1, 1):
            add_box(U_lintel, "dancheong", (up_w + 0.5, 0.5, 0.9),
                    (0, sy * up_d / 2, ub - 0.45), uv_scale=1.8)
        for sx in (-1, 1):
            add_box(U_lintel, "dancheong", (0.5, up_d + 0.5, 0.9),
                    (sx * up_w / 2, 0, ub - 0.45), uv_scale=1.8)
        # 평방: a ring, so the upper storey stays open through the middle
        pw, pd = up_w + 1.1, up_d + 1.1
        for sy in (-1, 1):
            add_box(U_lintel, "red_deep", (pw, 0.6, 0.3),
                    (0, sy * (pd / 2 - 0.3), ub + 0.05), uv_scale=1.8)
        for sx in (-1, 1):
            add_box(U_lintel, "red_deep", (0.6, pd - 1.2, 0.3),
                    (sx * (pw / 2 - 0.3), 0, ub + 0.05), uv_scale=1.8)

        # -------------------------------------------------- 상층 공포
        bracket_ring(U_brack, uxs, uys, ub + 0.22, scale=0.7)

        # -------------------------------------------- 상층 도리 · 장혀
        up_eave = ub + 1.05
        for sy in (-1, 1):
            add_box(U_purlin, "wood_dark", (up_w + 1.4, 0.4, 0.4),
                    (0, sy * up_d / 2, up_eave - 0.28), uv_scale=1.5)
            add_box(U_purlin, "wood_dark", (up_w + 1.1, 0.26, 0.16),
                    (0, sy * up_d / 2, up_eave - 0.55), uv_scale=1.3)
        for sx in (-1, 1):
            add_box(U_purlin, "wood_dark", (0.4, up_d + 1.4, 0.4),
                    (sx * up_w / 2, 0, up_eave - 0.28), uv_scale=1.5)
            add_box(U_purlin, "wood_dark", (0.26, up_d + 1.1, 0.16),
                    (sx * up_w / 2, 0, up_eave - 0.55), uv_scale=1.3)

        # -------------------------------------- 상층 서까래 · 부연 · 추녀
        up_roof_w, up_roof_d = up_w + over * 2.8, up_d + over * 2.8
        up_eave_w, up_eave_d = up_roof_w + 1.8, up_roof_d + 1.8
        rafter_field(U_raft, up_roof_w, up_roof_d, up_eave)
        eave_detail(U_eave, up_eave_w, up_eave_d, up_eave)
        hip_rafters(U_hip, up_eave_w, up_eave_d, up_eave, abs(uxs[0]), abs(uys[0]))

        # -------------------------------------------------- 상층 지붕
        add_roof(U_roof, "roof_base", "wood_dark", up_roof_w, up_roof_d,
                 roof_h * 1.02, up_eave, hip=True, lift=1.0, thickness=0.4)
        add_roof_tiles(U_tile, U_maksae, up_roof_w, up_roof_d, roof_h * 1.02,
                       up_eave, hip=True, lift=1.0)
        add_roof_ridges(L_ridge, "ridge", up_roof_w, up_roof_d, roof_h * 1.02, up_eave,
                        hip=True, lift=1.0)
        ridge_top = up_eave + roof_h * 1.02
    else:
        add_roof(L_roof, "roof_base", "wood_dark", roof_w, roof_d, roof_h,
                 eave_base, hip=True, lift=1.0, thickness=0.4)
        add_roof_tiles(L_tile, L_maksae, roof_w, roof_d, roof_h, eave_base,
                       hip=True, lift=1.0)
        add_roof_ridges(L_ridge, "ridge", roof_w, roof_d, roof_h, eave_base,
                        hip=True, lift=1.0)
        ridge_top = eave_base + roof_h

    # signboard: a two-storey hall carries its 편액 on the upper storey
    if sign:
        if double:
            add_sign(U_lintel, sign, 0, -(up_d / 2 + 0.55), ub - 0.45,
                     width=cfg.get("sign_w", 3.4), height=cfg.get("sign_h", 0.85))
        else:
            add_sign(L_lintel, sign, 0, ys[0] - 0.55, top_z + 1.1,
                     width=cfg.get("sign_w", 3.4), height=cfg.get("sign_h", 0.85))

    b.meta["height"] = round(ridge_top, 2)
    b.meta["width"] = W
    b.meta["depth"] = D
    b.meta["tiers"] = 2 if double else 1
    return ridge_top


def build_woldae(b, cfg, z0=0.0):
    L_base = b.bx[0]
    w1, d1 = cfg.get("w1", cfg["w"] + 20), cfg.get("d1", cfg["d"] + 18)
    h1 = cfg.get("woldae_h1", 2.2)
    w2, d2 = cfg.get("w2", cfg["w"] + 10), cfg.get("d2", cfg["d"] + 8)
    h2 = cfg.get("woldae_h2", 2.2)

    # lower tier
    add_box(L_base, "stone", (w1, d1, h1), (0, 0, z0 + h1 / 2), uv_scale=2.8)
    add_box(L_base, "stone_light", (w1 + 0.6, d1 + 0.6, 0.24),
            (0, 0, z0 + h1 + 0.12), uv_scale=2.2)
    # upper tier
    add_box(L_base, "stone", (w2, d2, h2), (0, 0, z0 + h1 + h2 / 2), uv_scale=2.8)
    zt = z0 + h1 + h2
    add_box(L_base, "stone_light", (w2 + 0.6, d2 + 0.6, 0.24), (0, 0, zt + 0.12), uv_scale=2.2)
    top = zt + 0.24

    stairs(L_base, 0, -d1 / 2, z0, z0 + h1 + 0.24, 16, n=5)
    stairs(L_base, 0, -d2 / 2, z0 + h1 + 0.24, top, 12, n=4)

    # stone balustrades, with a gap in the south side for the central stair
    ps, rs = (0.32, 0.32), 0.2
    for tier, (ww, dd, zz, gap) in enumerate((
            (w1, d1, z0 + h1 + 0.24, 8.6),
            (w2, d2, top, 6.6))):
        add_rail(L_base, "stone_light", -ww / 2, dd / 2, ww / 2, dd / 2, zz,
                 height=1.05, post_every=2.4, post_size=ps, rail_size=rs)
        add_rail(L_base, "stone_light", -ww / 2, -dd / 2, -ww / 2, dd / 2, zz,
                 height=1.05, post_every=2.4, post_size=ps, rail_size=rs)
        add_rail(L_base, "stone_light", ww / 2, -dd / 2, ww / 2, dd / 2, zz,
                 height=1.05, post_every=2.4, post_size=ps, rail_size=rs)
        add_rail(L_base, "stone_light", -ww / 2, -dd / 2, -gap / 2, -dd / 2, zz,
                 height=1.05, post_every=2.4, post_size=ps, rail_size=rs)
        add_rail(L_base, "stone_light", gap / 2, -dd / 2, ww / 2, -dd / 2, zz,
                 height=1.05, post_every=2.4, post_size=ps, rail_size=rs)

    # bronze cauldrons (드므) flanking the stair
    for sx in (-1, 1):
        x = sx * 7.6
        add_cyl(L_base, "bronze", 0.58, 0.82, (x, -d2 / 2 + 4.5, top + 0.48),
                segments=18, taper=1.16, uv_scale=1.2)
        add_cyl(L_base, "bronze", 0.70, 0.12, (x, -d2 / 2 + 4.5, top + 0.93),
                segments=18, uv_scale=1.0)
        add_cyl(L_base, "black", 0.60, 0.05, (x, -d2 / 2 + 4.5, top + 0.99),
                segments=18, uv_scale=1.0)
        for k in range(3):
            ang = k * 2.1 + 0.4
            add_box(L_base, "bronze", (0.14, 0.14, 0.34),
                    (x + math.cos(ang) * 0.46,
                     -d2 / 2 + 4.5 + math.sin(ang) * 0.46, top + 0.17),
                    uv_scale=0.5)
    return top


# --------------------------------------------------------------------------
# gates
# --------------------------------------------------------------------------
def arch_base(name, w, d, h, arches, parent, uv_scale=2.6):
    """Stone gate base with true arched passages, via boolean subtraction."""
    for ob in list(bpy.context.selected_objects):
        ob.select_set(False)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, h / 2))
    base = bpy.context.active_object
    base.name = name
    base.scale = (w, d, h)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    base.data.materials.append(MAT["stone"])

    for cx, aw, spring in arches:
        # rectangular lower opening
        bpy.ops.mesh.primitive_cube_add(size=1, location=(cx, 0, spring / 2))
        cut = bpy.context.active_object
        cut.scale = (aw, d + 4, spring)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        mod = base.modifiers.new("cut", "BOOLEAN")
        mod.operation = "DIFFERENCE"
        mod.solver = "EXACT"
        mod.object = cut
        bpy.context.view_layer.objects.active = base
        bpy.ops.object.modifier_apply(modifier=mod.name)
        bpy.data.objects.remove(cut, do_unlink=True)

        # round arch top
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=32, radius=aw / 2, depth=d + 4,
            location=(cx, 0, spring), rotation=(math.pi / 2, 0, 0))
        cut = bpy.context.active_object
        mod = base.modifiers.new("cut", "BOOLEAN")
        mod.operation = "DIFFERENCE"
        mod.solver = "EXACT"
        mod.object = cut
        bpy.context.view_layer.objects.active = base
        bpy.ops.object.modifier_apply(modifier=mod.name)
        bpy.data.objects.remove(cut, do_unlink=True)

    # soften the silhouette a touch
    bev = base.modifiers.new("bevel", "BEVEL")
    bev.width = 0.05
    bev.segments = 1
    bpy.context.view_layer.objects.active = base
    bpy.ops.object.modifier_apply(modifier=bev.name)

    # planar UVs from local coordinates (replace the cube's default UV layer,
    # otherwise the material keeps sampling the stretched 0..1 cube mapping)
    me = base.data
    for layer in list(me.uv_layers):
        me.uv_layers.remove(layer)
    uv = me.uv_layers.new(name="UVMap")
    for poly in me.polygons:
        n = poly.normal
        for li in poly.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            if abs(n.z) > 0.75:
                uv.data[li].uv = (co.x / uv_scale, co.y / uv_scale)
            elif abs(n.x) > abs(n.y):
                uv.data[li].uv = (co.y / uv_scale, co.z / uv_scale)
            else:
                uv.data[li].uv = (co.x / uv_scale, co.z / uv_scale)
    base.parent = parent
    return base


def build_gate(b, cfg):
    (L_base, _L_floor, _L_plinth, _L_col, _L_wall, L_door) = b.lower[:6]
    W, D, H = cfg["w"], cfg["d"], cfg["base_h"]
    arches = cfg["arches"]
    arch_base(f"{b.bid}_base", W, D, H, arches, b.layer_nodes[0])

    # cornice + parapet
    add_box(L_base, "stone_light", (W + 0.9, D + 0.9, 0.45), (0, 0, H + 0.22), uv_scale=2.2)
    top = H + 0.45
    for s in (-1, 1):
        add_box(L_base, "stone", (W, 0.55, 1.0), (0, s * (D / 2 - 0.28), top + 0.5), uv_scale=1.6)
        n = int(W / 1.5)
        for i in range(n):
            x = -W / 2 + 0.7 + (W - 1.4) * i / (n - 1)
            add_box(L_base, "stone", (0.8, 0.62, 0.45), (x, s * (D / 2 - 0.28), top + 1.2), uv_scale=1.0)
    for s in (-1, 1):
        add_box(L_base, "stone", (0.55, D, 1.0), (s * (W / 2 - 0.28), 0, top + 0.5), uv_scale=1.6)

    # pavilion on top
    hall_cfg = dict(cfg)
    hall_cfg.update({
        "base": top + 0.05,
        "platform": False,
        "open_bays": cfg.get("open_bays", 0),
        "walls": cfg.get("walls", True),
        "double": cfg.get("double", False),
    })
    hall_cfg.pop("base_h", None)
    build_hall(b, hall_cfg)

    # railing around the stone terrace
    if cfg.get("terrace_rail", True):
        zr = top + 0.05
        add_rail(L_door, "wood_red", -W / 2 + 1.2, -D / 2 + 0.8, W / 2 - 1.2, -D / 2 + 0.8,
                 zr, height=1.0, post_every=2.4)
        add_rail(L_door, "wood_red", -W / 2 + 1.2, D / 2 - 0.8, W / 2 - 1.2, D / 2 - 0.8,
                 zr, height=1.0, post_every=2.4)
        add_rail(L_door, "wood_red", -W / 2 + 1.2, -D / 2 + 0.8, -W / 2 + 1.2, D / 2 - 0.8,
                 zr, height=1.0, post_every=2.4)
        add_rail(L_door, "wood_red", W / 2 - 1.2, -D / 2 + 0.8, W / 2 - 1.2, D / 2 - 0.8,
                 zr, height=1.0, post_every=2.4)


# --------------------------------------------------------------------------
# hexagonal pavilion (Hyangwonjeong)
# --------------------------------------------------------------------------
def add_hex_roof(b, mat_top, mat_under, radius, h, base_z, cx=0.0, cy=0.0,
                 rings=10, sides=6, lift=0.55, thickness=0.22, uv=(2.2, 1.6),
                 t_max=1.0, power=1.55):
    """Hexagonal hip roof with upturned corners.

    ``t_max`` < 1 stops the surface early, leaving a hexagonal hole in the
    middle: that turns the roof into the skirt below an upper storey.
    """
    nside = sides * 3
    angs = [2 * math.pi * i / nside + math.pi / 6 for i in range(nside)]

    def uplift(ang):
        return lift * (abs(math.sin(sides / 2 * ang)) ** 2.4)

    major = radius

    verts_top, verts_bot = [], []
    for j in range(rings + 1):
        t = t_max * j / rings
        r = radius * (1 - t)
        tt = min(1.0, t / t_max)
        for ang in angs:
            z = h * (tt ** power) + uplift(ang) * ((1 - tt) ** 3.2)
            x, y = cx + r * math.cos(ang), cy + r * math.sin(ang)
            verts_top.append((x, y, base_z + z))
            verts_bot.append((x, y, base_z + z - thickness))

    n = len(verts_top)
    perim = sides * major
    slope = math.hypot(major, h)
    faces_t, uvs_t = [], []
    for j in range(rings):
        for i in range(nside):
            i2 = (i + 1) % nside
            a = j * nside + i
            faces_t.append((a, j * nside + i2, (j + 1) * nside + i2, (j + 1) * nside + i))
            u0 = i / nside * perim / uv[0]
            u1 = (i + 1) / nside * perim / uv[0]
            v0 = j / rings * slope / uv[1]
            v1 = (j + 1) / rings * slope / uv[1]
            uvs_t.append([(u0, v0), (u1, v0), (u1, v1), (u0, v1)])
    b.add(mat_top, verts_top + verts_bot, faces_t, uvs_t)

    faces_u, uvs_u = [], []
    for j in range(rings):
        for i in range(nside):
            i2 = (i + 1) % nside
            a = n + j * nside + i
            faces_u.append((a, n + (j + 1) * nside + i, n + (j + 1) * nside + i2, n + j * nside + i2))
            u0 = i / nside * perim / 3.0
            u1 = (i + 1) / nside * perim / 3.0
            v0 = j / rings * slope / 3.0
            v1 = (j + 1) / rings * slope / 3.0
            uvs_u.append([(u0, v0), (u0, v1), (u1, v1), (u1, v0)])
    b.add(mat_under, verts_top + verts_bot, faces_u, uvs_u)

    # rim: eave always, inner rim only for a skirt roof
    faces_r = []
    for i in range(nside):
        i2 = (i + 1) % nside
        faces_r.append((i, n + i, n + i2, i2))
        if t_max < 0.999:
            k = rings * nside
            faces_r.append((k + i, k + i2, n + k + i2, n + k + i))
    b.add(mat_under, verts_top + verts_bot, faces_r, [[(0, 0)] * 4 for _ in faces_r])

    # eave trim, following the same uplift curve as the surface
    pts = [(cx + radius * math.cos(a), cy + radius * math.sin(a),
            base_z + uplift(a) + 0.03) for a in angs]
    pts.append(pts[0])
    add_tube(b, mat_top, pts, 0.1, sides=5, uv_scale=1.0)
    return base_z + h


def hex_roof_tiles(bt, bm, radius, h, base_z, cx=0.0, cy=0.0, sides=6,
                   lift=0.55, power=1.55, t_max=1.0, rings=6,
                   pitch=TILE_PITCH, mat="roof", mat_edge="roof_dark"):
    """기와 + 막새 skin for an :func:`add_hex_roof` surface.

    The hex roof is a cone of revolution with six upswept corners, so the tile
    rows run radially while the courses follow the rings.
    """
    def uplift(ang):
        return lift * (abs(math.sin(sides / 2 * ang)) ** 2.4)

    def at(ang, t):
        tt = max(0.0, min(1.0, t / t_max))
        r = radius * (1 - t)
        return (cx + r * math.cos(ang), cy + r * math.sin(ang),
                base_z + h * (tt ** power) + uplift(ang) * ((1 - tt) ** 3.2))

    t_end = 0.965 * t_max
    # The plate needs a much finer polar grid than the substrate: with the bare
    # hex corners (every 20°) one quad would swallow several tile courses and
    # the texture would break into dark blocks.
    nplate = sides * 12
    plate_angs = [2 * math.pi * i / nplate + math.pi / 6
                  for i in range(nplate + 1)]
    rows = [[at(a, t_end * j / rings) for a in plate_angs]
            for j in range(rings + 1)]

    ncol = max(6, int(round(2 * math.pi * radius / pitch)))
    col_angs = [2 * math.pi * k / ncol for k in range(ncol)]
    columns = [[at(a, t_end * j / 6) for j in range(7)] for a in col_angs]

    add_tile_field(bt, mat, [rows])
    add_tile_ridges(bt, mat, columns)
    add_maksae(bm, mat_edge, [[at(a, 0.0) for a in plate_angs]],
               [(at(a, 0.0), (math.cos(a), math.sin(a))) for a in col_angs])


def build_hex_pavilion(b, cfg):
    (L_base, L_floor, L_plinth, L_col, _L_wall, L_door, L_lintel, L_frame,
     L_brack, L_purlin, L_raft, L_eave, L_hip, L_roof, L_tile,
     L_maksae) = b.lower
    (U_floor, U_col, _U_wall, U_door, U_lintel, U_brack, U_purlin, U_raft,
     U_eave, U_hip, U_roof, U_tile, U_maksae) = b.upper
    L_ridge = b.ridge
    r = cfg["radius"]
    ch1 = cfg.get("col_h1", 3.4)
    ch2 = cfg.get("col_h2", 2.6)
    base_h = cfg.get("platform_h", 0.9)
    z0 = cfg.get("base", 0.0)

    # hexagonal stone base with two short flights of steps
    add_cyl(L_base, "stone", r * 1.16, base_h, (0, 0, z0 + base_h / 2), segments=6,
            rot=(0, 0, math.pi / 6), uv_scale=2.0)
    add_cyl(L_base, "stone_light", r * 1.24, 0.2, (0, 0, z0 + base_h + 0.1), segments=6,
            rot=(0, 0, math.pi / 6), uv_scale=1.6)
    z0 += base_h + 0.2
    for s in (-1, 1):
        for k in range(3):
            add_box(L_base, "stone", (3.2, 0.7, 0.3 * (k + 1)),
                    (0, s * (r * 1.06 + 0.7 + k * 0.7), z0 - 0.2 - 0.3 * (k + 1) / 2 + 0.1),
                    uv_scale=1.4)

    corners = [(math.cos(math.pi / 6 + 2 * math.pi * i / 6),
                math.sin(math.pi / 6 + 2 * math.pi * i / 6)) for i in range(6)]

    # ---- 마루: the hexagonal deck
    add_cyl(L_floor, "wood_floor", r * 1.02, 0.24, (0, 0, z0 + 0.12), segments=6,
            rot=(0, 0, math.pi / 6), uv_scale=1.6)

    # ---- 초석 · 기둥
    for cx, cy in corners:
        add_box(L_plinth, "stone_light", (0.72, 0.72, 0.26),
                (cx * r * 0.92, cy * r * 0.92, z0 + 0.13), uv_scale=0.9)
        add_cyl(L_col, "wood_red", 0.24, ch1, (cx * r * 0.92, cy * r * 0.92, z0 + 0.26 + ch1 / 2),
                segments=10, taper=0.98, uv_scale=1.3)
    add_hex_railing(L_door, 0, 0, r * 0.95, z0 + 0.3)

    # ---- 창방 · 평방
    add_cyl(L_lintel, "dancheong", r * 0.99, 0.55, (0, 0, z0 + ch1 + 0.05), segments=6,
            rot=(0, 0, math.pi / 6), uv_scale=1.6)
    add_cyl(L_lintel, "red_deep", r * 1.06, 0.24, (0, 0, z0 + ch1 + 0.45), segments=6,
            rot=(0, 0, math.pi / 6), uv_scale=1.4)

    # ---- bracket sets (공포) on every corner column and between the bays
    bz = z0 + ch1 + 0.57
    col_pts = [(math.cos(math.pi / 6 + k * math.pi / 3) * r * 0.94,
                math.sin(math.pi / 6 + k * math.pi / 3) * r * 0.94) for k in range(6)]
    for k in range(6):
        x, y = col_pts[k]
        bracket(L_brack, x, y, bz, "x", 0.42)
        nx, ny = col_pts[(k + 1) % 6]
        bracket(L_brack, (x + nx) / 2, (y + ny) / 2, bz, "x", 0.36)

    # ---- 도리: the hexagonal purlin ring on top of the brackets
    ring = [(math.cos(math.pi / 6 + k * math.pi / 3) * r * 1.02,
             math.sin(math.pi / 6 + k * math.pi / 3) * r * 1.02,
             bz + 0.4) for k in range(6)]
    for k in range(6):
        add_tube(L_purlin, "wood_dark", [ring[k], ring[(k + 1) % 6]], 0.14,
                 sides=5, uv_scale=0.9)
        # 장혀: a thinner board tucked under the purlin
        add_tube(L_purlin, "wood_dark",
                 [(ring[k][0] * 0.98, ring[k][1] * 0.98, bz + 0.24),
                  (ring[(k + 1) % 6][0] * 0.98, ring[(k + 1) % 6][1] * 0.98, bz + 0.24)],
                 0.09, sides=5, uv_scale=0.8)

    # ---- 가구: the six beams that cross the well and carry the upper storey
    for k in range(6):
        a = math.pi / 6 + k * math.pi / 3
        add_tube(L_frame, "wood_dark",
                 [(math.cos(a) * r * 0.94, math.sin(a) * r * 0.94, bz + 0.55),
                  (0.0, 0.0, bz + 0.62)], 0.12, sides=5, uv_scale=0.9)
    add_cyl(L_frame, "wood_dark", 0.52, 0.34, (0, 0, bz + 0.62), segments=6, uv_scale=0.8)

    # ---- rafter field under the skirt eave
    low_r = r * 1.52
    for k in range(6):
        ax, ay = col_pts[k]
        bx, by = col_pts[(k + 1) % 6]
        for j in range(6):
            t = (j + 0.5) / 6
            px, py = ax + (bx - ax) * t, ay + (by - ay) * t
            ln = math.hypot(px, py) or 1.0
            ux, uy = px / ln, py / ln
            add_tube(L_raft, "wood_dark",
                     [(ux * r, uy * r, bz + 0.45),
                      (ux * low_r * 0.99, uy * low_r * 0.99, bz + 0.14)],
                     0.09, sides=5, uv_scale=0.8)

    # ---- 부연 · 평고대: the outer tier of the skirt eave
    skirt_base = bz + 0.52
    for k in range(6):
        ax, ay = col_pts[k]
        bx, by = col_pts[(k + 1) % 6]
        for j in range(6):
            t = (j + 0.5) / 6
            px, py = ax + (bx - ax) * t, ay + (by - ay) * t
            ln = math.hypot(px, py) or 1.0
            ux, uy = px / ln, py / ln
            ang = math.atan2(uy, ux)
            edge = skirt_base + 0.72 * (abs(math.sin(3.0 * ang)) ** 2.4)
            add_tube(L_eave, "wood_red",
                     [(ux * low_r * 0.84, uy * low_r * 0.84, bz + 0.34),
                      (ux * low_r * 1.0, uy * low_r * 1.0, edge - 0.06)],
                     0.075, sides=5, uv_scale=0.8)
    fascia = []
    for i in range(18 + 1):
        ang = 2 * math.pi * i / 18 + math.pi / 6
        fascia.append((math.cos(ang) * low_r * 0.995, math.sin(ang) * low_r * 0.995,
                       skirt_base + 0.72 * (abs(math.sin(3.0 * ang)) ** 2.4) - 0.18))
    add_tube(L_eave, "wood_dark", fascia, 0.09, sides=5, uv_scale=1.0)

    # ---- 추녀 · 사래 at the six skirt corners
    for i in range(6):
        ang = math.pi / 6 + i * math.pi / 3
        x0, y0 = math.cos(ang) * r * 0.94, math.sin(ang) * r * 0.94
        x1, y1 = math.cos(ang) * low_r * 0.99, math.sin(ang) * low_r * 0.99
        add_tube(L_hip, "wood_dark",
                 [(x0, y0, bz + 0.44),
                  ((x0 + x1) / 2, (y0 + y1) / 2, bz + 0.28),
                  (x1, y1, skirt_base + 0.72)],
                 0.15, sides=6, uv_scale=1.0)
        add_tube(L_hip, "wood_red",
                 [(x0 * 0.6 + x1 * 0.4, y0 * 0.6 + y1 * 0.4, bz + 0.32),
                  (x1, y1, skirt_base + 0.79)],
                 0.09, sides=5, uv_scale=0.85)

    # ---- skirt roof, then the second storey emerges from it
    skirt_h = 1.45
    hole_r = r * 0.86
    t_max = 1.0 - hole_r / low_r
    z1 = add_hex_roof(L_roof, "roof_base", "wood_dark", low_r, skirt_h, skirt_base,
                      0, 0, lift=0.72, thickness=0.3, rings=8, t_max=t_max)
    hex_roof_tiles(L_tile, L_maksae, low_r, skirt_h, skirt_base,
                   lift=0.72, rings=7, t_max=t_max)

    # ---- 상층 마루 · 기둥 · 난간
    add_cyl(U_floor, "wood_floor", r * 0.95, 0.2, (0, 0, z1 + 0.1), segments=6,
            rot=(0, 0, math.pi / 6), uv_scale=1.4)
    for cx, cy in corners:
        add_cyl(U_col, "wood_red", 0.2, ch2,
                (cx * r * 0.84, cy * r * 0.84, z1 + 0.2 + ch2 / 2),
                segments=10, taper=0.98, uv_scale=1.1)
    add_hex_railing(U_door, 0, 0, r * 0.86, z1 + 0.22, height=0.8, panel=True)

    # ---- 상층 창방 · 평방
    ub = z1 + 0.2 + ch2
    add_cyl(U_lintel, "dancheong", r * 0.9, 0.45, (0, 0, ub - 0.225), segments=6,
            rot=(0, 0, math.pi / 6), uv_scale=1.4)
    add_cyl(U_lintel, "red_deep", r * 0.96, 0.22, (0, 0, ub + 0.11), segments=6,
            rot=(0, 0, math.pi / 6), uv_scale=1.3)

    # ---- 상층 공포: one bracket set on each of the six columns
    for cx, cy in corners:
        bracket(U_brack, cx * r * 0.84, cy * r * 0.84, ub + 0.25, "x", 0.46)

    # ---- 상층 도리 · 장혀: the hexagonal purlin ring
    ring6 = [(math.cos(math.pi / 6 + k * math.pi / 3) * r * 0.85,
              math.sin(math.pi / 6 + k * math.pi / 3) * r * 0.85) for k in range(6)]
    for k in range(6):
        a0, a1 = ring6[k], ring6[(k + 1) % 6]
        add_tube(U_purlin, "wood_dark",
                 [(a0[0], a0[1], ub + 0.74), (a1[0], a1[1], ub + 0.74)],
                 0.13, sides=5, uv_scale=0.9)
        add_tube(U_purlin, "wood_dark",
                 [(a0[0], a0[1], ub + 0.52), (a1[0], a1[1], ub + 0.52)],
                 0.08, sides=5, uv_scale=0.8)

    # ---- top roof: rafters, flying rafters, roof, then the finial
    up_r = r * 1.34
    up_base = ub + 0.95

    def hex_edge(ang):
        return up_base + 0.8 * (abs(math.sin(3.0 * ang)) ** 2.4)

    for i in range(24):
        ang = 2 * math.pi * i / 24 + math.pi / 12
        edge = hex_edge(ang)
        add_tube(U_raft, "wood_dark",
                 [(math.cos(ang) * r * 0.86, math.sin(ang) * r * 0.86, up_base + 0.24),
                  (math.cos(ang) * up_r * 0.96, math.sin(ang) * up_r * 0.96, edge - 0.08)],
                 0.075, sides=5, uv_scale=0.8)

    # ---- 상층 부연 · 평고대: the outer, flying tier of the top eave
    for i in range(24):
        ang = 2 * math.pi * i / 24 + math.pi / 12
        edge = hex_edge(ang)
        add_tube(U_eave, "wood_red",
                 [(math.cos(ang) * up_r * 0.82, math.sin(ang) * up_r * 0.82, up_base + 0.04),
                  (math.cos(ang) * up_r * 1.01, math.sin(ang) * up_r * 1.01, edge - 0.02)],
                 0.065, sides=5, uv_scale=0.8)
    fascia = []
    for i in range(36 + 1):
        ang = 2 * math.pi * i / 36 + math.pi / 6
        fascia.append((math.cos(ang) * up_r * 1.0, math.sin(ang) * up_r * 1.0,
                       hex_edge(ang) - 0.15))
    add_tube(U_eave, "wood_dark", fascia, 0.085, sides=5, uv_scale=1.0)

    # ---- 상층 추녀 · 사래 at the six corners of the top roof
    for k in range(6):
        ang = math.pi / 6 + k * math.pi / 3
        x0, y0 = math.cos(ang) * r * 0.84, math.sin(ang) * r * 0.84
        x1, y1 = math.cos(ang) * up_r, math.sin(ang) * up_r
        add_tube(U_hip, "wood_dark",
                 [(x0, y0, ub + 0.72),
                  ((x0 + x1) / 2, (y0 + y1) / 2, up_base - 0.04),
                  (x1, y1, up_base + 0.78)],
                 0.13, sides=6, uv_scale=1.0)
        add_tube(U_hip, "wood_red",
                 [(x0 * 0.55 + x1 * 0.45, y0 * 0.55 + y1 * 0.45, up_base + 0.06),
                  (x1, y1, up_base + 0.84)],
                 0.08, sides=5, uv_scale=0.85)

    # ---- 상층 지붕, the finial and the six descending ridges
    apex = add_hex_roof(U_roof, "roof_base", "wood_dark", up_r, 2.9, up_base, 0, 0,
                        lift=0.8, thickness=0.3, rings=12)
    hex_roof_tiles(U_tile, U_maksae, up_r, 2.9, up_base, lift=0.8, rings=10)
    add_cyl(L_ridge, "gold", 0.1, 1.5, (0, 0, apex + 0.75), segments=8, uv_scale=1.0, caps=False)
    for k in range(3):
        add_cyl(L_ridge, "gold", 0.4 - k * 0.09, 0.12, (0, 0, apex + 0.42 + k * 0.4),
                segments=10, uv_scale=0.8)
    add_sphere(L_ridge, "gold", 0.26, (0, 0, apex + 1.62), segs=8, rings=5)

    # ---- 용마루: the six descending ridges that meet at the finial
    for k in range(6):
        ang = math.pi / 6 + k * math.pi / 3
        pts = []
        for j in range(7):
            t = j / 6
            rr = up_r * (1 - t)
            zz = 2.9 * (t ** 1.55) + 0.8 * ((1 - t) ** 3.2)
            pts.append((math.cos(ang) * rr, math.sin(ang) * rr, up_base + zz + 0.07))
        add_tube(L_ridge, "ridge", pts, 0.1, sides=5, uv_scale=1.0)

    if cfg.get("sign"):
        add_sign(U_lintel, cfg["sign"], 0, -(r * 0.94), z1 + ch2 * 0.62,
                 width=1.9, height=0.5)
    b.meta["height"] = round(apex + 1.7, 2)
    b.meta["width"] = round(r * 2, 2)
    b.meta["depth"] = round(r * 2, 2)
    b.meta["tiers"] = 2


def add_hex_railing(b, cx, cy, r, z, height=0.95, panel=False):
    pts = []
    for i in range(6):
        ang = math.pi / 6 + 2 * math.pi * i / 6
        pts.append((cx + math.cos(ang) * r, cy + math.sin(ang) * r, z))
    for i in range(6):
        x0, y0, _ = pts[i]
        x1, y1, _ = pts[(i + 1) % 6]
        add_rail(b, "wood_red", x0, y0, x1, y1, z, height=height, post_every=1.4,
                 post_size=(0.1, 0.1), rail_size=0.09)
        if panel:
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2
            ang = math.atan2(y1 - y0, x1 - x0)
            add_box(b, "dancheong", (math.hypot(x1 - x0, y1 - y0) - 0.4, 0.07, height * 0.5),
                    (mx, my, z + height * 0.5), rot=(0, 0, ang), uv_scale=1.4)


# --------------------------------------------------------------------------
# corridors / walls / site
# --------------------------------------------------------------------------
def add_corridor(b, x0, y0, x1, y1, width=5.8, col_h=4.3):
    length = math.hypot(x1 - x0, y1 - y0)
    ang = math.atan2(y1 - y0, x1 - x0)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    dx, dy = math.cos(ang), math.sin(ang)
    px, py = -dy, dx
    n = max(2, int(length / 2.9))
    z0 = 0.35
    for i in range(n + 1):
        t = i / n
        bx, by = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
        for s in (-1, 1):
            add_cyl(b, "wood_red", 0.2, col_h, (bx + px * s * width / 2, by + py * s * width / 2,
                                               z0 + col_h / 2), segments=8, uv_scale=1.2)
            add_box(b, "stone_light", (0.55, 0.55, 0.22),
                    (bx + px * s * width / 2, by + py * s * width / 2, z0 / 2), uv_scale=0.8)
    for s in (-1, 1):
        wx, wy = cx + px * s * width / 2, cy + py * s * width / 2
        add_box(b, "plaster", (length, 0.32, 1.85), (wx, wy, z0 + 0.92), rot=(0, 0, ang), uv_scale=1.8)
        add_box(b, "wood_dark", (length, 0.4, 0.3), (wx, wy, z0 + 0.2), rot=(0, 0, ang), uv_scale=1.2)
        add_lattice_panel(b, wx + px * s * 0.18, wy + py * s * 0.18, z0 + 1.25,
                          length - 0.5, 0.8, rot_z=ang, facing_south=(s < 0))
        add_box(b, "wood_dark", (length, 0.3, 0.22), (wx, wy, z0 + 2.05), rot=(0, 0, ang), uv_scale=1.2)
    add_box(b, "dancheong", (length, 0.4, 0.5), (cx, cy, z0 + col_h - 0.25), rot=(0, 0, ang), uv_scale=2.0)
    add_box(b, "red_deep", (length, 0.5, 0.25), (cx, cy, z0 + col_h + 0.1), rot=(0, 0, ang), uv_scale=1.6)
    rotate = 0.0 if abs(ang) < 1 else math.pi / 2
    add_roof(b, "roof_base", "wood_dark", length + 1.4, width + 2.6, 1.85,
             z0 + col_h + 0.3, hip=False, lift=0.35, thickness=0.26, nx=24, ny=8,
             uv=(2.4, 1.8), loc=(cx, cy), rot_z=rotate)
    add_roof_tiles(b, b, length + 1.4, width + 2.6, 1.85, z0 + col_h + 0.3,
                   hip=False, lift=0.35, loc=(cx, cy), rot_z=rotate)
    add_tube(b, "ridge", [(cx - math.cos(ang) * (length / 2 + 0.7), cy - math.sin(ang) * (length / 2 + 0.7),
                           z0 + col_h + 2.15),
                          (cx + math.cos(ang) * (length / 2 + 0.7), cy + math.sin(ang) * (length / 2 + 0.7),
                           z0 + col_h + 2.15)], 0.15, sides=6)


def add_wall(b, x0, y0, x1, y1, h=4.8):
    length = math.hypot(x1 - x0, y1 - y0)
    ang = math.atan2(y1 - y0, x1 - x0)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    add_box(b, "stone_dark", (length, 2.0, 0.9), (cx, cy, 0.45), rot=(0, 0, ang), uv_scale=2.4)
    add_box(b, "plaster_wall", (length, 1.6, h - 0.9), (cx, cy, 0.9 + (h - 0.9) / 2),
            rot=(0, 0, ang), uv_scale=2.0)
    add_box(b, "wood_dark", (length, 1.8, 0.22), (cx, cy, h - 0.15), rot=(0, 0, ang), uv_scale=1.6)
    add_prism(b, "roof", [(-1.25, 0), (1.25, 0), (0, 0.62)], length + 0.5,
              (cx, cy, h - 0.05), rot=(0, 0, ang + math.pi / 2), uv_scale=2.0)
    add_tube(b, "ridge", [(cx - math.cos(ang) * length / 2, cy - math.sin(ang) * length / 2, h + 0.56),
                          (cx + math.cos(ang) * length / 2, cy + math.sin(ang) * length / 2, h + 0.56)],
             0.12, sides=6)


def add_pond(b, x, y, w, d, island=None):
    rim_w = 1.2
    add_box(b, "stone_dark", (w, rim_w, 0.55), (x, y - d / 2, 0.27), uv_scale=1.6)
    add_box(b, "stone_dark", (w, rim_w, 0.55), (x, y + d / 2, 0.27), uv_scale=1.6)
    add_box(b, "stone_dark", (rim_w, d, 0.55), (x - w / 2, y, 0.27), uv_scale=1.6)
    add_box(b, "stone_dark", (rim_w, d, 0.55), (x + w / 2, y, 0.27), uv_scale=1.6)
    add_plane(b, "water", (w - rim_w * 1.6, d - rim_w * 1.6), (x, y, 0.28), uv_scale=9.0)
    if island:
        iw, id_, ih = island[:3]
        top = island[3] if len(island) > 3 else "stone"
        add_box(b, "stone_dark", (iw, id_, ih), (x, y, ih / 2), uv_scale=2.4)
        add_box(b, top, (iw + 0.2, id_ + 0.2, 0.16), (x, y, ih + 0.08), uv_scale=3.2)


def add_bridge(b, x, y, length, width, rot_z=0.0):
    ca, sa = math.cos(rot_z), math.sin(rot_z)
    add_box(b, "stone_light", (length, width, 0.55), (x, y, 1.0), rot=(0, 0, rot_z), uv_scale=2.0)
    for s in (-1, 1):
        ox, oy = -sa * s * width / 2, ca * s * width / 2
        add_rail(b, "stone_light", x - ca * length / 2 + ox, y - sa * length / 2 + oy,
                 x + ca * length / 2 + ox, y + sa * length / 2 + oy, 1.28,
                 height=0.9, post_every=1.6, post_size=(0.16, 0.16), rail_size=0.14)


def build_site():
    b = site
    # ground
    add_plane(b, "ground", (900, 900), (0, 0, -0.06), uv_scale=7.0)
    # paving: main courtyard, gate courts, northern quarters
    add_plane(b, "paving", (88, 96), (0, -3, 0.015), uv_scale=4.2)
    add_plane(b, "paving", (58, 52), (0, -76, 0.016), uv_scale=4.2)
    add_plane(b, "paving", (42, 58), (0, -128, 0.016), uv_scale=4.2)
    add_plane(b, "paving", (64, 40), (0, 84, 0.017), uv_scale=4.2)
    add_plane(b, "paving", (26, 16), (-70, 20, 0.018), uv_scale=4.2)
    add_plane(b, "paving", (14, 20), (58, 131, 0.018), uv_scale=4.2)
    add_plane(b, "paving", (34, 28), (48, 96, 0.018), uv_scale=4.2)
    add_plane(b, "paving", (32, 26), (-45, 104, 0.018), uv_scale=4.2)

    # corridors framing the main courtyard
    add_corridor(b, -44, -46, -44, 40, width=5.6)
    add_corridor(b, 44, -46, 44, 40, width=5.6)
    add_corridor(b, -44, 40, 44, 40, width=6.2)

    # palace walls
    add_wall(b, -114, -176, -22, -176)
    add_wall(b, 22, -176, 114, -176)
    add_wall(b, -114, 176, 114, 176)
    add_wall(b, -114, -176, -114, 176)
    add_wall(b, 114, -176, 114, 176)

    # ponds
    add_pond(b, -82, 20, 50, 44, island=(27, 21, 1.25))
    add_pond(b, 58, 146, 34, 28, island=(15, 13, 1.25, "ground"))
    add_bridge(b, -64.5, 20, 13, 5.4, rot_z=0.0)
    add_bridge(b, 58, 136.5, 11, 4.2, rot_z=math.pi / 2)

    # pumgyeseok (rank stones) flanking the approach to Geunjeongjeon
    for side in (-1, 1):
        for i in range(6):
            x = side * 6.2
            y = -42 + i * 4.4
            add_box(b, "stone_light", (0.55, 0.55, 1.35), (x, y, 0.68), uv_scale=0.8)
            add_box(b, "stone_light", (0.72, 0.72, 0.14), (x, y, 1.42), uv_scale=0.6)

    # lanterns
    add_lantern(b, -30, -46, 0, 1.15)
    add_lantern(b, 30, -46, 0, 1.15)
    add_lantern(b, -72, 6, 0, 0.95)
    add_lantern(b, -96, 34, 0, 0.95)
    add_lantern(b, 40, 128, 0, 0.95)
    add_lantern(b, 76, 146, 0, 0.95)
    add_lantern(b, -30, 84, 0, 0.9)
    add_lantern(b, 30, 84, 0, 0.9)

    # rocks around the ponds
    rng = random.Random(11)
    for (px, py, pw, pd) in [(-82, 20, 44, 40), (58, 146, 34, 28)]:
        for i in range(16):
            ang = rng.uniform(0, math.tau)
            add_rock(b, px + math.cos(ang) * (pw / 2 + rng.uniform(0.4, 5.0)),
                     py + math.sin(ang) * (pd / 2 + rng.uniform(0.4, 5.0)),
                     rng, rng.uniform(0.5, 1.2))
    # a few rocks on the islands
    for i in range(7):
        ang = rng.uniform(0, math.tau)
        add_rock(b, -82 + math.cos(ang) * 13.4, 20 + math.sin(ang) * 10.4, rng,
                 rng.uniform(0.35, 0.75))
    for i in range(5):
        ang = rng.uniform(0, math.tau)
        add_rock(b, 58 + math.cos(ang) * 6.2, 146 + math.sin(ang) * 5.2, rng,
                 rng.uniform(0.3, 0.6))

    # ------------------------------------------------------------------
    # trees
    # ------------------------------------------------------------------
    tree_rng = random.Random(37)
    # (cx, cy, w, d) rectangles that must stay clear of trees
    exclusions = [
        (0, -3, 96, 104),          # main courtyard + corridors
        (0, -128, 46, 110),        # gate approach
        (0, 8, 64, 50),            # geunjeongjeon + woldae
        (0, 68, 30, 24),
        (0, 100, 36, 26),
        (0, 134, 30, 24),
        (48, 96, 28, 22),
        (-45, 104, 28, 22),
        (-82, 20, 52, 48),         # gyeonghoeru pond
        (58, 146, 42, 36),         # hyangwon pond
        (0, 42, 92, 14),           # north corridor
    ]

    def free(x, y, pad=2.5):
        for ex, ey, ew, ed in exclusions:
            if abs(x - ex) < ew / 2 + pad and abs(y - ey) < ed / 2 + pad:
                return False
        return True

    placed = []
    zones = [
        # (x0, y0, x1, y1, count)
        (-110, -172, -52, -14, 16),
        (-110, -172, -22, -60, 6),
        (52, -172, 110, 78, 22),
        (-110, 46, -56, 76, 8),
        (-110, 82, 110, 172, 26),
        (-160, -240, -24, -186, 14),
        (24, -240, 160, -186, 14),
        (-240, -240, -124, 200, 26),
        (124, -240, 240, 200, 26),
        (-120, 190, 120, 260, 14),
    ]
    for x0, y0, x1, y1, count in zones:
        tries = 0
        made = 0
        # plant in groves: a clump centre, then a few trees around it
        while made < count and tries < count * 40:
            tries += 1
            gx = tree_rng.uniform(x0, x1)
            gy = tree_rng.uniform(y0, y1)
            if not free(gx, gy):
                continue
            clump = tree_rng.randint(2, 5)
            for _ in range(clump):
                if made >= count:
                    break
                x = gx + tree_rng.gauss(0, 3.4)
                y = gy + tree_rng.gauss(0, 3.4)
                if not (x0 <= x <= x1 and y0 <= y <= y1) or not free(x, y):
                    continue
                if any((x - px) ** 2 + (y - py) ** 2 < 25 for px, py in placed):
                    continue
                placed.append((x, y))
                add_tree(b, x, y, tree_rng, scale=tree_rng.uniform(0.7, 1.3))
                made += 1

    # a handful of deliberate garden trees (outside the ceremonial courtyards)
    for (x, y, s) in [(-62, 60, 0.9), (74, 74, 0.9), (-96, 60, 0.95),
                      (96, 120, 0.95), (-58, -30, 0.8), (58, -34, 0.8)]:
        add_tree(b, x, y, tree_rng, scale=s)


# --------------------------------------------------------------------------
# build all buildings
# --------------------------------------------------------------------------
buildings = []


def make(bid, ko, hanja, x, y, kind, year, builder, **extra):
    b = Building(bid, ko, hanja, (x, y, 0.0), kind=kind, year=year, **extra)
    builder(b)
    b.emit()
    buildings.append(b)
    return b


make("gwanghwamun", "광화문", "光化門", 0, -156, "gate", "1395 · 1867 중건", lambda b: build_gate(b, {
    "w": 38, "d": 14, "base_h": 11.0,
    "arches": [(-11.0, 4.6, 5.2), (0.0, 6.2, 5.6), (11.0, 4.6, 5.2)],
    "col_h": 5.4, "roof_h": 5.6, "double": True, "bays_x": 5, "bays_y": 2,
    "walls": True, "sign": "gwanghwamun", "sign_w": 3.8, "sign_h": 0.95,
    "overhang": 2.4, "col_r": 0.3,
}), sign_note="사직로 방면 정문")

make("heungnyemun", "흥례문", "興禮門", 0, -100, "gate", "1395 · 1867 중건", lambda b: build_gate(b, {
    "w": 26, "d": 11, "base_h": 6.4,
    "arches": [(-7.0, 3.6, 3.0), (0.0, 4.6, 3.4), (7.0, 3.6, 3.0)],
    "col_h": 5.8, "roof_h": 4.4, "bays_x": 3, "bays_y": 2,
    "walls": True, "open_bays": 0, "sign": "heungnyemun",
    "overhang": 2.1, "col_r": 0.3, "double": False,
}))

make("geunjeongmun", "근정문", "勤政門", 0, -52, "gate", "1395 · 1867 중건", lambda b: build_gate(b, {
    "w": 32, "d": 12, "base_h": 6.8,
    "arches": [(-8.2, 3.8, 3.5), (0.0, 5.0, 4.0), (8.2, 3.8, 3.5)],
    "col_h": 6.4, "roof_h": 4.9, "bays_x": 3, "bays_y": 2,
    "walls": True, "open_bays": 0, "sign": "geunjeongmun",
    "overhang": 2.3, "col_r": 0.32,
}))

make("geunjeongjeon", "근정전", "勤政殿", 0, 8, "hall", "1395 · 1867 중건", lambda b: build_hall(b, {
    "w": 30, "d": 21, "col_h": 9.0, "roof_h": 5.4, "double": True,
    "woldae": True, "w1": 56, "d1": 42, "w2": 42, "d2": 30,
    "woldae_h1": 2.2, "woldae_h2": 2.2,
    "bays_x": 5, "bays_y": 4, "open_bays": 1, "interior": True,
    "sign": "geunjeongjeon", "sign_w": 4.4, "sign_h": 1.05,
    "overhang": 2.6, "col_r": 0.42, "platform": True, "platform_h": 0.9,
}), sign_note="조선 왕조의 정전")

make("sajeongjeon", "사정전", "思政殿", 0, 68, "hall", "1395 · 1867 중건", lambda b: build_hall(b, {
    "w": 22, "d": 15, "col_h": 7.0, "roof_h": 4.3, "bays_x": 3, "bays_y": 3,
    "sign": "sajeongjeon", "col_r": 0.33, "overhang": 2.1,
}))

make("gangnyeongjeon", "강녕전", "康寧殿", 0, 100, "hall", "1395 · 1867 중건", lambda b: build_hall(b, {
    "w": 28, "d": 17, "col_h": 7.4, "roof_h": 4.7, "bays_x": 5, "bays_y": 3,
    "sign": "gangnyeongjeon", "col_r": 0.36, "overhang": 2.2,
}))

make("gyotaejeon", "교태전", "交泰殿", 0, 134, "hall", "1440 · 1867 중건", lambda b: build_hall(b, {
    "w": 22, "d": 15, "col_h": 7.0, "roof_h": 4.3, "bays_x": 3, "bays_y": 3,
    "sign": "gyotaejeon", "col_r": 0.33, "overhang": 2.1,
}))

make("jagyeongjeon", "자경전", "慈慶殿", 48, 96, "hall", "1865", lambda b: build_hall(b, {
    "w": 20, "d": 14, "col_h": 6.6, "roof_h": 4.0, "bays_x": 3, "bays_y": 3,
    "sign": "jagyeongjeon", "col_r": 0.32, "overhang": 2.0,
}))

make("sujeongjeon", "수정전", "修政殿", -45, 104, "hall", "1867", lambda b: build_hall(b, {
    "w": 20, "d": 14, "col_h": 6.4, "roof_h": 4.0, "bays_x": 3, "bays_y": 3,
    "sign": "sujeongjeon", "col_r": 0.31, "overhang": 2.0,
}))

make("gyeonghoeru", "경회루", "慶會樓", -82, 20, "pavilion", "1412 · 1867 중건", lambda b: build_hall(b, {
    "w": 26, "d": 18, "col_h": 5.0, "roof_h": 5.2, "double": True, "open_upper": True,
    "bays_x": 5, "bays_y": 3, "walls": False, "railing": True,
    "platform": False, "base": 1.25, "sign": "gyeonghoeru",
    "sign_w": 3.4, "sign_h": 0.8, "overhang": 2.5, "col_r": 0.38,
    "skirt_h": 2.2, "upper_col_h": 3.2,
}), sign_note="누각 · 연회와 외교의 장소")

make("hyangwonjeong", "향원정", "香遠亭", 58, 146, "pavilion", "1873", lambda b: build_hex_pavilion(b, {
    "radius": 4.4, "col_h1": 3.0, "col_h2": 2.2, "platform_h": 0.9,
    "base": 1.33, "sign": "hyangwonjeong",
}), sign_note="육각형 정자 · 향원지")

build_site()
site.emit(site_root, COLL)

# --------------------------------------------------------------------------
# layer report — every part must hold geometry, and each part's z-range is
# printed so the exploded stack can be sanity-checked
# --------------------------------------------------------------------------
def _z_range(node):
    zs = []
    for child in node.children_recursive:
        if child.type == "MESH" and child.data and len(child.data.vertices):
            zs.extend(v.co.z for v in child.data.vertices)
    return (min(zs), max(zs)) if zs else None


def layer_report():
    """Print each building's members bottom-up and flag unexpected empty slots.

    Only the wall slots are allowed to stay empty: the open pavilions
    (경회루 · 향원정) have no walls on either storey, and single-storey halls
    have no upper storey at all.
    """
    expected = {
        ("gyeonghoeru", "wall"), ("hyangwonjeong", "wall"),
        ("gyeonghoeru", "upper_wall"), ("hyangwonjeong", "upper_wall"),
    }
    group_of = {k: g for k, _label, g in LAYERS}
    tier_of = {b.bid: b.meta.get("tiers", 1) for b in buildings}
    empty, single, bad = [], [], []
    for b in buildings:
        tiers = b.meta.get("tiers", 1)
        rows = []
        for i, node in enumerate(b.layer_nodes):
            rng = _z_range(node)
            if rng is None:
                empty.append((b.bid, LAYERS[i][0]))
                rows.append("-")
                continue
            rows.append(f"{rng[0]:.1f}/{rng[1]:.1f}")
        print(f"LAYERS {b.bid:<16} tiers={tiers}")
        for group in ("lower", "upper", "cap"):
            cells = [f"{rows[i]:>12}" for i, (_k, _l, g) in enumerate(LAYERS)
                     if g == group]
            print(f"  {group:<5} " + " ".join(cells))
    for bid, key in empty:
        if (bid, key) in expected:
            continue
        if group_of[key] == "upper" and tier_of[bid] == 1:
            single.append(f"{bid}:{key}")
            continue
        bad.append(f"{bid}:{key}")
    print(f"EMPTY SLOTS ({len(empty)}): "
          + (", ".join(f"{b}:{k}" for b, k in empty) or "none"))
    print(f"  single-storey upper slots (expected): {len(single)}")
    if bad:
        print("UNEXPECTED EMPTY: " + ", ".join(bad))
    else:
        print("UNEXPECTED EMPTY: none")


layer_report()

# --------------------------------------------------------------------------
# metadata + export
# --------------------------------------------------------------------------
meta = {
    "name": "Gyeongbokgung",
    "ko": "경복궁",
    "hanja": "景福宮",
    "built": 2026,
    "units": "meters",
    "layers": [{"index": i, "key": k, "ko": label, "group": group}
               for i, (k, label, group) in enumerate(LAYERS)],
    "buildings": [{k: v for k, v in b.meta.items()} for b in buildings],
}
(OUT_GLB.parent / "scene-meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))

for ob in bpy.context.scene.objects:
    ob.select_set(True)

bpy.ops.export_scene.gltf(
    filepath=str(OUT_GLB),
    export_format="GLB",
    use_selection=False,
    export_apply=False,
    export_extras=True,
    export_cameras=False,
    export_lights=False,
    export_yup=True,
    export_texcoords=True,
    export_normals=True,
    export_materials="EXPORT",
    export_image_format="AUTO",
    export_draco_mesh_compression_enable=False,
    export_unused_images=False,
    export_animations=False,
)

print(f"EXPORTED {OUT_GLB}  ({OUT_GLB.stat().st_size / 1e6:.2f} MB)")
print(f"buildings: {len(buildings)}")

if os.environ.get("PREVIEW"):
    import preview

    preview.render(ROOT, buildings)
