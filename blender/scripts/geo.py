"""Geometry + material helpers for the procedural Gyeongbokgung build.

Everything is authored in metres.  Blender axes: +X east, +Y north, +Z up.
The glTF exporter converts to the usual Y-up convention used by three.js.
"""

from __future__ import annotations

import math
from pathlib import Path

import bpy
from mathutils import Euler, Vector

ROOT = Path(__file__).resolve().parents[1]
TEX = ROOT / "textures"

# --------------------------------------------------------------------------
# scene / materials
# --------------------------------------------------------------------------
def reset_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in (bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.curves):
        for item in list(block):
            if item.users == 0:
                block.remove(item)
    for coll in list(bpy.data.collections):
        if coll.users == 0:
            bpy.data.collections.remove(coll)


def _image(path: Path, non_color=False):
    img = bpy.data.images.load(str(path), check_existing=True)
    if non_color:
        img.colorspace_settings.name = "Non-Color"
    return img


def _texture_node(nt, path: Path, non_color=False):
    node = nt.nodes.new("ShaderNodeTexImage")
    node.image = _image(path, non_color)
    node.interpolation = "Linear"
    node.extension = "REPEAT"
    return node


def _principled(mat):
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return nt, bsdf


def textured(name, image, roughness=0.7, normal=None, normal_strength=1.0,
             metallic=0.0, tint=(1, 1, 1, 1), emission=None, emission_strength=0.0):
    mat = bpy.data.materials.new(name)
    nt, bsdf = _principled(mat)
    tex = _texture_node(nt, TEX / image)
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Base Color"].default_value = tint
    if normal:
        ntex = _texture_node(nt, TEX / normal, non_color=True)
        nmap = nt.nodes.new("ShaderNodeNormalMap")
        nmap.inputs["Strength"].default_value = normal_strength
        nt.links.new(ntex.outputs["Color"], nmap.inputs["Color"])
        nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    if emission:
        etex = _texture_node(nt, TEX / emission)
        nt.links.new(etex.outputs["Color"], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = emission_strength
    mat.diffuse_color = tint
    return mat


def solid(name, color, roughness=0.65, metallic=0.0, emission=None, emission_strength=0.0):
    mat = bpy.data.materials.new(name)
    nt, bsdf = _principled(mat)
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if emission:
        bsdf.inputs["Emission Color"].default_value = (*emission, 1)
        bsdf.inputs["Emission Strength"].default_value = emission_strength
    mat.diffuse_color = (*color, 1)
    return mat


MAT: dict[str, bpy.types.Material] = {}


def build_materials():
    MAT.clear()
    MAT["stone"] = textured("stone", "granite_block.jpg", 0.85,
                            "granite_block_normal.jpg", 0.9)
    MAT["stone_fine"] = textured("stone_fine", "granite.jpg", 0.88, "granite_normal.jpg", 0.6)
    MAT["stone_dark"] = textured("stone_dark", "granite_dark.jpg", 0.9, "granite_normal.jpg", 0.7)
    MAT["stone_light"] = textured("stone_light", "granite_light.jpg", 0.8, "granite_normal.jpg", 0.7)
    MAT["paving"] = textured("paving", "paving.jpg", 0.9, "paving_normal.jpg", 1.0)
    MAT["ground"] = textured("ground", "ground.jpg", 1.0, "ground_normal.jpg", 0.6)
    MAT["wood_red"] = textured("wood_red", "wood_red.jpg", 0.72)
    MAT["wood_dark"] = textured("wood_dark", "wood_dark.jpg", 0.8)
    MAT["wood_floor"] = textured("wood_floor", "wood_floor.jpg", 0.85)
    MAT["plaster"] = textured("plaster", "plaster.jpg", 0.92, "plaster_normal.jpg", 0.5)
    MAT["plaster_wall"] = textured("plaster_wall", "plaster_wall.jpg", 0.9, "plaster_normal.jpg", 0.5)
    MAT["lattice"] = textured("lattice", "lattice.jpg", 0.75,
                              emission="lattice_emissive.jpg", emission_strength=0.0)
    MAT["roof"] = textured("roof", "roof_tile.jpg", 0.78, "roof_tile_normal.jpg", 0.75)
    MAT["dancheong"] = textured("dancheong", "dancheong_strip.jpg", 0.62)
    MAT["screen"] = textured("screen", "throne_screen.jpg", 0.82)
    MAT["roof_dark"] = textured("roof_dark", "roof_tile.jpg", 0.74, "roof_tile_normal.jpg", 0.75,
                                tint=(0.82, 0.85, 0.9, 1))
    # 개판 + 산자 + 진흙: what is left once the 기와 are lifted off
    MAT["roof_base"] = solid("roof_base", (0.115, 0.098, 0.082), 0.94)
    MAT["ridge"] = solid("ridge", (0.055, 0.06, 0.065), 0.45)
    MAT["green"] = solid("dancheong_green", (0.055, 0.145, 0.12), 0.6)
    MAT["green_light"] = solid("dancheong_green_light", (0.09, 0.23, 0.18), 0.62)
    MAT["red"] = solid("dancheong_red", (0.24, 0.062, 0.045), 0.62)
    MAT["red_deep"] = solid("dancheong_red_deep", (0.16, 0.045, 0.035), 0.66)
    MAT["blue"] = solid("dancheong_blue", (0.05, 0.12, 0.19), 0.6)
    MAT["white"] = solid("dancheong_white", (0.72, 0.68, 0.57), 0.7)
    MAT["gold"] = solid("gold", (0.55, 0.40, 0.16), 0.32, 0.72)
    MAT["bronze"] = solid("bronze", (0.16, 0.20, 0.16), 0.4, 0.65)
    MAT["black"] = solid("black_lacquer", (0.02, 0.018, 0.016), 0.35)
    MAT["water"] = solid("water", (0.03, 0.075, 0.085), 0.08, 0.35)
    MAT["foliage"] = solid("foliage", (0.045, 0.085, 0.042), 0.95)
    MAT["foliage_light"] = solid("foliage_light", (0.08, 0.135, 0.055), 0.95)
    MAT["trunk"] = solid("trunk", (0.07, 0.05, 0.035), 0.92)
    MAT["foliage_sun"] = solid("foliage_sun", (0.14, 0.18, 0.06), 0.95)
    MAT["lantern"] = solid("lantern_paper", (0.8, 0.5, 0.25), 0.6,
                           emission=(1.0, 0.62, 0.3), emission_strength=0.0)
    MAT["moon"] = solid("moon", (0.9, 0.88, 0.8), 0.4, emission=(1.0, 0.95, 0.82), emission_strength=2.0)

    # per-building signboards
    for path in sorted((TEX / "signs").glob("*.png")):
        key = path.stem
        mat = bpy.data.materials.new(f"sign_{key}")
        nt, bsdf = _principled(mat)
        tex = _texture_node(nt, path)
        tex.interpolation = "Linear"
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        bsdf.inputs["Roughness"].default_value = 0.42
        bsdf.inputs["Metallic"].default_value = 0.15
        MAT[f"sign_{key}"] = mat


# --------------------------------------------------------------------------
# raw mesh accumulation
# --------------------------------------------------------------------------
class MeshData:
    __slots__ = ("verts", "faces", "uvs", "smooth")

    def __init__(self):
        self.verts: list[tuple[float, float, float]] = []
        self.faces: list[tuple[int, ...]] = []
        self.uvs: list[list[tuple[float, float]]] = []
        self.smooth: list[bool] = []

    def add(self, verts, faces, uvs, smooth=False):
        off = len(self.verts)
        self.verts.extend(verts)
        for f, uv in zip(faces, uvs):
            self.faces.append(tuple(i + off for i in f))
            self.uvs.append(uv)
            self.smooth.append(smooth if not callable(smooth) else smooth(len(self.faces) - 1))


class Builder:
    """Accumulates geometry per material and emits one mesh per material."""

    def __init__(self, name: str):
        self.name = name
        self.data: dict[str, MeshData] = {}

    def m(self, mat: str) -> MeshData:
        return self.data.setdefault(mat, MeshData())

    def add(self, mat, verts, faces, uvs, smooth=False):
        self.m(mat).add(verts, faces, uvs, smooth)

    def emit(self, parent, collection):
        objects = []
        for mat_name, d in self.data.items():
            if not d.verts:
                continue
            me = bpy.data.meshes.new(f"{self.name}_{mat_name}")
            me.from_pydata(d.verts, [], d.faces)
            me.update()
            uv_layer = me.uv_layers.new(name="UVMap")
            for poly, uv, sm in zip(me.polygons, d.uvs, d.smooth):
                poly.use_smooth = bool(sm)
                for li, co in zip(poly.loop_indices, uv):
                    uv_layer.data[li].uv = co
            ob = bpy.data.objects.new(f"{self.name}_{mat_name}", me)
            ob.data.materials.append(MAT[mat_name])
            collection.objects.link(ob)
            ob.parent = parent
            objects.append(ob)
        return objects


# --------------------------------------------------------------------------
# primitives
# --------------------------------------------------------------------------
def _rot(p, rot):
    if rot == (0, 0, 0):
        return p
    m = Euler(rot, "XYZ").to_matrix()
    return tuple(m @ Vector(p))


def _face_uv(coords, scale):
    """Planar UV from world axes, chosen by the face normal."""
    if len(coords) < 3:
        return [(0.0, 0.0)] * len(coords)
    a = Vector(coords[0])
    b = Vector(coords[1])
    c = Vector(coords[2])
    n = (b - a).cross(c - a)
    ax, ay, az = abs(n.x), abs(n.y), abs(n.z)
    out = []
    for x, y, z in coords:
        if az >= ax and az >= ay:
            out.append((x / scale, y / scale))
        elif ax >= ay:
            out.append((y / scale, z / scale))
        else:
            out.append((x / scale, z / scale))
    return out


def add_box(b: Builder, mat: str, size, loc, rot=(0, 0, 0), uv_scale=2.0,
            pivot=(0, 0, 0)):
    sx, sy, sz = size
    hx, hy, hz = sx / 2, sy / 2, sz / 2
    local = [
        (-hx, -hy, -hz), (hx, -hy, -hz), (hx, hy, -hz), (-hx, hy, -hz),
        (-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz),
    ]
    pts = []
    for p in local:
        p = (p[0] + pivot[0], p[1] + pivot[1], p[2] + pivot[2])
        p = _rot(p, rot)
        pts.append((p[0] + loc[0], p[1] + loc[1], p[2] + loc[2]))

    quads = [
        (0, 3, 2, 1), (4, 5, 6, 7),
        (0, 1, 5, 4), (1, 2, 6, 5),
        (2, 3, 7, 6), (3, 0, 4, 7),
    ]
    faces, uvs = [], []
    for q in quads:
        coords = [pts[i] for i in q]
        faces.append(q)
        uvs.append(_face_uv(coords, uv_scale))
    b.add(mat, pts, faces, uvs)
    return pts


def add_plane(b: Builder, mat: str, size, loc, rot=(0, 0, 0), uv_scale=2.0, uv_range=None):
    sx, sy = size
    hx, hy = sx / 2, sy / 2
    local = [(-hx, -hy, 0), (hx, -hy, 0), (hx, hy, 0), (-hx, hy, 0)]
    pts = []
    for p in local:
        p = _rot(p, rot)
        pts.append((p[0] + loc[0], p[1] + loc[1], p[2] + loc[2]))
    uv = uv_range or [(x / uv_scale, y / uv_scale) for x, y in [(-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy)]]
    b.add(mat, pts, [(0, 1, 2, 3)], [uv])


def add_cyl(b: Builder, mat: str, radius: float, height: float, loc,
            segments=12, rot=(0, 0, 0), taper=1.0, uv_scale=1.5, caps=True):
    r0 = radius
    r1 = radius * taper
    hz = height / 2

    def place(p):
        q = _rot(p, rot)
        return (q[0] + loc[0], q[1] + loc[1], q[2] + loc[2])

    # ---- side wall (shared verts, smooth) ----
    side_v = []
    for i in range(segments):
        ang = 2 * math.pi * i / segments
        ca, sa = math.cos(ang), math.sin(ang)
        side_v.append(place((r0 * ca, r0 * sa, -hz)))
        side_v.append(place((r1 * ca, r1 * sa, hz)))
    side_f, side_uv = [], []
    circ = 2 * math.pi * r0
    for i in range(segments):
        j = (i + 1) % segments
        side_f.append((i * 2, j * 2, j * 2 + 1, i * 2 + 1))
        u0 = i / segments * circ / uv_scale
        u1 = (i + 1) / segments * circ / uv_scale
        side_uv.append([(u0, 0), (u1, 0), (u1, height / uv_scale), (u0, height / uv_scale)])
    b.add(mat, side_v, side_f, side_uv, smooth=True)

    # ---- caps (separate ring verts, flat) ----
    if caps:
        for zz, rr, flipped in ((-hz, r0, True), (hz, r1, False)):
            ring = [place((rr * math.cos(2 * math.pi * i / segments),
                           rr * math.sin(2 * math.pi * i / segments), zz))
                    for i in range(segments)]
            centre_uv = (0.5, 0.5)
            ruv = [(0.5 + 0.5 * math.cos(2 * math.pi * i / segments),
                    0.5 + 0.5 * math.sin(2 * math.pi * i / segments))
                   for i in range(segments)]
            verts = [place((0, 0, zz))] + ring
            faces, uvs = [], []
            for i in range(segments):
                i2 = (i + 1) % segments
                tri = (0, i2 + 1, i + 1) if flipped else (0, i + 1, i2 + 1)
                faces.append(tri)
                uvs.append([centre_uv, ruv[i2], ruv[i]])
            b.add(mat, verts, faces, uvs)


def add_tube(b: Builder, mat: str, points, radius, sides=8, uv_scale=1.0,
             closed=False):
    pts = [Vector(p) for p in points]
    if len(pts) < 2:
        return
    # parallel transport frames
    tangents = []
    for i in range(len(pts)):
        if i == 0:
            t = pts[1] - pts[0]
        elif i == len(pts) - 1:
            t = pts[-1] - pts[-2]
        else:
            t = pts[i + 1] - pts[i - 1]
        tangents.append(t.normalized())
    up = Vector((0, 0, 1))
    if abs(tangents[0].dot(up)) > 0.92:
        up = Vector((0, 1, 0))
    normal = tangents[0].cross(up).normalized()
    rings = []
    for i, p in enumerate(pts):
        t = tangents[i]
        normal = (normal - t * normal.dot(t)).normalized()
        binormal = t.cross(normal).normalized()
        ring = []
        for s in range(sides):
            ang = 2 * math.pi * s / sides
            ring.append(p + normal * (math.cos(ang) * radius) + binormal * (math.sin(ang) * radius))
        rings.append(ring)
    verts = []
    for ring in rings:
        verts.extend([tuple(v) for v in ring])
    faces, uvs = [], []
    total_len = 0.0
    for i in range(len(rings) - 1):
        for s in range(sides):
            s2 = (s + 1) % sides
            faces.append((i * sides + s, i * sides + s2, (i + 1) * sides + s2, (i + 1) * sides + s))
            u0 = s / sides * 2 * math.pi * radius / uv_scale
            u1 = (s + 1) / sides * 2 * math.pi * radius / uv_scale
            v0 = total_len / uv_scale
            v1 = (total_len + (pts[i + 1] - pts[i]).length) / uv_scale
            uvs.append([(u0, v0), (u1, v0), (u1, v1), (u0, v1)])
        total_len += (pts[i + 1] - pts[i]).length
    if closed:
        # not used for the palace, kept for completeness
        pass
    b.add(mat, verts, faces, uvs, smooth=True)


def add_sphere(b: Builder, mat: str, radius, loc, scale=(1, 1, 1), segs=10, rings=6):
    verts = []
    for j in range(rings + 1):
        phi = math.pi * j / rings
        for i in range(segs):
            th = 2 * math.pi * i / segs
            x = math.sin(phi) * math.cos(th) * radius * scale[0]
            y = math.sin(phi) * math.sin(th) * radius * scale[1]
            z = math.cos(phi) * radius * scale[2]
            verts.append((x + loc[0], y + loc[1], z + loc[2]))
    faces, uvs = [], []
    for j in range(rings):
        for i in range(segs):
            i2 = (i + 1) % segs
            a = j * segs + i
            b_ = j * segs + i2
            c = (j + 1) * segs + i2
            d = (j + 1) * segs + i
            faces.append((a, b_, c, d))
            uvs.append([(i / segs, j / rings), ((i + 1) / segs, j / rings),
                        ((i + 1) / segs, (j + 1) / rings), (i / segs, (j + 1) / rings)])
    b.add(mat, verts, faces, uvs, smooth=True)


def add_prism(b: Builder, mat: str, profile, depth, loc, rot=(0, 0, 0), uv_scale=2.0):
    """Extrude a 2D profile (x,z) along Y (centred), then transform."""
    hy = depth / 2
    verts = []
    n = len(profile)
    for y in (-hy, hy):
        for x, z in profile:
            verts.append((x, y, z))
    faces, uvs = [], []
    # caps (fan)
    for i in range(1, n - 1):
        faces.append((0, i + 1, i))
        uvs.append([(profile[0][0] / uv_scale, profile[0][1] / uv_scale),
                    (profile[i + 1][0] / uv_scale, profile[i + 1][1] / uv_scale),
                    (profile[i][0] / uv_scale, profile[i][1] / uv_scale)])
        faces.append((n, n + i, n + i + 1))
        uvs.append([(profile[0][0] / uv_scale, profile[0][1] / uv_scale),
                    (profile[i][0] / uv_scale, profile[i][1] / uv_scale),
                    (profile[i + 1][0] / uv_scale, profile[i + 1][1] / uv_scale)])
    for i in range(n):
        j = (i + 1) % n
        faces.append((i, j, n + j, n + i))
        uvs.append([(0, 0), (1, 0), (1, 1), (0, 1)])
    out = []
    for x, y, z in verts:
        p = _rot((x, y, z), rot)
        out.append((p[0] + loc[0], p[1] + loc[1], p[2] + loc[2]))
    b.add(mat, out, faces, uvs)


# --------------------------------------------------------------------------
# roofs
# --------------------------------------------------------------------------
def _clamp(v, a, b):
    return max(a, min(b, v))


def roof_height(x, y, w, d, h, hip=True, power=1.65, lift=0.9):
    hw, hd = w / 2, d / 2
    if hip:
        t = min((hd - abs(y)) / hd, (hw - abs(x)) / hd)
    else:
        t = (hd - abs(y)) / hd
    t = _clamp(t, 0, 1)
    z = h * (t ** power)
    corner = _clamp((abs(x) / hw) * (abs(y) / hd), 0, 1)
    z += lift * ((1 - t) ** 4) * (corner ** 2.2)
    return z


def _slope_uv(coords, ax, ay):
    """UV for a roof face: ``u`` runs along the eave, ``v`` up the slope.

    Tiles must run down the slope on every side of a hip roof, so the axes are
    derived from the face normal instead of a fixed world projection.
    """
    a = Vector(coords[0])
    n = (Vector(coords[1]) - a).cross(Vector(coords[2]) - a)
    if n.length < 1e-9:
        n = Vector((0.0, 0.0, 1.0))
    n.normalize()
    uphill = Vector((-n.x, -n.y, 0.0))
    if uphill.length < 1e-6:
        uphill = Vector((0.0, 1.0, 0.0))
    uphill.normalize()
    along = Vector((-uphill.y, uphill.x, 0.0))
    out = []
    for p in coords:
        v = Vector(p)
        out.append((v.dot(along) / ax, v.dot(uphill) / ay))
    return out


def add_roof(b: Builder, mat_top: str, mat_under: str, w, d, h, base_z,
             hip=True, power=1.65, lift=0.9, nx=28, ny=20, thickness=0.38,
             uv=(2.6, 1.9), loc=(0, 0), rot_z=0.0, overhang_trim=True):
    ca, sa = (math.cos(rot_z), math.sin(rot_z)) if rot_z else (1.0, 0.0)

    def tr(x, y, z):
        return (x * ca - y * sa + loc[0], x * sa + y * ca + loc[1], z)

    xs = [-w / 2 + w * i / nx for i in range(nx + 1)]
    ys = [-d / 2 + d * j / ny for j in range(ny + 1)]
    top_rows, bot_rows = [], []
    for y in ys:
        row_t, row_b = [], []
        for x in xs:
            z = roof_height(x, y, w, d, h, hip, power, lift)
            row_t.append(tr(x, y, base_z + z))
            row_b.append(tr(x, y, base_z + z - thickness))
        top_rows.append(row_t)
        bot_rows.append(row_b)

    verts = [p for row in top_rows for p in row] + [p for row in bot_rows for p in row]
    n = (nx + 1) * (ny + 1)

    def uv_at(x, y):
        return (x / uv[0], y / uv[1])

    top_faces, top_uvs = [], []
    for j in range(ny):
        for i in range(nx):
            a = j * (nx + 1) + i
            top_faces.append((a, a + 1, a + nx + 2, a + nx + 1))
            coords = [top_rows[j][i], top_rows[j][i + 1],
                      top_rows[j + 1][i + 1], top_rows[j + 1][i]]
            top_uvs.append(_slope_uv(coords, uv[0], uv[1]))
    b.add(mat_top, verts, top_faces, top_uvs)

    under_faces, under_uvs = [], []
    for j in range(ny):
        for i in range(nx):
            a = n + j * (nx + 1) + i
            under_faces.append((a, a + nx + 1, a + nx + 2, a + 1))
            coords = [bot_rows[j][i], bot_rows[j + 1][i],
                      bot_rows[j + 1][i + 1], bot_rows[j][i + 1]]
            under_uvs.append(_slope_uv(coords, 3.2, 3.2))
    b.add(mat_under, verts, under_faces, under_uvs)

    # rim faces around the eave
    rim_pairs = []
    for i in range(nx):
        rim_pairs.append((i, i + 1))
        rim_pairs.append((ny * (nx + 1) + i, ny * (nx + 1) + i + 1))
    for j in range(ny):
        rim_pairs.append((j * (nx + 1), (j + 1) * (nx + 1)))
        rim_pairs.append((j * (nx + 1) + nx, (j + 1) * (nx + 1) + nx))
    rim_faces, rim_uvs = [], []
    run = 0.0
    for a, b_ in rim_pairs:
        rim_faces.append((a, b_, n + b_, n + a))
        pa, pb = verts[a], verts[b_]
        seg = math.dist(pa, pb)
        rim_uvs.append([(run / 1.4, pa[2] / 1.4), (run + seg / 1.4, pb[2] / 1.4),
                        ((run + seg) / 1.4, (pb[2] - thickness) / 1.4),
                        (run / 1.4, (pa[2] - thickness) / 1.4)])
        run += seg
    b.add(mat_under, verts, rim_faces, rim_uvs)

    if overhang_trim:
        edge = []
        steps = 18
        corners = [
            [tr(-w / 2 + w * i / steps, -d / 2,
                base_z + roof_height(-w / 2 + w * i / steps, -d / 2, w, d, h, hip, power, lift) + 0.04)
             for i in range(steps)],
            [tr(w / 2, -d / 2 + d * i / steps,
                base_z + roof_height(w / 2, -d / 2 + d * i / steps, w, d, h, hip, power, lift) + 0.04)
             for i in range(steps)],
            [tr(w / 2 - w * i / steps, d / 2,
                base_z + roof_height(w / 2 - w * i / steps, d / 2, w, d, h, hip, power, lift) + 0.04)
             for i in range(steps)],
            [tr(-w / 2, d / 2 - d * i / steps,
                base_z + roof_height(-w / 2, d / 2 - d * i / steps, w, d, h, hip, power, lift) + 0.04)
             for i in range(steps)],
        ]
        for c in corners:
            edge.extend(c)
        edge.append(edge[0])
        add_tube(b, mat_top, edge, 0.12, sides=6, uv_scale=1.2)

    return base_z + h


def add_roof_ridges(b: Builder, mat: str, w, d, h, base_z, hip=True, power=1.65,
                    lift=0.9, loc=(0, 0), rot_z=0.0, radius=0.24, main_ridge=True):
    ca, sa = (math.cos(rot_z), math.sin(rot_z)) if rot_z else (1.0, 0.0)

    def tr(x, y, z):
        return (x * ca - y * sa + loc[0], x * sa + y * ca + loc[1], z)

    hw, hd = w / 2, d / 2
    ridge_half = hw - hd if hip else hw
    ridge_z = base_z + h
    if main_ridge:
        add_tube(b, mat, [tr(-ridge_half, 0, ridge_z + 0.14), tr(ridge_half, 0, ridge_z + 0.14)],
                 radius, sides=8, uv_scale=1.0)
        # decorative end blocks (chimi)
        for sx in (-1, 1):
            add_box(b, "ridge", (0.65, 0.5, 0.95),
                    tr(sx * ridge_half, 0, ridge_z + 0.45), rot=(0, sx * 0.12, rot_z))
            add_box(b, "ridge", (0.3, 0.75, 0.55),
                    tr(sx * ridge_half, 0, ridge_z + 0.95), rot=(0, sx * 0.18, rot_z))
    if hip:
        for sx in (-1, 1):
            for sy in (-1, 1):
                pts = []
                steps = 6
                for i in range(steps + 1):
                    t = i / steps
                    x = sx * (hw - (hw - ridge_half) * t)
                    y = sy * (hd - hd * t)
                    z = base_z + roof_height(x, y, w, d, h, hip, power, lift) + 0.12
                    pts.append(tr(x, y, z))
                add_tube(b, mat, pts, radius * 0.75, sides=6, uv_scale=1.0)


def _skirt_height(t, u, h, power, lift):
    """Rise of a skirt roof at slope ``t`` and offset ``u`` along the eave."""
    tt = max(0.0, min(1.0, t))
    return h * (tt ** power) + lift * ((1 - tt) ** 3) * (abs(2 * u - 1) ** 4)


def add_skirt_roof(b: Builder, mat_top: str, mat_under: str, w, d, iw, id_,
                   h, base_z, lift=0.9, nx=18, ny=14, thickness=0.34,
                   power=1.35, uv=(2.4, 1.9), loc=(0, 0), rot_z=0.0,
                   trim=True):
    """Rectangular "skirt" roof.

    A frame that rises from the eave rectangle ``w x d`` to a flat inner rim
    ``iw x id_`` at height ``h``.  Two-storey pavilions (and the double-eaved
    halls) let the upper storey emerge through this lower roof, which is what
    a real 겹처마/부연 roof looks like.
    """
    ca, sa = (math.cos(rot_z), math.sin(rot_z)) if rot_z else (1.0, 0.0)

    def tr(x, y, z):
        return (x * ca - y * sa + loc[0], x * sa + y * ca + loc[1], z)

    def height(t, u):
        return _skirt_height(t, u, h, power, lift)

    strips = []
    # south (sy=-1) and north (sy=+1): u runs west -> east
    for sy in (-1, 1):
        rows = []
        for j in range(ny + 1):
            t = j / ny
            row = []
            for i in range(nx + 1):
                u = i / nx
                xo, yo = -w / 2 + w * u, sy * d / 2
                xi, yi = -iw / 2 + iw * u, sy * id_ / 2
                row.append((xo + (xi - xo) * t, yo + (yi - yo) * t, base_z + height(t, u)))
            rows.append(row)
        strips.append(rows)
    # west (sx=-1) and east (sx=+1): u runs south -> north
    for sx in (-1, 1):
        rows = []
        for j in range(ny + 1):
            t = j / ny
            row = []
            for i in range(nx + 1):
                u = i / nx
                xo, yo = sx * w / 2, -d / 2 + d * u
                xi, yi = sx * iw / 2, -id_ / 2 + id_ * u
                row.append((xo + (xi - xo) * t, yo + (yi - yo) * t, base_z + height(t, u)))
            rows.append(row)
        strips.append(rows)

    for si, rows in enumerate(strips):
        verts = [tr(x, y, z) for row in rows for x, y, z in row]
        nv = len(verts)
        verts += [tr(x, y, z - thickness) for row in rows for x, y, z in row]
        top_f, top_uv, bot_f, bot_uv = [], [], [], []
        span = w if si < 2 else d
        run = (w - iw) / 2 if si < 2 else (d - id_) / 2
        slope = max(math.hypot(run, h), 1e-3)
        for j in range(ny):
            for i in range(nx):
                a = j * (nx + 1) + i
                top_f.append((a, a + 1, a + nx + 2, a + nx + 1))
                u0 = (i / nx) * span / uv[0]
                u1 = ((i + 1) / nx) * span / uv[0]
                v0 = (j / ny) * slope / uv[1]
                v1 = ((j + 1) / ny) * slope / uv[1]
                top_uv.append([(u0, v0), (u1, v0), (u1, v1), (u0, v1)])
                bot_f.append((nv + a, nv + a + nx + 1, nv + a + nx + 2, nv + a + 1))
                bot_uv.append([(u0, v0), (u0, v1), (u1, v1), (u1, v0)])
        b.add(mat_top, verts, top_f, top_uv)
        b.add(mat_under, verts, bot_f, bot_uv)

    if trim:
        # continuous eave trim around the outer edge
        loop = []
        for i in range(nx):
            u = i / nx
            loop.append(tr(-w / 2 + w * u, -d / 2, base_z + height(0, u) + 0.03))
        for i in range(ny):
            u = i / ny
            loop.append(tr(w / 2, -d / 2 + d * u, base_z + height(0, u) + 0.03))
        for i in range(nx):
            u = i / nx
            loop.append(tr(w / 2 - w * u, d / 2, base_z + height(0, u) + 0.03))
        for i in range(ny):
            u = i / ny
            loop.append(tr(-w / 2, d / 2 - d * u, base_z + height(0, u) + 0.03))
        loop.append(loop[0])
        add_tube(b, mat_top, loop, 0.12, sides=6, uv_scale=1.2)

    # hip ridges along the four mitred corners
    for sx in (-1, 1):
        for sy in (-1, 1):
            pts = [tr(sx * w / 2, sy * d / 2, base_z + lift + 0.03)]
            steps = 5
            for i in range(1, steps + 1):
                t = i / steps
                x = sx * (w / 2 + (iw / 2 - w / 2) * t)
                y = sy * (d / 2 + (id_ / 2 - d / 2) * t)
                pts.append(tr(x, y, base_z + height(t, 1 if sx * sy > 0 else 0) + 0.06))
            add_tube(b, "ridge", pts, 0.13, sides=6, uv_scale=1.0)

    return base_z + h


# --------------------------------------------------------------------------
# 기와 · 막새 — the tile skin that sits on the roof shell
# --------------------------------------------------------------------------
# 수키와 pitch.  The roof texture holds eight ridges per repeat, so the sheet
# is UV-mapped to the same period and the modelled ridges line up with the
# painted ones instead of fighting them.
TILE_PITCH = 0.62
TILE_UV = (TILE_PITCH * 8.0, 1.9)


def add_tile_field(b: Builder, mat: str, grids, offset=0.17, thickness=0.075,
                   uv=TILE_UV):
    """Lay the tile plate over a roof.

    ``grids`` holds one point grid per roof face; row 0 runs along the eave and
    the last row runs along the ridge.  Every grid becomes a thin plate with a
    real rim, so an isolated 기와 layer reads as a solid skin, not a plane.
    """
    for rows in grids:
        nt, nu = len(rows) - 1, len(rows[0]) - 1
        if nt < 1 or nu < 1:
            continue
        top = [[(x, y, z + offset) for x, y, z in row] for row in rows]
        bot = [[(x, y, z + offset - thickness) for x, y, z in row] for row in rows]
        verts = [p for row in top for p in row] + [p for row in bot for p in row]
        n = (nt + 1) * (nu + 1)
        faces, uvs = [], []
        for j in range(nt):
            for i in range(nu):
                a = j * (nu + 1) + i
                faces.append((a, a + 1, a + nu + 2, a + nu + 1))
                uvs.append(_slope_uv([top[j][i], top[j][i + 1],
                                      top[j + 1][i + 1], top[j + 1][i]], *uv))
                faces.append((n + a, n + a + nu + 1, n + a + nu + 2, n + a + 1))
                uvs.append(_slope_uv([bot[j][i], bot[j + 1][i],
                                      bot[j + 1][i + 1], bot[j][i + 1]], *uv))
        loop = ([(0, i) for i in range(nu)]
                + [(j, nu) for j in range(nt)]
                + [(nt, i) for i in range(nu, 0, -1)]
                + [(j, 0) for j in range(nt, 0, -1)])
        for k in range(len(loop)):
            j0, i0 = loop[k]
            j1, i1 = loop[(k + 1) % len(loop)]
            a = j0 * (nu + 1) + i0
            c = j1 * (nu + 1) + i1
            faces.append((a, n + a, n + c, c))
            uvs.append([(0, 0), (0, 1), (1, 1), (1, 0)])
        b.add(mat, verts, faces, uvs, smooth=False)


def add_tile_ridges(b: Builder, mat: str, columns, radius=0.06, sides=3,
                    offset=0.195):
    """수키와 — the convex cover-tile rows running down every slope."""
    for pts in columns:
        add_tube(b, mat, [(x, y, z + offset) for x, y, z in pts], radius,
                 sides=sides, uv_scale=1.0)


def _disc(b: Builder, mat: str, center, normal, radius=0.115, sides=6):
    """A flat hexagonal face — the 와당 at the end of a 수키와."""
    cx, cy, cz = center
    nx, ny = normal
    ux, uy = -ny, nx
    rim = []
    for k in range(sides):
        a = math.pi / sides + 2 * math.pi * k / sides
        rim.append((cx + ux * radius * math.cos(a),
                    cy + uy * radius * math.cos(a),
                    cz + radius * math.sin(a)))
    verts = [(cx, cy, cz)] + rim
    faces = [(0, 1 + k, 1 + (k + 1) % sides) for k in range(sides)]
    uvs = [[(0.5, 0.5)] + [(0.5 + 0.5 * math.cos(math.pi / sides + 2 * math.pi * k / sides),
                            0.5 + 0.5 * math.sin(math.pi / sides + 2 * math.pi * k / sides))
                           for k in range(sides)] for _ in faces]
    b.add(mat, verts, faces, uvs)


def add_maksae(b: Builder, mat: str, loops, discs, offset=0.12,
               band_radius=0.09, disc_radius=0.115):
    """막새 — the eave-end band and one 와당 for every cover-tile row."""
    for pts in loops:
        add_tube(b, mat, [(x, y, z + offset) for x, y, z in pts], band_radius,
                 sides=4, uv_scale=0.9)
    for (x, y, z), (nx, ny) in discs:
        _disc(b, mat, (x + nx * 0.03, y + ny * 0.03, z + offset + 0.02),
              (nx, ny), disc_radius)


def _decimate(rows, cols):
    """Thin a point grid to ``cols`` columns, keeping both ends."""
    nu = len(rows[0]) - 1
    idx = sorted({min(nu, int(round(i * nu / cols))) for i in range(cols + 1)})
    return [[row[i] for i in idx] for row in rows]


def roof_face_grids(w, d, h, hip=True, power=1.65, lift=0.9,
                    pitch=TILE_PITCH, nt=6, t_end=0.965, inset=0.09, tf=None):
    """Sample an :func:`add_roof` surface face by face.

    Returns ``(grids, columns, loops, discs)``: the tile plate grids, the
    수키와 polylines, the eave loops that carry the 막새 band and the outward
    normal for the 와당 at every ridge.
    """
    if tf is None:
        tf = lambda p: p  # noqa: E731

    def sides_at(ins):
        hw_, hd_ = w / 2 - ins, d / 2 - ins
        if hip:
            if w >= d:
                tx, ty = (w - d) / 2, 0.0
            else:
                tx, ty = 0.0, (d - w) / 2
            return [
                ((-hw_, -hd_), (hw_, -hd_), (-tx, 0.0), (tx, 0.0)),
                ((hw_, hd_), (-hw_, hd_), (tx, 0.0), (-tx, 0.0)),
                ((hw_, -hd_), (hw_, hd_), (tx, -ty), (tx, ty)),
                ((-hw_, hd_), (-hw_, -hd_), (-tx, ty), (-tx, -ty)),
            ]
        return [
            ((-hw_, -hd_), (hw_, -hd_), (-w / 2, 0.0), (w / 2, 0.0)),
            ((hw_, hd_), (-hw_, hd_), (w / 2, 0.0), (-w / 2, 0.0)),
        ]

    grids, columns, loops, discs = [], [], [], []
    for (b0, b1, t0, t1), (o0, o1, _ot0, _ot1) in zip(sides_at(inset), sides_at(0.0)):
        span = math.dist(b0, b1)
        nu = max(2, int(round(span / pitch)))
        rows = []
        for j in range(nt + 1):
            t = t_end * j / nt
            row = []
            for i in range(nu + 1):
                u = i / nu
                bx = b0[0] + (b1[0] - b0[0]) * u
                by = b0[1] + (b1[1] - b0[1]) * u
                tx = t0[0] + (t1[0] - t0[0]) * u
                ty = t0[1] + (t1[1] - t0[1]) * u
                x = bx + (tx - bx) * t
                y = by + (ty - by) * t
                row.append(tf((x, y, roof_height(x, y, w, d, h, hip, power, lift))))
            rows.append(row)
        grids.append(_decimate(rows, max(3, int(round(span / (pitch * 2.2))))))
        for i in range(1, nu):
            columns.append([rows[j][i] for j in range(nt + 1)])

        # eave line on the un-inset edge, where the 막새 band actually sits
        dx, dy = o1[0] - o0[0], o1[1] - o0[1]
        ln = math.hypot(dx, dy) or 1.0
        nx, ny = dy / ln, -dx / ln
        loop = []
        for i in range(nu + 1):
            u = i / nu
            x = o0[0] + dx * u
            y = o0[1] + dy * u
            if nx * x + ny * y < 0:
                nx, ny = -nx, -ny
            loop.append(tf((x, y, roof_height(x, y, w, d, h, hip, power, lift))))
        loops.append(loop)
        for i in range(1, nu):
            p = tf((o0[0] + dx * (i / nu), o0[1] + dy * (i / nu),
                    roof_height(o0[0] + dx * (i / nu), o0[1] + dy * (i / nu),
                                w, d, h, hip, power, lift)))
            discs.append((p, (nx, ny)))
    return grids, columns, loops, discs


def add_roof_tiles(bt: Builder, bm: Builder, w, d, h, base_z, hip=True,
                   power=1.65, lift=0.9, loc=(0, 0), rot_z=0.0, inset=0.09,
                   t_end=0.965, pitch=TILE_PITCH, mat="roof",
                   mat_edge="roof_dark", ridge_radius=0.075):
    """Full 기와 + 막새 skin for an :func:`add_roof` surface."""
    ca, sa = (math.cos(rot_z), math.sin(rot_z)) if rot_z else (1.0, 0.0)

    def tf(p):
        x, y, z = p
        return (x * ca - y * sa + loc[0], x * sa + y * ca + loc[1], base_z + z)

    grids, columns, loops, discs = roof_face_grids(
        w, d, h, hip=hip, power=power, lift=lift, pitch=pitch, t_end=t_end,
        inset=inset, tf=tf)
    add_tile_field(bt, mat, grids)
    add_tile_ridges(bt, mat, columns, radius=ridge_radius)
    add_maksae(bm, mat_edge, loops, discs)


def add_skirt_roof_tiles(bt: Builder, bm: Builder, w, d, iw, id_, h, base_z,
                         lift=0.9, power=1.35, pitch=TILE_PITCH, nt=6,
                         t_end=0.97, inset=0.09, mat="roof",
                         mat_edge="roof_dark", ridge_radius=0.075):
    """기와 + 막새 skin for an :func:`add_skirt_roof` surface."""
    grids, columns, loops, eave = [], [], [], []
    ow, od = w - 2 * inset, d - 2 * inset
    for sy in (-1, 1):
        nu = max(2, int(round(ow / pitch)))
        rows = []
        for j in range(nt + 1):
            t = t_end * j / nt
            row = []
            for i in range(nu + 1):
                u = i / nu
                xo, yo = -ow / 2 + ow * u, sy * od / 2
                xi, yi = -iw / 2 + iw * u, sy * id_ / 2
                row.append((xo + (xi - xo) * t, yo + (yi - yo) * t,
                            base_z + _skirt_height(t, u, h, power, lift)))
            rows.append(row)
        grids.append(_decimate(rows, max(3, int(round(ow / (pitch * 2.2))))))
        columns.extend([rows[j][i] for j in range(nt + 1)] for i in range(1, nu))
        loops.append([(-w / 2 + w * i / nu, sy * d / 2,
                       base_z + _skirt_height(0.0, i / nu, h, power, lift))
                      for i in range(nu + 1)])
        eave.extend((p, (0.0, float(sy))) for p in loops[-1][1:-1])
    for sx in (-1, 1):
        nu = max(2, int(round(od / pitch)))
        rows = []
        for j in range(nt + 1):
            t = t_end * j / nt
            row = []
            for i in range(nu + 1):
                u = i / nu
                xo, yo = sx * ow / 2, -od / 2 + od * u
                xi, yi = sx * iw / 2, -id_ / 2 + id_ * u
                row.append((xo + (xi - xo) * t, yo + (yi - yo) * t,
                            base_z + _skirt_height(t, u, h, power, lift)))
            rows.append(row)
        grids.append(_decimate(rows, max(3, int(round(od / (pitch * 2.2))))))
        columns.extend([rows[j][i] for j in range(nt + 1)] for i in range(1, nu))
        loops.append([(sx * w / 2, -d / 2 + d * i / nu,
                       base_z + _skirt_height(0.0, i / nu, h, power, lift))
                      for i in range(nu + 1)])
        eave.extend((p, (float(sx), 0.0)) for p in loops[-1][1:-1])
    add_tile_field(bt, mat, grids)
    add_tile_ridges(bt, mat, columns, radius=ridge_radius)
    add_maksae(bm, mat_edge, loops, eave)


# --------------------------------------------------------------------------
# misc helpers
# --------------------------------------------------------------------------
def add_rail(b: Builder, mat, x0, y0, x1, y1, z, height=1.0, post_every=2.0,
             post_size=(0.16, 0.16), rail_size=0.14, skip=None):
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy)
    if length < 0.01:
        return
    ang = math.atan2(dy, dx)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2

    # continuous sill so the balustrade reads as masonry, not floating sticks
    add_box(b, mat, (length, post_size[1] * 1.45, 0.12), (cx, cy, z + 0.06),
            rot=(0, 0, ang), uv_scale=1.6)

    n = max(1, int(length / post_every))
    for i in range(n + 1):
        t = i / n
        x, y = x0 + dx * t, y0 + dy * t
        if skip and skip(x, y):
            continue
        add_box(b, mat, (post_size[0], post_size[1], height), (x, y, z + height / 2),
                rot=(0, 0, ang), uv_scale=1.2)
        # small capstone
        add_box(b, mat, (post_size[0] * 1.3, post_size[1] * 1.3, 0.09),
                (x, y, z + height + 0.045), rot=(0, 0, ang), uv_scale=1.0)

    add_box(b, mat, (length, rail_size * 1.2, rail_size), (cx, cy, z + height - rail_size * 0.55),
            rot=(0, 0, ang), uv_scale=1.8)
    add_box(b, mat, (length, rail_size * 0.7, rail_size * 0.7), (cx, cy, z + height * 0.58),
            rot=(0, 0, ang), uv_scale=1.8)


def add_lattice_panel(b: Builder, x, y, z, width, height, rot_z=0.0, mat="lattice",
                      facing_south=True):
    rx = math.pi / 2 if facing_south else -math.pi / 2
    add_plane(b, mat, (width, height), (x, y, z), rot=(rx, 0, rot_z),
              uv_range=[(0, 0), (1, 0), (1, 1), (0, 1)])


def add_sign(b: Builder, key, x, y, z, width=3.4, height=0.85, rot_z=0.0, foot=0.0):
    mat = f"sign_{key}"
    if mat not in MAT:
        return
    add_box(b, "black", (width + 0.2, 0.16, height + 0.2), (x, y, z), rot=(0, 0, rot_z))
    # sit slightly proud of the frame, outward along the local -Y normal
    off = 0.11
    ca, sa = math.cos(rot_z), math.sin(rot_z)
    px, py = x + sa * off, y - ca * off
    add_plane(b, mat, (width, height), (px, py, z), rot=(math.pi / 2, 0, rot_z),
              uv_range=[(0, 0), (1, 0), (1, 1), (0, 1)])


def add_lantern(b: Builder, x, y, z, scale=1.0):
    # stone lantern: base, pillar, light housing, roof
    add_box(b, "stone", (1.0 * scale, 1.0 * scale, 0.28 * scale), (x, y, z + 0.14 * scale), uv_scale=1.2)
    add_cyl(b, "stone", 0.16 * scale, 1.05 * scale, (x, y, z + 0.8 * scale), segments=8)
    add_box(b, "stone", (0.62 * scale, 0.62 * scale, 0.16 * scale), (x, y, z + 1.37 * scale), uv_scale=1.0)
    add_box(b, "lantern", (0.52 * scale, 0.52 * scale, 0.5 * scale), (x, y, z + 1.7 * scale), uv_scale=0.6)
    add_box(b, "stone", (0.8 * scale, 0.8 * scale, 0.12 * scale), (x, y, z + 1.98 * scale), uv_scale=1.0)
    add_prism(b, "stone", [(-0.5 * scale, 0), (0.5 * scale, 0), (0, 0.35 * scale)],
              0.7 * scale, (x, y, z + 2.03 * scale), uv_scale=1.0)


def add_tree(b: Builder, x, y, rng, scale=1.0):
    h = rng.uniform(7.0, 12.0) * scale
    trunk_r = rng.uniform(0.22, 0.4) * scale
    lean = (rng.uniform(-0.6, 0.6), rng.uniform(-0.6, 0.6))
    # slightly crooked trunk
    pts = [(x, y, 0),
           (x + lean[0] * 0.4, y + lean[1] * 0.4, h * 0.45),
           (x + lean[0], y + lean[1], h * 0.85)]
    add_tube(b, "trunk", pts, trunk_r, sides=6, uv_scale=1.0)
    n = rng.randint(3, 5)
    for i in range(n):
        ang = rng.uniform(0, math.tau)
        rad = rng.uniform(0.8, 3.0) * scale
        cx = x + lean[0] + math.cos(ang) * rad
        cy = y + lean[1] + math.sin(ang) * rad
        cz = h * rng.uniform(0.62, 0.98)
        rr = rng.uniform(1.6, 3.2) * scale
        mat = rng.choice(["foliage", "foliage", "foliage_light", "foliage_sun"])
        add_sphere(b, mat, rr, (cx, cy, cz), scale=(1.0, 1.0, rng.uniform(0.55, 0.8)),
                   segs=9, rings=6)


def add_rock(b: Builder, x, y, rng, scale=1.0):
    n = rng.randint(3, 5)
    for i in range(n):
        r = rng.uniform(0.5, 1.6) * scale
        add_sphere(b, "stone_dark", r,
                   (x + rng.uniform(-1, 1) * scale, y + rng.uniform(-1, 1) * scale,
                    r * 0.35), scale=(1.2, 1.0, 0.55), segs=7, rings=4)
