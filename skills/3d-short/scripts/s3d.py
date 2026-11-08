"""s3d — helper library for vertical 3D "How X becomes Y" cutaway shorts in Blender (4.2+ / 5.x).

Load it inside Blender (CLI or MCP):
    import sys; sys.path.insert(0, "<this scripts folder>"); import s3d, human
    s3d.new_short(seconds=40)                 # 1080x1920, 30 fps, EEVEE raytraced, HDRI sky + sun
    s3d.backyard()                            # textured fence, houses, trees, shrubs behind the cut
    g = s3d.ground_section(width=16)          # photo-textured soil cut + strata + stones + roots + 3D lawn
    s3d.dig(g, x=0, width=5, depth=3, start=10, end=60)   # animated hole, grass/stones/roots handled, dirt mound grows
    box = s3d.box("container", (5.2, 2.4, 2.4), (0, 1.2, -1.6), s3d.tex("rusty_metal_02", tint=(0.6, 0.75, 0.9)))
    s3d.drop_in(box, frame=70, sfx="heavy")
    cam = s3d.camera_cutaway(target=(0, 0, -1.2), dist=12)
    s3d.render_mp4("/abs/out/render.mp4")

Coordinates: X = left/right, Y = depth (camera looks along +Y, the cut face is the plane y = 0),
Z = up, lawn surface is z = 0.03. Metres. Textures come from Poly Haven (CC0) via assets.py and are cached;
without internet every material falls back to a procedural version, so builds never fail.
"""
from __future__ import annotations

import json
import math
import os
import random

import bpy
import numpy as np
from mathutils import Vector

FPS = 30
TOP = 0.03                    # lawn surface height
_rng = random.Random(7)
_markers: list[dict] = []
_ground: dict = {}            # state shared by ground_section() and dig()

try:
    import assets as _assets  # same folder
except Exception:             # pragma: no cover
    _assets = None

# ---------------------------------------------------------------- palette (fallbacks + tints)
PAL = {
    "grass": (0.16, 0.42, 0.06),
    "grass_dark": (0.05, 0.18, 0.02),
    "topsoil": (0.10, 0.06, 0.03),
    "soil": (0.30, 0.17, 0.08),
    "clay": (0.42, 0.24, 0.11),
    "rock": (0.30, 0.28, 0.26),
    "pebble": (0.45, 0.42, 0.38),
    "concrete": (0.62, 0.62, 0.60),
    "white_metal": (0.88, 0.89, 0.90),
    "steel": (0.55, 0.57, 0.60),
    "wood": (0.45, 0.28, 0.14),
    "fence": (0.55, 0.40, 0.26),
    "roof": (0.42, 0.16, 0.12),
    "leaf": (0.12, 0.30, 0.06),
    "trunk": (0.22, 0.14, 0.08),
    "water": (0.06, 0.38, 0.62),
    "label_bg": (0.16, 0.17, 0.19),
}


# ---------------------------------------------------------------- scene
def new_short(res=(1080, 1920), fps=FPS, seconds=None, engine="BLENDER_EEVEE", sky="kloofendal_48d_partly_cloudy_puresky",
              sun_elev=48, sun_azim=-35):
    """Wipe the file and set up a vertical short: resolution, fps, colour management, HDRI sky, sun."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _markers.clear()
    _ground.clear()
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.fps = fps
    sc.frame_start = 1
    if seconds:
        sc.frame_end = int(seconds * fps)
    try:
        sc.render.engine = engine
    except TypeError:
        sc.render.engine = "BLENDER_EEVEE"
    view = os.environ.get("S3D_VIEW", "AgX")
    try:
        sc.view_settings.view_transform = view
        if view == "AgX":
            sc.view_settings.look = os.environ.get("S3D_LOOK", "AgX - Medium High Contrast")
        sc.view_settings.exposure = float(os.environ.get("S3D_EXPOSURE", "0.25"))
    except TypeError:
        sc.view_settings.view_transform = "Filmic"
    sc.render.use_motion_blur = True
    sc.render.motion_blur_shutter = 0.3
    ee = sc.eevee
    for attr, val in (("taa_render_samples", 32), ("use_raytracing", True), ("use_shadows", True),
                      ("shadow_ray_count", 2), ("shadow_step_count", 10), ("use_fast_gi", True),
                      ("fast_gi_distance", 2.0), ("shadow_resolution_scale", 1.0), ("use_volumetric_shadows", False)):
        if hasattr(ee, attr):
            try:
                setattr(ee, attr, val)
            except Exception:
                pass
    if hasattr(ee, "ray_tracing_options"):
        try:
            ee.ray_tracing_options.resolution_scale = "2"
            ee.ray_tracing_options.use_denoise = True
        except Exception:
            pass
    w = bpy.data.worlds.new("World")
    w.use_nodes = True
    sc.world = w
    ok = False
    if sky and _assets:
        try:
            _assets.hdri(sky, strength=float(os.environ.get("S3D_SKY", "0.9")), rotation=sun_azim + 180)
            if hasattr(w, "sun_threshold"):
                w.sun_threshold = 1000.0   # the sun lamp is the only hard shadow
            ok = True
        except Exception as e:  # offline
            print("s3d: HDRI unavailable, using gradient sky:", e)
    if not ok:
        sky_world()
    sun(elev=sun_elev, azim=sun_azim)
    return sc


def sky_world(top=(0.16, 0.42, 0.95), horizon=(0.62, 0.80, 0.98), strength=0.8):
    """Fallback daylight world: vertical gradient sky that also gives gentle ambient light."""
    w = bpy.context.scene.world or bpy.data.worlds.new("SkyWorld")
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = strength
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (*horizon, 1)
    ramp.color_ramp.elements[1].position = 0.6
    ramp.color_ramp.elements[1].color = (*top, 1)
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    nt.links.new(sep.outputs["Z"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs[0], out.inputs[0])
    return w


def sun(elev=48, azim=-35, energy=4.5, color=(1.0, 0.95, 0.86), soft=1.5):
    """Warm key sun from front-left-above + a soft fill from the camera so the cut face never goes black."""
    d = bpy.data.lights.new("Sun", "SUN")
    d.energy = energy
    d.color = color
    d.angle = math.radians(soft)
    o = bpy.data.objects.new("Sun", d)
    bpy.context.scene.collection.objects.link(o)
    o.rotation_euler = (math.radians(90 - elev), 0, math.radians(azim))
    f = bpy.data.lights.new("Fill", "AREA")
    f.energy = 260
    f.size = 14
    f.color = (0.9, 0.94, 1.0)
    fo = bpy.data.objects.new("Fill", f)
    bpy.context.scene.collection.objects.link(fo)
    fo.location = (0, -15, 3)
    fo.rotation_euler = (math.radians(84), 0, 0)
    return o


# ---------------------------------------------------------------- materials
def _principled(name, color, rough=0.6, metal=0.0, spec=0.5):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if "Specular IOR Level" in b.inputs:
        b.inputs["Specular IOR Level"].default_value = spec
    return m, b


def mat(name, color, rough=0.6, metal=0.0, noise=0.0, noise_scale=8.0):
    """Plain material; noise > 0 adds soft colour variation (object space, so it never swims)."""
    m, b = _principled(name, color, rough, metal)
    if noise > 0:
        nt = m.node_tree
        tc = nt.nodes.new("ShaderNodeTexCoord")
        n = nt.nodes.new("ShaderNodeTexNoise")
        n.inputs["Scale"].default_value = noise_scale
        nt.links.new(tc.outputs["Object"], n.inputs["Vector"])
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        dark = [c * (1 - 0.35 * noise) for c in color]
        mix.inputs[6].default_value = (*color, 1)
        mix.inputs[7].default_value = (*dark, 1)
        nt.links.new(n.outputs["Fac"], mix.inputs[0])
        nt.links.new(mix.outputs[2], b.inputs["Base Color"])
    return m


def tex(asset_id, tile=None, tint=None, fallback=(0.5, 0.5, 0.5), rough=0.7, name=None, normal=1.0, rough_mul=1.0):
    """Photo-real PBR material from Poly Haven (CC0); procedural fallback if offline."""
    if _assets:
        try:
            return _assets.pbr_material(asset_id, "2k", tile, tuple(tint) if tint else None, name, normal, rough_mul)
        except Exception as e:
            print(f"s3d: texture {asset_id} unavailable ({e}); fallback colour")
    return mat(name or asset_id, fallback, rough=rough, noise=0.4)


SOIL_LAYERS = [  # (Poly Haven texture, bottom of the layer in metres, tile size, tint) — top to bottom
    ("brown_mud_02", -0.9, 1.4, (0.9, 0.85, 0.8)),        # dark topsoil with roots
    ("dry_ground_rocks", -3.6, 1.8, (0.95, 0.85, 0.75)),  # brown soil with pebbles
    ("red_mud_stones", -6.8, 2.0, (0.95, 0.85, 0.78)),    # reddish clay
    ("rocks_ground_02", -99, 2.4, (0.85, 0.82, 0.8)),     # grey rock
]


def mat_soil(layers=None):
    """The cut face: real photo-scanned soils stacked as strata (topsoil -> soil -> clay -> rock) with wavy,
    noise-warped boundaries. Object-space mapping: rock-steady while the hole is dug or objects move."""
    layers = layers or SOIL_LAYERS
    m, b = _principled("Soil", PAL["soil"], rough=0.92)
    nt = m.node_tree
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    warp = nt.nodes.new("ShaderNodeTexNoise")
    warp.inputs["Scale"].default_value = 0.45
    warp.inputs["Detail"].default_value = 3.0
    nt.links.new(tc.outputs["Object"], warp.inputs["Vector"])
    depth = nt.nodes.new("ShaderNodeMath")          # z warped by noise -> wavy layer boundaries
    depth.operation = "MULTIPLY_ADD"
    depth.inputs[1].default_value = 0.7
    nt.links.new(warp.outputs["Fac"], depth.inputs[0])
    nt.links.new(sep.outputs["Z"], depth.inputs[2])
    col_prev = nor_prev = None
    top = 0.0
    for i, (asset, bottom, tile, tint) in enumerate(layers):
        mp = nt.nodes.new("ShaderNodeMapping")
        mp.inputs["Scale"].default_value = (1 / tile,) * 3
        mp.inputs["Location"].default_value = (i * 0.37, i * 0.21, i * 0.53)
        nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
        paths = {}
        if _assets:
            try:
                paths = _assets.maps(asset)
            except Exception as e:
                print(f"s3d: {asset} unavailable ({e})")
        if "diff" in paths:
            im = nt.nodes.new("ShaderNodeTexImage")
            im.image = bpy.data.images.load(paths["diff"], check_existing=True)
            im.projection, im.projection_blend = "BOX", 0.3
            nt.links.new(mp.outputs["Vector"], im.inputs["Vector"])
            tm = nt.nodes.new("ShaderNodeMix")
            tm.data_type, tm.blend_type = "RGBA", "MULTIPLY"
            tm.inputs[0].default_value = 1.0
            nt.links.new(im.outputs["Color"], tm.inputs[6])
            tm.inputs[7].default_value = (*tint, 1)
            col = tm.outputs[2]
        else:
            rgb = nt.nodes.new("ShaderNodeRGB")
            rgb.outputs[0].default_value = (*[PAL["topsoil"], PAL["soil"], PAL["clay"], PAL["rock"]][min(i, 3)], 1)
            col = rgb.outputs[0]
        nor = None
        if "nor" in paths:
            imn = nt.nodes.new("ShaderNodeTexImage")
            imn.image = bpy.data.images.load(paths["nor"], check_existing=True)
            imn.image.colorspace_settings.name = "Non-Color"
            imn.projection, imn.projection_blend = "BOX", 0.3
            nt.links.new(mp.outputs["Vector"], imn.inputs["Vector"])
            nor = imn.outputs["Color"]
        if col_prev is None:
            col_prev, nor_prev = col, nor
        else:
            # mask = 1 below `top` (this layer), soft 12 cm transition
            mr = nt.nodes.new("ShaderNodeMapRange")
            mr.interpolation_type = "SMOOTHSTEP"
            mr.inputs["From Min"].default_value = top + 0.06
            mr.inputs["From Max"].default_value = top - 0.06
            nt.links.new(depth.outputs[0], mr.inputs["Value"])
            mx = nt.nodes.new("ShaderNodeMix")
            mx.data_type = "RGBA"
            nt.links.new(mr.outputs["Result"], mx.inputs[0])
            nt.links.new(col_prev, mx.inputs[6])
            nt.links.new(col, mx.inputs[7])
            col_prev = mx.outputs[2]
            if nor is not None and nor_prev is not None:
                mn = nt.nodes.new("ShaderNodeMix")
                mn.data_type = "RGBA"
                nt.links.new(mr.outputs["Result"], mn.inputs[0])
                nt.links.new(nor_prev, mn.inputs[6])
                nt.links.new(nor, mn.inputs[7])
                nor_prev = mn.outputs[2]
        top = bottom
    nt.links.new(col_prev, b.inputs["Base Color"])
    if nor_prev is not None:
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.inputs["Strength"].default_value = 1.2
        nt.links.new(nor_prev, nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
    return m


def mat_lawn_slab():
    """Top of the lawn slab = grass photo texture, sides = dark root-filled topsoil."""
    g = tex("leafy_grass", tile=1.5, tint=(0.85, 1.0, 0.7), fallback=PAL["grass"], name="LawnTop")
    nt = g.node_tree
    b = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    side = nt.nodes.new("ShaderNodeBsdfPrincipled")
    side.inputs["Base Color"].default_value = (*PAL["topsoil"], 1)
    side.inputs["Roughness"].default_value = 0.95
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Normal"], sep.inputs[0])
    gt = nt.nodes.new("ShaderNodeMath")
    gt.operation = "GREATER_THAN"
    gt.inputs[1].default_value = 0.5
    nt.links.new(sep.outputs["Z"], gt.inputs[0])
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(gt.outputs[0], mix.inputs[0])
    nt.links.new(side.outputs[0], mix.inputs[1])
    nt.links.new(b.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    return g


def mat_grass():
    return mat_lawn_slab()


def mat_concrete():
    return tex("concrete_wall_006", tile=2.0, fallback=PAL["concrete"], name="Concrete")


def mat_metal_white():
    return tex("painted_metal_shutter", tile=2.0, tint=(1.05, 1.05, 1.05), fallback=PAL["white_metal"], name="WhiteMetal")


def mat_steel():
    m = mat("Steel", PAL["steel"], rough=0.32, metal=1.0, noise=0.15, noise_scale=20)
    return m


def mat_wood():
    return tex("fine_grained_wood", tile=0.8, fallback=PAL["wood"], name="Wood")


def mat_water():
    m, b = _principled("Water", PAL["water"], rough=0.04)
    if "Transmission Weight" in b.inputs:
        b.inputs["Transmission Weight"].default_value = 0.35
    if "Coat Weight" in b.inputs:
        b.inputs["Coat Weight"].default_value = 0.5
    b.inputs["Alpha"].default_value = 0.88
    nt = m.node_tree
    tc = nt.nodes.new("ShaderNodeTexCoord")
    n = nt.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = 3.0
    nt.links.new(tc.outputs["Object"], n.inputs["Vector"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.15
    nt.links.new(n.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


def mat_emit(name, color, strength=3.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs["Color"].default_value = (*color, 1)
    e.inputs["Strength"].default_value = strength
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(e.outputs[0], o.inputs[0])
    return m


# ---------------------------------------------------------------- primitives
def _link(o, coll=None):
    (coll or bpy.context.scene.collection).objects.link(o)
    return o


def box(name, size=(1, 1, 1), loc=(0, 0, 0), mat=None, bevel=0.03, rot=(0, 0, 0)):
    """Box with bevelled edges (sharp CG edges are the #1 'cheap 3D' tell)."""
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.name = name
    o.scale = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        m = o.modifiers.new("Bevel", "BEVEL")
        m.width = bevel
        m.segments = 3
        m.limit_method = "ANGLE"
    if mat:
        o.data.materials.append(mat)
    return o


def cylinder(name, radius=0.5, depth=1.0, loc=(0, 0, 0), rot=(0, 0, 0), mat=None, verts=48):
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=depth, location=loc, rotation=rot, vertices=verts)
    o = bpy.context.active_object
    o.name = name
    m = o.modifiers.new("Bevel", "BEVEL")
    m.width = min(0.02, radius * 0.2)
    m.segments = 2
    m.limit_method = "ANGLE"
    if mat:
        o.data.materials.append(mat)
    bpy.ops.object.shade_smooth()
    return o


def hollow_box(name, size=(5.6, 2.4, 2.4), wall=0.08, loc=(0, 0, 0), mat=None, inner_mat=None, open_front=True):
    """Container/room: box with walls; the front wall (facing camera, -Y) is removed so we see inside."""
    sx, sy, sz = size
    o = box(name, size, loc, mat, bevel=0.02)
    cut = box(name + "_cut", (sx - 2 * wall, sy - 2 * wall + (sy if open_front else 0), sz - 2 * wall),
              (loc[0], loc[1] - (sy / 2 if open_front else 0), loc[2]), bevel=0)
    mod = o.modifiers.new("Hollow", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.object = cut
    o.modifiers.move(len(o.modifiers) - 1, 0)
    cut.hide_render = True
    cut.display_type = "WIRE"
    cut["s3d_always_hidden"] = 1
    cut.parent = o
    cut.matrix_parent_inverse = o.matrix_world.inverted()
    if inner_mat:
        o.data.materials.append(inner_mat)
    return o


def origin_to_base(o):
    """Move the object's origin to the bottom centre of its geometry without moving it (needed for grow on Z)."""
    me = o.data
    zmin = min(v.co.z for v in me.vertices)
    for v in me.vertices:
        v.co.z -= zmin
    o.location.z += zmin * o.scale.z
    return o


def ladder(name, height=3.0, width=0.6, loc=(0, 0, 0), mat=None):
    mat = mat or mat_steel()
    parts = []
    for sx in (-width / 2, width / 2):
        parts.append(cylinder(f"{name}_rail", 0.03, height, (loc[0] + sx, loc[1], loc[2] + height / 2), mat=mat, verts=12))
    n = int(height / 0.3)
    for i in range(n):
        parts.append(cylinder(f"{name}_rung", 0.022, width, (loc[0], loc[1], loc[2] + 0.2 + i * 0.3), rot=(0, math.radians(90), 0), mat=mat, verts=10))
    return group(name, parts)


def group(name, objs, origin=None):
    """Parent objects under an empty so they animate as one. origin='base' puts the pivot at the bottom centre."""
    e = bpy.data.objects.new(name, None)
    _link(e)
    if objs:
        bpy.context.view_layer.update()
        c = sum((o.matrix_world.translation for o in objs), Vector()) / len(objs)
        if origin == "base":
            zs = [(o.matrix_world @ Vector(v)).z for o in objs if o.type == "MESH" for v in o.bound_box]
            c.z = min(zs) if zs else c.z
        e.location = c
        bpy.context.view_layer.update()
        for o in objs:
            mw = o.matrix_world.copy()
            o.parent = e
            o.matrix_world = mw
    return e


def label(text, loc=(0, -0.05, 0), size=0.22, bg=True):
    """Small dark tag with white text, glued to an object (like 'steel bars', 'air vent' in the reference)."""
    cu = bpy.data.curves.new(text, "FONT")
    cu.body = text
    cu.size = size
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    cu.extrude = 0.004
    t = bpy.data.objects.new("lbl_" + text, cu)
    _link(t)
    t.location = (loc[0], loc[1] - 0.012, loc[2])
    t.rotation_euler = (math.radians(90), 0, 0)
    t.data.materials.append(mat_emit("lbl_txt", (1, 1, 1), 1.2))
    if not bg:
        return t
    w = len(text) * size * 0.6 + size * 0.9
    plate = box("lbl_bg_" + text, (w, 0.02, size * 1.7), (loc[0], loc[1], loc[2]), mat("lbl_bg", PAL["label_bg"], rough=0.5), bevel=0.012)
    return group("label_" + text, [plate, t])


def rock(name, size=0.3, loc=(0, 0, 0), material=None, seed=0, flat=0.7):
    """Irregular stone (displaced icosphere)."""
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=size, location=loc)
    o = bpy.context.active_object
    o.name = name
    r = random.Random(seed)
    o.scale = (1 + r.random() * 0.4, 0.8 + r.random() * 0.3, flat + r.random() * 0.2)
    o.rotation_euler = (r.random() * 0.4, r.random() * 0.4, r.random() * math.tau)
    d = o.modifiers.new("Lumpy", "DISPLACE")
    t = bpy.data.textures.new(f"rk{seed}", "VORONOI")
    t.noise_scale = 0.6 * size / 0.3
    d.texture = t
    d.texture_coords = "OBJECT"
    d.strength = size * 0.35
    o.data.materials.append(material or tex("rock_surface", tile=0.8, fallback=PAL["rock"], name="Rock"))
    bpy.ops.object.shade_smooth()
    return o


# ---------------------------------------------------------------- 3D lawn (mesh blades, numpy-built)
def _blades(n, x0, x1, y0, y1, seed, h=(0.07, 0.17), exclude=(), lean_front=0.0):
    rng = np.random.default_rng(seed)
    px = rng.uniform(x0, x1, n)
    py = rng.uniform(y0, y1, n)
    keep = np.ones(n, bool)
    for (ex0, ex1, ey0, ey1) in exclude:
        keep &= ~((px > ex0) & (px < ex1) & (py > ey0) & (py < ey1))
    return px, py, rng, keep


def _grass_mesh(name, px, py, rng, sel, h=(0.07, 0.17), width=(0.010, 0.018), mat_=None):
    px, py = px[sel], py[sel]
    n = len(px)
    hh = rng.uniform(*h, size=len(sel))[sel]
    ww = rng.uniform(*width, size=len(sel))[sel]
    yaw = rng.uniform(0, math.tau, size=len(sel))[sel]
    bend = rng.uniform(0.15, 0.6, size=len(sel))[sel] * hh
    near_edge = np.clip(1 - py / 0.25, 0, 1)            # blades on the cut edge lean over it
    tint = rng.uniform(0.0, 1.0, size=len(sel))[sel]
    ts = np.array([0.0, 0.38, 0.72, 1.0])
    half = (1 - ts * 0.82)[None, :] * ww[:, None] / 2
    ux, uy = np.cos(yaw), np.sin(yaw)                     # blade width direction
    bx, by = -uy, ux                                      # bend direction
    by = by * (1 - near_edge) - near_edge * 1.0
    bx = bx * (1 - near_edge)
    cx = px[:, None] + bx[:, None] * bend[:, None] * ts[None, :] ** 2
    cy = py[:, None] + by[:, None] * bend[:, None] * ts[None, :] ** 2
    cz = TOP - 0.01 + hh[:, None] * ts[None, :] * (1 - 0.25 * near_edge[:, None] * ts[None, :])
    verts = np.zeros((n, 7, 3), np.float32)
    for k in range(3):
        verts[:, 2 * k, 0] = cx[:, k] - ux * half[:, k]
        verts[:, 2 * k, 1] = cy[:, k] - uy * half[:, k]
        verts[:, 2 * k + 1, 0] = cx[:, k] + ux * half[:, k]
        verts[:, 2 * k + 1, 1] = cy[:, k] + uy * half[:, k]
        verts[:, 2 * k, 2] = verts[:, 2 * k + 1, 2] = cz[:, k]
    verts[:, 6, 0], verts[:, 6, 1], verts[:, 6, 2] = cx[:, 3], cy[:, 3], cz[:, 3]
    base = (np.arange(n) * 7)[:, None]
    quads = np.array([[0, 1, 3, 2], [2, 3, 5, 4]])
    loops = np.concatenate([(base[:, None, :] + quads[None]).reshape(n, 8), base + np.array([4, 5, 6])], axis=1).ravel()
    starts = (np.arange(n)[:, None] * 11 + np.array([0, 4, 8])).ravel()
    me = bpy.data.meshes.new(name)
    me.vertices.add(n * 7)
    me.vertices.foreach_set("co", verts.ravel())
    me.loops.add(len(loops))
    me.loops.foreach_set("vertex_index", loops.astype(np.int32))
    me.polygons.add(n * 3)
    me.polygons.foreach_set("loop_start", starts.astype(np.int32))
    me.update(calc_edges=True)
    # colour per vertex: dark root -> light tip, some yellowish blades
    root = np.array([0.025, 0.07, 0.008])
    tipg = np.array([0.20, 0.42, 0.05])
    tipy = np.array([0.36, 0.42, 0.10])
    tip = tipg[None] * (1 - tint[:, None] * 0.35) + tipy[None] * (tint[:, None] * 0.35)
    tk = np.array([0, 0, 0.38, 0.38, 0.72, 0.72, 1.0])
    col = root[None, None] * (1 - tk[None, :, None]) + tip[:, None, :] * tk[None, :, None]
    rgba = np.concatenate([col, np.ones((n, 7, 1))], axis=2).astype(np.float32)
    ca = me.color_attributes.new("Col", "FLOAT_COLOR", "POINT")
    ca.data.foreach_set("color", rgba.ravel())
    me.polygons.foreach_set("use_smooth", np.ones(n * 3, bool))
    o = bpy.data.objects.new(name, me)
    _link(o)
    o.data.materials.append(mat_ or _mat_blades())
    return o


def _mat_blades():
    m = bpy.data.materials.get("GrassBlades")
    if m:
        return m
    m, b = _principled("GrassBlades", PAL["grass"], rough=0.55, spec=0.35)
    nt = m.node_tree
    a = nt.nodes.new("ShaderNodeVertexColor")
    a.layer_name = "Col"
    nt.links.new(a.outputs["Color"], b.inputs["Base Color"])
    if "Subsurface Weight" in b.inputs:
        b.inputs["Subsurface Weight"].default_value = 0.15
    m.use_backface_culling = False
    return m


def _grass_regions():
    g = _ground
    w = g["width"]
    return [("Lawn_front", -w / 2, w / 2, 0.0, 2.6, int(w * 2.6 * g["density"]), 11),
            ("Lawn_mid", -w / 2, w / 2, 2.6, 6.5, int(w * 3.9 * g["density"] * 0.45), 12)]


def _build_lawn(exclude=()):
    for o in _ground.get("lawn_objs", []):
        bpy.data.objects.remove(o, do_unlink=True)
    objs = []
    for name, x0, x1, y0, y1, n, seed in _grass_regions():
        px, py, rng, keep = _blades(n, x0, x1, y0, y1, seed, exclude=exclude)
        objs.append(_grass_mesh(name, px, py, rng, keep))
    _ground["lawn_objs"] = objs
    return objs


def _hole_grass(fp, frame):
    """Blades inside a hole footprint: separate object that disappears when digging starts."""
    out = []
    for name, x0, x1, y0, y1, n, seed in _grass_regions():
        px, py, rng, _ = _blades(n, x0, x1, y0, y1, seed)
        sel = (px > fp[0]) & (px < fp[1]) & (py > fp[2]) & (py < fp[3])
        if sel.any():
            o = _grass_mesh(name + "_hole", px, py, rng, sel)
            shrink_out(o, frame, dur=6)
            out.append(o)
    return out


# ---------------------------------------------------------------- the cutaway world
def ground_section(width=16, depth_back=10, depth=14.0, slab=0.16, front_y=0.0, name="Ground", density=900,
                   stones=46, roots=22, grass=True):
    """Earth block whose front face (y = 0) is the visible cross-section. Returns the soil object.
    Adds: lawn slab (grass texture on top, dark topsoil edge), 3D grass blades (dense near the cut),
    stones half-buried in the cut face, roots near the top. dig() keeps all of them consistent."""
    soil = box(name, (width, depth_back, depth), (0, front_y + depth_back / 2, -depth / 2), mat_soil(), bevel=0.0)
    for v in soil.data.vertices:            # origin at the world origin: material depth == real depth
        v.co += soil.location
    soil.location = (0, 0, 0)
    lawn = box(name + "_slab", (width, depth_back, slab), (0, front_y + depth_back / 2, TOP - slab / 2), mat_lawn_slab(), bevel=0.0)
    soil["s3d_lawn"] = lawn.name
    _ground.update(width=width, density=density, holes=[], stones=[], roots=[], lawn_objs=[])
    if grass:
        _build_lawn()
    rmat = tex("rock_surface", tile=0.8, tint=(0.62, 0.58, 0.54), fallback=PAL["rock"], name="Rock")
    for i in range(stones):
        z = -0.7 - _rng.random() ** 0.9 * (depth - 2.0)
        s = 0.07 + _rng.random() * (0.10 + 0.22 * min(1, -z / 6))
        x = -width / 2 + 0.3 + _rng.random() * (width - 0.6)
        r = rock(f"Stone{i}", s, (x, s * 0.5, z), rmat, seed=i)
        _ground["stones"].append(r)
    if roots:
        _roots(width, roots)
    return soil


def _roots(width, n):
    m = mat("Root", (0.16, 0.10, 0.06), rough=0.85, noise=0.3)
    for i in range(n):
        cu = bpy.data.curves.new(f"root{i}", "CURVE")
        cu.dimensions = "3D"
        cu.bevel_depth = 0.016 + _rng.random() * 0.02
        cu.bevel_resolution = 2
        sp = cu.splines.new("NURBS")
        k = 5
        sp.points.add(k - 1)
        x = -width / 2 + _rng.random() * width
        z = TOP - 0.1
        for j in range(k):
            sp.points[j].co = (x, 0.005, z, 1)
            x += (_rng.random() - 0.5) * 0.4
            z -= 0.06 + _rng.random() * 0.2
        sp.use_endpoint_u = True
        sp.order_u = 3
        o = bpy.data.objects.new(f"Root{i}", cu)
        o.data.materials.append(m)
        o.data.taper_radius_mode = "OVERRIDE"
        _link(o)
        _ground["roots"].append(o)


def dig(soil, x=0.0, width=6.0, depth=3.0, start=1, end=30, back=None, name="Hole", mound=True, chunks=True, mound_side=None):
    """Animated hole: a boolean cutter grows down from the surface between start and end frames.
    Grass over the hole vanishes as digging starts, stones/roots inside disappear as the cut reaches them,
    a dirt mound grows next to the hole and clods fly out. Returns the cutter (hidden)."""
    back = back or 3.0
    cut = box(name, (width, back, depth + 0.3), (x, back / 2 - 0.05, -depth / 2 + 0.15), bevel=0.0)
    cut.display_type = "WIRE"
    cut.hide_render = True
    lawn = bpy.data.objects.get(soil.get("s3d_lawn", ""))
    for tgt in [soil] + ([lawn] if lawn else []):
        m = tgt.modifiers.new(name, "BOOLEAN")
        m.operation = "DIFFERENCE"
        m.object = cut
        m.solver = "EXACT"
    cut.scale = (1, 1, 0.01)
    cut.location.z = 0.15
    _key(cut, start, scale=True, loc=True)
    cut.scale = (1, 1, 1)
    cut.location.z = -depth / 2 + 0.15
    _key(cut, end, scale=True, loc=True)
    marker("dig", start)
    fp = (x - width / 2, x + width / 2, -0.1, back)
    if _ground.get("lawn_objs"):
        _ground["holes"].append(fp)
        _build_lawn(exclude=_ground["holes"])
        _hole_grass(fp, start)
    for o in _ground.get("stones", []) + _ground.get("roots", []):
        bpy.context.view_layer.update()
        c = o.matrix_world.translation if o.type == "MESH" else Vector(o.data.splines[0].points[0].co[:3])
        if fp[0] - 0.1 < c.x < fp[1] + 0.1 and c.z > -depth - 0.1:
            f = start + int((end - start) * min(1, max(0, -c.z / depth)))
            shrink_out(o, f, dur=4)
    side = mound_side or (1 if x <= 0 else -1)
    if mound:
        mx = x + side * (width / 2 + 1.4)
        bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=1.0, location=(mx, 2.4, TOP - 0.05))
        mo = bpy.context.active_object
        mo.name = name + "_mound"
        d = mo.modifiers.new("Lumpy", "DISPLACE")
        t = bpy.data.textures.new("mound", "CLOUDS")
        t.noise_scale = 0.35
        d.texture = t
        d.texture_coords = "OBJECT"
        d.strength = 0.18
        bpy.ops.object.shade_smooth()
        mo.data.materials.append(tex("dry_ground_rocks", tile=1.2, tint=(0.8, 0.7, 0.62), fallback=PAL["soil"], name="Mound"))
        full = (0.9 + width * 0.08, 0.9, 0.35 + depth * 0.05)
        mo.scale = (0.01, 0.01, 0.01)
        _key(mo, start, scale=True)
        mo.scale = full
        _key(mo, end, scale=True)
        _ease(mo, "SINE", "EASE_OUT")
        _hide_before(mo, start)
        _ground.setdefault("mounds", []).append(mo)
    if chunks:
        dm = bpy.data.materials.get("Mound") or tex("dry_ground_rocks", tile=1.2, fallback=PAL["topsoil"], name="Clod")
        for i in range(12):
            f = start + int((end - start) * i / 12)
            bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=0.07 + _rng.random() * 0.07, location=(x, 1.0, 0))
            ch = bpy.context.active_object
            ch.data.materials.append(dm)
            p0 = Vector((x + (_rng.random() - 0.5) * width * 0.6, 0.8 + _rng.random(), TOP - 0.3))
            p2 = Vector((x + side * (width / 2 + 0.6 + _rng.random() * 1.0), 1.0 + _rng.random() * 1.5, TOP + 0.1))
            p1 = (p0 + p2) / 2 + Vector((0, 0, 1.0 + _rng.random() * 0.6))
            ch.location = p0
            _key(ch, f, loc=True)
            ch.location = p1
            _key(ch, f + 6, loc=True)
            ch.location = p2
            _key(ch, f + 12, loc=True)
            _hide_before(ch, f)
            shrink_out(ch, f + 14, dur=5)
    return cut


def fence(width=18, y=6.0, height=1.85):
    """Wooden board fence along the back of the yard (one mesh, weathered-plank texture)."""
    import bmesh
    bm = bmesh.new()

    def bx(sx, sy, sz, cx, cy, cz):
        r = bmesh.ops.create_cube(bm, size=1.0)
        for v in r["verts"]:
            v.co.x = v.co.x * sx + cx
            v.co.y = v.co.y * sy + cy
            v.co.z = v.co.z * sz + cz
    n = int(width / 0.15)
    for i in range(n):
        x = -width / 2 + i * 0.15 + 0.075
        h = height + (0.05 if i % 2 else 0) + _rng.random() * 0.02
        bx(0.138, 0.025, h, x, y, h / 2)
    for z in (0.3, height - 0.3):
        bx(width, 0.045, 0.09, 0, y + 0.04, z)
    for x in np.arange(-width / 2, width / 2 + 0.01, 2.4):
        bx(0.1, 0.1, height + 0.1, x, y + 0.08, (height + 0.1) / 2)
    me = bpy.data.meshes.new("Fence")
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new("Fence", me)
    _link(o)
    bv = o.modifiers.new("Bevel", "BEVEL")
    bv.width = 0.006
    bv.segments = 2
    o.data.materials.append(tex("weathered_brown_planks", tile=1.8, tint=(1.1, 1.0, 0.9), fallback=PAL["fence"], name="FenceWood"))
    return o


def house(x, y, w=6.0, h=5.0, d=6.0, wall=None, roof_tint=(0.85, 0.55, 0.5), seed=0):
    """Suburban house: plaster walls, gable tiled roof, framed windows, door (background, gets DOF blur)."""
    r = random.Random(seed)
    wall = wall or r.choice([(1.0, 0.97, 0.92), (0.92, 0.95, 1.0), (1.0, 0.93, 0.82), (0.88, 0.92, 0.86)])
    wm = tex("painted_plaster_wall", tile=3.0, tint=wall, fallback=(0.86, 0.84, 0.78), name=f"Plaster{seed}")
    parts = [box("wall", (w, d, h), (x, y + d / 2, h / 2), wm, bevel=0.03)]
    # gable roof prism
    rh = h * 0.42
    me = bpy.data.meshes.new("roof")
    ov = 0.35
    vs = [(-w / 2 - ov, -ov, 0), (w / 2 + ov, -ov, 0), (w / 2 + ov, d + ov, 0), (-w / 2 - ov, d + ov, 0), (0, -ov, rh), (0, d + ov, rh)]
    fs = [(0, 1, 4), (3, 5, 2), (0, 4, 5, 3), (1, 2, 5, 4), (0, 3, 2, 1)]
    me.from_pydata(vs, [], fs)
    ro = bpy.data.objects.new("roof", me)
    _link(ro)
    ro.location = (x, y, h - 0.02)
    sol = ro.modifiers.new("Thick", "SOLIDIFY")
    sol.thickness = 0.12
    ro.data.materials.append(tex("clay_roof_tiles", tile=2.0, tint=roof_tint, fallback=PAL["roof"], name=f"Roof{seed}"))
    parts.append(ro)
    glass = mat("Glass", (0.10, 0.16, 0.22), rough=0.05, metal=0.2)
    frame = mat("Frame", (0.95, 0.95, 0.93), rough=0.5)
    cols = max(2, int(w / 1.7))
    for row in range(2):
        for col in range(cols):
            wx = x - w / 2 + 1.0 + col * ((w - 2.0) / max(1, cols - 1))
            wz = 1.4 + row * 2.0
            if wz + 0.8 > h:
                continue
            if row == 0 and col == cols // 2:
                parts.append(box("door", (0.95, 0.08, 2.0), (wx, y - 0.03, 1.0), mat("Door", (0.35, 0.18, 0.10), rough=0.5), bevel=0.01))
                continue
            parts.append(box("win_f", (0.95, 0.07, 1.2), (wx, y - 0.02, wz), frame, bevel=0.01))
            parts.append(box("win_g", (0.8, 0.08, 1.04), (wx, y - 0.035, wz), glass, bevel=0.0))
            parts.append(box("sill", (1.05, 0.14, 0.06), (wx, y - 0.06, wz - 0.62), frame, bevel=0.01))
    return group("House", parts)


def tree(x, y, h=5.5, r=2.0, seed=0):
    """Soft rounded tree: trunk + branches + clustered leaf masses with colour variation."""
    rr = random.Random(seed)
    bark = tex("bark_brown_02", tile=1.0, fallback=PAL["trunk"], name="Bark")
    parts = [cylinder("trunk", 0.18, h * 0.6, (x, y, h * 0.3), mat=bark, verts=14)]
    leaf = mat("Leaf", PAL["leaf"], rough=0.75, noise=0.8, noise_scale=3.0)
    for i in range(14):
        a = rr.random() * math.tau
        rad = r * (0.35 + rr.random() * 0.3)
        loc = (x + math.cos(a) * r * 0.55 * rr.random(), y + math.sin(a) * r * 0.4, h * 0.62 + rr.random() * r * 0.9)
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=rad, location=loc)
        s = bpy.context.active_object
        s.data.materials.append(leaf)
        d = s.modifiers.new("Lumpy", "DISPLACE")
        t = bpy.data.textures.new("lumpy", "VORONOI")
        t.noise_scale = 0.25
        d.texture = t
        d.texture_coords = "OBJECT"
        d.strength = 0.18
        bpy.ops.object.shade_smooth()
        parts.append(s)
    return group("Tree", parts)


def backyard(width=20, fence_y=6.5, houses=True, trees=True, shrubs=True):
    """Fence + neighbour houses + trees + shrubs behind the cut (the suburban backyard backdrop)."""
    f = fence(width, fence_y)
    hs, ts = [], []
    if houses:
        for i, x in enumerate((-8.0, 0.0, 8.5)):
            hs.append(house(x, fence_y + 4.5 + (i % 2) * 2.5, w=6.5 + _rng.random() * 1.5, h=5.2 + _rng.random() * 1.0, seed=i))
    if trees:
        for i, x in enumerate((-4.5, 4.0, 10.5, -11)):
            ts.append(tree(x, fence_y + 1.8 + _rng.random() * 1.5, h=5.5 + _rng.random() * 2, seed=i))
    if shrubs and _assets:
        try:
            for i, x in enumerate(np.arange(-width / 2 + 1.5, width / 2, 3.2)):
                s = _assets.model("shrub_02", size=2.6 + _rng.random() * 0.8, loc=(float(x) + _rng.random(), fence_y - 0.7, TOP - 0.02))
                s.rotation_euler.z = _rng.random() * math.tau
        except Exception as e:
            print("s3d: shrubs unavailable:", e)
    far = box("FarGround", (160, 160, 0.1), (0, fence_y + 80, TOP - 0.06), tex("leafy_grass", tile=3, tint=(0.8, 0.95, 0.6), fallback=PAL["grass_dark"], name="FarLawn"), bevel=0)
    mid = box("YardLawn", (width + 8, fence_y + 2, 0.1), (0, (fence_y + 2) / 2 + 3.0, TOP - 0.055), bpy.data.materials.get("FarLawn"), bevel=0)
    return {"fence": f, "houses": hs, "trees": ts, "ground": [far, mid]}


# ---------------------------------------------------------------- animation
def _key(o, frame, loc=False, rot=False, scale=False):
    if loc:
        o.keyframe_insert("location", frame=frame)
    if rot:
        o.keyframe_insert("rotation_euler", frame=frame)
    if scale:
        o.keyframe_insert("scale", frame=frame)


def fcurves(o):
    ad = o.animation_data
    if not ad or not ad.action:
        return []
    curves = getattr(ad.action, "fcurves", None)
    if curves is None:  # Blender 5 layered actions
        curves = [c for layer in ad.action.layers for strip in layer.strips for bag in strip.channelbags for c in bag.fcurves]
    return list(curves)


def _ease(o, kind="BACK", easing="EASE_OUT", path=None, frames=None):
    for fc in fcurves(o):
        if path and not fc.data_path.startswith(path):
            continue
        for kp in fc.keyframe_points:
            if frames and int(round(kp.co.x)) not in frames:
                continue
            kp.interpolation = kind
            kp.easing = easing


def drop_in(o, frame, height=7.0, dur=14, sfx="thud", prompt=None):
    """Object falls from above and lands with a small bounce at `frame + dur` (impact SFX on the landing)."""
    z = o.location.z
    o.location.z = z + height
    _key(o, frame, loc=True)
    o.location.z = z
    _key(o, frame + dur, loc=True)
    _ease(o, "BOUNCE", "EASE_OUT", "location", {frame, frame + dur})
    _hide_before(o, frame)
    marker(sfx, frame + int(dur * 0.5), prompt)
    return o


def pop_in(o, frame, dur=10, sfx="pop", prompt=None):
    """Scale from 0 with overshoot (labels, small props)."""
    s = o.scale.copy()
    o.scale = (0, 0, 0)
    _key(o, frame, scale=True)
    o.scale = s
    _key(o, frame + dur, scale=True)
    _ease(o, "BACK", "EASE_OUT", "scale", {frame, frame + dur})
    _hide_before(o, frame)
    if sfx:
        marker(sfx, frame, prompt)
    return o


def slide_in(o, frame, offset=(0, 0, 4), dur=16, sfx="whoosh", prompt=None):
    """Glide in from an offset with a soft settle (pipes, panels, doors)."""
    end = o.location.copy()
    o.location = end + Vector(offset)
    _key(o, frame, loc=True)
    o.location = end
    _key(o, frame + dur, loc=True)
    _ease(o, "BACK", "EASE_OUT", "location", {frame, frame + dur})
    _hide_before(o, frame)
    if sfx:
        marker(sfx, frame, prompt)
    return o


def grow(o, frame, axis="Z", dur=18, sfx="pour", prompt=None):
    """Grow along one axis from its base (concrete pour, water fill, pipe rising). Origin should be at the base."""
    s = o.scale.copy()
    i = "XYZ".index(axis)
    t = list(s)
    t[i] = 0.001
    o.scale = t
    _key(o, frame, scale=True)
    o.scale = s
    _key(o, frame + dur, scale=True)
    _ease(o, "SINE", "EASE_IN_OUT", "scale", {frame, frame + dur})
    _hide_before(o, frame)
    if sfx:
        marker(sfx, frame, prompt)
    return o


def shake(o, frame, dur=12, amp=0.06, sfx="crack", prompt=None):
    """Short shake (something cracks, crushes, explodes)."""
    base = o.location.copy()
    for k in range(dur):
        a = amp * (1 - k / dur)
        o.location = base + Vector(((_rng.random() - 0.5) * a, 0, (_rng.random() - 0.5) * a))
        _key(o, frame + k, loc=True)
    o.location = base
    _key(o, frame + dur, loc=True)
    if sfx:
        marker(sfx, frame, prompt)


def squash(o, frame, amount=0.35, dur=10):
    """Walls crushed 'like a soda can': quick inward squash."""
    s = o.scale.copy()
    _key(o, frame, scale=True)
    o.scale = (s.x * (1 - amount * 0.6), s.y, s.z * (1 - amount))
    _key(o, frame + dur, scale=True)
    marker("crunch", frame)


def _hide_before(o, frame):
    for x in [o] + list(o.children_recursive):
        if x.get("s3d_always_hidden"):
            continue
        x.hide_render = True
        x.keyframe_insert("hide_render", frame=frame - 1)
        x.hide_render = False
        x.keyframe_insert("hide_render", frame=frame)
        x.hide_viewport = False


def hide_at(o, frame):
    """Hard cut an object out of the render from `frame` on."""
    for x in [o] + list(o.children_recursive):
        if x.get("s3d_always_hidden"):
            continue
        x.hide_render = False
        x.keyframe_insert("hide_render", frame=frame - 1)
        x.hide_render = True
        x.keyframe_insert("hide_render", frame=frame)


def shrink_out(o, frame, dur=8):
    """Scale an object away (it is replaced by something else)."""
    s = o.scale.copy()
    _key(o, frame, scale=True)
    o.scale = (0.001, 0.001, 0.001)
    _key(o, frame + dur, scale=True)
    o.scale = s
    hide_at(o, frame + dur + 1)


def marker(kind, frame, prompt=None, gain=0.0, seconds=None):
    """Record an SFX cue for assembly. `prompt` = custom ElevenLabs sound description for this moment."""
    m = {"sfx": kind, "frame": int(frame), "t": round(int(frame) / bpy.context.scene.render.fps, 3)}
    if prompt:
        m["prompt"] = prompt
    if gain:
        m["gain"] = gain
    if seconds:
        m["seconds"] = seconds
    _markers.append(m)
    try:
        bpy.context.scene.timeline_markers.new(f"sfx:{kind}", frame=int(frame))
    except Exception:
        pass


def export_markers(path):
    with open(path, "w") as f:
        json.dump(sorted(_markers, key=lambda m: m["frame"]), f, indent=1)
    return path


def color_to(material, color, frame, dur=20, socket="Base Color"):
    """Animate a material colour (water turning green, metal heating up...). Works on plain materials."""
    node = next(n for n in material.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    inp = node.inputs[socket]
    inp.keyframe_insert("default_value", frame=frame)
    inp.default_value = (*color, 1)
    inp.keyframe_insert("default_value", frame=frame + dur)


def light_level(light_obj, frame, energy, dur=4):
    """Animate a lamp's power (switch on/off, flicker)."""
    L = light_obj.data
    L.keyframe_insert("energy", frame=frame)
    L.energy = energy
    L.keyframe_insert("energy", frame=frame + dur)


def emit_level(material, frame, strength, dur=4):
    node = next(n for n in material.node_tree.nodes if n.type == "EMISSION")
    node.inputs["Strength"].keyframe_insert("default_value", frame=frame)
    node.inputs["Strength"].default_value = strength
    node.inputs["Strength"].keyframe_insert("default_value", frame=frame + dur)


def tag(text, loc, frame, hold=75, size=0.24):
    """Label that pops in on `frame`, stays `hold` frames, then shrinks away (keeps frames uncluttered)."""
    lb = label(text, loc=loc, size=size)
    pop_in(lb, frame, dur=8, sfx=None)
    shrink_out(lb, frame + hold, dur=8)
    return lb


# ---------------------------------------------------------------- camera
def camera_cutaway(target=(0, 0, -1.2), dist=16.0, height=1.2, lens=35, name="Cam", fstop=5.6):
    """Front camera looking at the cut face (+Y), slightly above the target. One straight dolly axis,
    no orbit: the format moves the camera only in and out and pans between beats. Light DOF blurs the backdrop."""
    c = bpy.data.cameras.new(name)
    c.lens = lens
    c.clip_end = 400
    c.dof.use_dof = True
    c.dof.aperture_fstop = fstop
    o = bpy.data.objects.new(name, c)
    _link(o)
    bpy.context.scene.camera = o
    _place_cam(o, target, dist, height)
    _key(o, 1, loc=True, rot=True)
    c.dof.focus_distance = dist
    c.dof.keyframe_insert("focus_distance", frame=1)
    return o


def _place_cam(o, target, dist, height):
    t = Vector(target)
    o.location = (t.x, t.y - dist, t.z + height + dist * 0.08)
    d = t - Vector(o.location)
    o.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def cam_move(o, frame, target, dist, height=1.2, dur=24):
    """Eased dolly/pan to a new framing that completes at `frame` (starts at frame - dur, holds before)."""
    _key(o, frame - dur, loc=True, rot=True)
    o.data.dof.keyframe_insert("focus_distance", frame=frame - dur)
    _place_cam(o, target, dist, height)
    _key(o, frame, loc=True, rot=True)
    o.data.dof.focus_distance = dist
    o.data.dof.keyframe_insert("focus_distance", frame=frame)
    _ease(o, "SINE", "EASE_IN_OUT")


def cam_drift(o, start, end, amount=0.25):
    """Very slow push-in over a long hold so the frame never feels frozen."""
    _key(o, start, loc=True)
    fwd = o.matrix_world.to_quaternion() @ Vector((0, 0, -1))
    o.location = Vector(o.location) + fwd * amount
    _key(o, end, loc=True)


# ---------------------------------------------------------------- render
def preview_still(path, frame=None, scale=40, samples=16):
    """Fast low-res still to check composition (Claude: look at it before rendering the whole thing)."""
    sc = bpy.context.scene
    if frame:
        sc.frame_set(frame)
    old = sc.render.resolution_percentage, sc.eevee.taa_render_samples
    sc.render.resolution_percentage = scale
    sc.eevee.taa_render_samples = samples
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    sc.render.resolution_percentage, sc.eevee.taa_render_samples = old
    return path


def check_scene():
    """Problems that ruin a render but are invisible in the build log. Returns a list of strings."""
    probs = []
    for img in bpy.data.images:
        if img.source in ("FILE", "SEQUENCE", "MOVIE") and not img.packed_file and img.users:
            path = bpy.path.abspath(img.filepath, library=img.library)
            if not os.path.exists(path):
                probs.append(f"missing texture '{img.name}' -> {path} (renders MAGENTA). Pack it "
                             f"(bpy.ops.file.pack_all) or fix the path")
    for m in bpy.data.materials:
        if not m.users or not m.use_nodes or not m.node_tree:
            continue
        for n in m.node_tree.nodes:
            if n.type == "TEX_IMAGE" and n.image is None and any(o.is_linked for o in n.outputs):
                probs.append(f"material '{m.name}' has an empty image node (renders black/pink)")
    sc = bpy.context.scene
    if sc.camera is None and not any(mk.camera for mk in sc.timeline_markers):
        probs.append("no camera")
    for o in sc.objects:
        if o.get("s3d_always_hidden") and not o.hide_render and not (o.animation_data and o.animation_data.action):
            probs.append(f"boolean cutter '{o.name}' is visible in the render (white box)")
    return probs


def qa_gate(extra=(), abort=True):
    """Print every QA problem (scene + `extra`, e.g. Person.check()) and stop before a long render.
    Set S3D_FORCE=1 to render anyway."""
    probs = check_scene() + list(extra)
    for p in probs:
        print("QA:", p)
    if not probs:
        print("QA: ok")
    if probs and abort and os.environ.get("S3D_FORCE") != "1":
        raise SystemExit(f"QA failed with {len(probs)} problem(s) - fix them (or S3D_FORCE=1) before rendering")
    return probs


def render_mp4(path, start=None, end=None, scale=100, crf="HIGH", qa=()):
    """Render the animation straight to H.264 mp4 (no audio; audio is mixed in assemble.py).
    Runs qa_gate(qa) first: missing textures or broken poses stop the render before it wastes an hour."""
    qa_gate(qa)
    sc = bpy.context.scene
    if start:
        sc.frame_start = start
    if end:
        sc.frame_end = end
    sc.render.resolution_percentage = scale
    r = sc.render
    try:
        r.image_settings.media_type = "VIDEO"
    except Exception:
        pass
    r.image_settings.file_format = "FFMPEG"
    r.ffmpeg.format = "MPEG4"
    r.ffmpeg.codec = "H264"
    r.ffmpeg.constant_rate_factor = crf
    r.filepath = path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    export_markers(os.path.splitext(path)[0] + ".sfx.json")
    bpy.ops.render.render(animation=True)
    return path


# ---------------------------------------------------------------- timing from the voiceover
def load_beats(path):
    """beats.json from beats.py: one entry per script line with start/end frames and word timings."""
    with open(path) as f:
        return json.load(f)


def when(beats, i, word=None, offset=0):
    """Frame where beat i starts, or where `word` is spoken inside beat i (+offset frames).
    Use it so every object lands exactly on the word that names it."""
    b = beats[i]
    fps = bpy.context.scene.render.fps
    if word:
        w = word.lower().strip(".,!?")
        for x in b["words"]:
            if x["w"].lower().strip(".,!?").startswith(w):
                return int(round(x["s"] * fps)) + 1 + offset
        print(f"s3d.when: WARNING word {word!r} not found in beat {i} ({b.get('text', '')[:50]!r}) - using the beat start")
    return b["fs"] + offset
