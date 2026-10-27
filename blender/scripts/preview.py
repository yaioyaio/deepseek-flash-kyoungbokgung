"""Quick EEVEE preview renders of the generated palace scene.

Enable with PREVIEW=1 when running build_scene.py:

    PREVIEW=1 blender -b --factory-startup -P blender/scripts/build_scene.py

Renders land in blender/renders/.
"""

from __future__ import annotations

import math
import os
from pathlib import Path

import bpy
from mathutils import Vector


def _look_at(obj, target: Vector) -> None:
    direction = target - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def _camera(name: str, loc, target, lens: float = 40.0, ortho: float | None = None):
    cam_data = bpy.data.cameras.new(name)
    cam_data.lens = lens
    if ortho:
        cam_data.type = "ORTHO"
        cam_data.ortho_scale = ortho
    cam_data.clip_start = 0.5
    cam_data.clip_end = 4000
    cam = bpy.data.objects.new(name, cam_data)
    bpy.context.scene.collection.objects.link(cam)
    cam.location = Vector(loc)
    _look_at(cam, Vector(target))
    return cam


def _setup_world(sun_elev: float = 42.0, sun_azim: float = -35.0):
    scene = bpy.context.scene
    world = bpy.data.worlds.new("PreviewWorld")
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.52, 0.68, 0.86, 1.0)
    bg.inputs["Strength"].default_value = 0.6
    scene.world = world

    sun_data = bpy.data.lights.new("Sun", "SUN")
    sun_data.energy = 2.8
    sun_data.angle = math.radians(2.5)
    sun_data.color = (1.0, 0.96, 0.90)
    sun = bpy.data.objects.new("Sun", sun_data)
    scene.collection.objects.link(sun)
    el = math.radians(sun_elev)
    az = math.radians(sun_azim)
    sun.rotation_euler = (math.radians(90) - el, 0.0, az)

    # a soft fill from the opposite side keeps the eaves readable
    fill_data = bpy.data.lights.new("Fill", "SUN")
    fill_data.energy = 0.45
    fill_data.color = (0.72, 0.82, 1.0)
    fill_data.angle = math.radians(12)
    fill = bpy.data.objects.new("Fill", fill_data)
    scene.collection.objects.link(fill)
    fill.rotation_euler = (math.radians(70), 0.0, math.radians(145))


def render(root: Path, buildings) -> None:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1600
    scene.render.resolution_y = 1000
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Punchy" if "AgX - Punchy" in [
        i.identifier for i in scene.view_settings.bl_rna.properties["look"].enum_items
    ] else "None"

    eevee = scene.eevee
    for attr, value in (
        ("taa_render_samples", 48),
        ("use_shadows", True),
        ("use_raytracing", True),
        ("use_shadow_jitter_viewport", True),
    ):
        if hasattr(eevee, attr):
            setattr(eevee, attr, value)

    _setup_world()

    locs = {b.meta["building_id"]: b.meta for b in buildings}

    def at(bid):
        m = locs[bid]
        return Vector((m["x"], m["y"], 0.0))

    shots = [
        ("01-aerial", (0, -300, 175), (0, 10, 0), 42.0),
        ("02-geunjeongjeon", (62, -62, 34), at("geunjeongjeon"), 50.0),
        ("03-gyeonghoeru", (-118, -26, 22), at("gyeonghoeru"), 42.0),
        ("04-hyangwonjeong", (36, 120, 15), at("hyangwonjeong"), 42.0),
        ("05-gwanghwamun", (0, -232, 20), at("gwanghwamun"), 38.0),
        ("06-eave-detail", (26, -34, 21), Vector((0, -12, 16.4)), 58.0),
        ("00-plan", (0, 0, 400), (0, 0, 0), 40.0, 700.0),
    ]

    out_dir = root / "blender" / "renders"
    out_dir.mkdir(parents=True, exist_ok=True)

    only = os.environ.get("PREVIEW_ONLY")
    for shot in shots:
        name, loc, target, lens = shot[:4]
        ortho = shot[4] if len(shot) > 4 else None
        if only and only not in name:
            continue
        cam = _camera(f"cam-{name}", loc, target, lens, ortho)
        scene.camera = cam
        scene.render.filepath = str(out_dir / f"{name}.png")
        bpy.ops.render.render(write_still=True)
        print(f"RENDERED {scene.render.filepath}")
