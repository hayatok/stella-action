# Stella - part-based low-poly character with object animation.
# Build: blender -b --factory-startup -noaudio --python assets/scripts/make_stella.py
# Character faces -Y in Blender. No armature / no skinning: every moving part
# is a mesh (or group of meshes) parented to a pivot Empty whose origin is
# the joint. Animations are per-object Actions named "<Anim>__<Object>";
# the 4 GLB exports are merged into one GLB with clips Idle/Run/Jump/Attack.
import bpy, math, os, json, struct
from mathutils import Vector

try:
    ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
except NameError:
    ROOT = os.path.expanduser("~/workspace/stella-action")
GLB_OUT = os.path.join(ROOT, "public", "models", "stella.glb")
BLEND_OUT = os.path.join(ROOT, "assets", "source", "stella.blend")
ASSETS = os.path.join(ROOT, "assets")
TMP = "/tmp/stella_parts"
os.makedirs(TMP, exist_ok=True)

D = math.radians

# ---------------------------------------------------------------- scene reset
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.fps = 24

# ---------------------------------------------------------------- materials
def mat(name, color, rough=0.8, emission=None, estr=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    if emission is not None:
        bsdf.inputs["Emission Color"].default_value = (*emission, 1.0)
        bsdf.inputs["Emission Strength"].default_value = estr
    return m

M = {
    "skin":   mat("Skin",   (1.00, 0.83, 0.66), 0.65),
    "hair":   mat("Hair",   (0.05, 0.52, 0.50), 0.55),
    "hair_d": mat("HairDk", (0.05, 0.33, 0.32), 0.6),
    "cream":  mat("Cream",  (0.96, 0.92, 0.84), 0.8),
    "teal":   mat("Teal",   (0.04, 0.43, 0.41), 0.75),
    "teal_d": mat("TealDk", (0.05, 0.30, 0.30), 0.8),
    "orange": mat("Orange", (0.95, 0.53, 0.13), 0.7),
    "dark":   mat("Dark",   (0.13, 0.14, 0.17), 0.85),
    "sock":   mat("Sock",   (0.15, 0.16, 0.22), 0.9),
    "glove":  mat("Glove",  (0.16, 0.16, 0.19), 0.85),
    "white":  mat("White",  (0.98, 0.98, 0.97), 0.6),
    "eye":    mat("Eye",    (0.04, 0.23, 0.24), 0.35),
    "metal":  mat("Metal",  (0.55, 0.58, 0.62), 0.45),
    "mouth":  mat("Mouth",  (0.55, 0.22, 0.22), 0.7),
    "blade":  mat("Blade",  (0.10, 0.55, 0.65), 0.3, emission=(0.20, 0.90, 1.00), estr=3.0),
    "bag":    mat("Bag",    (0.09, 0.28, 0.28), 0.85),
}

# ---------------------------------------------------------------- builders
def _finish(o, name, parent, loc, material=None, rot=(0, 0, 0)):
    o.name = name
    if material is not None:
        o.data.materials.append(material)
    if parent is not None:
        o.parent = parent
    o.location = loc
    o.rotation_euler = rot
    return o

def box(parent, name, loc, size, material, rot=(0, 0, 0), bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(location=(0, 0, 0))
    o = bpy.context.active_object
    o.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel > 0:
        mod = o.modifiers.new("bev", 'BEVEL')
        mod.width = bevel
        mod.segments = 2
    return _finish(o, name, parent, loc, material, rot)

def cyl(parent, name, loc, radius, depth, material, rot=(0, 0, 0), vertices=14):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=(0, 0, 0))
    o = bpy.context.active_object
    for p in o.data.polygons:
        p.use_smooth = True
    return _finish(o, name, parent, loc, material, rot)

def sph(parent, name, loc, scale, material, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=20, ring_count=14, radius=1.0, location=(0, 0, 0))
    o = bpy.context.active_object
    o.scale = scale
    for p in o.data.polygons:
        p.use_smooth = True
    return _finish(o, name, parent, loc, material, rot)

def cone(parent, name, loc, r1, r2, depth, material, rot=(0, 0, 0), vertices=12):
    bpy.ops.mesh.primitive_cone_add(vertices=vertices, radius1=r1, radius2=r2, depth=depth, location=(0, 0, 0))
    o = bpy.context.active_object
    for p in o.data.polygons:
        p.use_smooth = True
    return _finish(o, name, parent, loc, material, rot)

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
    return _finish(o, name, parent, loc, None, rot)

# ---------------------------------------------------------------- hierarchy
Root  = pivot(None, "Stella", (0, 0, 0))
Body  = pivot(Root, "Body", (0, 0, 0.87))          # hips; bob animated here

# ---- pelvis / shorts (child of Body)
box(Body, "Shorts", (0, 0, 0.02), (0.30, 0.215, 0.17), M["dark"], bevel=0.03)
box(Body, "Belt", (0, 0, 0.115), (0.315, 0.225, 0.05), M["glove"], bevel=0.01)
box(Body, "Buckle", (0, -0.112, 0.115), (0.075, 0.012, 0.038), M["metal"])
box(Body, "BeltStrapL", (0.07, -0.115, 0.02), (0.035, 0.012, 0.14), M["orange"])
box(Body, "BeltStrapR", (-0.075, -0.115, 0.03), (0.035, 0.012, 0.11), M["orange"])
# sheath at her LEFT hip (+X), blade grip up
box(Body, "Sheath", (0.185, 0.01, -0.10), (0.05, 0.075, 0.30), M["teal_d"],
    rot=(D(8), 0, D(-6)), bevel=0.01)
box(Body, "SheathCap", (0.175, 0.01, 0.045), (0.055, 0.08, 0.03), M["metal"])

# ---- legs (pivot at hip). Character right = -X, left = +X (faces -Y)
def build_leg(side_sign, tag):
    leg = pivot(Body, f"Leg_{tag}", (0.095 * side_sign, 0, -0.01))
    cyl(leg, f"Thigh_{tag}", (0, 0, -0.10), 0.063, 0.20, M["skin"])
    cyl(leg, f"SockBand_{tag}", (0, 0, -0.215), 0.058, 0.035, M["teal"])
    cyl(leg, f"Sock_{tag}", (0, 0, -0.375), 0.055, 0.30, M["sock"])
    box(leg, f"BootCuff_{tag}", (0, 0, -0.575), (0.14, 0.155, 0.07), M["teal_d"], bevel=0.015)
    box(leg, f"Boot_{tag}", (0, -0.012, -0.715), (0.135, 0.205, 0.22), M["dark"], bevel=0.025)
    box(leg, f"BootToe_{tag}", (0, -0.082, -0.795), (0.13, 0.075, 0.115), M["dark"], bevel=0.02)
    box(leg, f"Sole_{tag}", (0, -0.02, -0.845), (0.14, 0.225, 0.032), M["glove"])
    box(leg, f"SoleAccent_{tag}", (0, -0.115, -0.838), (0.10, 0.02, 0.045), M["orange"])
    box(leg, f"BootStrap_{tag}", (0, -0.105, -0.66), (0.14, 0.015, 0.045), M["glove"])
    box(leg, f"BootBuckle_{tag}", (0.055 * side_sign, -0.112, -0.66), (0.035, 0.012, 0.03), M["orange"])
    box(leg, f"BootTab_{tag}", (0, 0.085, -0.545), (0.035, 0.02, 0.06), M["orange"])
    if tag == "R":  # thigh strap on her right leg (art)
        cyl(leg, "ThighStrap", (0, 0, -0.145), 0.066, 0.03, M["glove"])
        box(leg, "ThighBuckle", (0, -0.062, -0.145), (0.04, 0.012, 0.025), M["metal"])
    return leg

LegL = build_leg(+1, "L")
LegR = build_leg(-1, "R")

# ---- torso (pivot at waist)
Torso = pivot(Body, "Torso", (0, 0, 0.10))
box(Torso, "Midriff", (0, 0, 0.01), (0.235, 0.16, 0.10), M["skin"], bevel=0.02)
box(Torso, "Jacket", (0, 0, 0.165), (0.365, 0.245, 0.27), M["cream"], bevel=0.045)
box(Torso, "JacketHem", (0, 0, 0.038), (0.37, 0.25, 0.032), M["orange"], bevel=0.008)
box(Torso, "ChestPanel", (0, -0.108, 0.175), (0.30, 0.035, 0.215), M["teal"], bevel=0.01)
box(Torso, "Zipper", (0, -0.128, 0.165), (0.022, 0.008, 0.21), M["dark"])
star(Torso, "ChestStar", (0.085, -0.13, 0.225), 0.036, 0.016, 0.008, M["white"])
box(Torso, "Collar", (0, 0.015, 0.315), (0.25, 0.19, 0.075), M["teal_d"], bevel=0.015)
box(Torso, "CollarIn", (0, -0.02, 0.30), (0.16, 0.14, 0.06), M["orange"], bevel=0.01)
# shoulder-strap across chest (diagonal in the X-Z plane => rotate about Y)
box(Torso, "Strap", (0.01, -0.132, 0.16), (0.052, 0.012, 0.36), M["dark"], rot=(0, D(38), 0))
box(Torso, "StrapBuckle", (-0.075, -0.138, 0.245), (0.05, 0.014, 0.05), M["orange"])

# ---- satchel on her right side (-X), hanging from the strap
box(Torso, "Satchel", (-0.265, 0.03, -0.06), (0.095, 0.21, 0.23), M["bag"], bevel=0.02)
box(Torso, "SatchelFlap", (-0.265, -0.075, -0.005), (0.10, 0.025, 0.13), M["cream"], bevel=0.008)
star(Torso, "SatchelStar", (-0.265, -0.09, -0.005), 0.032, 0.014, 0.006, M["orange"])
box(Torso, "SatchelClasp", (-0.265, -0.085, -0.075), (0.045, 0.014, 0.035), M["metal"])

# ---- arms (pivot at shoulder). Right = -X (holds the blade), Left = +X
def build_arm(side_sign, tag):
    arm = pivot(Torso, f"Arm_{tag}", (0.215 * side_sign, 0, 0.235))
    cyl(arm, f"Sleeve_{tag}", (0, 0, -0.065), 0.070, 0.15, M["cream"])
    cyl(arm, f"SleeveCuff_{tag}", (0, 0, -0.15), 0.072, 0.04, M["teal"])
    cyl(arm, f"Forearm_{tag}", (0, 0, -0.235), 0.047, 0.13, M["skin"])
    cyl(arm, f"Wrist_{tag}", (0, 0, -0.30), 0.052, 0.032, M["orange"])
    sph(arm, f"Hand_{tag}", (0, 0, -0.365), (0.056, 0.052, 0.072), M["glove"])
    sph(arm, f"Thumb_{tag}", (0.035 * side_sign, -0.02, -0.35), (0.020, 0.020, 0.032), M["glove"])
    if tag == "R":  # orange star patch on her right sleeve (art)
        star(arm, "SleevePatch", (0, -0.068, -0.03), 0.030, 0.013, 0.05, M["orange"])
    return arm

ArmL = build_arm(+1, "L")
ArmR = build_arm(-1, "R")

# ---- energy blade, gripped in the right hand for every action.
# Arm hangs down in Idle/Run/Jump, so the blade rests along her right hip
# (reads as carried/sheathed); in Attack the arm swings it.
Blade = pivot(ArmR, "Blade", (0, 0, -0.38))
cyl(Blade, "BladeGrip", (0, 0, -0.02), 0.017, 0.12, M["dark"], vertices=10)
box(Blade, "BladePommel", (0, 0, 0.045), (0.035, 0.035, 0.02), M["blade"])
box(Blade, "BladeGuard", (0, 0, -0.085), (0.075, 0.03, 0.018), M["metal"])
box(Blade, "BladeEdge", (0, 0, -0.235), (0.052, 0.013, 0.28), M["blade"], bevel=0.004)
cone(Blade, "BladeTip", (0, 0, -0.415), 0.026, 0.001, 0.08, M["blade"], rot=(D(180), 0, 0))

# ---- head (pivot at neck)
Head = pivot(Torso, "Head", (0, 0, 0.355))
cyl(Head, "Neck", (0, 0, -0.015), 0.045, 0.07, M["skin"])
sph(Head, "Face", (0, 0, 0.105), (0.148, 0.138, 0.158), M["skin"])
sph(Head, "HairCap", (0, 0.024, 0.132), (0.158, 0.148, 0.168), M["hair"])
sph(Head, "Fringe", (0, -0.082, 0.188), (0.150, 0.062, 0.075), M["hair"])
for sx, tag in ((+1, "L"), (-1, "R")):
    cone(Head, f"FringeSpike{tag}", (0.062 * sx, -0.136, 0.158), 0.034, 0.004, 0.085,
         M["hair"], rot=(D(168), 0, D(8 * sx)))
    sph(Head, f"SideLock{tag}", (0.132 * sx, -0.045, 0.015), (0.030, 0.034, 0.105), M["hair"])
    sph(Head, f"Ear{tag}", (0.146 * sx, 0, 0.075), (0.026, 0.020, 0.034), M["skin"])
cone(Head, "FringeSpikeC", (0, -0.144, 0.168), 0.036, 0.004, 0.09, M["hair"], rot=(D(170), 0, 0))
cone(Head, "Ahoge", (0.01, 0.01, 0.315), 0.012, 0.004, 0.09, M["hair"], rot=(D(35), 0, D(-15)))
# face: big teal eyes + highlights + small mouth (front = -Y)
for sx, tag in ((+1, "L"), (-1, "R")):
    sph(Head, f"Eye{tag}", (0.056 * sx, -0.140, 0.115), (0.024, 0.012, 0.038), M["eye"])
    sph(Head, f"EyeHi{tag}", (0.056 * sx, -0.149, 0.134), (0.009, 0.005, 0.012), M["white"])
sph(Head, "Mouth", (0, -0.136, 0.046), (0.016, 0.007, 0.011), M["mouth"])
# star hairpin on her right side (-X), like the art
star(Head, "Hairpin", (-0.10, -0.152, 0.18), 0.042, 0.019, 0.010, M["orange"], rot=(D(-18), 0, D(12)))

# ---- twintails (pivot at the tie, on the head)
def build_tail(side_sign, tag):
    tail = pivot(Head, f"Twintail_{tag}", (0.128 * side_sign, 0.035, 0.205))
    box(tail, f"Tie_{tag}", (0, 0, 0.01), (0.075, 0.075, 0.10), M["hair_d"], bevel=0.012)
    box(tail, f"Ribbon_{tag}", (0.045 * side_sign, -0.01, 0.045), (0.10, 0.018, 0.045),
        M["orange"], rot=(D(10), 0, D(-32 * side_sign)))
    n = 6
    for i in range(n):
        r = 0.064 - 0.0075 * i
        loc = (0.030 * side_sign * i, 0.020 * i, -0.055 - 0.115 * i)
        sph(tail, f"Tail_{tag}_{i}", loc, (r, r * 0.92, 0.078), M["hair"])
    cone(tail, f"TailTip_{tag}", (0.030 * side_sign * n, 0.020 * n, -0.055 - 0.115 * n - 0.03),
         0.026, 0.002, 0.13, M["hair"], rot=(D(180), 0, 0))
    return tail

TwinL = build_tail(+1, "L")
TwinR = build_tail(-1, "R")

bpy.context.view_layer.update()
print("BUILD OK, objects:", len(bpy.data.objects))

# ---------------------------------------------------------------- animation
ANIMATED = [Body, Torso, Head, ArmL, ArmR, LegL, LegR, TwinL, TwinR]
BASE_LOC = {o.name: tuple(o.location) for o in ANIMATED}
ACTIONS = {}  # anim name -> {obj name: action}

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

def KB(frame, dz=0.0, rot=(0, 0, 0)):
    K(Body, frame, rot=rot, loc=(0, 0, BASE_LOC["Body"][2] + dz))

# NOTE on signs (character faces -Y, up is +Z):
#  rotation X positive = top tips forward (-Y). A limb pointing down (-Z)
#  swings FORWARD with negative rotation X, backward with positive.
#  Arm at +X (left) angles outward with negative rotation Z; arm at -X
#  (right) angles outward with positive rotation Z.

# ---- Idle: 48f loop @24fps (keys at 0..48, frame 48 == frame 0)
begin("Idle")
for f, ph in ((0, 0.0), (12, 1.0), (24, 0.0), (36, 1.0), (48, 0.0)):
    KB(f, dz=0.010 * ph, rot=(1.2 * ph, 0, 0))
    K(Torso, f, rot=(1.6 * ph, 0, 1.0 * math.sin(ph * math.pi)))
    K(Head, f, rot=(0.8 * ph, 0, 2.0 if f in (12, 36) else -1.0))
for f, s in ((0, 0), (12, 1), (24, 0), (36, -1), (48, 0)):
    K(ArmL, f, rot=(3.0 * s, 0, -6))
    K(ArmR, f, rot=(-3.0 * s, 0, 6))
    K(TwinL, f, rot=(2.5 * s, 0, -3 + 1.5 * s))
    K(TwinR, f, rot=(2.5 * s, 0, 3 + 1.5 * s))
    K(LegL, f, rot=(0, 0, 1.5))
    K(LegR, f, rot=(0, 0, -1.5))

# ---- Run: 24f loop, keys every 3 frames from a sine phase
begin("Run")
for i in range(9):
    f = i * 3
    ph = 2 * math.pi * i / 8.0
    s, c = math.sin(ph), math.cos(ph)
    KB(f, dz=0.028 * abs(c) - 0.005, rot=(7, 0, 2.5 * s))
    K(Torso, f, rot=(9, 0, 4.0 * s))
    K(Head, f, rot=(-4, 0, -3.0 * s))
    K(LegL, f, rot=(-36 * s, 0, 1.5))
    K(LegR, f, rot=(36 * s, 0, -1.5))
    K(ArmL, f, rot=(27 * s, 0, -9))
    K(ArmR, f, rot=(-27 * s, 0, 9))
    K(TwinL, f, rot=(14 + 9 * c, 0, -5))
    K(TwinR, f, rot=(14 + 9 * c, 0, 5))

# ---- Jump: 24f, crouch(0-4) -> rise(8) -> apex(13) -> fall(19) -> land(24)
begin("Jump")
KB(0, 0, (0, 0, 0)); K(Torso, 0, rot=(0, 0, 0)); K(Head, 0, rot=(0, 0, 0))
K(ArmL, 0, rot=(0, 0, -6)); K(ArmR, 0, rot=(0, 0, 6))
K(LegL, 0, rot=(0, 0, 1.5)); K(LegR, 0, rot=(0, 0, -1.5))
K(TwinL, 0, rot=(0, 0, -3)); K(TwinR, 0, rot=(0, 0, 3))
KB(4, -0.085, (4, 0, 0)); K(Torso, 4, rot=(13, 0, 0)); K(Head, 4, rot=(-8, 0, 0))
K(ArmL, 4, rot=(24, 0, -10)); K(ArmR, 4, rot=(24, 0, 10))
K(LegL, 4, rot=(16, 0, 2)); K(LegR, 4, rot=(20, 0, -2))
K(TwinL, 4, rot=(-7, 0, -3)); K(TwinR, 4, rot=(-7, 0, 3))
KB(8, 0.14, (-2, 0, 0)); K(Torso, 8, rot=(2, 0, 0)); K(Head, 8, rot=(-3, 0, 0))
K(ArmL, 8, rot=(-52, 0, -16)); K(ArmR, 8, rot=(-52, 0, 16))
K(LegL, 8, rot=(-26, 0, 2)); K(LegR, 8, rot=(8, 0, -2))
K(TwinL, 8, rot=(17, 0, -5)); K(TwinR, 8, rot=(17, 0, 5))
KB(13, 0.21, (-3, 0, 0)); K(Torso, 13, rot=(0, 0, 0)); K(Head, 13, rot=(-2, 0, 0))
K(ArmL, 13, rot=(-38, 0, -22)); K(ArmR, 13, rot=(-38, 0, 22))
K(LegL, 13, rot=(-38, 0, 3)); K(LegR, 13, rot=(-14, 0, -3))
K(TwinL, 13, rot=(24, 0, -6)); K(TwinR, 13, rot=(24, 0, 6))
KB(19, 0.09, (2, 0, 0)); K(Torso, 19, rot=(6, 0, 0)); K(Head, 19, rot=(2, 0, 0))
K(ArmL, 19, rot=(-16, 0, -12)); K(ArmR, 19, rot=(-16, 0, 12))
K(LegL, 19, rot=(13, 0, 2)); K(LegR, 19, rot=(18, 0, -2))
K(TwinL, 19, rot=(7, 0, -4)); K(TwinR, 19, rot=(7, 0, 4))
KB(24, -0.035, (2, 0, 0)); K(Torso, 24, rot=(7, 0, 0)); K(Head, 24, rot=(-3, 0, 0))
K(ArmL, 24, rot=(8, 0, -8)); K(ArmR, 24, rot=(8, 0, 8))
K(LegL, 24, rot=(9, 0, 1.5)); K(LegR, 24, rot=(11, 0, -1.5))
K(TwinL, 24, rot=(-3, 0, -3)); K(TwinR, 24, rot=(-3, 0, 3))

# ---- Attack: 20f. Right arm (blade) winds back, raises overhead, slashes.
begin("Attack")
KB(0, 0, (0, 0, 0)); K(Torso, 0, rot=(0, 0, 0)); K(Head, 0, rot=(0, 0, 0))
K(ArmL, 0, rot=(0, 0, -6)); K(ArmR, 0, rot=(0, 0, 6))
K(LegL, 0, rot=(0, 0, 1.5)); K(LegR, 0, rot=(0, 0, -1.5))
K(TwinL, 0, rot=(0, 0, -3)); K(TwinR, 0, rot=(0, 0, 3))
# windup
KB(5, -0.02, (0, 0, -3)); K(Torso, 5, rot=(2, 0, -13)); K(Head, 5, rot=(0, 0, 7))
K(ArmL, 5, rot=(10, 0, -14)); K(ArmR, 5, rot=(42, -12, 14))
K(LegL, 5, rot=(-7, 0, 3)); K(LegR, 5, rot=(7, 0, -3))
K(TwinL, 5, rot=(-5, 0, -4)); K(TwinR, 5, rot=(-5, 0, 4))
# overhead
KB(9, 0.005, (-2, 0, -2)); K(Torso, 9, rot=(-3, 0, -7)); K(Head, 9, rot=(-3, 0, 4))
K(ArmL, 9, rot=(-14, 0, -18)); K(ArmR, 9, rot=(-168, -8, 4))
K(LegL, 9, rot=(-5, 0, 3)); K(LegR, 9, rot=(5, 0, -3))
K(TwinL, 9, rot=(-13, 0, -5)); K(TwinR, 9, rot=(-13, 0, 5))
# slash (fast diagonal down)
KB(12, -0.045, (6, 0, 5)); K(Torso, 12, rot=(18, 0, 20)); K(Head, 12, rot=(4, 0, -6))
K(ArmL, 12, rot=(16, 0, -10)); K(ArmR, 12, rot=(-58, 24, -34))
K(LegL, 12, rot=(6, 0, 3)); K(LegR, 12, rot=(-8, 0, -3))
K(TwinL, 12, rot=(26, 0, -6)); K(TwinR, 12, rot=(26, 0, 6))
# follow-through
KB(16, -0.015, (2, 0, 2)); K(Torso, 16, rot=(9, 0, 10)); K(Head, 16, rot=(2, 0, -3))
K(ArmL, 16, rot=(7, 0, -8)); K(ArmR, 16, rot=(-14, 10, -12))
K(LegL, 16, rot=(2, 0, 2)); K(LegR, 16, rot=(-3, 0, -2))
K(TwinL, 16, rot=(13, 0, -4)); K(TwinR, 16, rot=(13, 0, 4))
# recover
KB(20, 0, (0, 0, 0)); K(Torso, 20, rot=(0, 0, 0)); K(Head, 20, rot=(0, 0, 0))
K(ArmL, 20, rot=(0, 0, -6)); K(ArmR, 20, rot=(0, 0, 6))
K(LegL, 20, rot=(0, 0, 1.5)); K(LegR, 20, rot=(0, 0, -1.5))
K(TwinL, 20, rot=(0, 0, -3)); K(TwinR, 20, rot=(0, 0, 3))

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

# ---- merge the 4 GLBs into one, combining per-object clips by prefix
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
    merged = {}   # clip name -> {'name':..., 'channels':[], 'samplers':[]}
    order = []
    def add_anims(js, bin_offset, bv_base, acc_base):
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
    add_anims(base_j, 0, 0, 0)
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
        add_anims(j, off, bv_base, acc_base)
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

# verify merged animations from the file itself
fj, _ = read_glb(GLB_OUT)
for a in fj.get('animations', []):
    times = []
    for s in a['samplers']:
        acc = fj['accessors'][s['input']]
        times.append(acc.get('max', [0])[0])
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
scene.cycles.samples = 48
scene.cycles.device = 'CPU'
scene.render.resolution_x = 520
scene.render.resolution_y = 640
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

render_pose("Idle", 1, (1.55, -2.25, 1.12), "preview.png")
render_pose("Run", 3, (2.1, -1.55, 0.95), "anim_run.png")
render_pose("Attack", 12, (1.5, -2.1, 1.05), "anim_attack.png")
render_pose("Jump", 13, (1.95, -2.35, 1.32), "anim_jump.png", target=(0, 0, 1.02))
print("ALL DONE")
