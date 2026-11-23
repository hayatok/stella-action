# Stella v2 - production-quality rebuild. Part-based character, object
# animation (no armature). Same contract as v1: faces -Y in Blender (+Z in
# glTF), feet at z=0, height ~1.55m, clips Idle/Run/Jump/Attack with the
# same frame counts, pivot names Body/Torso/Head/Arm_L/Arm_R/Leg_L/Leg_R/
# Twintail_L/Twintail_R plus new Elbow_L/R and Knee_L/R sub-pivots.
# Build: blender -b --factory-startup -noaudio --python assets/scripts/make_stella_v2.py
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
    "hair":   mat("Hair",   (0.005, 0.35, 0.33), 0.48),
    "hair_d": mat("HairDk", (0.008, 0.19, 0.185), 0.55),
    "cream":  mat("Cream",  (0.97, 0.93, 0.84), 0.85),
    "teal":   mat("Teal",   (0.015, 0.33, 0.32), 0.78),
    "teal_d": mat("TealDk", (0.02, 0.19, 0.19), 0.82),
    "orange": mat("Orange", (0.88, 0.40, 0.04), 0.68),
    "dark":   mat("Dark",   (0.08, 0.09, 0.12), 0.88),
    "sock":   mat("Sock",   (0.09, 0.10, 0.15), 0.92),
    "glove":  mat("Glove",  (0.13, 0.13, 0.16), 0.85),
    "white":  mat("White",  (0.98, 0.98, 0.97), 0.55),
    "eye":    mat("Eye",    (0.015, 0.19, 0.20), 0.30),
    "eye_hi": mat("EyeHi",  (0.10, 0.72, 0.68), 0.35, emission=(0.05, 0.45, 0.42), estr=0.5),
    "metal":  mat("Metal",  (0.56, 0.59, 0.63), 0.35, metal=0.85),
    "mouth":  mat("Mouth",  (0.48, 0.16, 0.15), 0.65),
    "blush":  mat("Blush",  (1.00, 0.58, 0.52), 0.95),
    "blade":  mat("Blade",  (0.10, 0.55, 0.65), 0.28, emission=(0.20, 0.90, 1.00), estr=2.6),
    "bag":    mat("Bag",    (0.03, 0.17, 0.17), 0.85),
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

def _apply_bevel(o, bevel, segments=3):
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
        vertices=20, scale=None):
    bpy.ops.mesh.primitive_cone_add(vertices=vertices, radius1=r_bot,
                                    radius2=r_top, depth=depth, location=(0, 0, 0))
    o = bpy.context.active_object
    for p in o.data.polygons:
        p.use_smooth = True
    return _finish(o, name, parent, loc, material, rot, scale)

def sph(parent, name, loc, scale, material, rot=(0, 0, 0), seg=28, rings=20):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=seg, ring_count=rings,
                                         radius=1.0, location=(0, 0, 0))
    o = bpy.context.active_object
    o.scale = scale
    for p in o.data.polygons:
        p.use_smooth = True
    return _finish(o, name, parent, loc, material, rot)

def tube(parent, name, rings, material, radial=14):
    """Smooth tapered tube through rings [(center Vector, rx, ry), ...].
    Rings ordered along the path; start cap + end fan included."""
    verts, faces = [], []
    n = len(rings)
    for (c, rx, ry) in rings:
        for k in range(radial):
            a = 2 * math.pi * k / radial
            verts.append((c.x + rx * math.cos(a), c.y + ry * math.sin(a), c.z))
    for i in range(n - 1):
        for k in range(radial):
            k2 = (k + 1) % radial
            faces.append((i * radial + k, (i + 1) * radial + k,
                          (i + 1) * radial + k2, i * radial + k2))
    ci = len(verts)
    verts.append(tuple(rings[0][0]))
    for k in range(radial):
        faces.append((ci, (k + 1) % radial, k))
    ci = len(verts)
    verts.append(tuple(rings[-1][0]))
    base = (n - 1) * radial
    for k in range(radial):
        faces.append((ci, base + k, base + (k + 1) % radial))
    me = bpy.data.meshes.new(name + "Mesh")
    me.from_pydata(verts, [], faces)
    me.update()
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

# ---------------------------------------------------------------- hierarchy
# World layout (Blender z): hip 0.82, knee 0.46, waist 0.90, shoulder 1.14,
# neck 1.20, head centre ~1.37, head top ~1.54. Right = -X, left = +X.
Root = pivot(None, "Stella", (0, 0, 0))
Body = pivot(Root, "Body", (0, 0, 0.82))

# ---- pelvis / shorts (children of Body)
pelvis = rbox(Body, "Shorts", (0, 0, 0.03), (0.315, 0.225, 0.20), M["dark"], bevel=0.055)
taper_z(pelvis, -0.10, 0.10, 0.94, 1.02)
for s, tag in ((+1, "L"), (-1, "R")):
    cyl(Body, f"ShortsLeg{tag}", (0.088 * s, 0, -0.085), 0.086, 0.080, 0.10,
        M["dark"], rot=(0, D(-4 * s), 0))
    cyl(Body, f"ShortsCuff{tag}", (0.089 * s, 0, -0.125), 0.084, 0.082, 0.032,
        M["glove"], rot=(0, D(-4 * s), 0))
rbox(Body, "Belt", (0, 0, 0.125), (0.33, 0.235, 0.055), M["glove"], bevel=0.014)
rbox(Body, "Buckle", (0, -0.118, 0.125), (0.082, 0.014, 0.042), M["metal"], bevel=0.004)
rbox(Body, "BuckleIn", (0, -0.126, 0.125), (0.05, 0.006, 0.024), M["dark"], bevel=0.002)
rbox(Body, "BeltStrapL", (0.075, -0.118, 0.045), (0.034, 0.012, 0.13), M["orange"],
     rot=(D(4), 0, D(-5)), bevel=0.004)
rbox(Body, "BeltStrapR", (-0.082, -0.118, 0.055), (0.034, 0.012, 0.105), M["orange"],
     rot=(D(4), 0, D(5)), bevel=0.004)
# sheath at her LEFT hip (+X), grip up
rbox(Body, "Sheath", (0.195, 0.015, -0.085), (0.052, 0.078, 0.30), M["teal_d"],
     rot=(D(9), 0, D(-7)), bevel=0.012)
rbox(Body, "SheathCap", (0.183, 0.013, 0.062), (0.058, 0.084, 0.032), M["metal"], bevel=0.006)
sph(Body, "SheathGem", (0.178, -0.032, 0.062), (0.012, 0.008, 0.012), M["blade"])

# ---- legs: Leg pivot (hip) -> thigh; Knee pivot -> shin + boot
def build_leg(s, tag):
    leg = pivot(Body, f"Leg_{tag}", (0.095 * s, 0, -0.02))
    cyl(leg, f"Thigh_{tag}", (0, 0, -0.17), 0.058, 0.074, 0.34, M["skin"])
    sph(leg, f"HipBall_{tag}", (0, 0, -0.01), (0.075, 0.072, 0.07), M["skin"])
    if tag == "R":  # thigh strap on her right leg (art)
        cyl(leg, "ThighStrap", (0, 0, -0.125), 0.0715, 0.0735, 0.034, M["glove"])
        rbox(leg, "ThighBuckle", (0, -0.070, -0.125), (0.042, 0.012, 0.026), M["metal"], bevel=0.003)
    knee = pivot(leg, f"Knee_{tag}", (0, 0, -0.34))
    sph(knee, f"KneeBall_{tag}", (0, 0, 0.005), (0.056, 0.054, 0.052), M["skin"])
    cyl(knee, f"SockBand_{tag}", (0, 0, -0.035), 0.0585, 0.0575, 0.04, M["teal"])
    cyl(knee, f"Shin_{tag}", (0, 0, -0.155), 0.047, 0.056, 0.27, M["sock"])
    if tag == "L":  # small white star on her left sock (art)
        star(knee, "SockStar", (0, -0.0505, -0.115), 0.020, 0.009, 0.005, M["white"])
    # chunky boot
    rbox(knee, f"BootCuff_{tag}", (0, 0, -0.265), (0.148, 0.162, 0.085), M["teal_d"], bevel=0.02)
    rbox(knee, f"BootIn_{tag}", (0, -0.01, -0.245), (0.115, 0.125, 0.05), M["teal"], bevel=0.015)
    boot = rbox(knee, f"Boot_{tag}", (0, -0.012, -0.355), (0.138, 0.205, 0.185), M["dark"], bevel=0.032)
    taper_z(boot, -0.09, 0.09, 0.96, 1.05)
    sph(knee, f"BootToe_{tag}", (0, -0.092, -0.400), (0.066, 0.072, 0.050), M["dark"])
    rbox(knee, f"Midsole_{tag}", (0, -0.022, -0.428), (0.148, 0.238, 0.02), M["cream"], bevel=0.006)
    rbox(knee, f"Sole_{tag}", (0, -0.02, -0.45), (0.146, 0.236, 0.032), M["glove"], bevel=0.008)
    rbox(knee, f"SoleAccent_{tag}", (0, -0.128, -0.448), (0.102, 0.02, 0.042), M["orange"], bevel=0.004)
    for i, zz in enumerate((-0.315, -0.385)):
        rbox(knee, f"BootStrap{tag}{i}", (0, -0.112, zz), (0.142, 0.016, 0.042), M["glove"], bevel=0.004)
        rbox(knee, f"BootBuckle{tag}{i}", (0.062 * s, -0.118, zz), (0.034, 0.012, 0.028), M["orange"], bevel=0.003)
    rbox(knee, f"BootTab_{tag}", (0, 0.088, -0.245), (0.036, 0.02, 0.058), M["orange"], bevel=0.005)
    return leg, knee

LegL, KneeL = build_leg(+1, "L")
LegR, KneeR = build_leg(-1, "R")

# ---- torso (pivot at waist, world z 0.90)
Torso = pivot(Body, "Torso", (0, 0, 0.08))
rbox(Torso, "Midriff", (0, 0, 0.005), (0.238, 0.168, 0.115), M["skin"], bevel=0.038)
sph(Torso, "Navel", (0, -0.0865, -0.005), (0.008, 0.004, 0.011), M["skin_sh"])
jacket = rbox(Torso, "Jacket", (0, 0, 0.165), (0.375, 0.25, 0.30), M["cream"], bevel=0.058)
taper_z(jacket, -0.15, 0.15, 1.05, 0.94)
rbox(Torso, "JacketHem", (0, 0, 0.028), (0.382, 0.256, 0.034), M["orange"], bevel=0.008)
rbox(Torso, "ChestPanel", (0, -0.112, 0.175), (0.305, 0.034, 0.225), M["teal"], bevel=0.012)
rbox(Torso, "Zipper", (0, -0.130, 0.168), (0.02, 0.008, 0.215), M["dark"], bevel=0.002)
star(Torso, "ChestStar", (0.088, -0.1315, 0.19), 0.037, 0.0165, 0.008, M["white"])
# popped collar: two angled flaps, teal outside / orange lining
for s, tag in ((+1, "L"), (-1, "R")):
    rbox(Torso, f"Collar{tag}", (0.096 * s, -0.046, 0.318), (0.115, 0.02, 0.14),
         M["teal_d"], rot=(D(-33), D(-14 * s), D(8 * s)), bevel=0.008)
    rbox(Torso, f"CollarIn{tag}", (0.089 * s, -0.057, 0.311), (0.095, 0.012, 0.12),
         M["orange"], rot=(D(-33), D(-14 * s), D(8 * s)), bevel=0.006)
rbox(Torso, "CollarBack", (0, 0.055, 0.315), (0.20, 0.10, 0.11), M["teal_d"],
     rot=(D(14), 0, 0), bevel=0.02)
# diagonal shoulder strap + buckle
rbox(Torso, "Strap", (0.012, -0.133, 0.155), (0.054, 0.012, 0.40), M["dark"],
     rot=(0, D(38), 0), bevel=0.004)
rbox(Torso, "StrapBuckle", (-0.078, -0.139, 0.248), (0.052, 0.014, 0.052), M["orange"], bevel=0.004)
# satchel on her right side (-X)
rbox(Torso, "Satchel", (-0.272, 0.028, -0.075), (0.10, 0.215, 0.235), M["bag"], bevel=0.024)
rbox(Torso, "SatchelFlap", (-0.272, -0.062, -0.018), (0.104, 0.028, 0.135), M["cream"], bevel=0.010)
star(Torso, "SatchelStar", (-0.272, -0.0785, -0.018), 0.031, 0.0135, 0.006, M["orange"])
rbox(Torso, "SatchelClasp", (-0.272, -0.072, -0.088), (0.046, 0.016, 0.036), M["metal"], bevel=0.004)
rbox(Torso, "SatchelStrapBit", (-0.235, -0.06, 0.055), (0.045, 0.012, 0.13), M["dark"],
     rot=(D(18), 0, D(14)), bevel=0.004)

# ---- arms: Arm pivot (shoulder) -> puffy sleeve; Elbow pivot -> forearm+hand
def build_arm(s, tag):
    arm = pivot(Torso, f"Arm_{tag}", (0.218 * s, 0, 0.245))
    sph(arm, f"Shoulder_{tag}", (0.006 * s, 0, 0.005), (0.079, 0.074, 0.081), M["cream"])
    cyl(arm, f"Sleeve_{tag}", (0.008 * s, 0, -0.088), 0.054, 0.066, 0.17, M["cream"],
        rot=(0, 0, D(3 * s)))
    cyl(arm, f"SleeveCuff_{tag}", (0.010 * s, 0, -0.168), 0.063, 0.060, 0.046, M["teal"])
    if tag == "R":  # orange star patch on her right sleeve (art)
        star(arm, "SleevePatch", (0.008 * s, -0.0665, -0.055), 0.029, 0.0125, 0.05, M["orange"])
    elbow = pivot(arm, f"Elbow_{tag}", (0.010 * s, 0, -0.19))
    sph(elbow, f"ElbowBall_{tag}", (0, 0, 0.004), (0.047, 0.045, 0.045), M["skin"])
    cyl(elbow, f"Forearm_{tag}", (0, 0, -0.072), 0.040, 0.047, 0.145, M["skin"])
    cyl(elbow, f"Wrist_{tag}", (0, 0, -0.152), 0.048, 0.046, 0.036, M["orange"])
    sph(elbow, f"Hand_{tag}", (0, -0.004, -0.208), (0.053, 0.049, 0.070), M["glove"])
    sph(elbow, f"Thumb_{tag}", (0.014 * s, -0.040, -0.188), (0.018, 0.019, 0.031), M["glove"])
    return arm, elbow

ArmL, ElbowL = build_arm(+1, "L")
ArmR, ElbowR = build_arm(-1, "R")

# ---- energy blade gripped in the right hand (child of Elbow_R).
# Arm hangs down in Idle/Run/Jump, so the blade rests along her right hip.
Blade = pivot(ElbowR, "Blade", (0, -0.004, -0.215))
cyl(Blade, "BladeGrip", (0, 0, -0.008), 0.0165, 0.0165, 0.115, M["dark"], vertices=12)
cyl(Blade, "BladePommel", (0, 0, 0.056), 0.020, 0.020, 0.02, M["blade"], vertices=12)
rbox(Blade, "BladeGuard", (0, 0, -0.072), (0.078, 0.032, 0.018), M["metal"], bevel=0.004)
blade_mesh = rbox(Blade, "BladeEdge", (0, 0, -0.232), (0.056, 0.013, 0.30), M["blade"], bevel=0.004)
taper_z(blade_mesh, -0.15, 0.15, 0.45, 1.0, axes=(0,))
cyl(Blade, "BladeTip", (0, 0, -0.415), 0.0012, 0.0275, 0.07, M["blade"],
    rot=(D(180), 0, 0), vertices=12, scale=(1.0, 0.24, 1.0))

# ---- head (pivot at neck, world z 1.20)
Head = pivot(Torso, "Head", (0, 0, 0.30))
cyl(Head, "Neck", (0, 0, -0.005), 0.046, 0.050, 0.09, M["skin"])
sph(Head, "Face", (0, -0.005, 0.165), (0.168, 0.152, 0.172), M["skin"], seg=36, rings=26)
# hair mass: cap + back panel (face front stays open)
sph(Head, "HairCap", (0, 0.020, 0.190), (0.179, 0.163, 0.183), M["hair"], seg=36, rings=26)
sph(Head, "HairBack", (0, 0.062, 0.115), (0.170, 0.140, 0.195), M["hair"], seg=32, rings=22)
# fringe scoop hugging the forehead
sph(Head, "Fringe", (0, -0.058, 0.252), (0.170, 0.104, 0.088), M["hair"], seg=32, rings=20)
# bang spikes along the hairline (flattened cones, tips just above the eyes)
bang_specs = [(-0.104, 0.085, -8), (-0.056, 0.115, -3), (0.0, 0.128, 0),
              (0.056, 0.115, 3), (0.104, 0.085, 8)]
for i, (bx, blen, tilt) in enumerate(bang_specs):
    cyl(Head, f"Bang{i}", (bx, -0.148, 0.252 - blen / 2), 0.0035, 0.031, blen,
        M["hair"], rot=(D(180 + 9), 0, D(tilt)), vertices=12, scale=(1.0, 0.48, 1.0))
# side locks framing the face (smooth tapered tubes)
for s, tag in ((+1, "L"), (-1, "R")):
    rings = []
    for (lx, ly, lz, r) in ((0.148, -0.055, 0.265, 0.037), (0.156, -0.072, 0.185, 0.034),
                            (0.158, -0.078, 0.105, 0.029), (0.154, -0.080, 0.035, 0.021),
                            (0.148, -0.078, -0.015, 0.008)):
        rings.append((Vector((lx * s, ly, lz)), r, r * 0.82))
    tube(Head, f"SideLock{tag}", rings, M["hair"], radial=12)
    sph(Head, f"Ear{tag}", (0.164 * s, 0.002, 0.135), (0.023, 0.019, 0.033), M["skin"])
# ahoge: small curved tube on top
rings = [(Vector((0.008, 0.010, 0.352)), 0.0115, 0.0115),
         (Vector((0.016, 0.006, 0.385)), 0.010, 0.010),
         (Vector((0.034, 0.000, 0.405)), 0.008, 0.008),
         (Vector((0.056, -0.004, 0.402)), 0.005, 0.005),
         (Vector((0.070, -0.006, 0.388)), 0.0015, 0.0015)]
tube(Head, "Ahoge", rings, M["hair"], radial=10)
# face: big oval eyes + bright lower iris + highlight, brows, mouth, blush
for s, tag in ((+1, "L"), (-1, "R")):
    sph(Head, f"Eye{tag}", (0.060 * s, -0.1435, 0.152), (0.0275, 0.011, 0.047), M["eye"], seg=20, rings=14)
    sph(Head, f"EyeIris{tag}", (0.060 * s, -0.1505, 0.128), (0.019, 0.007, 0.026), M["eye_hi"], seg=18, rings=12)
    sph(Head, f"EyeHi{tag}", (0.058 * s, -0.1535, 0.172), (0.0095, 0.0045, 0.0135), M["white"], seg=12, rings=10)
    rbox(Head, f"Brow{tag}", (0.062 * s, -0.140, 0.228), (0.046, 0.007, 0.011),
         M["hair_d"], rot=(D(-14), 0, D(-7 * s)), bevel=0.003)
    sph(Head, f"Blush{tag}", (0.099 * s, -0.117, 0.092), (0.030, 0.010, 0.017),
        M["blush"], rot=(0, D(-24 * s), 0), seg=16, rings=12)
sph(Head, "Mouth", (0, -0.1415, 0.072), (0.019, 0.0075, 0.0125), M["mouth"], seg=16, rings=12)
# star hairpin on her right side (-X), sitting on the hair surface
star(Head, "Hairpin", (-0.104, -0.148, 0.196), 0.043, 0.0195, 0.010, M["orange"],
     rot=(D(-16), D(14), D(10)))

# ---- twintails: smooth tapered curved tubes from tie pivots on the head
def build_tail(s, tag):
    tail = pivot(Head, f"Twintail_{tag}", (0.148 * s, 0.045, 0.238))
    tie = rbox(tail, f"Tie_{tag}", (0.004 * s, 0.002, 0.012), (0.082, 0.078, 0.115),
               M["hair_d"], rot=(D(6), 0, D(-8 * s)), bevel=0.014)
    rbox(tail, f"RibbonA_{tag}", (0.052 * s, -0.012, 0.052), (0.105, 0.016, 0.042),
         M["orange"], rot=(D(12), 0, D(-30 * s)), bevel=0.005)
    rbox(tail, f"RibbonB_{tag}", (0.030 * s, 0.030, 0.058), (0.085, 0.015, 0.036),
         M["orange"], rot=(D(-16), D(10 * s), D(-52 * s)), bevel=0.005)
    path = [  # (out, back, down, r) from the tie to the pointed tip
        (0.008, 0.004, 0.020, 0.077), (0.036, 0.012, -0.075, 0.075),
        (0.062, 0.024, -0.185, 0.070), (0.078, 0.034, -0.310, 0.064),
        (0.082, 0.040, -0.440, 0.056), (0.074, 0.043, -0.570, 0.047),
        (0.058, 0.043, -0.695, 0.038), (0.040, 0.040, -0.810, 0.029),
        (0.022, 0.036, -0.905, 0.020), (0.009, 0.032, -0.975, 0.011),
        (0.002, 0.030, -1.020, 0.002),
    ]
    rings = [(Vector((px * s, py, pz)), r, r * 0.84) for (px, py, pz, r) in path]
    tube(tail, f"TailMesh_{tag}", rings, M["hair"], radial=16)
    return tail

TwinL = build_tail(+1, "L")
TwinR = build_tail(-1, "R")

bpy.context.view_layer.update()
print("BUILD OK, objects:", len(bpy.data.objects))

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
scene.render.resolution_x = 560
scene.render.resolution_y = 700
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

render_pose("Idle", 1, (1.55, -2.30, 1.12), "preview_v2.png")
render_pose("Idle", 1, (0.0, -3.15, 1.02), "preview_front_v2.png")
render_pose("Idle", 1, (1.65, 2.45, 1.18), "preview_back_v2.png")
render_pose("Run", 6, (2.1, -1.55, 0.95), "anim_run_v2.png")
render_pose("Jump", 13, (1.95, -2.35, 1.32), "anim_jump_v2.png", target=(0, 0, 1.02))
render_pose("Attack", 11, (1.5, -2.1, 1.05), "anim_attack_v2.png")
print("ALL DONE")
