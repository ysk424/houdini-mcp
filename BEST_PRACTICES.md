# Houdini MCP — Best Practices

Hard-won lessons from real production use of the Houdini MCP. Organized by context so you can jump to what's relevant.

**Contributing:** Keep entries brief — problem, symptom, fix. Check this file before adding to avoid duplicates. Every entry must include the Houdini version it was validated against. Use the anti-pattern format when applicable: "Tried X, it silently failed, do Y instead."

## Index

- [Copernicus COPs (Compositing)](#copernicus-cops-compositing)
  - [Layer Naming](#layer-naming)
  - [ImageLayer Creation](#imagelayer-creation)
  - [Python Snippet COP](#python-snippet-cop)
  - [Temporal Access (Time-Shifting)](#temporal-access-time-shifting)
  - [Node Categories](#node-categories)
  - [COP HDA Output Naming](#cop-hda-output-naming)
  - [Resolution Mismatch at Sequence Boundaries](#resolution-mismatch-at-sequence-boundaries)
  - [HDA matchCurrentDefinition Resets Internals](#hda-matchcurrentdefinition-resets-internals)
- [COP2 (Legacy Compositing)](#cop2-legacy-compositing)
  - [COP2 VEX Filter Custom Shaders](#cop2-vex-filter-custom-shaders)
  - [Copernicus to COP2 Translation](#copernicus-to-cop2-translation)
  - [COP2 File Node Frame Range](#cop2-file-node-frame-range)
- [Merge / Blend Mode Math Reference](#merge--blend-mode-math-reference)
- [LOPs / USD](#lops--usd)
  - [Standalone husk: Let Karma Author RenderVars, Don't DIY](#standalone-husk-let-karma-author-rendervars-dont-diy)
  - [Standalone husk: productName Time-Sampled vs Default](#standalone-husk-productname-time-sampled-vs-default)
  - [Standalone husk: VEX Shaders Need opdef: URIs](#standalone-husk-vex-shaders-need-opdef-uris)
  - [editmaterialproperties: parm.unexpandedString() Aborts Mid-Node on Non-String Spare Parms](#editmaterialproperties-parmunexpandedstring-aborts-mid-node-on-non-string-spare-parms)
- [SOPs / File Cache](#sops--file-cache)
  - [parm.set() Silently Ignored When Expression Active](#parmset-silently-ignored-when-expression-active)
  - [hbatch render Only Works with ROPs, Not SOPs](#hbatch-render-only-works-with-rops-not-sops)
- [ROPs / Rendering](#rops--rendering)
  - [OpenGL ROP picture Defaults to Literal "ip"](#opengl-rop-picture-defaults-to-literal-ip-mplay-not-a-file-path)
  - [Unsaved HIP Resolves $HIP to Install Dir](#unsaved-hip-resolves-hip-to-the-houdini-install-directory)
  - [Karma & Mantra Sidecar Parms](#karma--mantra-rops-have-multiple-write-tagged-sidecar-parms)
  - [usdrender_rop outputimage Empty by Default](#usdrender_rop-defaults-outputimage-to-empty--real-output-is-in-rendersettings-prim)
  - [Alembic ROP Tags Differently](#alembic-rop-tags-output-parm-differently-than-most-rops)
  - [Sequence Detection by Frame Comparison](#sequence-detection-compare-frame-substitutions-dont-regex-the-raw-string)
  - [hou.expandString Loses Node Context for $OS](#houexpandstring-loses-node-context-for-os)
  - [flipbookSettings.resolution Silently Ignored Without useResolution](#flipbooksettingsresolution-is-silently-ignored-without-useresolutiontrue)
  - [Toggle Server Does Not Reload Plugin Code](#toggle-server-shelf-button-does-not-reload-plugin-code)
  - [Flipbook Off-Screen Viewport in Single Layout](#sceneviewerflipbookviewport-settings-silently-fails-for-off-screen-viewports-in-single-layout)
- [General MCP Usage](#general-mcp-usage)
  - [Connection Discipline](#connection-discipline)
  - [Node Inspection Caveats](#node-inspection-caveats)
  - [HDA Script Sync](#hda-script-sync)
  - [Diagnostics Workflow](#diagnostics-workflow)

---

## Copernicus COPs (Compositing)

### Layer Naming

> Houdini 21.0.631

**The Layer Merge (average) node matches inputs by layer name, not by input index.** Mismatched names are **silently ignored** — no error, no warning, just missing pixels.

**Anti-pattern:** Created a Python Snippet COP with output named `"C"` feeding into a Layer Merge alongside a `"mono"` input. Merge output contained only the mono input. Zero contribution from the other layer, zero errors.

**Diagnosis:** Check `node.outputNames()` on each input to the merge.

**Fix:** Set your node's `output1_name` parm to match the upstream layer name. The `return` dict key must also match: `return {'mono': out_layer}`.

### ImageLayer Creation

> Houdini 21.0.631

When creating a new `hou.ImageLayer()` from scratch (e.g., in a Python Snippet COP), three things will break downstream nodes:

#### 1. Construction order matters

**Anti-pattern:** Set `setDataWindow()` before `setChannelCount()` / `setStorageType()`. Result: `"Provided buffer incorrect size"` on `setAllBufferElements()`.

Buffer size is calculated from resolution + channels + storage at the time the window is set. Set channel count and storage type **first**.

```python
out_layer = hou.ImageLayer()
out_layer.setChannelCount(1)                            # FIRST
out_layer.setStorageType(hou.imageLayerStorageType.Float32)  # FIRST
out_layer.setDataWindow(0, 0, width, height)            # THEN
out_layer.setDisplayWindow(0, 0, width, height)
out_layer.setAllBufferElements(result.tobytes())
```

#### 2. `setDataWindow` / `setDisplayWindow` take 4 separate args, not a list

**Anti-pattern:** Called `setDataWindow([0, 0, 1920, 1080])`. Fails with `"missing 3 required positional arguments"`.

**Fix:** `setDataWindow(0, 0, 1920, 1080)` — four separate ints.

#### 3. Copy all metadata from the source layer

**Anti-pattern:** Returned a new `hou.ImageLayer()` with correct pixel data but no attributes. Downstream Layer Merge **silently discarded** the entire layer.

A bare `hou.ImageLayer()` has zero attributes. Always copy metadata:

```python
out_layer.setBorder(input_layer.border())
out_layer.setPixelScale(input_layer.pixelScale())
out_layer.setTypeInfo(input_layer.typeInfo())
out_layer.setProjection(input_layer.projection())
out_layer.setAttributes(input_layer.attributes())
```

### Python Snippet COP

> Houdini 21.0.631

#### `kwargs` contains ImageLayer objects, not numpy arrays

Extract pixel data with:

```python
data = layer.allBufferElements(hou.imageLayerStorageType.Float32, channels)
arr = np.frombuffer(data, dtype=np.float32).reshape(height, width).copy()
```

The `.copy()` is required — the original buffer is read-only.

#### Input layers are GPU-resident and NOT frozen

**Anti-pattern:** Tried `setAllBufferElements()`, `makeConstant()`, and `freeze()` on `kwargs` input layers. All fail — they're GPU-resident with `isFrozen=False`.

**Fix:** Always create a new `hou.ImageLayer()` for output. Never modify the input in-place.

#### `hou` module IS accessible

Despite the docs stating "this node can't access the currently evaluating node", `import hou` works. You can call `hou.pwd()`, `hou.frame()`, `hou.node()`, and critically `node.layerAtFrame(frame)` for temporal effects. See [Temporal Access](#temporal-access-time-shifting).

### Temporal Access (Time-Shifting)

> Houdini 21.0.631

**Copernicus has no native timeshift COP.** The old COP2 `shift` node does not exist in Copernicus networks.

**Anti-patterns tried:**
- `op:` syntax in the File COP to reference another COP's output → `"Unable to read file"`
- Searching for `shift`, `timefilter`, `timeshift` in the Cop category → none exist
- File COP `videoframemethod` / `videoframe` with expressions → only works for on-disk sequences, not upstream COP outputs

**Workaround:** `node.layerAtFrame(float)` from Python (via `execute_houdini_code` or inside a Python Snippet COP). Cooks the target node at any frame and returns an `ImageLayer`.

```python
source = hou.pwd().inputs()[0]
layer_past = source.layerAtFrame(hou.frame() - 5)
layer_future = source.layerAtFrame(hou.frame() + 5)
```

**Performance:** Each call triggers a full upstream cook at that frame. 10 echo offsets = 10 extra cooks per frame.

### Node Categories

> Houdini 21.0.631

**Copernicus node category is `"Cop"`, not `"Cop2"`.** Use `node.childTypeCategory()` to query. Old COP2 nodes (`shift`, `timefilter`, `vopcop2filter`, etc.) are not available in Copernicus networks.

```python
parent = hou.node("/path/to/copnet")
for name in sorted(parent.childTypeCategory().nodeTypes().keys()):
    print(name)
```

### COP HDA Output Naming

> Houdini 21.0.631

**For COP HDAs, `outputNames()` is controlled by the `output` line in the DialogScript section of the HDA definition — NOT by the `outputname#` multiparm parm.**

**Anti-pattern:** Created a COP HDA with `outputname1` multiparm (matching the null node pattern) and set it to `"mono"`. `outputNames()` still returned `('output1',)` — the default connector name from the DialogScript. Downstream Layer Merge silently ignored the HDA's output.

**Diagnosis:** Read the HDA's DialogScript section: `hda_def.sections()['DialogScript'].contents()`. Look for the `output` line (format: `output <connector_name> <label>`).

**Fix:** Modify the DialogScript's `output` line to set the desired layer name:

```python
hda_def = node.type().definition()
ds = hda_def.sections()['DialogScript'].contents()
ds = ds.replace('output\toutput1\tC', 'output\tlayer\tlayer')
hda_def.sections()['DialogScript'].setContents(ds)
node.matchCurrentDefinition()
```

**Note:** The `outputname#` multiparm on a COP HDA has no effect on `outputNames()`. It works on built-in nodes like `null` because their output naming is handled in C++, not via DialogScript.

### Resolution Mismatch at Sequence Boundaries

> Houdini 21.0.631

**`layerAtFrame()` returns a default 1024×1024 layer for frames outside the source sequence range.** No error — just wrong resolution.

**Anti-pattern:** Echo effect called `layerAtFrame(frame - 5)` near the start of a sequence (frame 1001). Frames before 1001 returned 1024×1024 instead of the expected 1920×1080. `np.maximum()` then failed or produced garbage due to shape mismatch.

**Fix:** Guard against resolution mismatch before blending:

```python
echo_layer = source.layerAtFrame(echo_frame)
if echo_layer.bufferResolution() != (width, height):
    continue
```

### HDA `matchCurrentDefinition` Resets Internals

> Houdini 21.0.631

**Calling `node.matchCurrentDefinition()` on an unlocked HDA reverts ALL internal edits** — manually created nodes, rewired connections, and parm changes inside the HDA are lost.

**Anti-pattern:** Unlocked an HDA with `allowEditingOfContents()`, created a null node inside, wired it into the chain, then called `matchCurrentDefinition()` to refresh the outer node. The null node disappeared and the internal chain reverted to the saved definition.

**Fix:** Make all changes to the HDA definition (DialogScript, parm template, etc.) BEFORE calling `matchCurrentDefinition()`. Or save the definition (`hda_def.save()`) after internal edits and before refreshing.

---

## COP2 (Legacy Compositing)

### COP2 VEX Filter Custom Shaders

> Houdini 21.0.631

**The `vexfilter` node cannot find custom `.vex` shaders by short name from user directories.** It only resolves short names from the system `$HH/vex/Cop2/` directory.

**Anti-pattern:** Compiled a `.vfl` to `~/houdini21.0/vex/Cop2/softlight.vex` (which IS on `HOUDINI_PATH`), set `function` parm to `"softlight"`. Error: `"Could not find VEX Cop2 shader 'softlight'"`.

**Fix:** Use the full absolute path without extension:

```python
node.parm("function").set("/home/user/houdini21.0/vex/Cop2/softlight")
```

**VFL compilation:** `vcc myfilter.vfl` from the target directory. The `cop2` context is declared in the file itself — no `-d` flag needed (that flag means "compile all functions", not "set context").

### Copernicus to COP2 Translation

> Houdini 21.0.631

**Copernicus (`copnet`, child category `Cop`) and COP2 (`cop2net`, child category `Cop2`) are different systems.** Node types don't cross between them.

Key type mappings:

| Copernicus | COP2 | Notes |
|---|---|---|
| `blend` (mode=over) | `over` | Input order swapped: COP2 `over` is FG=in0, BG=in1 (Copernicus blend is A/BG=in0, B/FG=in1) |
| `blend` (mode=max) | `max` | `mask` parm → `effectamount` parm |
| `xform2d` | `xform` | Same parm names (tx, ty, etc.) |
| `constant` | `color` | `f4r/f4g/f4b` → `colorr/colorg/colorb`; COP2 `color` is a generator (set resolution explicitly) |
| `resample` | `scale` | COP2 `scale` uses explicit resolution, not a reference input |
| `rop_image` | `rop_comp` | `filename` → `filename1`; frame range parms differ |
| `channelswap` | `channelcopy` | No direct equivalent; consider skipping if `mono` is downstream |
| `file`, `null`, `mono`, `invert`, `gamma`, `layer` | same name | Parm names may differ (e.g. COP2 file uses `filename1`) |

### COP2 File Node Frame Range

> Houdini 21.0.631

**COP2 `file` node shows a grey dotted X when the current frame is outside the node's `start`/`length` range.** No error — just a blank frame with a grey X overlay.

**Anti-pattern:** File node with expression-based frame offset (e.g. `` `padzero(4,$F-1001)` ``) mapping frames 1002–1265 to files frame_0001.png–frame_0264.png. Default `start=1` and `length=264` meant valid range was frames 1–264, but timeline was at frame 1016.

**Fix:** Set `start` to match the first Houdini frame where a file exists (1002 in this case). The `length` stays at the file count (264).

---

## Merge / Blend Mode Math Reference

Comprehensive reference for compositing blend modes. Useful when implementing custom VEX filters.

Source: [Nuke Merge Operations](https://learn.foundry.com/nuke/9.0/content/comp_environment/merging/merge_operations.html)

Where **A = foreground**, **B = background**, **a/b = respective alpha**:

| Mode | Formula |
|---|---|
| Over | `A + B(1-a)` |
| Under | `A(1-b) + B` |
| Plus / Add | `A + B` |
| Multiply | `AB` |
| Screen | `A + B - AB` |
| Max / Lighten | `max(A, B)` |
| Min / Darken | `min(A, B)` |
| Soft Light | If `AB < 1`: `B(2A + B(1 - AB))`, else: `2AB` |
| Hard Light | If `A < 0.5`: `2AB`, else: `1 - 2(1-A)(1-B)` |
| Overlay | Hard Light with inputs swapped |
| Color Dodge | `B / (1-A)` |
| Color Burn | `1 - (1-B)/A` |
| Difference | `|A - B|` |
| Exclusion | `A + B - 2AB` |

---

## LOPs / USD

### Standalone husk: Let Karma Author RenderVars, Don't DIY

> Houdini 21.0.631

**Symptom:** Manually authored RenderVars produce `Unsupported AOV settings for: C` or black renders. No orderedVars produces `No orderedVars to specify channels`.

**Cause:** Karma in-process and standalone husk validate RenderVar attributes differently (SideFX BUG #134678). Copying the exact values from `karmarendersettings` LOP output (`color4f` + LPE + `color4h`) fails in standalone husk. Manually authoring simpler values (`color3f`/`raw`/`C`) also fails. There is no known manually-authored RenderVar configuration that reliably works across husk versions.

**Anti-patterns tried:**
- `color4f` + `sourceName=C.*[LO]` + `sourceType=lpe` → "Unsupported AOV settings"
- `color3f` + `sourceName=C` + `sourceType=raw` + husk attrs → "Unsupported AOV settings"
- `color3f` + `sourceName=Ci` + `sourceType=raw` (no husk attrs) → warning + black render

**Fix:** Don't author RenderVars yourself. Enable the **Beauty AOV** checkbox on the Karma RenderSettings LOP in the scene. The LOP authors RenderVars through an internal code path that husk accepts. Detect missing orderedVars during auditing and warn the user to enable Beauty.

### Standalone husk: productName Time-Sampled vs Default

> Houdini 21.0.631

**Symptom:** husk writes to a stale path like `/old/path/$HIPNAME.$OS.$F4.exr` instead of the productName you authored.

**Cause:** Karma RenderSettings LOP evaluates `$HIP/render/$HIPNAME.$OS.$F4.exr` at cook time, baking it as a **time-sampled** value on `productName`. After `stage.Flatten()`, setting `attr_spec.default = new_path` is ignored — time-sampled values always win over defaults in USD composition.

**Fix:** Clear time-sampled values before setting the default:

```python
attr = prim.GetAttribute("productName")
if attr and attr.GetTimeSamples():
    attr.Clear()
attr_spec = Sdf.AttributeSpec(prim_spec, "productName", Sdf.ValueTypeNames.Token)
attr_spec.default = new_path
```

**Diagnostic:** `attr.GetTimeSamples()` returns non-empty if time samples exist.

### Standalone husk: VEX Shaders Need opdef: URIs

> Houdini 21.0.631

**Symptom:** `Unhandled node type <name> in material`. Objects render default grey.

**Cause:** VEX shader resolution in husk works ONLY through `opdef:` URI resolution (e.g. `opdef:/Vop/principledshader::2.0?SurfaceVexCode`), which triggers on-demand VEX compilation via `VEX_VexResolver`. There is **no Sdr parser plugin for VEX/VFL** — the Sdr registry only handles `kma`, `mtlx`, `glslfx`, and `USD` source types. Baking opdef: references to VFL files on disk does nothing — husk cannot use them.

**Anti-patterns tried:**
- Baking VFL source to a file inside USDZ → husk can't read files from zip archives
- Extracting VFL to disk and overriding sourceAsset → no Sdr parser for VFL files
- Baking to disk with various file extensions → irrelevant, no parser exists

**Fix:** Preserve `opdef:` URIs for VEX shaders. If you must bake `opdef:` references for USDZ packaging (`CreateNewUsdzPackage` needs real files), override `info:sourceAsset` back to the original `opdef:` URI in a wrapper USDA layer:

```python
# During baking: record original opdef: URIs for Shader prims
# After USDZ creation: wrapper overrides sourceAsset back to opdef:

# In wrapper .usda:
# over "materials" { over "mirror" { over "mirror_surface" {
#     asset info:sourceAsset = @opdef:/Vop/principledshader::2.0?SurfaceVexCode@
# }}}
```

**Requirements:** Karma CPU only (not XPU). Houdini must be installed on the render machine — the OTL libraries (`$HH/otls/OPlibVop.hda`) must be loadable for factory shaders. Custom VOP HDAs need their `.hda` files deployed via `HOUDINI_OTLSCAN_PATH`.

**Fully portable alternative:** Replace VEX shaders with MaterialX (`mtlxstandard_surface`, `ND_*` nodes) or `UsdPreviewSurface`. These work with Karma CPU, XPU, and standalone husk without any Houdini dependencies.

### editmaterialproperties: parm.unexpandedString() Aborts Mid-Node on Non-String Spare Parms

> Houdini 21.0.631

**`editmaterialproperties` LOP nodes have 160+ spare parameters, most of which are non-string types (folders, floats, toggles, vectors). Calling `parm.unexpandedString()` on any of them raises `OperationFailed: Only string parms have unexpanded string`. Without a per-parm try/except, the scan loop aborts on the first non-string spare parm and never reaches later string parms (like file texture paths).**

**Anti-pattern:** Iterating `node.parms()` and calling `parm.unexpandedString()` to scan for file path references. The first spare folder parm raises, killing the loop. File parms like `emission_color_file` appear later in the list and are silently skipped.

**Symptom:** File path parms on `editmaterialproperties` nodes are missed during a scan, even though they contain the search string and `node.parms()` does include them.

**Fix:** Check the parm template type before calling `unexpandedString()`, or guard per-parm:

```python
for p in node.parms():
    if p.parmTemplate().type() != hou.parmTemplateType.String:
        continue
    try:
        val = p.unexpandedString()
    except Exception:
        continue
    if search_string in val:
        hits.append((node.path(), p.name(), val))
```

**Note:** `node.parms()` DOES include spare parameters — that's not the issue. The issue is solely that non-string spare parms raise on `unexpandedString()`.

---

## SOPs / File Cache

### `parm.set()` Silently Ignored When Expression Active

> Houdini 21.0.631

**`parm.set(value)` on a float/int parm is silently ignored if the parm has an active expression or keyframe.** The expression always takes priority. No error, no warning — the value just doesn't stick.

**Anti-pattern:** Created a `filecache::2.0` node and called `fc.parm("f1").set(100)`. The parm still evaluated to `1` because `f1` has a default expression (`$FSTART`). The `set()` call was completely ignored.

**Affected parms on filecache::2.0:** `f1` (`$FSTART`), `f2` (`$FEND`), `f3` (may have `$FINC`). String parms like `basedir` and `basename` are NOT affected — they store raw strings, not expressions.

**Fix:** Call `deleteAllKeyframes()` before `set()` to clear the expression first:

```python
fc.parm("f1").deleteAllKeyframes()
fc.parm("f1").set(100)  # Now actually takes effect
```

**Note:** This applies to any parm with a default expression, not just filecache nodes. Common offenders: `$FSTART`/`$FEND` on frame range parms, `ch("../parm")` on HDA-internal parms.

### hbatch `render` Only Works with ROPs, Not SOPs

> Houdini 21.0.631

**The hbatch `render` command silently does nothing when given a SOP path like a filecache node.** It only works with ROP nodes. No error, no output — just exits cleanly with rc=0.

**Anti-pattern:** `hbatch -c "mread scene.hip; render -f 1 1 /obj/geo/filecache1; quit"` — exits successfully but produces zero cache files.

**Fix:** Use hython with `pressButton()` on the filecache's `execute` parm instead:

```bash
hython -c '
import hou
hou.hipFile.load("scene.hip")
node = hou.node("/obj/geo/filecache1")
node.parm("execute").pressButton()
'
```

`pressButton()` is synchronous in hython — it blocks until all frames are written.

---

## ROPs / Rendering

### OpenGL ROP `picture` Defaults to Literal `"ip"` (MPlay), Not a File Path

> Houdini 21.0.631

A freshly created `opengl` ROP has `picture = "ip"`. Calling `parm.eval()` returns the string `"ip"` — not a path. Code that treats every ROP's output parm as a filesystem path will report a non-existent file at `"ip"` and confuse downstream logic.

**Fix:** Treat raw values `"ip"` and `"md"` as MPlay sentinels (in-process and disk-backed MPlay). Classify them out of the image category and skip filesystem checks. `get_rop_output_path` returns `category: "mplay"`, `exists: false`.

### Unsaved HIP Resolves `$HIP` to the Houdini Install Directory

> Houdini 21.0.631

In an unsaved scene, `hou.hipFile.path()` returns `<install>/bin/untitled.hip`, so `hou.expandString("$HIP/render/...")` lands inside the Houdini install dir (e.g., `C:/Program Files/.../bin/render/`). Renders technically succeed but write to a surprising location, and the agent reports paths the user can't easily find.

**Diagnosis:** Check `hou.hipFile.name() == "untitled.hip"` and the resolved path — they're consistent indicators.

**Fix:** Surface a warning when `$HIP` or `$HIPNAME` appears in a raw parm value while the scene is unsaved. `get_rop_output_path` emits `warnings: ["hip_unsaved"]` for this case.

### Karma & Mantra ROPs Have Multiple Write-Tagged Sidecar Parms

> Houdini 21.0.631

A naive scan of "all `FileReference` parms with `tags.filechooser_mode == 'write'`" picks up sidecars, not the actual output:

- **Karma** (`karma`): `picture`, `dcmfilename`, `husk_chromefile`, `husk_stdout`, `husk_stderr` — five candidates.
- **Mantra** (`ifd`): `vm_picture`, `soho_diskfile` (.ifd intermediate), `vm_tmpsharedstorage` (storage path), `vm_tmplocalstorage`.

**Fix:** When tag-scanning for an output parm, reject names starting with `husk_`, `soho_`, `vm_tmp`, `dcm`, or containing `_storage`/`_chromefile`/`_stdout`/`_stderr`. Better yet, prefer a per-ROP-type known-name map and fall back to tag scanning only for unknown types.

### `usdrender_rop` Defaults `outputimage` to Empty — Real Output Is in RenderSettings Prim

> Houdini 21.0.631

A freshly created `usdrender_rop` has `outputimage = ""`. The actual render output is governed by the USD `RenderSettings` prim (path in the `rendersettings` parm, default `/Render/rendersettings`), specifically its `outputs:render` / `productName` attributes. The ROP only honors `outputimage` if it's explicitly set as an override.

**Anti-pattern:** Reading `outputimage` and reporting it as the render output — returns empty string.

**Fix:** When `outputimage` is empty on a `usdrender_rop`, classify as needing USD-stage resolution. `get_rop_output_path` returns `category: "usd_render_via_settings"` with the RenderSettings prim path in `hint`. Resolving the actual product name requires cooking the LOP stage and reading the prim — out of scope for a pure parm read.

### Alembic ROP Tags Output Parm Differently Than Most ROPs

> Houdini 21.0.631

The `alembic` ROP's `filename` parm has `tags = {"filechooser_pattern": "*.abc"}` — no `filechooser_mode: write` tag. Tag scans that filter strictly on `filechooser_mode == "write"` miss it.

**Fix:** Accept either tag as a write-output marker: `tags.get("filechooser_mode") == "write"` OR `"filechooser_pattern" in tags`. (`get_rop_output_path` uses both.)

### Sequence Detection: Compare Frame Substitutions, Don't Regex the Raw String

> Houdini 21.0.631

Detecting whether a parm value renders a sequence by regex-matching `$F` / `$FF` / `$F\d+` in the raw string misses custom HDA tokens, expression-driven frame substitution, and edge cases like `$N`. The definitive test is whether the parm evaluates differently at two distinct frames:

```python
is_sequence = parm.evalAtFrame(1) != parm.evalAtFrame(2)
```

This works for any frame-dependent expression, not just the documented frame variables.

### `hou.expandString` Loses Node Context for `$OS`

> Houdini 21.0.631

Karma's default output is `$HIP/render/$HIPNAME.$OS.$F4.exr`. Resolving with `hou.expandString(raw)` gives the wrong result because `$OS` (operator name) requires node context. `hou.expandStringAtFrame(raw, frame)` has the same issue.

**Fix:** Use `parm.evalAtFrame(frame)` instead — it carries the parm's owning node context and resolves `$OS` to the node name correctly.

---

### `flipbookSettings.resolution()` Is Silently Ignored Without `useResolution(True)`

> Houdini 21.0.700

`SceneViewer.flipbookSettings()` exposes both `resolution((w,h))` and `useResolution(bool)`. Calling `resolution()` alone has no effect — the flipbook writes at the viewport's current pixel size. Must call `useResolution(True)` first.

Also: `outputToMPlay(False)` is required to avoid flashing the MPlay window, and `frameRange((F, F))` for a single static frame does **not** move the playbar — no `setFrame` save/restore needed.

---

### "Toggle Server" Shelf Button Does Not Reload Plugin Code

> Houdini 21.0.700

The Toggle Server shelf button calls `stop()` / `start()` on the running `HoudiniMCPServer` instance. This re-binds the TCP listener but does **not** reload the `houdinimcp` Python modules — the running instance's class still references the imports captured at original load time. New commands added to the dispatcher after deploying updated handler files will return `Unknown command type: <name>` until Houdini is fully restarted.

**Fix (clean):** Restart Houdini after `python scripts/install.py`. The plugin auto-imports via `pythonrc.py` and picks up the new code.

**Fix (no-restart, runtime patch):** From an MCP `execute_houdini_code` call, `importlib.reload` the affected modules then monkey-patch the running server's class to inject the new handler:

```
import importlib, hou
import houdinimcp.handlers.rendering, houdinimcp.server
importlib.reload(houdinimcp.handlers.rendering)
importlib.reload(houdinimcp.server)
from houdinimcp.handlers.rendering import new_handler
running = hou.session.houdinimcp_server
orig = type(running)._get_handlers
def patched(self):
    h = orig(self); h["new_command"] = new_handler; return h
type(running)._get_handlers = patched
```

The patch survives only until Houdini exits.

---

### `SceneViewer.flipbook(viewport, settings)` Silently Fails for Off-Screen Viewports in Single Layout

> Houdini 21.0.700

A SceneViewer in `Single` layout still reports four `viewports()` (e.g. `right1`, `front1`, `top1`, `front2`), but only `curViewport()` is actually drawn — the others sit at a 1×1 / 101×101 stub. Calling `flipbook(off_screen_vp, settings)` produces no output file, and on some builds hangs Houdini's renderer until the bridge connection times out (WinError 10053).

**Fix:** Before flipbook, gate on `viewer.viewportLayout() == hou.geometryViewportLayout.Single` and require the requested viewport to equal `viewer.curViewport()`. Multi-view layouts (Quad, Double*, Triple*) draw all `viewports()` and accept any of them.

---

## General MCP Usage

### Connection Discipline

> Houdini 21.0.631

**The MCP plugin uses a single-threaded TCP listener.**

1. **Ping before starting work** — verify connectivity before issuing commands.
2. **Never rapid-fire commands** — the plugin needs time to reset between connections.
3. **If you get a connection error, stop** — don't retry in a loop. The plugin likely needs a restart.
4. **Use `batch` for bulk operations** — executes atomically in a single undo group.

### Node Inspection Caveats

> Houdini 21.0.631

**`get_node_info` can crash on certain node types.** We encountered a `'Color' object is not iterable` error when calling it on nodes with non-standard color configurations.

**Workaround:** Use `execute_houdini_code` to inspect nodes manually when `get_node_info` fails. Iterate `node.parms()`, `node.inputs()`, `node.outputs()` directly.

### HDA Script Sync

> Houdini 21.0.631

**Editing HDA script files on disk does NOT update the embedded code inside the `.hdalc`.** The HDA definition carries its own copy of `PythonModule.py`, `OnCreated.py`, etc. If you only change the on-disk files, the live HDA keeps running the old code.

**Anti-pattern:** Changed `PythonModule.py` in the repo, committed, but didn't update the HDA definition. The node in Houdini still ran the old logic.

**Fix:** After modifying any HDA script file, push the updated code into the HDA definition — via Type Properties → Scripts in the Houdini UI, or via MCP (`set_hda_section_content` / `update_hda`). Treat HDA sync as part of the commit.

### Diagnostics Workflow

> Houdini 21.0.631

When something looks wrong in a COP network, use `execute_houdini_code` to inspect systematically:

1. **Check network topology** — iterate `parent.children()`, print inputs/outputs for each node.
2. **Check for errors** — `node.errors()` and `node.warnings()` on each node in the chain.
3. **Check layer names first** — `node.outputNames()` mismatches are the #1 cause of silent failures in Copernicus. See [Layer Naming](#layer-naming).
4. **Compare pixel values** — `layer.allBufferElements()` + numpy at specific coordinates. Don't trust visual inspection alone.
5. **Compare layer metadata** — `outputNames()`, `channelCount()`, `attributes()`, `typeInfo()` between working and broken paths.
6. **Use a switch node for A/B testing** — insert a switch to isolate which part of the chain causes the issue.
