"""Real CC0 assets from Poly Haven inside Blender (no account, free for commercial use, no credit required).

Inside a build script (after `import s3d`):
    import assets
    hits = assets.search("ladder")                 # [(id, name), ...]
    obj = assets.model("wooden_ladder", size=2.5, loc=(2, 0.5, -2.4))   # scaled so its largest side = 2.5 m
    m = assets.pbr_material("excavated_soil_wall", tile=2.0)   # PBR material (object-space box mapping)
    assets.texture_on(obj_or_name, "brown_mud_02")   # same, assigned to an object
    assets.hdri("kloofendal_48d_partly_cloudy_puresky", strength=1.0)

Files are cached in ~/.cache/kylo-3d-shorts/polyhaven so each asset downloads once.
Poly Haven licence: CC0 — https://polyhaven.com/license
"""
from __future__ import annotations

import json
import os
import urllib.request

import bpy
from mathutils import Vector

API = "https://api.polyhaven.com"
CACHE = os.path.expanduser("~/.cache/kylo-3d-shorts/polyhaven")
UA = {"User-Agent": "kylo-3d-shorts/1.0"}


def _get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def _download(url, path):
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        data = _get(url)
        with open(path, "wb") as f:
            f.write(data)
    return path


def search(query, kind="models", limit=15):
    """Find Poly Haven assets whose id, name, tags or categories contain the query words."""
    allx = json.loads(_get(f"{API}/assets?type={kind}"))
    words = query.lower().split()
    hits = []
    for aid, a in allx.items():
        hay = " ".join([aid, a.get("name", ""), " ".join(a.get("tags", [])), " ".join(a.get("categories", []))]).lower()
        if all(w in hay for w in words):
            hits.append((aid, a.get("name", aid)))
    return hits[:limit]


def model(asset_id, size=None, loc=(0, 0, 0), res="1k", name=None):
    """Import a Poly Haven model (glTF) and scale it so its largest dimension equals `size` metres."""
    files = json.loads(_get(f"{API}/files/{asset_id}"))
    g = files["gltf"][res]["gltf"]
    base = os.path.join(CACHE, asset_id, res)
    main = _download(g["url"], os.path.join(base, os.path.basename(g["url"])))
    for rel, inc in g.get("include", {}).items():
        _download(inc["url"], os.path.join(base, rel))
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=main)
    new = [o for o in bpy.data.objects if o not in before]
    roots = [o for o in new if o.parent is None or o.parent not in new]
    root = bpy.data.objects.new(name or asset_id, None)
    bpy.context.scene.collection.objects.link(root)
    for r in roots:
        r.parent = root
    bpy.context.view_layer.update()
    pts = [o.matrix_world @ Vector(c) for o in new if o.type == "MESH" for c in o.bound_box]
    if pts:
        mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
        mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
        dim = max(mx - mn)
        s = (size / dim) if (size and dim > 0) else 1.0
        # origin at bottom centre, then scale and place
        offset = Vector(((mn.x + mx.x) / 2, (mn.y + mx.y) / 2, mn.z))
        for r in roots:
            r.location -= offset
        root.scale = (s, s, s)
    root.location = loc
    return root


_MATS = {}


def _info(asset_id):
    return json.loads(_get(f"{API}/info/{asset_id}"))


def pbr_material(asset_id, res="2k", tile=None, tint=None, name=None, normal_strength=1.0, rough_mul=1.0):
    """PBR material from a Poly Haven texture, mapped in object space with box projection
    (no UVs needed, no swimming when objects move). `tile` = metres per texture repeat
    (defaults to the scan's real-world size). `tint` multiplies the colour. Cached per arguments."""
    key = (asset_id, res, tile, tint, name)
    if key in _MATS and _MATS[key].name in bpy.data.materials:
        return _MATS[key]
    files = json.loads(_get(f"{API}/files/{asset_id}"))
    if tile is None:
        try:
            tile = max(_info(asset_id).get("dimensions", [2000]))/1000.0
        except Exception:
            tile = 2.0
    maps = {}
    for k, want in (("Diffuse", "diff"), ("nor_gl", "nor"), ("Rough", "rough")):
        if k in files and res in files[k]:
            info = files[k][res].get("jpg") or files[k][res].get("png")
            maps[want] = _download(info["url"], os.path.join(CACHE, asset_id, res, os.path.basename(info["url"])))
    m = bpy.data.materials.new(name or asset_id)
    m.use_nodes = True
    nt = m.node_tree
    b = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1 / tile, 1 / tile, 1 / tile)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])

    def img(path, non_color=False):
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = bpy.data.images.load(path, check_existing=True)
        n.projection = "BOX"
        n.projection_blend = 0.25
        if non_color:
            n.image.colorspace_settings.name = "Non-Color"
        nt.links.new(mp.outputs["Vector"], n.inputs["Vector"])
        return n

    if "diff" in maps:
        col = img(maps["diff"]).outputs["Color"]
        if tint:
            mix = nt.nodes.new("ShaderNodeMix")
            mix.data_type = "RGBA"
            mix.blend_type = "MULTIPLY"
            mix.inputs[0].default_value = 1.0
            nt.links.new(col, mix.inputs[6])
            mix.inputs[7].default_value = (*tint, 1)
            col = mix.outputs[2]
        nt.links.new(col, b.inputs["Base Color"])
        m["s3d_color_socket"] = "Base Color"
    if "rough" in maps:
        r = img(maps["rough"], True).outputs["Color"]
        if rough_mul != 1.0:
            mm = nt.nodes.new("ShaderNodeMath")
            mm.operation = "MULTIPLY"
            mm.use_clamp = True
            mm.inputs[1].default_value = rough_mul
            nt.links.new(r, mm.inputs[0])
            r = mm.outputs[0]
        nt.links.new(r, b.inputs["Roughness"])
    if "nor" in maps:
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.inputs["Strength"].default_value = normal_strength
        nt.links.new(img(maps["nor"], True).outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
    _MATS[key] = m
    return m


def maps(asset_id, res="2k"):
    """Download a texture's diffuse / normal / roughness maps and return their local paths."""
    files = json.loads(_get(f"{API}/files/{asset_id}"))
    out = {}
    for k, want in (("Diffuse", "diff"), ("nor_gl", "nor"), ("Rough", "rough")):
        if k in files and res in files[k]:
            info = files[k][res].get("jpg") or files[k][res].get("png")
            out[want] = _download(info["url"], os.path.join(CACHE, asset_id, res, os.path.basename(info["url"])))
    return out


def texture_on(target, asset_id, res="2k", tile=None, tint=None):
    """Put a Poly Haven PBR texture on an object (or object name)."""
    obj = bpy.data.objects[target] if isinstance(target, str) else target
    m = pbr_material(asset_id, res, tile, tint)
    obj.data.materials.clear()
    obj.data.materials.append(m)
    return m


def hdri(asset_id, strength=1.0, res="2k", rotation=0.0):
    """Replace the world with a Poly Haven HDRI (realistic sky light and reflections). rotation in degrees (Z)."""
    files = json.loads(_get(f"{API}/files/{asset_id}"))
    info = files["hdri"][res]["hdr"]
    path = _download(info["url"], os.path.join(CACHE, asset_id, os.path.basename(info["url"])))
    w = bpy.context.scene.world
    nt = w.node_tree
    nt.nodes.clear()
    env = nt.nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(path, check_existing=True)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Rotation"].default_value = (0, 0, __import__("math").radians(rotation))
    nt.links.new(tc.outputs["Generated"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], env.inputs["Vector"])
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = strength
    out = nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(env.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs[0], out.inputs[0])
    return w
