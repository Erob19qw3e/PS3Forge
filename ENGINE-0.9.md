# PS3Forge 0.9.0 — Engine systems

This release adds an initial usable implementation of the seven engine systems.
Existing projects, baked IYAM1 models and earlier desktop releases are preserved.
The independent **Engine Lab 0.9** project demonstrates the new features.

## Build a character from the Inspector

1. Import a self-contained **GLB** with one skin, up to four influences per vertex,
   triangle meshes and embedded base-color PNG/JPEG images. Import runs locally,
   without Blender, SSH or a conversion server. Add the imported asset to the scene.
2. Add **Character Controller**, **Health**, **Weapon** and **Animator** using
   **Choose a component**. The controller uses sticks, X jump, R1 crouch,
   L3 sprint, Triangle first/third person and R2 fire. Square reloads/interacts.
3. Add **Camera Follow** to a separate object, set its Target to the character,
   and set First person on the controller for the initial camera. Camera Follow
   avoids static box obstacles and can hide the character in first person.
4. Select an object such as a weapon, add **Attachment**, select its character
   Target, and use **Attach to right hand** or choose another bone. Adjust
   Offset / Rotation / Scale in Attachment. The socket drives Transform.
   The parent object's scale must be uniform; cyclic references are rejected.

The right-hand preset searches common hand/wrist names. A different rig may
require choosing the bone manually. This is a socket system; automatic hand IK,
retargeting between unrelated rigs and automatic grip correction are future work.

## Skeletal animation and state graph

IYAM2 stores bind geometry, four vertex weights, inverse bind matrices, a bone
hierarchy, local TRS keys and named animation events. It replaces vertex-frame
duplication for newly imported models. Existing IYAM1 assets are still supported;
they are not silently converted or replaced. CPU skinning shares loaded model
data between instances, reserves known storage sizes and computes each bone's
normal transform once per pose. GPU/SPU skinning is not implemented.

Animator includes a visual state graph and editable states, clip selection,
transition conditions, blend durations, parameters and timed events. **Speed**,
**Moving**, **Grounded**, **Health**, **Sprint** and **Crouch** are runtime parameters;
other parameters may be set with `e.parameters["Name"]=value`. Preview parameter
defaults let you inspect transitions without a PS3 build. Skeletal blending
interpolates bone-local TRS with shortest-path quaternion interpolation.

Scripts can consume events with `forge::pollEvent(e,"Footstep")` and emit their
own with `forge::emit(e,"EventName")`. Queues are bounded to 64 pending events.
Built-in events include Shot, Hit, Reload, ReloadComplete, Damaged, Died,
TriggerExit, PathBlocked, and the names set on triggers/interactables/animations.

## Independent materials

Use **Material slots** to assign a material to each mesh primitive/group, create
materials, change color, import textures and choose **Opaque** or **Cutout**.
Texture imports accept PNG/JPEG/WebP and convert to square 128–1024 PNG files.
GLB primitive materials are assigned when adding the imported model to the scene.
Project textures and slot assignments travel inside `.forgepack` packages.
Old atlas materials remain compatible; independent materials can be combined
between projects without sharing an atlas. Existing custom-atlas restrictions
still apply when a package explicitly uses the old atlas.

The initial PS3 path uses ARGB1555 source colors expanded into RSX textures:
five bits per color channel and one-bit opacity. It supports base color and
cutout, not full glTF PBR, normal maps, metallic/roughness maps, emissive maps,
translucent blending or vertex colors. GLB alpha BLEND, morph targets, sparse
accessors, compressed required extensions, extra UV sets used for base color,
external buffers/images, multiple skins and more than four influences are
rejected with an explanation rather than silently dropped. Other unsupported
PBR channels are not imported. GLB node TRS animation accepts LINEAR, STEP and
CUBICSPLINE and is sampled at 30 fps; clips currently loop.

## NPCs, triggers and interaction

Add **Navigation Agent** and **NPC** to an actor. Configure patrol points, player
Target, perception range, attack distance, damage and attack interval. The
agent routes around static AABB obstacles with a bounded horizontal A* grid
(maximum 64×64), patrols, chases visible targets and attacks at configured range.
The native profiler HUD shows the actor's decision state; **Show / hide route
preview** displays the planned static route in the editor. **Show / hide bones**
displays the skeleton. Health can hide a dead actor. Trigger and Interactable
send configurable named events to the owner and target; scripts supply custom
reactions such as healing or checkpoint behavior.

This is basic navigation and range-based combat, not a complete navmesh,
crowd avoidance, climbing, cover-selection, animation IK or tactical AI system.
Box collision is axis-aligned. Physics, controller input, NPC logic and scripts
execute in the native game; the editor previews meshes, animation, sockets,
LOD and debug routes. Weapon is a basic controller-driven hitscan/reload component
intended for the player, not an automatic AI gun controller.

## Performance and asset changes

**Profiler** in the viewport shows editor draw calls, triangles and memory
estimates. Add a **Profiler** component to show native CPU logic/submission time,
flip wait, draws, triangles, resident model data and tracked RSX allocations.
Flip wait is not a GPU execution timer. These counters are not a physical PS3
performance guarantee or a complete system memory accounting.

**LOD** accepts 1–4 independently prepared model assets with increasing distances
and an optional maximum draw distance. LODs must retain the same skeleton names,
hierarchy and required clips. The native renderer allocates buffers for the
largest configured level and loads alternative assets on first use. Loading is
synchronous, cached and not asynchronous streaming; automatic mesh simplification
and unloading are not implemented. A frame may pause on first load.

The editor checks model/texture timestamps every three seconds, validates changed
files and reloads their preview while preserving scene edits. Save and rebuild
are required to update an existing native executable. Replacing a skeleton or
clip set may require repairing affected component references before saving.

## Projects and sharing

**Save copy…** creates an independent standard project including its assets and
textures. Browser-local draft recovery preserves unsaved scene/script edits.
Every changed save keeps the preceding project JSON in the project's `.history`
folder. Concurrent revision checks reject stale editor saves; choose Save copy
or reopen instead of replacing another editor's work. Historical JSON snapshots
do not duplicate large model files and are not a full external backup.

Right-click export includes component target objects recursively, LOD models,
scripts, material textures and license/readme files. Imports validate hashes,
remap object/model/material/texture IDs and preserve component links. A package
can include more objects than explicitly selected because its targets are
dependencies. Existing object-name/script conflicts still require a new project.

Runtime script exceptions report the object and its attached script name(s) in
the native HUD. Asset load/reload failures include the asset name or path. Hard
crashes, invalid pointers and arbitrary native C++ behavior cannot be recovered
by an exception handler.

## Budgets and verification

Initial limits: 128 objects, 64,000 animated instance vertices (largest LOD),
32 model assets, 80 MiB model files per project, 64 MiB per IYAM model,
128 bones, 4,096 total key frames, 128 clips, 8 independent project textures,
32 materials and 32 MiB tracked texture variants. These are guardrails, not a
promise that every combination reaches a chosen frame rate on PS3.

Acceptance evidence is recorded under `diagnostics/engine09` and
`diagnostics/engine-*.log`. Tests distinguish Python validation/package tests,
host C++ simulation, JS/native skeletal sampling parity, actual Qt/WebGL editor
checks, and compilation/package verification using the local PS3 SDK.
Physical-console testing remains necessary before shipping a game.


## 0.9.1 texture correction

Independent materials repeat their original UVs beyond 0�1 in both editor and native renderer. Atlas materials still clamp to avoid neighboring tiles. This fixes stretched texture edges on the recovered detailed Delta body without modifying its original UVs. MW3 Delta Skeletal Detail is a separate original-asset review project; its report records mesh, source weights, 92 clips and verification.


## 0.9.2 native World Sectors prototype

Optional sector resources preserve shared original geometry and placement data while loading a bounded nearby set. See WORLD-SECTORS.md for budgets, synchronous cache behavior, packaging and remaining preview/material/terrain limitations. Prior scene/asset behavior and desktop releases are preserved.
