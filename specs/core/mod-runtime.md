# Current Mod Runtime

This reference records the current engine mod wiring. It is not a statement of the target gameplay design.

## Enabled Plugin Set

The `vanilla_mods` engine feature includes eight plugins: `combat-core`, `empire-upkeep`, `fog-of-war`, `pve-spawning`, `resource-decay`, `special-attacks`, `depot-storage`, and `vanilla-boss`. The checked-in `mods.lock` enables all eight. The engine feature-gates construction of these plugins at build time.

`mods.lock` currently registers plugin metadata in the engine plugin registry. It does not demonstrate application of each `PluginEntry.config` object to the feature-gated plugin constructors. Treat lock-file configuration as registry metadata unless the runtime application path is added and verified.

## vanilla-boss Defaults

The `vanilla-boss` manifest and checked-in lock configuration set `arena_bosses_enabled = true` and `world_bosses_enabled = false`. The Rust `WorldConfig::default()` and `VanillaBossPlugin::default()` instead enable world bosses. Because the lock config is not applied to constructors by the current engine path, runtime behavior follows the Rust defaults rather than the manifest/lock value.

Do not describe World boss disablement as an effective runtime default until the lock configuration is wired into plugin construction.
