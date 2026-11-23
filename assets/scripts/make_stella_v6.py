# Stella v6 - REBUILD re-anchored to art/stella-concept.png per
# docs/MEASUREMENTS_V6.md: ~7.3-head proportions, long legs, cropped
# jacket + bare midriff, wide wavy ribbon twintails. Same 14 pivots and
# clip contract as v3/v4; v4 texture system carried over.
# Stella v3 - high-detail pass over v2. Same part-based structure, same
# pivots and the same animation content/timing as v2; the polygon budget
# (target 80k-120k tris) is spent on multi-strand hair, a refined face and
# clothing surface detail, with smooth shading and denser tessellation.
# Contract unchanged: faces -Y in Blender (+Z in glTF), feet at z=0,
# height ~1.55m, clips Idle/Run/Jump/Attack, pivots Body/Torso/Head/
# Arm_L/Arm_R/Leg_L/Leg_R/Twintail_L/Twintail_R/Elbow_L/R/Knee_L/R/Blade.
# Build: blender -b --factory-startup -noaudio --python assets/scripts/make_stella_v3.py
import bpy, math, os, json, struct
from mathutils import Vector

try:
    ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
except NameError:
    ROOT = os.path.expanduser("~/workspace/stella-action")
GLB_OUT = os.path.join(ROOT, "public", "models", "stella.glb")
BLEND_OUT = os.path.join(ROOT, "assets", "source", "stella.blend")
ASSETS = os.path.join(ROOT, "assets")
TMP = "/tmp/stella2_parts"
os.makedirs(TMP, exist_ok=True)

D = math.radians

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.fps = 24

# ---------------------------------------------------------------- materials
def mat(name, color, rough=0.8, emission=None, estr=0.0, metal=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    if emission is not None:
        bsdf.inputs["Emission Color"].default_value = (*emission, 1.0)
        bsdf.inputs["Emission Strength"].default_value = estr
    return m

M = {
    "skin":   mat("Skin",   (1.00, 0.80, 0.63), 0.60),
    "skin_sh": mat("SkinSh", (0.88, 0.58, 0.42), 0.70),
    "hair":   mat("Hair",   (0.002, 0.265, 0.255), 0.48),
    "hair_d": mat("HairDk", (0.004, 0.135, 0.130), 0.55),
    "cream":  mat("Cream",  (0.97, 0.93, 0.84), 0.85),
    "teal":   mat("Teal",   (0.008, 0.265, 0.255), 0.78),
    "teal_d": mat("TealDk", (0.010, 0.145, 0.145), 0.82),
    "orange": mat("Orange", (0.88, 0.40, 0.04), 0.68),
    "dark":   mat("Dark",   (0.08, 0.09, 0.12), 0.88),
    "sock":   mat("Sock",   (0.09, 0.10, 0.15), 0.92),
    "glove":  mat("Glove",  (0.13, 0.13, 0.16), 0.85),
    "white":  mat("White",  (0.98, 0.98, 0.97), 0.55),
    "eye":    mat("Eye",    (0.015, 0.19, 0.20), 0.30),
    "eye_mid": mat("EyeMid", (0.03, 0.45, 0.44), 0.32),
    "eye_hi": mat("EyeHi",  (0.10, 0.72, 0.68), 0.35, emission=(0.05, 0.45, 0.42), estr=0.5),
    "metal":  mat("Metal",  (0.56, 0.59, 0.63), 0.35, metal=0.85),
    "mouth":  mat("Mouth",  (0.48, 0.16, 0.15), 0.65),
    "blush":  mat("Blush",  (1.00, 0.58, 0.52), 0.95),
    "blade":  mat("Blade",  (0.10, 0.55, 0.65), 0.28, emission=(0.20, 0.90, 1.00), estr=2.6),
    "bag":    mat("Bag",    (0.015, 0.125, 0.125), 0.85),
}

# ---------------------------------------------------------------- builders
def _finish(o, name, parent, loc, material=None, rot=(0, 0, 0), scale=None):
    o.name = name
    if material is not None and o.type == 'MESH':
        o.data.materials.append(material)
    if parent is not None:
        o.parent = parent
    o.location = loc
    o.rotation_euler = rot
    if scale is not None:
        o.scale = scale
    return o

def _apply_bevel(o, bevel, segments=4):
    if bevel > 0:
        mod = o.modifiers.new("bev", 'BEVEL')
        mod.width = bevel
        mod.segments = segments
        bpy.context.view_layer.objects.active = o
        o.select_set(True)
        bpy.ops.object.modifier_apply(modifier=mod.name)
        o.select_set(False)

def taper_z(o, z0, z1, s0, s1, axes=(0, 1)):
    """Scale x/y of verts by a factor interpolated over local z."""
    me = o.data
    for v in me.vertices:
        t = (v.co.z - z0) / max(1e-6, (z1 - z0))
        t = min(1.0, max(0.0, t))
        s = s0 + (s1 - s0) * t
        for a in axes:
            v.co[a] *= s
    me.update()

def rbox(parent, name, loc, size, material, rot=(0, 0, 0), bevel=0.02):
    bpy.ops.mesh.primitive_cube_add(location=(0, 0, 0))
    o = bpy.context.active_object
    o.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    _apply_bevel(o, bevel)
    return _finish(o, name, parent, loc, material, rot)

def cyl(parent, name, loc, r_top, r_bot, depth, material, rot=(0, 0, 0),
        vertices=32, scale=None):
    bpy.ops.mesh.primitive_cone_add(vertices=vertices, radius1=r_bot,
                                    radius2=r_top, depth=depth, location=(0, 0, 0))
    o = bpy.context.active_object
    for p in o.data.polygons:
        p.use_smooth = True
    return _finish(o, name, parent, loc, material, rot, scale)

def sph(parent, name, loc, scale, material, rot=(0, 0, 0), seg=40, rings=28):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=seg, ring_count=rings,
                                         radius=1.0, location=(0, 0, 0))
    o = bpy.context.active_object
    o.scale = scale
    for p in o.data.polygons:
        p.use_smooth = True
    return _finish(o, name, parent, loc, material, rot)

def tube(parent, name, rings, material, radial=24):
    """Smooth tapered tube through rings [(center Vector, rx, ry), ...].
    v4: UVs built in - (radial+1) verts per ring with the seam duplicated
    at the BACK (+Y side, angle offset +90deg), U around circumference
    (front -Y = u 0.5), V = cumulative path length 0 root -> 1 tip."""
    verts, faces, vcoord = [], [], []
    n = len(rings)
    cum = [0.0]
    for i in range(1, n):
        cum.append(cum[-1] + (rings[i][0] - rings[i - 1][0]).length)
    total = max(cum[-1], 1e-6)
    for ri, (c, rx, ry) in enumerate(rings):
        for k in range(radial + 1):
            a = math.pi / 2 + 2 * math.pi * k / radial
            verts.append((c.x + rx * math.cos(a), c.y + ry * math.sin(a), c.z))
            vcoord.append((k / radial, cum[ri] / total))
    stride = radial + 1
    for i in range(n - 1):
        for k in range(radial):
            faces.append((i * stride + k, (i + 1) * stride + k,
                          (i + 1) * stride + k + 1, i * stride + k + 1))
    ci = len(verts)
    verts.append(tuple(rings[0][0])); vcoord.append((0.5, 0.0))
    for k in range(radial):
        faces.append((ci, (k + 1) % radial, k))
    ci = len(verts)
    verts.append(tuple(rings[-1][0])); vcoord.append((0.5, 1.0))
    base = (n - 1) * stride
    for k in range(radial):
        faces.append((ci, base + k, base + (k + 1) % radial))
    me = bpy.data.meshes.new(name + "Mesh")
    me.from_pydata(verts, [], faces)
    me.update()
    uv = me.uv_layers.new(name="UVMap")
    for loop in me.loops:
        uv.data[loop.index].uv = vcoord[loop.vertex_index]
    o = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(o)
    for p in me.polygons:
        p.use_smooth = True
    if material is not None:
        me.materials.append(material)
    o.parent = parent
    o.location = (0, 0, 0)
    return o

def pivot(parent, name, loc):
    o = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(o)
    o.empty_display_size = 0.04
    if parent is not None:
        o.parent = parent
    o.location = loc
    return o

def star(parent, name, loc, r_out, r_in, thick, material, rot=(0, 0, 0)):
    verts, faces = [(0.0, 0.0, 0.0)], []
    ring = []
    for k in range(10):
        a = D(90 + k * 36)
        r = r_out if k % 2 == 0 else r_in
        ring.append(len(verts))
        verts.append((r * math.cos(a), 0.0, r * math.sin(a)))
    for k in range(10):
        faces.append((0, ring[k], ring[(k + 1) % 10]))
    me = bpy.data.meshes.new(name + "Mesh")
    me.from_pydata(verts, [], faces)
    me.update()
    o = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(o)
    me.materials.append(material)
    mod = o.modifiers.new("sol", 'SOLIDIFY')
    mod.thickness = thick
    bpy.context.view_layer.objects.active = o
    o.select_set(True)
    bpy.ops.object.modifier_apply(modifier=mod.name)
    o.select_set(False)
    return _finish(o, name, parent, loc, None, rot)

def arc_strip(parent, name, cx, cz, y, radius, a0, a1, width, thick, material, steps=14):
    """Thin curved ribbon in the XZ plane at fixed y (for lash lines).
    Angles in degrees, 90 = top. Ribbon width runs radially, then a
    SOLIDIFY pass gives it thickness along its normal."""
    verts, faces = [], []
    for i in range(steps + 1):
        a = D(a0 + (a1 - a0) * i / steps)
        dx, dz = math.cos(a), math.sin(a)
        verts.append((cx + dx * (radius - width / 2), y, cz + dz * (radius - width / 2)))
        verts.append((cx + dx * (radius + width / 2), y, cz + dz * (radius + width / 2)))
    for i in range(steps):
        b = i * 2
        faces.append((b, b + 2, b + 3, b + 1))
    me = bpy.data.meshes.new(name + "Mesh")
    me.from_pydata(verts, [], faces)
    me.update()
    o = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(o)
    me.materials.append(material)
    mod = o.modifiers.new("sol", 'SOLIDIFY')
    mod.thickness = thick
    bpy.context.view_layer.objects.active = o
    o.select_set(True)
    bpy.ops.object.modifier_apply(modifier=mod.name)
    o.select_set(False)
    o.parent = parent
    o.location = (0, 0, 0)
    return o

# ---------------------------------------------------------------- hierarchy
# v6 layout (Blender z, ground 0, total height 1.55, ~7.3 heads), measured
# from art/stella-concept.png (docs/MEASUREMENTS_V6.md):
#   eyes 1.438 (0.93) / chin 1.338 (0.86) / shoulders 1.33 (0.86)
#   jacket hem 1.116 (0.72) / navel 1.039 (0.67) / shorts hem 0.775 (0.50)
#   knees 0.51 (0.33) / boot tops 0.279 (0.18) / twintail tips ~0.70 (0.45)
# Right = -X, left = +X (faces -Y in Blender, +Z in glTF).

def jaw_taper_unit(o, amt):
    """Narrow the lower half of a unit-sphere mesh toward a tapered chin."""
    me = o.data
    for v in me.vertices:
        if v.co.z < 0.0:
            t = min(1.0, -v.co.z)
            s = 1.0 - amt * (t ** 1.6)
            v.co.x *= s
            if v.co.y < 0.0:
                v.co.y *= (1.0 - 0.38 * amt * (t ** 1.6))
    me.update()

Root = pivot(None, "Stella", (0, 0, 0))
Body = pivot(Root, "Body", (0, 0, 0.98))

# ---- pelvis / shorts (children of Body; shorts span z 1.00 -> 0.78)
pelvis = rbox(Body, "Shorts", (0, 0, -0.09), (0.27, 0.19, 0.22), M["dark"], bevel=0.045)
taper_z(pelvis, -0.11, 0.11, 0.95, 1.03)
for s, tag in ((+1, "L"), (-1, "R")):
    cyl(Body, f"ShortsLeg{tag}", (0.082 * s, 0, -0.155), 0.082, 0.077, 0.13,
        M["dark"], rot=(0, D(-3 * s), 0))
    cyl(Body, f"ShortsCuff{tag}", (0.083 * s, 0, -0.205), 0.080, 0.078, 0.030,
        M["glove"], rot=(0, D(-3 * s), 0))
for s, tag in ((+1, "L"), (-1, "R")):  # shorts side seams
    rbox(Body, f"ShortsSeam{tag}", (0.137 * s, 0, -0.075), (0.005, 0.17, 0.13),
         M["glove"], bevel=0.002)
rbox(Body, "Belt", (0, 0, 0.005), (0.282, 0.20, 0.05), M["glove"], bevel=0.012)
for i, hx in enumerate((-0.108, -0.086, 0.086, 0.108)):  # belt holes
    cyl(Body, f"BeltHole{i}", (hx, -0.1015, 0.005), 0.005, 0.005, 0.006,
        M["dark"], rot=(D(90), 0, 0), vertices=12)
rbox(Body, "Buckle", (0, -0.10, 0.005), (0.07, 0.012, 0.038), M["metal"], bevel=0.004)
rbox(Body, "BuckleIn", (0, -0.108, 0.005), (0.042, 0.005, 0.022), M["dark"], bevel=0.002)
rbox(Body, "BeltStrapL", (0.062, -0.10, -0.065), (0.030, 0.010, 0.115), M["orange"],
     rot=(D(4), 0, D(-5)), bevel=0.004)
rbox(Body, "BeltStrapR", (-0.068, -0.10, -0.055), (0.030, 0.010, 0.095), M["orange"],
     rot=(D(4), 0, D(5)), bevel=0.004)
# sheath at her LEFT hip (+X), grip up; blade tip when sheathed ~0.62
rbox(Body, "Sheath", (0.163, 0.012, -0.10), (0.045, 0.066, 0.27), M["teal_d"],
     rot=(D(9), 0, D(-7)), bevel=0.010)
rbox(Body, "SheathCap", (0.153, 0.010, 0.028), (0.050, 0.072, 0.028), M["metal"], bevel=0.005)
sph(Body, "SheathGem", (0.148, -0.028, 0.028), (0.010, 0.007, 0.010), M["blade"], seg=16, rings=12)

# ---- legs: Leg pivot (hip, world 0.97) -> thigh; Knee pivot (0.51) -> shin + boot
def build_leg(s, tag):
    leg = pivot(Body, f"Leg_{tag}", (0.085 * s, 0, -0.01))
    sph(leg, f"HipBall_{tag}", (0, 0, -0.005), (0.064, 0.060, 0.058), M["skin"])
    cyl(leg, f"Thigh_{tag}", (0, 0, -0.23), 0.062, 0.046, 0.46, M["skin"])
    # over-knee sock: top at world 0.68 (leg-local -0.29), teal band + star
    cyl(leg, f"SockTop_{tag}", (0, 0, -0.375), 0.0505, 0.0465, 0.17, M["sock"])
    cyl(leg, f"SockBand_{tag}", (0, 0, -0.302), 0.0525, 0.0515, 0.032, M["teal"])
    if tag == "L":  # small white star on her left sock (art)
        star(leg, "SockStar", (0, -0.0495, -0.345), 0.017, 0.0075, 0.005, M["white"])
    if tag == "R":  # thigh strap on her right leg, just below the shorts (art)
        cyl(leg, "ThighStrap", (0, 0, -0.235), 0.0565, 0.0545, 0.032, M["glove"])
        rbox(leg, "ThighBuckle", (0, -0.056, -0.235), (0.038, 0.010, 0.024), M["metal"], bevel=0.003)
    knee = pivot(leg, f"Knee_{tag}", (0, 0, -0.46))
    sph(knee, f"KneeBall_{tag}", (0, 0, 0.004), (0.047, 0.045, 0.043), M["sock"])
    cyl(knee, f"Shin_{tag}", (0, 0, -0.115), 0.046, 0.039, 0.23, M["sock"])
    sph(knee, f"Calf_{tag}", (0, 0.017, -0.085), (0.040, 0.038, 0.075), M["sock"])
    # chunky boot: cuff top at world 0.279 (knee-local -0.231), sole bottom 0
    rbox(knee, f"BootCuff_{tag}", (0, 0, -0.266), (0.128, 0.142, 0.07), M["teal_d"], bevel=0.018)
    rbox(knee, f"BootIn_{tag}", (0, -0.008, -0.248), (0.10, 0.11, 0.045), M["teal"], bevel=0.013)
    boot = rbox(knee, f"Boot_{tag}", (0, -0.010, -0.395), (0.122, 0.185, 0.18), M["dark"], bevel=0.028)
    taper_z(boot, -0.09, 0.09, 0.96, 1.05)
    rbox(knee, f"BootSeam_{tag}", (0, -0.086, -0.345), (0.124, 0.007, 0.009), M["glove"], bevel=0.002)
    rbox(knee, f"BootSideSeam_{tag}", (0.062 * s, -0.010, -0.395), (0.005, 0.17, 0.009), M["glove"], bevel=0.002)
    sph(knee, f"BootToe_{tag}", (0, -0.082, -0.435), (0.058, 0.064, 0.044), M["dark"])
    rbox(knee, f"ToeSeam_{tag}", (0, -0.132, -0.425), (0.104, 0.005, 0.011), M["glove"], bevel=0.002)
    rbox(knee, f"Midsole_{tag}", (0, -0.018, -0.478), (0.13, 0.215, 0.02), M["cream"], bevel=0.005)
    rbox(knee, f"Sole_{tag}", (0, -0.016, -0.494), (0.128, 0.212, 0.032), M["glove"], bevel=0.007)
    rbox(knee, f"SoleAccent_{tag}", (0, -0.112, -0.492), (0.09, 0.018, 0.04), M["orange"], bevel=0.004)
    for i, zz in enumerate((-0.345, -0.415)):
        rbox(knee, f"BootStrap{tag}{i}", (0, -0.10, zz), (0.126, 0.014, 0.038), M["glove"], bevel=0.004)
        rbox(knee, f"BootBuckle{tag}{i}", (0.054 * s, -0.106, zz), (0.030, 0.011, 0.025), M["orange"], bevel=0.003)
    rbox(knee, f"BootTab_{tag}", (0, 0.078, -0.272), (0.032, 0.018, 0.052), M["orange"], bevel=0.005)
    return leg, knee

LegL, KneeL = build_leg(+1, "L")
LegR, KneeR = build_leg(-1, "R")

# ---- torso (pivot at waist, world z 1.03)
Torso = pivot(Body, "Torso", (0, 0, 0.05))
# bare midriff: visible skin band world 1.00 -> 1.116, navel at 1.039
rbox(Torso, "Midriff", (0, 0, 0.045), (0.20, 0.148, 0.13), M["skin"], bevel=0.032)
sph(Torso, "Navel", (0, -0.0755, 0.009), (0.007, 0.0035, 0.010), M["skin_sh"], seg=12, rings=8)
# cropped jacket: hem at world 1.116 (local 0.086) up to shoulders 1.333
jacket = rbox(Torso, "Jacket", (0, 0, 0.195), (0.29, 0.19, 0.24), M["cream"], bevel=0.05)
taper_z(jacket, -0.12, 0.12, 0.92, 1.05)
rbox(Torso, "JacketHem", (0, 0, 0.09), (0.272, 0.182, 0.03), M["orange"], bevel=0.007)
rbox(Torso, "ChestPanel", (0, -0.082, 0.20), (0.215, 0.03, 0.185), M["teal"], bevel=0.010)
for s, tag in ((+1, "L"), (-1, "R")):  # chest panel piping
    rbox(Torso, f"PanelPipe{tag}", (0.102 * s, -0.094, 0.20), (0.008, 0.009, 0.175),
         M["teal_d"], bevel=0.003)
rbox(Torso, "Zipper", (0, -0.098, 0.195), (0.017, 0.007, 0.18), M["dark"], bevel=0.002)
rbox(Torso, "ZipperTeeth", (0, -0.101, 0.195), (0.007, 0.0035, 0.168), M["metal"], bevel=0.001)
rbox(Torso, "ZipperPull", (0, -0.104, 0.128), (0.014, 0.005, 0.03), M["metal"], bevel=0.002)
star(Torso, "ChestStar", (0.058, -0.0995, 0.215), 0.030, 0.0135, 0.007, M["white"])
# standing collar: teal outside / orange lining, points up beside the jaw
for s, tag in ((+1, "L"), (-1, "R")):
    rbox(Torso, f"Collar{tag}", (0.082 * s, -0.028, 0.318), (0.115, 0.02, 0.125),
         M["teal_d"], rot=(D(-30), D(-14 * s), D(8 * s)), bevel=0.008)
    rbox(Torso, f"CollarIn{tag}", (0.075 * s, -0.040, 0.310), (0.096, 0.011, 0.108),
         M["orange"], rot=(D(-30), D(-14 * s), D(8 * s)), bevel=0.005)
    rbox(Torso, f"CollarEdge{tag}", (0.089 * s, -0.021, 0.338), (0.121, 0.013, 0.022),
         M["teal"], rot=(D(-30), D(-14 * s), D(8 * s)), bevel=0.004)
rbox(Torso, "CollarBack", (0, 0.048, 0.322), (0.20, 0.10, 0.125), M["teal_d"],
     rot=(D(14), 0, 0), bevel=0.02)
# diagonal shoulder strap + buckle
rbox(Torso, "Strap", (0.008, -0.10, 0.175), (0.046, 0.011, 0.34), M["dark"],
     rot=(0, D(36), 0), bevel=0.004)
rbox(Torso, "StrapBuckle", (-0.062, -0.106, 0.235), (0.045, 0.013, 0.045), M["orange"], bevel=0.004)
# satchel hanging at her right hip (-X), world centre z ~0.89; flap faces out (-X)
rbox(Torso, "Satchel", (-0.205, 0.022, -0.14), (0.085, 0.185, 0.205), M["bag"], bevel=0.02)
rbox(Torso, "SatchelFlap", (-0.252, 0.018, -0.085), (0.024, 0.165, 0.115), M["cream"],
     bevel=0.009)
rbox(Torso, "SatchelFlapSeam", (-0.266, 0.018, -0.085), (0.006, 0.172, 0.122), M["bag"], bevel=0.002)
star(Torso, "SatchelStar", (-0.268, 0.018, -0.085), 0.027, 0.0115, 0.006, M["orange"],
     rot=(0, D(90), 0))
rbox(Torso, "SatchelClasp", (-0.258, 0.018, -0.155), (0.016, 0.042, 0.032), M["metal"], bevel=0.004)
rbox(Torso, "SatchelStrapBit", (-0.175, -0.045, -0.028), (0.04, 0.011, 0.115), M["dark"],
     rot=(D(18), 0, D(14)), bevel=0.004)

# ---- arms: Arm pivot (shoulder, world 1.33) -> puffy sleeve; Elbow (1.105)
def build_arm(s, tag):
    arm = pivot(Torso, f"Arm_{tag}", (0.15 * s, 0, 0.30))
    sph(arm, f"Shoulder_{tag}", (0.004 * s, 0, 0.002), (0.062, 0.058, 0.064), M["cream"])
    # puffy cream sleeve: bulb + short cylinder
    sph(arm, f"SleevePuff_{tag}", (0.008 * s, 0, -0.075), (0.072, 0.068, 0.082), M["cream"])
    cyl(arm, f"Sleeve_{tag}", (0.009 * s, 0, -0.135), 0.056, 0.050, 0.09, M["cream"],
        rot=(0, 0, D(2 * s)))
    cyl(arm, f"SleeveCuff_{tag}", (0.010 * s, 0, -0.185), 0.054, 0.051, 0.04, M["teal"])
    cyl(arm, f"CuffTrim_{tag}", (0.010 * s, 0, -0.162), 0.0565, 0.0555, 0.012, M["orange"])
    if tag == "R":  # orange patch with white star on her right sleeve (art)
        rbox(arm, "SleevePatch", (0.008 * s, -0.062, -0.075), (0.055, 0.012, 0.06),
             M["orange"], bevel=0.004)
        star(arm, "SleevePatchStar", (0.008 * s, -0.0695, -0.075), 0.016, 0.007, 0.004, M["white"])
    elbow = pivot(arm, f"Elbow_{tag}", (0.011 * s, 0, -0.225))
    sph(elbow, f"ElbowBall_{tag}", (0, 0, 0.003), (0.037, 0.035, 0.035), M["skin"])
    cyl(elbow, f"Forearm_{tag}", (0, 0, -0.10), 0.033, 0.029, 0.20, M["skin"])
    cyl(elbow, f"Wrist_{tag}", (0, 0, -0.207), 0.039, 0.037, 0.034, M["orange"])
    sph(elbow, f"Hand_{tag}", (0, -0.003, -0.262), (0.042, 0.039, 0.056), M["glove"])
    rbox(elbow, f"FingerGroove_{tag}", (0, -0.031, -0.285), (0.05, 0.008, 0.007), M["dark"], bevel=0.003)
    sph(elbow, f"Thumb_{tag}", (0.012 * s, -0.033, -0.232), (0.015, 0.016, 0.026), M["glove"], seg=20, rings=14)
    return arm, elbow

ArmL, ElbowL = build_arm(+1, "L")
ArmR, ElbowR = build_arm(-1, "R")

# ---- energy blade gripped in the right hand (child of Elbow_R)
Blade = pivot(ElbowR, "Blade", (0, -0.003, -0.268))
cyl(Blade, "BladeGrip", (0, 0, -0.006), 0.0145, 0.0145, 0.10, M["dark"], vertices=16)
for i, gz in enumerate((0.024, -0.006, -0.036)):  # handle wrap rings
    cyl(Blade, f"GripWrap{i}", (0, 0, gz), 0.0162, 0.0162, 0.011, M["orange"], vertices=16)
cyl(Blade, "BladePommel", (0, 0, 0.05), 0.0175, 0.0175, 0.018, M["blade"], vertices=16)
rbox(Blade, "BladeGuard", (0, 0, -0.062), (0.068, 0.028, 0.016), M["metal"], bevel=0.004)
blade_mesh = rbox(Blade, "BladeEdge", (0, 0, -0.20), (0.05, 0.012, 0.26), M["blade"], bevel=0.004)
rbox(Blade, "BladeFuller", (0, -0.0075, -0.195), (0.012, 0.0035, 0.21), M["eye_hi"], bevel=0.001)
taper_z(blade_mesh, -0.13, 0.13, 0.45, 1.0, axes=(0,))
cyl(Blade, "BladeTip", (0, 0, -0.362), 0.001, 0.024, 0.065, M["blade"],
    rot=(D(180), 0, 0), vertices=12, scale=(1.0, 0.24, 1.0))

# ---- head (pivot at neck, world z 1.36). Head height 0.214 (~7.3 heads):
# top 1.552, chin 1.338, eyes at local 0.078 (world 1.438, 56% from top).
Head = pivot(Torso, "Head", (0, 0, 0.33))
cyl(Head, "Neck", (0, 0, -0.018), 0.037, 0.040, 0.085, M["skin"])
face = sph(Head, "Face", (0, -0.004, 0.085), (0.104, 0.092, 0.106), M["skin"])
jaw_taper_unit(face, 0.30)
# hair mass: cap + back panel down to the shoulders (face front stays open)
cap = sph(Head, "HairCap", (0, 0.012, 0.098), (0.111, 0.099, 0.113), M["hair"])
jaw_taper_unit(cap, 0.20)
sph(Head, "HairBack", (0, 0.045, 0.045), (0.107, 0.088, 0.135), M["hair"])
# back-hair ribbons falling from the cap toward the shoulders
for i, (bx, bw) in enumerate([(-0.055, 0.040), (0.0, 0.046), (0.055, 0.040)]):
    rings = [(Vector((bx, 0.105, 0.150)), bw, 0.013),
             (Vector((bx * 1.06, 0.112, 0.060)), bw * 0.94, 0.012),
             (Vector((bx * 1.08, 0.112, -0.030)), bw * 0.80, 0.011),
             (Vector((bx * 1.04, 0.106, -0.095)), bw * 0.52, 0.009),
             (Vector((bx, 0.100, -0.135)), bw * 0.16, 0.005)]
    tube(Head, f"BackStrand{i}", rings, M["hair"], radial=16)
# fringe scoop hugging the forehead
sph(Head, "Fringe", (0, -0.045, 0.158), (0.107, 0.066, 0.060), M["hair"])
# bang locks: shaped ribbons hanging from the hairline to just above the eyes
bang_specs = [(-0.072, 0.060, -9), (-0.049, 0.072, -5), (-0.025, 0.080, -2),
              (0.0, 0.084, 0), (0.025, 0.080, 2), (0.049, 0.072, 5), (0.072, 0.060, 9)]
for i, (bx, blen, tilt) in enumerate(bang_specs):
    z0 = 0.186
    rings = [(Vector((bx, -0.080, z0)), 0.0205, 0.0075),
             (Vector((bx + tilt * 0.0004, -0.086, z0 - blen * 0.45)), 0.018, 0.007),
             (Vector((bx + tilt * 0.0008, -0.086, z0 - blen * 0.8)), 0.0125, 0.006),
             (Vector((bx + tilt * 0.0011, -0.082, z0 - blen)), 0.0012, 0.002)]
    tube(Head, f"Bang{i}", rings, M["hair"], radial=12)
# side locks framing the face down to the jaw: flat ribbons, width along Y
for s, tag in ((+1, "L"), (-1, "R")):
    rings = [(Vector((0.099 * s, -0.048, 0.175)), 0.009, 0.023),
             (Vector((0.103 * s, -0.056, 0.095)), 0.0085, 0.021),
             (Vector((0.102 * s, -0.058, 0.015)), 0.0075, 0.018),
             (Vector((0.097 * s, -0.056, -0.045)), 0.005, 0.012),
             (Vector((0.092 * s, -0.052, -0.075)), 0.0012, 0.003)]
    tube(Head, f"SideLock{tag}", rings, M["hair"], radial=12)
    rings = [(Vector((0.104 * s, -0.008, 0.160)), 0.007, 0.016),
             (Vector((0.108 * s, -0.012, 0.080)), 0.0065, 0.015),
             (Vector((0.106 * s, -0.013, 0.005)), 0.005, 0.011),
             (Vector((0.100 * s, -0.012, -0.050)), 0.0012, 0.003)]
    tube(Head, f"SideLockB{tag}", rings, M["hair_d"], radial=12)
    sph(Head, f"Ear{tag}", (0.101 * s, 0.002, 0.058), (0.016, 0.013, 0.024), M["skin"], seg=20, rings=14)
# ahoge: small curved strand on top
rings = [(Vector((0.006, 0.008, 0.205)), 0.0095, 0.0095),
         (Vector((0.013, 0.005, 0.232)), 0.0082, 0.0082),
         (Vector((0.028, 0.000, 0.248)), 0.0065, 0.0065),
         (Vector((0.046, -0.003, 0.246)), 0.004, 0.004),
         (Vector((0.058, -0.005, 0.234)), 0.0012, 0.0012)]
tube(Head, "Ahoge", rings, M["hair"], radial=12)
# face: two-tone eyes with lash line, brows, nose hint, open-smile mouth, blush
for s, tag in ((+1, "L"), (-1, "R")):
    sph(Head, f"Eye{tag}", (0.037 * s, -0.0830, 0.078), (0.0205, 0.0075, 0.0335), M["eye"], seg=28, rings=20)
    sph(Head, f"EyeMid{tag}", (0.037 * s, -0.0875, 0.073), (0.0155, 0.006, 0.0245), M["eye_mid"], seg=24, rings=16)
    sph(Head, f"EyeIris{tag}", (0.037 * s, -0.0890, 0.066), (0.0135, 0.0055, 0.0195), M["eye_hi"], seg=24, rings=16)
    sph(Head, f"EyePupil{tag}", (0.037 * s, -0.0900, 0.080), (0.0065, 0.003, 0.012), M["eye"], seg=16, rings=12)
    sph(Head, f"EyeHi{tag}", (0.0345 * s, -0.0915, 0.094), (0.0075, 0.0032, 0.010), M["white"], seg=16, rings=12)
    sph(Head, f"EyeHi2{tag}", (0.0405 * s, -0.0905, 0.062), (0.0038, 0.0022, 0.0052), M["white"], seg=12, rings=8)
    arc_strip(Head, f"Lash{tag}", 0.037 * s, 0.082, -0.0915, 0.0195, 30, 150, 0.005, 0.004, M["dark"])
    rbox(Head, f"Brow{tag}", (0.039 * s, -0.0895, 0.118), (0.030, 0.004, 0.007),
         M["hair_d"], rot=(D(-10), 0, D(-5 * s)), bevel=0.002)
    sph(Head, f"Blush{tag}", (0.064 * s, -0.070, 0.038), (0.020, 0.006, 0.011),
        M["blush"], rot=(0, D(-24 * s), 0), seg=20, rings=14)
sph(Head, "Nose", (0, -0.0945, 0.048), (0.0045, 0.0025, 0.006), M["skin_sh"], seg=12, rings=8)
sph(Head, "Mouth", (0, -0.0895, 0.030), (0.0135, 0.005, 0.009), M["mouth"], seg=20, rings=14)
# star hairpin on the viewer's left (-X), sitting on the hair surface
star(Head, "Hairpin", (-0.068, -0.088, 0.128), 0.029, 0.013, 0.008, M["orange"],
     rot=(D(-16), D(14), D(10)))

# ---- twintails: WIDE wavy ribbon volumes (not tubes). Root at world
# (+/-0.082, 0.028, 1.488); tips reach world z ~0.70 (0.45 of height) and
# the hair flares to about +/-0.36 in x - far wider than the body.
def build_tail(s, tag):
    tail = pivot(Head, f"Twintail_{tag}", (0.082 * s, 0.028, 0.128))
    # boxy black/orange root accessory (art)
    rbox(tail, f"Tie_{tag}", (0.004 * s, 0.002, 0.012), (0.062, 0.058, 0.085),
         M["dark"], rot=(D(6), 0, D(-8 * s)), bevel=0.010)
    rbox(tail, f"TieTop_{tag}", (0.004 * s, 0.0, 0.062), (0.064, 0.060, 0.030),
         M["orange"], rot=(D(6), 0, D(-8 * s)), bevel=0.006)
    # flowing orange ribbons from the tie
    rings = [(Vector((0.018 * s, 0.024, 0.030)), 0.020, 0.005),
             (Vector((0.062 * s, 0.036, -0.015)), 0.017, 0.0045),
             (Vector((0.095 * s, 0.040, -0.075)), 0.012, 0.004),
             (Vector((0.108 * s, 0.038, -0.125)), 0.0015, 0.0015)]
    tube(tail, f"RibbonA_{tag}", rings, M["orange"], radial=10)
    rings = [(Vector((0.010 * s, -0.026, 0.028)), 0.017, 0.0045),
             (Vector((0.045 * s, -0.034, -0.020)), 0.014, 0.004),
             (Vector((0.066 * s, -0.034, -0.085)), 0.0015, 0.0015)]
    tube(tail, f"RibbonB_{tag}", rings, M["orange"], radial=10)
    # main strand: wide flat wavy ribbon, S-curve flare, pointed tip
    main = [(0.005, 0.005, 0.030, 0.046, 0.020), (0.062, 0.012, -0.060, 0.068, 0.024),
            (0.128, 0.018, -0.180, 0.086, 0.027), (0.172, 0.020, -0.320, 0.092, 0.027),
            (0.185, 0.018, -0.460, 0.086, 0.025), (0.168, 0.014, -0.580, 0.070, 0.022),
            (0.138, 0.010, -0.680, 0.048, 0.017), (0.112, 0.006, -0.755, 0.022, 0.012),
            (0.100, 0.004, -0.795, 0.003, 0.004)]
    rings = [(Vector((px * s, py, pz)), rx, ry) for (px, py, pz, rx, ry) in main]
    tube(tail, f"TailMain_{tag}", rings, M["hair"], radial=20)
    # front strand: shorter, slightly narrower, in front of the main strand
    front = [(0.000, -0.030, 0.020, 0.038, 0.017), (0.048, -0.026, -0.070, 0.056, 0.020),
             (0.092, -0.020, -0.190, 0.066, 0.021), (0.125, -0.014, -0.320, 0.068, 0.020),
             (0.132, -0.010, -0.440, 0.060, 0.018), (0.116, -0.006, -0.545, 0.046, 0.015),
             (0.092, -0.003, -0.630, 0.028, 0.012), (0.075, -0.001, -0.690, 0.003, 0.004)]
    rings = [(Vector((px * s, py, pz)), rx, ry) for (px, py, pz, rx, ry) in front]
    tube(tail, f"TailFront_{tag}", rings, M["hair"], radial=20)
    # back strand: darker, behind, a touch wider flare
    back = [(0.010, 0.034, 0.025, 0.040, 0.018), (0.066, 0.040, -0.055, 0.058, 0.021),
            (0.120, 0.044, -0.175, 0.070, 0.022), (0.160, 0.046, -0.310, 0.072, 0.021),
            (0.168, 0.044, -0.440, 0.066, 0.019), (0.152, 0.040, -0.555, 0.052, 0.016),
            (0.120, 0.034, -0.650, 0.032, 0.013), (0.092, 0.028, -0.715, 0.003, 0.004)]
    rings = [(Vector((px * s, py, pz)), rx, ry) for (px, py, pz, rx, ry) in back]
    tube(tail, f"TailBack_{tag}", rings, M["hair_d"], radial=20)
    # split-tip companion: a thinner strand peeling off the main tip, inner side
    split = [(0.128, 0.008, -0.560, 0.020, 0.010), (0.106, 0.006, -0.650, 0.017, 0.009),
             (0.082, 0.004, -0.730, 0.012, 0.007), (0.064, 0.003, -0.800, 0.002, 0.002)]
    rings = [(Vector((px * s, py, pz)), rx, ry) for (px, py, pz, rx, ry) in split]
    tube(tail, f"TailSplit_{tag}", rings, M["hair"], radial=14)
    return tail

TwinL = build_tail(+1, "L")
TwinR = build_tail(-1, "R")

bpy.context.view_layer.update()
print("BUILD OK, objects:", len(bpy.data.objects))


# ---------------------------------------------------------------- v4 texture pass
# Runs after all geometry exists, before animation/export. Only UVs and
# material texture wiring change; no vertex positions, pivots or clips.
TEXDIR = os.path.join(ASSETS, "textures")

def tex_mat(name, fname, rough=0.6):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = rough
    img = bpy.data.images.load(os.path.join(TEXDIR, fname))
    img.colorspace_settings.name = 'sRGB'
    tex = m.node_tree.nodes.new("ShaderNodeTexImage")
    tex.image = img
    m.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    return m

SkinTex = tex_mat("SkinTex", "skin.png", 0.60)
HairTex = tex_mat("HairTex", "hair.png", 0.48)
HairTexDk = tex_mat("HairTexDk", "hair_dark.png", 0.55)
IrisTex = tex_mat("IrisTex", "iris.png", 0.30)
AtlasTex = tex_mat("ClothesAtlas", "clothes_atlas.png", 0.80)

def set_mat(obj, material):
    if obj is None or obj.type != 'MESH':
        return
    obj.data.materials.clear()
    obj.data.materials.append(material)

def obj(name):
    return bpy.data.objects.get(name)

# HEAD: planar front projection from local (unit-sphere) coords.
# u = x*0.5+0.5, v = z*0.5+0.5 - face front is one big island; the back
# of the sphere projects onto the same island but is covered by hair.
face = obj("Face")
me = face.data
if not me.uv_layers:
    me.uv_layers.new(name="UVMap")
uvl = me.uv_layers.active
vuv = {}
for v in me.vertices:
    vuv[v.index] = (v.co.x * 0.5 + 0.5, v.co.z * 0.5 + 0.5)
for loop in me.loops:
    uvl.data[loop.index].uv = vuv[loop.vertex_index]
set_mat(face, SkinTex)

# IRIS geometry gets the iris texture (sphere UVs; gradient runs along V)
for nm in ("EyeIrisL", "EyeIrisR"):
    set_mat(obj(nm), IrisTex)

# HAIR: every hair mesh gets the hair texture. Tube strands already carry
# proper U/V; caps/fringe/bangs use their primitive UVs (V gradient).
hair_names = ["HairCap", "HairBack", "Fringe", "Ahoge"]
hair_names += [f"Bang{i}" for i in range(7)]
hair_names += [f"BackStrand{i}" for i in range(3)]
for s in ("L", "R"):
    hair_names += [f"SideLock{s}", f"TailMain_{s}", f"TailFront_{s}", f"TailSplit_{s}"]
hair_dk_names = []
for s in ("L", "R"):
    hair_dk_names += [f"SideLockB{s}", f"TailBack_{s}"]
for nm in hair_names:
    set_mat(obj(nm), HairTex)
for nm in hair_dk_names:
    set_mat(obj(nm), HairTexDk)

# CLOTHES ATLAS: remap each mapped mesh's UVs into its material's tile
# (4x4 grid of 256px tiles; tile row counted from the bottom in UV space).
TILES = {"Cream": (0, 3), "Teal": (1, 3), "TealDk": (2, 3), "Orange": (3, 3),
         "Dark": (0, 2), "Bag": (1, 2), "Glove": (2, 2), "Sock": (3, 2)}
for o in list(bpy.data.objects):
    if o.type != 'MESH' or not o.data.materials:
        continue
    mname = o.data.materials[0].name if o.data.materials[0] else ""
    if mname not in TILES:
        continue
    col, row = TILES[mname]
    me = o.data
    if not me.uv_layers:  # from_pydata meshes (stars): park UV at tile centre
        uvl = me.uv_layers.new(name="UVMap")
        for loop in me.loops:
            uvl.data[loop.index].uv = ((col + 0.5) / 4.0, (row + 0.5) / 4.0)
    else:
        uvl = me.uv_layers.active
        inset = 0.004
        for d in uvl.data:
            u, v = d.uv
            d.uv = ((col + inset + u * (1 - 2 * inset)) / 4.0,
                    (row + inset + v * (1 - 2 * inset)) / 4.0)
    set_mat(o, AtlasTex)
print("TEXTURE PASS OK")

# ---------------------------------------------------------------- animation
# Signs (faces -Y, up +Z): limb forward swing = -rotX; knee bend (shin
# back) = +rotX on Knee; elbow bend (forearm fwd) = -rotX on Elbow;
# sideways limb swing = rotY (+rotY tips a downward limb toward -X);
# torso/head twist = rotZ; nod fwd = +rotX.
ANIMATED = [Body, Torso, Head, ArmL, ElbowL, ArmR, ElbowR,
            LegL, KneeL, LegR, KneeR, TwinL, TwinR, Blade]
BASE_LOC = {o.name: tuple(o.location) for o in ANIMATED}
ACTIONS = {}

def reset_pose():
    for o in ANIMATED:
        o.location = BASE_LOC[o.name]
        o.rotation_euler = (0, 0, 0)

def begin(anim):
    ACTIONS[anim] = {}
    for o in ANIMATED:
        a = bpy.data.actions.new(f"{anim}__{o.name}")
        a.use_fake_user = True
        o.animation_data_create()
        o.animation_data.action = a
        ACTIONS[anim][o.name] = a
    reset_pose()

def K(obj, frame, rot=None, loc=None):
    if loc is not None:
        obj.location = loc
        obj.keyframe_insert("location", frame=frame)
    if rot is not None:
        obj.rotation_euler = (D(rot[0]), D(rot[1]), D(rot[2]))
        obj.keyframe_insert("rotation_euler", frame=frame)

def KB(frame, dz=0.0, dx=0.0, rot=(0, 0, 0)):
    K(Body, frame, rot=rot, loc=(dx, 0, BASE_LOC["Body"][2] + dz))

# ---- Idle: 48f loop. Breathing + slow weight shift + tail sway.
begin("Idle")
for f, ph, sh in ((0, 0.0, -1.0), (12, 1.0, 0.0), (24, 0.0, 1.0), (36, 1.0, 0.0), (48, 0.0, -1.0)):
    KB(f, dz=0.009 * ph, dx=0.007 * sh, rot=(0.6 * ph, 1.3 * sh, 0))
    K(Torso, f, rot=(1.7 * ph, 0, 0.7 * sh))
    K(Head, f, rot=(0.9 * ph, -2.2 * sh, 1.2 * sh))
    K(ArmL, f, rot=(3 - 2.2 * ph, -5 - 1.2 * sh, 0))
    K(ArmR, f, rot=(3 + 2.2 * ph, 5 - 1.2 * sh, 0))
    K(ElbowL, f, rot=(-9 - 2.5 * ph, 0, 0))
    K(ElbowR, f, rot=(-9 + 2.5 * ph, 0, 0))
    K(LegL, f, rot=(0.8 * sh, -1.6, 0))
    K(LegR, f, rot=(-0.8 * sh, 1.6, 0))
    K(KneeL, f, rot=(3 + 0.8 * ph, 0, 0))
    K(KneeR, f, rot=(3 - 0.8 * ph, 0, 0))
    K(TwinL, f, rot=(2.6 * (ph - 0.5), -2.5 - 1.5 * sh, 0))
    K(TwinR, f, rot=(2.6 * (0.5 - ph), 2.5 - 1.5 * sh, 0))
    K(Blade, f, rot=(4, 0, 0))

# ---- Run: 24f loop, keys every 3 frames. Knee lift, elbow pump, bounce.
begin("Run")
for i in range(9):
    f = i * 3
    ph = 2 * math.pi * i / 8.0
    s, c = math.sin(ph), math.cos(ph)
    KB(f, dz=0.030 * abs(s) - 0.006, rot=(7, 0, 0))
    K(Torso, f, rot=(9.5, 0, 4.2 * s))
    K(Head, f, rot=(-5, 0, -3.2 * s))
    K(LegL, f, rot=(-38 * s, -1.5, 0))
    K(LegR, f, rot=(38 * s, 1.5, 0))
    K(KneeL, f, rot=(8 + 47 * max(0.0, c) ** 1.2, 0, 0))
    K(KneeR, f, rot=(8 + 47 * max(0.0, -c) ** 1.2, 0, 0))
    K(ArmL, f, rot=(27 * s, -8, 0))
    K(ArmR, f, rot=(-27 * s, 8, 0))
    K(ElbowL, f, rot=(-40 + 13 * s, 0, 0))
    K(ElbowR, f, rot=(-40 - 13 * s, 0, 0))
    K(TwinL, f, rot=(15 + 9 * math.sin(2 * ph - 1.2), -5 + 2 * s, 0))
    K(TwinR, f, rot=(15 + 9 * math.sin(2 * ph - 1.2), 5 + 2 * s, 0))
    # counter-rotate the blade so it stays resting along the hip while running
    K(Blade, f, rot=(40 + 40 * s, 0, 0))

# ---- Jump: 24f. Crouch -> rise -> tucked apex -> trailing fall -> land.
begin("Jump")
def jump_pose(f, body, torso, head, armL, armR, elbL, elbR, legL, legR, knL, knR, twin, blade=0):
    KB(f, dz=body[0], rot=body[1])
    K(Torso, f, rot=torso); K(Head, f, rot=head)
    K(ArmL, f, rot=armL); K(ArmR, f, rot=armR)
    K(ElbowL, f, rot=elbL); K(ElbowR, f, rot=elbR)
    K(LegL, f, rot=legL); K(LegR, f, rot=legR)
    K(KneeL, f, rot=knL); K(KneeR, f, rot=knR)
    K(TwinL, f, rot=twin); K(TwinR, f, rot=twin)
    K(Blade, f, rot=(blade, 0, 0))
jump_pose(0, (0, (0, 0, 0)), (0, 0, 0), (0, 0, 0),
          (3, -5, 0), (3, 5, 0), (-8, 0, 0), (-8, 0, 0),
          (0, -1.5, 0), (0, 1.5, 0), (3, 0, 0), (3, 0, 0), (0, 0, 0), blade=4)
jump_pose(4, (-0.105, (5, 0, 0)), (15, 0, 0), (-8, 0, 0),
          (26, -6, 0), (26, 6, 0), (-14, 0, 0), (-14, 0, 0),
          (-24, -2, 0), (-24, 2, 0), (58, 0, 0), (58, 0, 0), (-8, 0, 0), blade=-6)
jump_pose(8, (0.10, (-2, 0, 0)), (3, 0, 0), (-3, 0, 0),
          (-58, -16, 0), (-58, 16, 0), (-22, 0, 0), (-22, 0, 0),
          (-14, -2, 0), (-14, 2, 0), (16, 0, 0), (16, 0, 0), (16, 0, 0), blade=62)
jump_pose(13, (0.205, (-3, 0, 0)), (-1, 0, 0), (-3, 0, 0),
          (-38, -22, 0), (-38, 22, 0), (-30, 0, 0), (-30, 0, 0),
          (-46, -3, 0), (-46, 3, 0), (78, 0, 0), (78, 0, 0), (24, 0, 0), blade=55)
jump_pose(19, (0.085, (2, 0, 0)), (6, 0, 0), (2, 0, 0),
          (-18, -12, 0), (-18, 12, 0), (-12, 0, 0), (-12, 0, 0),
          (10, -2, 0), (10, 2, 0), (20, 0, 0), (20, 0, 0), (9, 0, 0), blade=22)
jump_pose(24, (-0.055, (3, 0, 0)), (8, 0, 0), (-3, 0, 0),
          (6, -6, 0), (6, 6, 0), (-8, 0, 0), (-8, 0, 0),
          (-16, -1.5, 0), (-16, 1.5, 0), (36, 0, 0), (36, 0, 0), (-4, 0, 0), blade=0)

# ---- Attack: 20f. Elbow wind-up overhead -> diagonal slash -> follow.
begin("Attack")
def atk_pose(f, body, torso, head, armL, armR, elbL, elbR, legL, legR, kn, twin):
    KB(f, dz=body[0], rot=body[1])
    K(Torso, f, rot=torso); K(Head, f, rot=head)
    K(ArmL, f, rot=armL); K(ArmR, f, rot=armR)
    K(ElbowL, f, rot=elbL); K(ElbowR, f, rot=elbR)
    K(LegL, f, rot=legL); K(LegR, f, rot=legR)
    K(KneeL, f, rot=kn); K(KneeR, f, rot=kn)
    K(TwinL, f, rot=twin); K(TwinR, f, rot=twin)
    K(Blade, f, rot=(0, 0, 0))
atk_pose(0, (0, (0, 0, 0)), (0, 0, 0), (0, 0, 0),
         (3, -5, 0), (3, 5, 0), (-8, 0, 0), (-8, 0, 0),
         (0, -1.5, 0), (0, 1.5, 0), (3, 0, 0), (0, 0, 0))
atk_pose(5, (-0.02, (0, 0, -3)), (2, 0, -14), (0, 0, 7),
         (-22, -10, 0), (38, 10, 0), (-18, 0, 0), (-52, 0, 0),
         (-8, -3, 0), (8, 3, 0), (10, 0, 0), (-6, 0, 0))
atk_pose(9, (0.008, (-2, 0, -2)), (-4, 0, -7), (-4, 0, 3),
         (-12, -20, 0), (-166, 4, 0), (-26, 0, 0), (-14, 0, 0),
         (-5, -3, 0), (5, 3, 0), (8, 0, 0), (-12, 0, 0))
atk_pose(12, (-0.048, (6, 0, 5)), (20, 0, 21), (3, 0, -7),
         (14, -10, 0), (-80, -44, 0), (-10, 0, 0), (-5, 0, 0),
         (-10, -3, 0), (6, 3, 0), (12, 0, 0), (27, 0, 0))
atk_pose(16, (-0.015, (2, 0, 2)), (9, 0, 11), (2, 0, -3),
         (7, -8, 0), (-16, -12, 0), (-8, 0, 0), (-12, 0, 0),
         (-3, -2, 0), (2, 2, 0), (6, 0, 0), (14, 0, 0))
atk_pose(20, (0, (0, 0, 0)), (0, 0, 0), (0, 0, 0),
         (3, -5, 0), (3, 5, 0), (-8, 0, 0), (-8, 0, 0),
         (0, -1.5, 0), (0, 1.5, 0), (3, 0, 0), (0, 0, 0))

reset_pose()
bpy.context.view_layer.update()
print("ANIM OK:", {k: len(v) for k, v in ACTIONS.items()})

# ---------------------------------------------------------------- GLB export
ANIM_LEN = {"Idle": 48, "Run": 24, "Jump": 24, "Attack": 20}
tmp_glbs = {}
for anim in ("Idle", "Run", "Jump", "Attack"):
    for o in ANIMATED:
        o.animation_data.action = ACTIONS[anim][o.name]
    scene.frame_start, scene.frame_end = 0, ANIM_LEN[anim]
    scene.frame_set(0)
    path = os.path.join(TMP, f"stella_{anim}.glb")
    bpy.ops.export_scene.gltf(filepath=path, export_format='GLB',
                              export_animations=True, export_animation_mode='ACTIONS',
                              export_apply=False)
    tmp_glbs[anim] = path
    print("EXPORTED", anim, os.path.getsize(path))

def read_glb(path):
    data = open(path, 'rb').read()
    assert data[:4] == b'glTF'
    jlen = struct.unpack('<I', data[12:16])[0]
    js = json.loads(data[20:20 + jlen])
    off = 20 + jlen
    blen = struct.unpack('<I', data[off:off + 4])[0]
    return js, data[off + 8:off + 8 + blen]

def merge_glbs(paths):
    base_j, base_bin = read_glb(paths[0])
    base_nodes = [n.get('name') for n in base_j['nodes']]
    out_bin = bytearray(base_bin)
    merged, order = {}, []
    def add_anims(js, acc_base):
        for a in js.get('animations', []):
            clip = a['name'].split('__')[0]
            if clip not in merged:
                merged[clip] = {'name': clip, 'channels': [], 'samplers': []}
                order.append(clip)
            tgt = merged[clip]
            smap = {}
            for i, s in enumerate(a['samplers']):
                smap[i] = len(tgt['samplers'])
                tgt['samplers'].append({'input': s['input'] + acc_base,
                                        'output': s['output'] + acc_base,
                                        'interpolation': s.get('interpolation', 'LINEAR')})
            for ch in a['channels']:
                tgt['channels'].append({'sampler': smap[ch['sampler']], 'target': ch['target']})
    add_anims(base_j, 0)
    for p in paths[1:]:
        j, b = read_glb(p)
        assert [n.get('name') for n in j['nodes']] == base_nodes, "node order differs"
        while len(out_bin) % 4:
            out_bin.append(0)
        off = len(out_bin)
        out_bin.extend(b)
        bv_base = len(base_j['bufferViews'])
        for bv in j['bufferViews']:
            nb = dict(bv)
            nb['byteOffset'] = nb.get('byteOffset', 0) + off
            base_j['bufferViews'].append(nb)
        acc_base = len(base_j['accessors'])
        for ac in j['accessors']:
            na = dict(ac)
            na['bufferView'] = na['bufferView'] + bv_base
            base_j['accessors'].append(na)
        add_anims(j, acc_base)
    base_j['animations'] = [merged[c] for c in order]
    base_j['buffers'][0]['byteLength'] = len(out_bin)
    jbytes = json.dumps(base_j).encode()
    while len(jbytes) % 4:
        jbytes += b' '
    total = 12 + 8 + len(jbytes) + 8 + len(out_bin)
    out = bytearray()
    out += b'glTF' + struct.pack('<II', 2, total)
    out += struct.pack('<I', len(jbytes)) + b'JSON' + jbytes
    out += struct.pack('<I', len(out_bin)) + b'BIN\x00' + out_bin
    return bytes(out)

final = merge_glbs([tmp_glbs[a] for a in ("Idle", "Run", "Jump", "Attack")])
with open(GLB_OUT, 'wb') as fh:
    fh.write(final)
print("MERGED GLB:", GLB_OUT, len(final))

fj, _ = read_glb(GLB_OUT)
for a in fj.get('animations', []):
    times = [fj['accessors'][s['input']].get('max', [0])[0] for s in a['samplers']]
    nodes = sorted({fj['nodes'][c['target']['node']].get('name') for c in a['channels']})
    print(f"CLIP {a['name']}: channels={len(a['channels'])} duration={max(times):.3f}s nodes={nodes}")

bpy.ops.wm.save_as_mainfile(filepath=BLEND_OUT)
print("BLEND SAVED:", BLEND_OUT, os.path.getsize(BLEND_OUT))

# ---------------------------------------------------------------- renders
world = bpy.data.worlds.new("W")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.88, 0.90, 0.93, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 1.0
scene.world = world

bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=3.2, depth=0.1, location=(0, 0, -0.05))
ground = bpy.context.active_object
ground.name = "StageGround"
gm = bpy.data.materials.new("Ground")
gm.use_nodes = True
gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.62, 0.68, 0.74, 1)
ground.data.materials.append(gm)

def add_light(name, typ, loc, energy, rot=(0, 0, 0)):
    ld = bpy.data.lights.new(name, typ)
    ld.energy = energy
    if typ == 'SUN':
        ld.angle = D(25)
    lo = bpy.data.objects.new(name, ld)
    bpy.context.collection.objects.link(lo)
    lo.location = loc
    lo.rotation_euler = rot
    return lo

add_light("Sun", 'SUN', (2.5, -2.0, 4.0), 3.2, (D(38), D(18), D(28)))
add_light("Fill", 'POINT', (-2.2, -1.6, 1.6), 60.0)
add_light("Rim", 'POINT', (0.5, 2.4, 2.0), 80.0)

cam_data = bpy.data.cameras.new("Cam")
cam = bpy.data.objects.new("Cam", cam_data)
bpy.context.collection.objects.link(cam)
scene.camera = cam
cam_data.clip_end = 100

def aim_camera(loc, target=(0, 0, 0.82)):
    cam.location = loc
    d = Vector(target) - Vector(loc)
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()

scene.render.engine = 'CYCLES'
scene.cycles.samples = 64
scene.cycles.device = 'CPU'
scene.render.resolution_x = 640
scene.render.resolution_y = 800
scene.render.film_transparent = False

def render_pose(anim, frame, cam_loc, out_name, target=(0, 0, 0.82)):
    for o in ANIMATED:
        o.animation_data.action = ACTIONS[anim][o.name]
    scene.frame_start, scene.frame_end = 0, ANIM_LEN[anim]
    scene.frame_set(frame)
    bpy.context.view_layer.update()
    aim_camera(cam_loc, target)
    scene.render.filepath = os.path.join(ASSETS, out_name)
    bpy.ops.render.render(write_still=True)
    print("RENDERED", out_name)

render_pose("Idle", 1, (0.0, -3.15, 1.02), "preview_v6.png")
render_pose("Idle", 1, (1.55, -2.30, 1.12), "preview_3q_v6.png")
render_pose("Idle", 1, (1.65, 2.45, 1.18), "preview_back_v6.png")
render_pose("Run", 6, (2.1, -1.55, 0.95), "anim_run_v6.png")
render_pose("Attack", 11, (1.5, -2.1, 1.05), "anim_attack_v6.png")
# face close-up: longer lens, target on the head
cam_data.lens = 72
render_pose("Idle", 1, (0.28, -0.78, 1.52), "preview_face_v6.png", target=(0, -0.02, 1.44))
cam_data.lens = 50
print("ALL DONE")
