# Step 2 Plan: Establish Domain Contracts

## Goal

Define the first stable domain model and explicit contracts so the next implementation steps can build on clear types instead of ad hoc dictionaries, widget state, or concrete infrastructure classes.

## Scope

This step includes only domain contracts and the minimum supporting tests needed to lock them in:

- core domain entities
- queue and playback state value types
- auth session record
- repository and service protocols
- shared project-specific domain errors if needed
- contract-oriented tests for the new interfaces and records

This step does not include:

- real Yandex Music API integration
- real playback backend implementation
- playback orchestration logic
- persistence implementation
- UI wiring for real player state

## Target Directory Structure

Keep the existing layered structure and expand `src/app/domain` explicitly.

Recommended substructure:

```text
src/app/domain/
  __init__.py
  auth.py
  playback.py
  playlist.py
  track.py
  protocols.py
  errors.py
```

Alternative acceptable shape if it stays small and obvious:

```text
src/app/domain/
  entities.py
  protocols.py
  errors.py
```

Tests should start using the project test buckets already created:

```text
tests/
  contract/
  integration/
  smoke/
```

## Deliverables

The output of Step 2 should include:

- explicit `dataclass(frozen=True)` style domain records for the initial model
- typed enums or literals where they clarify playback state
- explicit `Protocol` or `ABC` contracts for external-facing services and repositories
- domain-level naming for queue and playback behavior
- small contract tests proving the records and interfaces are usable
- short documentation note about the domain model shape if useful

## Work Breakdown

## 1. Define the Core Entities

Add the first stable records required by the architecture rules:

- `Track`
- `Playlist`
- `QueueItem`
- `PlaybackState`
- `AuthSession`

Rules:

- prefer frozen dataclasses
- keep fields typed and explicit
- avoid speculative fields that are not justified yet
- do not leak HTTP or storage formats into the entity definitions

Output:

- small stable records that can be used across application and tests

## 2. Define `Track`

Tasks:

- include a stable track identifier
- include the display fields needed soonest by playback and search flows
- include `stream_ref` as an internal stream identifier, not a direct URL requirement
- model durations in a clear typed way

Suggested fields:

- `id`
- `title`
- `artists`
- `album_title`
- `duration_ms`
- `stream_ref`
- `artwork_ref`
- `available`

Rules:

- do not assume every field is always present from all future adapters
- keep optionality explicit

Output:

- one track entity suitable for playback, search, and queueing work

## 3. Define `Playlist`

Tasks:

- include a stable playlist identifier
- include display metadata
- include optional track count and artwork metadata
- avoid embedding full track payloads if not yet required

Suggested fields:

- `id`
- `title`
- `owner_name`
- `description`
- `track_count`
- `artwork_ref`

Output:

- playlist metadata that can anchor later catalog flows

## 4. Define Queue and Playback State

Tasks:

- define `QueueItem`
- define `PlaybackState`
- model enough state for later playback orchestration without implementing it yet

Suggested `QueueItem` concerns:

- wrapped `Track`
- source type or source id
- original position within source

Suggested `PlaybackState` concerns:

- current status such as stopped / paused / playing / buffering
- active queue index
- current position
- duration
- volume
- shuffle
- repeat mode

Rules:

- use enums or explicit literals where state must stay bounded
- keep mutation policy outside the entities themselves

Output:

- a domain vocabulary ready for `PlaybackService`

## 5. Define `AuthSession`

Tasks:

- define the minimal auth/session record needed for persistence and startup recovery later
- model expiration and persistence-related fields without binding to a storage backend

Suggested fields:

- `user_id`
- `token`
- `expires_at`
- `display_name`

Rules:

- do not embed storage paths or JSON-specific concerns
- keep the record usable by both in-memory tests and future repos

Output:

- a stable session record for auth lifecycle work

## 6. Define Service and Repository Contracts

Add explicit contracts for:

- `MusicService`
- `PlaybackEngine`
- `SettingsRepo`
- `LibraryCacheRepo`
- `AuthRepo`
- `Clock`
- `Logger`

Rules:

- use `Protocol` unless an `ABC` is clearly more useful
- keep method sets focused on real near-term usage
- application code should depend on these contracts, not infrastructure classes
- avoid adding methods “just in case”

Output:

- one clear contract surface for later implementations and fakes

## 7. Shape the Playback and Music Contracts Carefully

Tasks:

- keep `MusicService` focused on catalog/auth/stream resolution boundaries
- keep `PlaybackEngine` focused on actual playback control and event/state access
- avoid mixing queue semantics into the engine

`MusicService` should be able to grow toward:

- auth/session inspection
- search
- liked tracks
- playlist or album loading
- stream resolution

`PlaybackEngine` should be able to grow toward:

- load/play
- pause
- stop
- seek
- volume
- current playback state callbacks or polling

Output:

- contracts that separate music-catalog concerns from local playback concerns

## 8. Add Domain Errors Where They Clarify Boundaries

Tasks:

- add a small set of domain-facing error types only if they improve clarity now
- prefer a few named exceptions over a large hierarchy

Good candidates:

- `AuthError`
- `NetworkError`
- `TrackUnavailableError`
- `StreamResolveError`
- `PlaybackBackendError`
- `StorageError`

Rules:

- do not mirror every possible low-level failure yet
- keep infrastructure-specific details out of domain exceptions

Output:

- a small vocabulary for recoverable failure categories

## 9. Add Contract-Focused Tests

Tasks:

- add tests that validate the records are usable and stable
- add tests that future fakes can target
- avoid wasting time on trivial constructor-only assertions

Useful coverage:

- frozen entity behavior where it matters
- enum or literal boundaries for playback state
- basic fake implementations satisfying the protocols
- serialization-adjacent assumptions only if they are part of the contract

Rules:

- prefer readable in-memory fakes over mocks
- focus on behavior and typing expectations, not cosmetic field access

Output:

- domain contracts protected against accidental churn

## 10. Keep the Domain Layer Clean

Tasks:

- ensure domain modules do not import Qt
- ensure domain modules do not import HTTP clients or storage adapters
- avoid any dependency on presentation or infrastructure

Rules:

- one-way dependency direction only
- no startup code in the domain layer
- no widget-facing formatting concerns in entities

Output:

- a domain layer that can support later application services cleanly

## 11. Document the Domain Surface

Tasks:

- add a short note describing the purpose of the core entities and contracts
- explain where future implementations should live
- keep the note short and operational

Recommended location:

- `docs/domain.md`

Output:

- lower ambiguity for future steps and LLM-assisted edits

## Suggested Implementation Order

1. Decide the domain module layout.
2. Add the entity records.
3. Add playback-related enums and queue state types.
4. Add repository and service protocols.
5. Add minimal domain errors if needed.
6. Add contract-focused tests and fakes.
7. Add short documentation.

## Acceptance Criteria

Step 2 is complete when all of the following are true:

- the project defines `Track`, `Playlist`, `QueueItem`, `PlaybackState`, and `AuthSession`
- the required interfaces exist for services, repos, clock, and logger
- application code can depend on contracts instead of concrete infrastructure
- no Qt, HTTP, or storage details leak into the domain layer
- at least some contract-oriented tests exist and pass
- the contracts are small enough to be readable and stable

## Risks in This Step

- overdesigning the domain before the playback core exists
- stuffing application orchestration concerns into entities
- putting infrastructure assumptions into protocol method signatures
- creating too many abstractions before the first concrete adapters exist

## Guardrails

- keep records small and explicit
- prefer one obvious contract over multiple overlapping abstractions
- model near-term reality, not a hypothetical final platform
- keep queue semantics in application services, not in the playback engine contract
- make fakes easy to write for tests
