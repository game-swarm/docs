# Swarm Game Engine — Updated Implementation Plan (AI + MCP + Docs + Debug)

## Planner Output — Full Plan for Review

This document is the Planner's output from the Ralplan Round 1 consensus process. It is being reviewed by Architect, Security Reviewer, and Game Designer agents in parallel.

---

## 1. Summary

This plan extends the existing Swarm architecture to make AI players first-class citizens alongside human WASM-based players, with MCP (Model Context Protocol) as the native AI integration layer. The engine gains a built-in MCP server (rmcp crate) exposing game state, action tools, and API documentation as MCP resources — enabling AI agents to discover and play the game without human assistance.

Core architectural changes:
- SandboxExecutor trait becomes PlayerExecutor with WasmSandboxExecutor + McpPlayerExecutor
- MCP server is a first-class engine subsystem, not a bolt-on
- Data model gains PlayerKind { Human, Ai { model, provider } }
- Debug/trace primitives from Phase 1, not Phase 5
- Schema registry for auto-generated docs feeding both human docs and MCP resources

## 2. 7-Phase Implementation Plan

### Phase 1: Foundation Hardening + MCP Scaffold
- 1.1 Add PlayerKind (Human/Ai) and AiSession ECS components
- 1.2 Add rmcp dependency, scaffold MCP server module with swarm_ping tool, wire into main.rs as Tokio task
- 1.3 Extend GameConfig with MCP settings (mcp_enabled, mcp_bind_addr, max_ai_players)
- 1.4 Define debug/trace data model: TickTrace, EntityEvent, TraceCollector with ring buffer + ClickHouse schema
- 1.5 Add documentation generation pipeline: SchemaRegistry, exposed via cargo run -- schema
- 1.6 Rename SandboxExecutor → PlayerExecutor, add player_kind() method, add McpPlayerExecutor stub

### Phase 2: MCP Server — Game State & Tools (AI player MVP)
- 2.1 Implement MCP tool swarm_get_snapshot — returns visible world state per player
- 2.2 Implement all game action MCP tools (11 tools mirroring Command enum)
- 2.3 Implement MCP resources for API docs: swarm://schema/*, swarm://docs/*
- 2.4 Implement MCP authentication and per-player isolation
- 2.5 Implement McpPlayerExecutor tick integration
- 2.6 AI player lifecycle management via gateway REST

### Phase 3: Multi-Player World + Persistence
- 3.1 Tick scheduler with mixed player types (WASM + MCP executors in parallel)
- 3.2 Command conflict resolution — deterministic ordering
- 3.3 FoundationDB persistence
- 3.4 Dragonfly hot cache
- 3.5 ClickHouse metrics pipeline
- 3.6 WebSocket real-time delta push
- 3.7 Room boundaries + multi-room

### Phase 4: Debugging Infrastructure
- 4.1 Per-tick logging with MCP-accessible replay
- 4.2 State inspection tools (swarm_inspect_entity, swarm_inspect_room)
- 4.3 WASM execution traces
- 4.4 Performance profiling per player
- 4.5 Visual debugging overlay (frontend)

### Phase 5: Client + Documentation
- 5.1 Web client — Monaco Editor + PixiJS
- 5.2 Auto-generated API reference site
- 5.3 TypeDoc + Rustdoc CI build
- 5.4 MCP-accessible documentation updates
- 5.5 OAuth2 login + player profiles

### Phase 6: Gameplay Systems
- 6.1 Controller + room claiming
- 6.2 Combat system
- 6.3 Market system
- 6.4 Leaderboards + seasons

### Phase 7: Production Hardening + AI Tournament Mode
- 7.1 AI tournament orchestration
- 7.2 Performance optimization — sharding + ECS parallelization
- 7.3 Anti-cheat system (including AI-specific abuse detection)
- 7.4 MCP server production hardening
- 7.5 CI/CD + automated testing

## 3. Key Risks Identified
- MCP protocol churn → pin rmcp, abstract via adapter
- AI player latency → async push-based snapshot delivery, command queue
- MCP tool explosion → proc macro code generation
- AI vs human fairness → same command limits, identical validation
- Prompt injection via game state → sanitize all player-generated strings
- Schema/documentation drift → CI enforcement
- Debug overhead → sampling

## 4. Open Questions
- Q1: Engine as MCP server, client, or both? → Hybrid (bidirectional)
- Q2: AI players need WASM? → No, MCP only
- Q3: AI sessions persist? → Yes, in FoundationDB
- Q4: MCP embedded or sidecar? → Embedded for MVP, separate later
- Q5: stdio or HTTP/SSE? → HTTP/SSE only (AI players are remote)
- Q6: Schema in engine or separate crate? → Separate swarm-schema crate
- Q7: AI player quality metrics? → Metrics-based evaluation

## 5. Codebase Reference
- Engine: /data/swarm/engine/ — Phase 1 code already exists (ECS components, systems, tick outline, game API types)
- Design doc: /data/swarm/docs/DESIGN.md — original architecture
- SDKs: /data/swarm/sdk-ts/, /data/swarm/sdk-rust/
- Gateway: /data/swarm/gateway/
- Frontend: /data/swarm/frontend/
- Sandbox: /data/swarm/sandbox/
