# Houdini-Evaluated Body Alembic for Marvelous Designer

This note records the accepted direction for exporting an avatar body cache from
Houdini to Marvelous Designer after a Blender character has been transferred into
Solaris.

The important rule is: **export the body cache from Houdini, not Blender**. Even
when the Blender and Houdini rigs look visually equivalent, their evaluated skin
positions can differ by a few millimeters. That is enough for Marvelous Designer
cloth to penetrate when the garment is brought back to Houdini/Solaris.

## Validated Scene

Validated on Houdini 21.0.631 with the Blender-to-Houdini USD character transfer
already loaded in Solaris.

Current accepted stage node:

```text
/stage/LUMI_alpha_texture_override
```

Current SkelRoot:

```text
/C__Users_azoo_git_houdini_hair_simulation_exports_lumi_tsudura_test_animation/Lumi_Tsudura_Test/TSUDURA_EXPORT_HD_Neutral_F
```

Current body mesh prim:

```text
/C__Users_azoo_git_houdini_hair_simulation_exports_lumi_tsudura_test_animation/Lumi_Tsudura_Test/TSUDURA_EXPORT_HD_Neutral_F/TSUDURA_EXPORT_CC_Base_Body/CC_Base_Body_001
```

Target Alembic names, matching the existing Tanabata / Marvelous Designer bridge:

```text
C:/Users/azoo/Desktop/avatar_one.abc
C:/Users/azoo/Desktop/avatar_all.abc
```

`avatar_one.abc` is the frame-1 avatar cache. `avatar_all.abc` is the full
animation cache.

## What Did Not Work

Do not export the body using only a LOP Import SOP.

This was tested with:

```text
lopimport::2.0
  loppath = /stage/LUMI_alpha_texture_override
  primpattern = <body mesh prim>
  timesample = animated
  importframe = $FF
unpackusd::2.0
```

The imported geometry contained the body mesh, but point positions were identical
at frames 1, 25, and 250. It imported the USD mesh data, not the final skinned
body positions needed by MD.

Also do not use `kinefx::usdcharacterimport` by itself as the Alembic source. It
imports character data, but the sampled point positions also stayed unchanged in
this test.

## Accepted Houdini Network

Create a dedicated OBJ network:

```text
/obj/MD_body_cache_from_houdini
```

Inside it, build this SOP chain:

```text
USD_SKIN_IMPORT
  type: kinefx::usdskinimport
  usdsource: lop
  loppath: /stage/LUMI_alpha_texture_override
  skelrootpath: <SkelRoot path>
  purpose: render
  shapeattrib: name

USD_ANIM_BIND_POSE
  type: kinefx::usdanimimport
  usdsource: lop
  loppath: /stage/LUMI_alpha_texture_override
  skelrootpath: <SkelRoot path>
  output: bind

USD_ANIM_CURRENT_FRAME
  type: kinefx::usdanimimport
  usdsource: lop
  loppath: /stage/LUMI_alpha_texture_override
  skelrootpath: <SkelRoot path>
  output: animation
  timeshiftmethod: byframe
  frame: $FF

JOINT_DEFORM_HOUDINI_EVAL
  type: kinefx::jointdeform
  input 0: USD_SKIN_IMPORT
  input 1: USD_ANIM_BIND_POSE
  input 2: USD_ANIM_CURRENT_FRAME
  method: frominputgeo
  donormal: 1
  deletecaptureattrib: 1

KEEP_BODY_ONLY_FULL_RES
  type: python
  input 0: JOINT_DEFORM_HOUDINI_EVAL

OUT_HOUDINI_EVALUATED_BODY_FULL_RES
  type: null
  input 0: KEEP_BODY_ONLY_FULL_RES
```

The Python SOP keeps only the body primitives and preserves the full body
resolution. It does not decimate or simplify the mesh.

```python
node = hou.pwd()
geo = node.geometry()
patterns = ("CC_Base_Body", "CC_Base_Body_001", "TSUDURA_EXPORT_CC_Base_Body")

to_delete = []
for prim in geo.prims():
    values = []
    for attr_name in ("name", "usdprimpath", "usdpath", "path"):
        attr = geo.findPrimAttrib(attr_name)
        if attr is not None:
            try:
                values.append(str(prim.attribValue(attr)))
            except Exception:
                pass
    if not any(any(pat in value for pat in patterns) for value in values):
        to_delete.append(prim)

geo.deletePrims(to_delete, keep_points=False)

path_attr = geo.findPrimAttrib("path") or geo.addAttrib(hou.attribType.Prim, "path", "")
name_attr = geo.findPrimAttrib("name") or geo.addAttrib(hou.attribType.Prim, "name", "")
for prim in geo.prims():
    prim.setAttribValue(path_attr, "/avatar/body")
    prim.setAttribValue(name_attr, "body")
```

## Validation Before Export

Before writing Alembic, sample the final output node at multiple frames and
confirm point positions change.

Validated result from the current character:

```text
output node: /obj/MD_body_cache_from_houdini/OUT_HOUDINI_EVALUATED_BODY_FULL_RES
frame range: 1..250
points: 225324
prims: 224876
frames checked: 1, 25, 250
result: point positions changed
```

The frame-1, frame-25, and frame-250 probe points and bounding box values were
different, so this is the Houdini-evaluated skinned body cache, not a rest-pose
mesh.

## Alembic ROPs

Create two `rop_alembic` SOP nodes under `/obj/MD_body_cache_from_houdini`.

Single-frame avatar:

```text
EXPORT_AVATAR_ONE_ABC
  input 0: OUT_HOUDINI_EVALUATED_BODY_FULL_RES
  filename: C:/Users/azoo/Desktop/avatar_one.abc
  trange: off
  f1/f2/f3: 1 / 1 / 1
  format: ogawa
  motionBlur: 0
  build_from_path: 1
  path_attrib: path
  save_attributes: 1
  pointAttributes: *
  vertexAttributes: *
  primitiveAttributes: *
```

Full animation avatar:

```text
EXPORT_AVATAR_ALL_ABC
  input 0: OUT_HOUDINI_EVALUATED_BODY_FULL_RES
  filename: C:/Users/azoo/Desktop/avatar_all.abc
  trange: normal
  f1/f2/f3: 1 / 250 / 1
  format: ogawa
  motionBlur: 0
  build_from_path: 1
  path_attrib: path
  save_attributes: 1
  pointAttributes: *
  vertexAttributes: *
  primitiveAttributes: *
```

Run the ROPs only after validation passes:

```python
hou.node("/obj/MD_body_cache_from_houdini/EXPORT_AVATAR_ONE_ABC").parm("execute").pressButton()
hou.node("/obj/MD_body_cache_from_houdini/EXPORT_AVATAR_ALL_ABC").parm("execute").pressButton()
```

## Notes for Marvelous Designer

Use the Houdini-exported `avatar_one.abc` / `avatar_all.abc` as the MD avatar
source. Keep FPS and frame range aligned with the Houdini timeline. For the
current test clip, the accepted range is 1..250 at 24 fps.

The export intentionally keeps the full body mesh because accuracy matters more
than file size for this pipeline. The workstation used for this test has enough
memory and GPU headroom for MD to handle the full-resolution collider.
