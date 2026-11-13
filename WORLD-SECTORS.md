# World Sectors — PS3Forge 0.9.6

Current reference: project f17e00612026, P3FNMAP03, Spawn and Door Fix. Previous game/editor copies are retained.

FWS4 extends FWS3 without changing its 64-byte header or geometry tables. Texture chunk FWT1 version2 allows up to1024 diffuse images (64/128/256 square), with a combined16MiB GPU texture cap. After pixel records: u32 texture-set count, three u32 texture IDs per set (zero means absent), u32 collision-model count, then {baseModelID,triangleCount,9float32 per triangle}. All fields are big-endian. Collider vertices share each family's normalized basis and instance transform. Triangle count is capped500000 and all offsets, floats, IDs and EOF are validated. The instance fourth word is texture-set index plus one. Material group tag uses lower24bits for base texture ID and upper8bits for source layer slot plus one. Slots0–2 select the actor's three layers; additional baked source material slots retain their explicit diffuse. FWS1/2/3 remain supported.

The reference keeps721 source diffuse images,707 actor texture sets and340 source building-layer mesh variants. Source normals are preserved. Diffuse resolution is reduced (generally64 square, vegetation256); original normal maps, wind, AO, transparency graphs and full lighting are not reproduced. Ten prior conservative flat-background cutouts remain derived masks, not recovered original alpha.

FCL1 source collision supplies48108 local triangles for1354 used families, with39660 active collidable instances. Capsule/triangle contact supports walls, openings, raised surfaces and sliding; camera and bullet rays use source collision. These colliders are separate from render LOD choice. Legacy worlds retain their AABB path. Source blocking-volumes/island-hull data is catalogued but not yet integrated. No full original physics implementation is claimed.

Original world_doors.txt supplies527 door leaves with matched parent transforms and local relative translations. Source FUN_820f33e0 multiplies the parent transform by local rotation and relative translation. An earlier project incorrectly interpreted that translation as a pivot and omitted it at closure; the current resource positions the leaf at parent*relativeLocation and rotates around the leaf origin. A source-based closed/open comparison covers all527 doors. Door animation is project code (90degrees at300degrees/second), not a recovered animation curve. worldTransform callbacks update mesh bounds and triangle collision; dynamic instances remain queryable across cells. Session restart restores closed poses.

Current selection uses radius400m, existing35/120m LOD thresholds,160000 instance-vertex budget,160 model variants,1100 group draws and16MiB mesh cache. FWS4 validator maxima are192000 world vertices,256000 combined scene/world vertices,160 world model definitions,192 combined definitions and1280 world draws. Legacy limits are unchanged. These are software budgets rather than fixed RSX hardware limits; actual per-mesh indices remain16bit and per-mesh vertices stay bounded. The previously restrictive model-count cap omitted source scenery. At the Spawn Island anchor, all610 eligible source instances within400m are now selected (139059 world instance vertices). This is not a claim that every object on the whole island is simultaneously resident. Source HLOD clusters and alternate-shadow duplicates remain excluded.

Verification distinguishes host/source checks, SDK compilation, native user feedback and physical console testing. Source pose probes independently check the corrected component translation rather than merely comparing the new exporter with itself. User confirmed textures/collision, extended view and the corrected door in RPCS3. No physical PS3 test or FPS guarantee. Full-project ZIP preserves the two scenes; the current fragment forgepack importer merges scenes and must not be used for this menu game.

## Historical implementation notes (0.9.2/0.9.3)

### Original 0.9.3 notes

Version 0.9.3 adds backward-compatible FWS2 resources with original authored vertex normals and distance-selected original mesh LODs. A model table's final u32 is its finer variant index plus one (zero ends the chain); chains must be acyclic and at most eight entries. The final header words are cellSize/nearDistance/midDistance float32 and reserved u32 zero. FWS1 remains readable with its original reserved words and no linked variants. Projects declare `worldSectors.format: 2`; portable packages require engine 0.9.3 for that resource.

FWS3 additionally embeds original diffuse textures: the final header u32 is the texture chunk offset. Geometry ends exactly there. The chunk is BE `magic=FWT1,version=1,count,totalBytes`, then `width,pixelBytes,ARGB8 pixels` per texture. Width is 64/128/256; count <=64 and total GPU pixels <=16 MiB. Material-group final words are texture indices plus one, zero retaining the average-color path. The Textured Trees project uses 12 original diffuse images reduced to 256 square (3 MiB GPU), mapped to 114 material groups across 25 vegetation families. Existing shader alpha clipping and repeating source UVs are used; normal maps, original wind and advanced foliage shaders remain absent. Binding a world texture explicitly invalidates ordinary material/atlas state. FWS1/2 retain zero texture count. Textures are held resident; geometric meshes continue to stream.

After user feedback that the LOD-only version still looked strange, the Textured Trees copy increases requested near/middle distances to 35/120 m. The same budgets still apply: this can reduce the visible instance count in dense areas. The update restores bark/leaf diffuse mapping rather than treating a shared texture's average color as both bark and leaves. This is not a complete scenery material port or a claim of visually verified success.

The Detailed Scenery project keeps 1481 original mesh families and 3237 source variants. Full detail is requested within 20 m of the instance bounds, intermediate detail within 60 m, and coarse detail farther away. Transitions use 10% hysteresis and the existing budgets; if a desired variant does not fit, selection tries its coarser variants before omitting an instance. GPU caches and draw calls use the selected variant, and all variants share the same instance transform/normalization scale. Source normals replace geometric smoothing; material colors are alpha-weighted source diffuse averages consistent across LODs. Scenery texture/alpha/shader streaming remains unimplemented. Single-LOD source models cannot acquire new detail.

The new project and desktop-dist-0.9.3 are separate from previous projects/releases. Profiler overlay starts disabled in the new project and can be enabled on Player in the Inspector. The software comparison image demonstrates exported source geometry only; it is not an RPCS3 screenshot. 0.9.3 verification includes 69 Python tests, all 3237 mesh payloads, LOD identity/hysteresis/fallback, 1875 bounded selector/cache traversals, 193134 source placement/normal probes and 14 gameplay scenarios. SDK compilation and native visual review are reported separately with each delivery.

Optional `worldSectors` project metadata describes one SHA-256 checked `world/world.fws` resource and an anchor entity. Ordinary projects keep the previous path. The source-backed 0.9.2 build and the separate desktop-dist-0.9.2 distribution support this resource; older desktop releases are preserved and do not support its package entry.

FWS1 keeps shared static mesh geometry and every original instance transform. The metadata/cell index is resident; mesh blocks are read synchronously on demand. Cache entries not used by a changed selection are released after an RSX completion fence. Static geometry buffers are shared by instances. No new renderer or SDK is introduced: drawing uses the existing Forge material shader, draw helper and frame fence infrastructure.

Selection is near the anchor, deterministic, and bounded by instance vertices, unique resident models, draw calls and combined CPU/GPU cache estimates. Normal scene vertices plus world instance vertices stay below 64000; normal model definitions plus cached world definitions stay below 32. Pack size plus normal assets stays below 80 MiB. If an area exceeds its budgets, some instances are omitted until a nearer selection fits; indexed does not mean every object is simultaneously drawn. Resource loads can pause a frame; asynchronous I/O is not implemented.

This first world path uses original mesh geometry/UVs and per-material average diffuse colors. It does not stream the original scenery textures or reproduce original shaders. Grass cutouts and other source material effects remain approximate. Collision uses nearby conservative AABBs for selected solid categories, not source triangle collision. Gameplay ray/camera checks explicitly consume the world boxes in the new Fortnite project. Height terrain is still the preceding downsampled full-island mesh with a fixed detailed spawn inset.

The Qt editor preserves/imports/exports the resource and builds it, but does not preview the streamed native scenery or provide an Inspector card for its settings yet. Use the compiled game to review scenery. The earlier Full Island Survey project remains available as an editor-visible static reference. Source/desktop changes do not overwrite the user's Blender file or existing game projects.

The portable package includes the resource and remaps its anchor when opened as a new project. Importing a streamed world into an existing project is rejected to prevent resource/anchor conflicts. Partial exports include the world only if its anchor is selected.

Verification distinguishes parser/package tests, host selector and physics tests, real PS3 SDK compilation and native/physical console review. No physical PS3 performance guarantee or complete RAM accounting is implied by the counters.


## Runtime world objects (0.9.7)

Optional Forge callbacks worldVisible(instance,bool), worldModel(instance,model), and
worldRaycastIgnoring(origin,direction,limit,ignoredInstance) support collectible props.
Model indices refer to the current validated FWS model table. Both mutation functions
reject out-of-range indices and disabled source records. They do not enable archived
HLOD/shadow records. A mesh change recomputes bounds using its source geometry and
collision payload; hidden objects leave render selection and collision/ray queries.
The renderer invalidates selection immediately on visibility/model changes, even if
the player has not moved. Callbacks are null for projects without a streamed world
and are cleared by initialize(). The on-disk FWS1-4 formats and budgets are unchanged.
Hidden-instance state belongs to the session and is not written back to the resource.
