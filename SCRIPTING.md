# Simple scripting — PS3Forge 0.6

Choose a template in **C++ Script → New script**, give it a name, then attach it
to an object with **Add component → C++ Script**. Build to run gameplay on PS3
or RPCS3. The editor previews objects and animation; it does not execute C++.

```cpp
#include "Forge.h"

FORGE_SCRIPT(MyItem) {
    self.rotate(0, self.number("Spin speed", 60), 0);
}
```

`self` is the object running this script. Move and rotation functions use units
or degrees **per second**; they handle elapsed time internally. Do not multiply
their arguments by deltaTime again. Existing full C++ callbacks still work.

## Variables without editing the code

`self.number("Speed", 3)` defines a numeric setting. `self.flag("Enabled", true)`
defines a checkbox. Literal names and constant defaults appear in that object's
Script card in the Inspector. Each object and script has independent values.
Change the value, save and rebuild. **Reset variables** restores the code defaults.
Labels start with an English letter and may contain letters, numbers, spaces,
underscores or hyphens (40 characters maximum). Up to 32 fields per script.
Declarations in comments are ignored; calculated defaults and aliases of `self`
are valid C++ but are not discovered by the Inspector.

Use `float speed = self.number("Speed", 3);` for a normal local C++ variable.
Locals are recreated each update. For a value that must survive updates, use:

```cpp
float& count = self.state("Collected count", 0);
```

State is private to this object/script and resets on scene restart. It is not a
save file and is not shared across objects. `number()` reads configuration;
`state()` stores changing gameplay data. Use fixed names, not a new name per frame.

## Common functions

| Function | Behavior |
| --- | --- |
| `self.move(x, y, z)` | Move in world coordinates, units per second |
| `self.rotate(x, y, z)` | Rotate in degrees per second |
| `self.moveByInput(speed)` | Left-stick movement on the world X/Z plane |
| `self.jump(5)` | Jump when grounded; requires a body with gravity |
| `self.play("Idle")` | Select an existing animation clip |
| `self.find("Player")` | Find an object in the active scene |
| `target.exists()` | Check that the target was found |
| `self.distanceTo(target)` | Three-dimensional centre-to-centre distance |
| `self.lookAt(target)` | Face a target horizontally |
| `self.moveToward(target, speed, stopDistance)` | Direct horizontal approach |
| `target.damage(20)` / `target.heal(25)` | Change shared object health |
| `target.health()` / `target.dead()` | Read health / check zero health |
| `self.setHealth(50, 100)` | Set current and maximum health |
| `self.hide()` / `self.show()` | Change visibility |
| `self.collectBy(target, radius)` | Hide a nearby visible item, return true once |
| `self.firstFrame()` | True during the object's initial update |
| `self.every("Fire", 0.5)` | True at timed intervals; call once per update |
| `self.hud("Health", self.health())` | Display a simple label and value |
| `self.restartScene()` | Reset the active scene on the next simulation step |

Missing targets are safe: modifying one does nothing, `exists()` is false and
distanceTo returns a very large distance. Check exists() when choosing behavior.
Health is an engine value shared by scripts on that object, defaults to 100,
and resets with the scene. Existing games with their own health variables must
explicitly adopt this API; their custom counters are not linked automatically.

## Controller input

```cpp
if (self.pressed(forge::Button::Jump)) self.jump(5);
if (self.held(forge::Button::Fire)) { /* firing behavior */ }
```

Buttons: Jump (Cross), Reload (Square), Restart (Triangle), Fire (R2/R1),
Aim (L2/L1), Sprint (L3). pressed() fires on a press; held() checks the current
state where the native API supplies a held value. Reload/Restart are press-only
in the underlying API. Use deltaTime for custom calculations not covered by helpers.

## Short health item

```cpp
FORGE_SCRIPT(HealthPickup) {
    auto player = self.find("Player");
    self.rotate(0, self.number("Spin speed", 60), 0);
    if (self.collectBy(player, self.number("Pickup radius", 1.5)))
        player.heal(self.number("Heal amount", 25));
}
```

The **Simple Scripts** example has two items using this same script, with
different healing amounts set in the Inspector. Blue cube: player; green cubes:
health items; yellow cube: rotating item. Start health is 50. Triangle resets.

These helpers do not add pathfinding, swept collisions, inventory, sound or
automatic death animations. moveToward follows a straight line; move/moveByInput
rely on the object's existing collider/body setup. Hiding affects rendering;
other scripts and static colliders remain active. Objects cannot be spawned or
deleted with this API, so handles remain valid for the fixed scene lifetime.
