# Forge packages — PS3Forge 0.9

New packages also preserve skeletal IYAM2 models, component target references,
LOD assets, independent materials and texture images. Component targets are
included recursively, then IDs are remapped together on import. Details and
current limits are in [ENGINE-0.9.md](ENGINE-0.9.md). Older packages still work.

`.forgepack` is a single reusable file containing scene objects, referenced IYAM
models with all their pose clips, object settings, script variables and C++ source.
The package is a versioned ZIP container, not a PS3 executable or a compiled PKG.

## Export and share

1. Select an object in Hierarchy. Ctrl-click more rows to select linked objects,
   such as Player and a first-person weapon. The transform gizmo edits the active
   object; multiple selection is used for package export.
2. Right-click and choose **Export selected (N)…**. To include all objects in the
   active scene, choose **Export scene package…**.
3. Choose the destination in the desktop Save dialog and send the `.forgepack`.

Right-click a model in Assets to export that model with its clips as a reusable
object package. The File menu also offers import and export commands.

Export uses the current editor draft, including code in the script editor. It
does not silently save or discard your edits. Model bytes come from project assets.
All project scripts are included to retain cross-script function/global dependencies.
References to other objects by name cannot be inferred reliably from arbitrary C++:
include those objects in the selection, or export the scene.

## Import

Right-click Hierarchy, the viewport, Assets or the project hub and choose
**Import package…**. Select a `.forgepack`, inspect its object/model/clip/script
counts, then choose:

- **Import into current project**: adds the objects to the active scene as an
  unsaved, undoable edit. Save when satisfied. Existing object IDs/assets are not
  overwritten; new IDs are allocated. Camera/HUD settings of the current project
  are retained.
- **Open as new project**: creates an independent project with its own project
  ID and PS3 title ID, retaining the package's initial camera and HUD. If current
  edits need saving, the editor offers to save them first; Cancel keeps them open.

Identical scripts are reused. If a script name already has different code, or an
object name already exists, the import is rejected with an explanation. Open as a
new project or resolve names deliberately; automatic text replacement in C++ could
break references. Original absolute positions are preserved, not converted to a
new prefab pivot. Runtime-only script state is not exported.

Project-local material atlases are supported from engine 0.8: their PNG is
embedded and validated by checksum and dimensions. A scene can use one material
atlas; incompatible atlas merges are rejected, with Open as new project available.

The built-in Forge atlas is embedded and checked against the installed engine
atlas. Team members should use matching engine materials. This does not introduce
general PNG/MTL material importing. Atlas sampling is now selected per model in
native builds, matching the editor, so importing textured assets does not texture
unrelated models. Build the destination project to run its imported gameplay.

## Contents and compatibility

Engine 0.8.2 supports IYAM libraries with up to 128 clips and 4,096 total frames,
within the existing memory budgets. Packages using more than 16 clips or 1,000
frames advertise minimum engine 0.8.2; recipients should update before importing.

- `manifest.json`: format `PS3Forge.Package`, integer version 1, minimum engine
  0.7.0, encoded scene fragment and file SHA-256 hashes.
- `assets/<id>.iyam`: referenced models with their clips/poses/material groups.
- `textures/forge-atlas.png`: shared atlas when required.
- `docs/`: available project readme and license documents, including licenses
  retained from earlier package imports.

Integrity checks detect corruption; they are not author signatures. Import reads
and validates source text but does not compile or execute it. Settings, passwords,
emulator profiles, builds and unrelated project folders are not included.

Standard projects only; Block Garden's special native source format is excluded.
Existing engine scene/asset/script budgets still apply. Package files are limited
to 100 MiB compressed, 96 MiB unpacked and 72 entries. Import rejects duplicate or
unexpected archive paths, damaged assets and incompatible package versions.

The example `outputs/FPS-Player-AR7.forgepack` contains a player and animated rifle;
`outputs/Combat-Yard.forgepack` contains the complete small combat scene.

## Editor flicker work

Scene rebuilds now prepare and initialize meshes before swapping them into the
visible scene. Resize updates avoid redundant canvas resets and rounded-size
feedback. The grid is offset slightly above the ground to reduce z-fighting.
Transform callbacks are applied only while dragging, preventing selection from
changing object positions. These address concrete editor issues; they do not
prove every possible graphics-driver or native-runtime flicker is resolved.
