# Mod Runtime Contract

This derived reference records the mod runtime contract from `design/engine.md`. Mod packages may publish rich metadata, but runtime inputs are `mods.lock` identity/enablement records plus strict typed `world.toml [mods.<plugin_id>]` parameter blocks that pass schema and security validation.

## Enabled Plugin Set

The `vanilla_mods` engine feature includes eight available plugins: `combat-core`, `empire-upkeep`, `fog-of-war`, `pve-spawning`, `resource-decay`, `special-attacks`, `depot-storage`, and `vanilla-boss`. The Vanilla default `mods.lock` enables seven and leaves optional `resource-decay` disabled. The engine binary must be compiled with the matching feature for every enabled plugin; a lock entry for a plugin absent from the binary is a startup-time security rejection.

`mods.lock` is the deployment input for the enabled plugin set. Each enabled entry must include `plugin_id`, `enabled`, `version`, `source`, `package_hash`, and `signature_hash` (or an explicitly trusted local-build signature class). The engine validates dependency ordering, rejects unknown plugin names/disabled dependencies, verifies the package and detached signature against these hashes, and records the accepted lock hash in the tick manifest. `mods.lock` does not carry gameplay parameter values.

## Config Injection and Precedence

Configuration precedence is:

1. Explicit engine-owned `world.toml` fields win for engine-owned `WorldConfig` paths.
2. Strict typed `world.toml [mods.<plugin_id>]` values provide plugin constructor arguments and plugin-owned world parameters.
3. Design-profile defaults fill unset plugin parameters for the selected profile (`Tutorial`, `World`, `Arena`, or a named design profile published by the plugin schema).
4. If neither explicit world config nor an accepted design-profile default supplies a required value, startup fails closed; unversioned Rust defaults are not a configuration source.

The runtime accepts these typed config groups from `world.toml [mods.<plugin_id>]` after confirming that the plugin is enabled in `mods.lock`:

- **combat-core**: `damage_multiplier` in basis points, plus positive-u32 `repair_hp_per_work_part` and `repair_energy_per_hp`; resolved defaults/overrides enter `world_config_hash`.
- **empire-upkeep**: `base_upkeep`, `room_soft_cap`, controller passive income/base resource, repair basis points, recycle refund basis points, and Tutorial full-refund ticks.
- **fog-of-war**: `fog_of_war` and `player_view`, unless an engine-owned `[visibility]` field explicitly overrides it.
- **pve-spawning**: `spawn_interval`, `max_npcs_per_room`, typed NPC body parts, and typed resource drop table.
- **resource-decay**: global `decay_rate_ppm` plus per-resource ppm overrides.
- **special-attacks**: `special_attacks_enabled`, full/Tutorial/Novice allowlists, fixed-bp damage multiplier, and strict typed schemas for Hack/Drain/Overload/Debilitate/Disrupt/Fortify/Leech/Fabricate. Each schema publishes required body parts, cost/cooldown/range/channel/effect values; Overload additionally publishes target-player-global cooldown/fuel pressure/min-budget bps，Fabricate publishes ordered non-empty `allowed_output_structures` and canonical default. All resolved action values enter `world_config_hash`.
- **depot-storage**: depot capacity/hits plus repair range and per-tick repair capacity.
- **vanilla-boss**: arena/world boss enablement, spawn interval, and published boss templates.

`mod.toml` remains package metadata. Runtime configuration is not read from `world.toml [[mods]]`, arbitrary `[mods.config]` tables, or free-form plugin maps. Server operators change the enabled version/source/package/signature hashes through checked `mods.lock` entries, and change gameplay parameters only through strict typed `world.toml [mods.<plugin_id>]` tables. Startup computes a resolved config hash per plugin from `(plugin_id, version, source, package_hash, signature_hash, design_profile, typed_params_after_defaults)` and includes the aggregate resolved config hash in `world_config_hash`.

## Security Rejection Rules

The engine must reject the runtime before ticking when any of these checks fails:

- `mods.lock` names an unknown plugin.
- An enabled plugin is missing from the compiled binary feature set.
- An enabled plugin depends on a disabled plugin.
- A lock entry omits version/source/hash/signature, or the signature/hash check fails.
- `world.toml [mods.<plugin_id>]` exists for a plugin not enabled by `mods.lock`.
- A typed config key is unknown for that plugin.
- A typed config value has the wrong type, omits a required field with no design-profile default, or fails plugin validation.
- A special-attack allowlist names an action outside the vanilla special attack set.

## Special Attack Mode Allowlists

`special-attacks` publishes three related controls:

| Field | Semantics |
|-------|-----------|
| `special_attacks_enabled` | Master switch for vanilla special action registration. |
| `tutorial_enabled` | Allowlist used by tutorial-mode world rules. |
| `novice_enabled` | Allowlist used by novice/soft-launch world rules. |

When the master switch is disabled, no special actions are registered. When enabled, mode-specific registries use the tutorial or novice allowlist; unrestricted world modes use the full canonical special attack set.
