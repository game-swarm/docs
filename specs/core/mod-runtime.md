# Mod Runtime Contract

This reference records the authoritative mod runtime contract for the engine. Mod packages may publish rich metadata, but only typed `mods.lock` entries that pass schema and security validation affect runtime behavior.

## Enabled Plugin Set

The `vanilla_mods` engine feature includes eight plugins: `combat-core`, `empire-upkeep`, `fog-of-war`, `pve-spawning`, `resource-decay`, `special-attacks`, `depot-storage`, and `vanilla-boss`. The checked-in `mods.lock` enables all eight. The engine binary must be compiled with the matching feature for every enabled plugin; a lock entry for a plugin absent from the binary is a startup-time security rejection.

`mods.lock` is the authoritative deployment input for built-in mod configuration. The engine decodes each enabled plugin's `config` object into a typed runtime config, validates keys and value types, checks dependency ordering, rejects unknown plugin names, rejects disabled dependencies, and then applies accepted values to `WorldConfig` or plugin constructors according to the precedence rules below.

## Config Injection and Precedence

Configuration precedence is:

1. Explicit `world.toml` fields win for engine-owned `WorldConfig` paths.
2. Typed `mods.lock` values fill unset engine-owned paths and plugin constructor arguments.
3. Rust defaults apply only when neither explicit world config nor an accepted lock value exists.

The runtime accepts these typed config groups from `mods.lock`:

- **combat-core**: `damage_multiplier` in basis points.
- **empire-upkeep**: `base_upkeep`, `room_soft_cap`, controller passive income/base resource, repair basis points, recycle refund basis points, and Tutorial full-refund ticks.
- **fog-of-war**: `fog_of_war` and `player_view`, unless explicitly set in `world.toml`.
- **pve-spawning**: `spawn_interval`, `max_npcs_per_room`, typed NPC body parts, and typed resource drop table.
- **resource-decay**: global `decay_rate_ppm` plus per-resource ppm overrides.
- **special-attacks**: `special_attacks_enabled`, full/Tutorial/Novice allowlists, and fixed-bp damage multiplier.
- **depot-storage**: depot capacity/hits plus repair range and per-tick repair capacity.
- **vanilla-boss**: arena/world boss enablement, spawn interval, and published boss templates.

`mod.toml` remains package metadata. Runtime configuration is not read from `world.toml [[mods]]` or arbitrary `[mods.config]` tables; server operators change effective built-in mod settings through signed/checked mod artifacts and `mods.lock` entries that match the engine's typed schema.

## Security Rejection Rules

The engine must reject the runtime before ticking when any of these checks fails:

- `mods.lock` names an unknown plugin.
- An enabled plugin is missing from the compiled binary feature set.
- An enabled plugin depends on a disabled plugin.
- A config key is unknown for that plugin.
- A config value has the wrong type or fails plugin validation.
- A special-attack allowlist names an action outside the vanilla special attack set.

## Special Attack Mode Allowlists

`special-attacks` publishes three related controls:

| Field | Semantics |
|-------|-----------|
| `special_attacks_enabled` | Master switch for vanilla special action registration. |
| `tutorial_enabled` | Allowlist used by tutorial-mode world rules. |
| `novice_enabled` | Allowlist used by novice/soft-launch world rules. |

When the master switch is disabled, no special actions are registered. When enabled, mode-specific registries use the tutorial or novice allowlist; unrestricted world modes use the full canonical special attack set.
