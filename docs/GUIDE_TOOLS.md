# MCP Tool Reference

HoudiniMCP exposes 88 MCP tools in the default Codex/Claude surface. The set is
kept intentionally focused on simulation, viewport capture, rendering, node
work, parameters, cache management, undo/redo, and documentation lookup.

All tools that interact with Houdini require a running Houdini instance with the
plugin loaded. `search_docs` and `get_doc` work offline.

## How Tools Work

Each tool sends a JSON command over TCP to the Houdini plugin, which executes it
and returns a JSON response. Mutating commands are wrapped in Houdini undo groups
where possible, and `undo`, `redo`, and `get_undo_history` are exposed directly.

For uncommon Houdini API work, use `execute_houdini_code` instead of exposing a
dedicated MCP wrapper for every possible operation.

## Default Tool Surface

### Scene and Code

- `ping`
- `get_scene_info`
- `save_scene`
- `load_scene`
- `execute_houdini_code`
- `batch`
- `get_scene_dossier`

### Nodes and Networks

- `create_node`
- `modify_node`
- `delete_node`
- `get_node_info`
- `set_node_flags`
- `layout_children`
- `find_error_nodes`
- `get_network_overview`
- `get_cook_chain`
- `get_selection`
- `set_selection`
- `copy_node`
- `move_node`
- `rename_node`
- `list_children`
- `find_nodes`
- `connect_nodes_batch`
- `set_current_network`

### Parameters and Animation

- `get_parameter`
- `set_parameters`
- `get_parameter_schema`
- `set_expression`
- `set_frame`
- `get_frame`
- `set_frame_range`
- `set_playback_range`
- `playbar_control`
- `set_keyframes`
- `get_keyframes`

### VEX, Materials, and Geometry

- `create_wrangle`
- `validate_vex`
- `set_material`
- `list_materials`
- `get_material_info`
- `create_material_network`
- `assign_material`
- `get_geo_summary`
- `get_points`
- `get_prims`
- `get_attrib_values`
- `set_detail_attrib`
- `get_bounding_box`
- `geo_export`

### Simulation and Cache

- `get_simulation_info`
- `list_dop_objects`
- `step_simulation`
- `reset_simulation`
- `list_caches`
- `get_cache_status`
- `clear_cache`
- `write_cache`
- `setup_pyro_sim`
- `setup_rbd_sim`
- `setup_flip_sim`
- `setup_vellum_sim`
- `build_sop_chain`

### Viewport, Capture, and Rendering

- `render_view`
- `render_flipbook`
- `screenshot_viewport`
- `list_panes`
- `get_viewport_info`
- `set_viewport_camera`
- `set_viewport_display`
- `set_viewport_renderer`
- `frame_view`
- `set_viewport_direction`
- `list_render_nodes`
- `get_render_settings`
- `set_render_settings`
- `create_render_node`
- `start_render`
- `get_render_progress`
- `get_rop_output_path`
- `monitor_render`
- `setup_render`
- `list_lights`

### Docs and Undo

- `search_docs`
- `get_doc`
- `undo`
- `redo`
- `get_undo_history`

## Removed From Default Surface

The previous expanded surface included many thin wrappers for PDG/TOPs, HDA
management, COPs, event polling, low-level USD attributes, HScript, node type
introspection, spare parameters, parameter locking/linking, and other infrequent
operations. Those are intentionally not exposed by default. They can still be
performed through `execute_houdini_code` when a workflow needs them.
