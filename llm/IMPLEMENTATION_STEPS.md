# Implementation Steps

This file defines the preferred implementation order for the project. Follow it unless a later decision explicitly changes priorities.

## Step 1: Bootstrap the Skeleton

Status: done

Create the minimal project shape:

- `src/app/bootstrap`
- `src/app/domain`
- `src/app/application`
- `src/app/infrastructure`
- `src/app/presentation`
- `tests/integration`
- `tests/contract`
- `tests/smoke`
- `tools`
- `scripts`
- `docs`

Implement:

- application entry point
- composition root/container
- startup config loading
- basic logging
- main window placeholder
- smoke run script
- basic lint/test CI skeleton

Result:

- the app launches locally
- the main window opens
- tests can start running against the structure

## Step 2: Establish Domain Contracts

Status: done

Define stable entities and protocols before feature work expands.

Add:

- `Track`
- `Playlist`
- `QueueItem`
- `PlaybackState`
- `AuthSession`

Add interfaces:

- `MusicService`
- `PlaybackEngine`
- `SettingsRepo`
- `LibraryCacheRepo`
- `AuthRepo`
- `Clock`
- `Logger`

Result:

- feature work uses explicit contracts
- tests can use fakes without coupling to infrastructure

## Step 3: Build the Playback Core Without Yandex

Status: done

Prove that the player architecture works before API integration.

Implement:

- `PlaybackEngine` interface and fake implementation
- `MpvPlaybackEngine`
- `mpv_loader.py`
- `PlaybackService`
- queue model and queue operations
- play/pause/next/previous/seek/volume flows
- basic playback state propagation into the UI

Use a local test file or test stream.

Result:

- the app can load and play audio
- queue transitions work
- playback state appears in the UI

## Step 4: Add Playback-Focused Tests

Status: done

Before expanding product scope, lock down playback behavior.

Add tests for:

- play single track
- replace queue and play from index
- next/previous edge behavior
- repeat-one and repeat-all
- shuffle semantics
- resolve-stream failure handling
- playback backend error handling
- seek and volume persistence

Rules:

- use fakes, not fragile mocks
- verify resulting state and observable side effects

## Step 5: Add Auth and Yandex Stream Resolution

Status: done

Integrate Yandex Music in a controlled way.

Implement:

- `YandexMusicService`
- auth/session loading and persistence
- session recovery on startup
- single-track resolve to playable stream
- play track by id

Result:

- a real Yandex track can be played
- auth and unavailable-track errors are handled predictably

## Step 6: Add Search and Library Basics

Status: done

Ship the first useful user workflow.

Implement:

- search service and UI
- search results mapping
- double-click to play
- liked tracks flow
- “My Tracks” or equivalent liked-tracks view
- recent searches
- artwork and metadata cache

Result:

- the user can search, play, and like tracks

## Step 7: Add Playlist and Album Flows

Status: done

Expand from single-track behavior to catalog navigation.

Implement:

- open album
- open playlist
- load playlist tracks
- replace queue
- append to queue
- source-aware queue semantics
- next/previous behavior relative to the active source
- basic shuffle and repeat

Result:

- album and playlist playback behaves like a real music player

## Step 8: Harden Persistence and Error Handling

Status: done

Prevent state sprawl before the app becomes harder to change.

Implement:

- settings repo
- auth repo
- SQLite metadata/cache layer
- artwork cache
- explicit infrastructure exception mapping
- safe user-facing error states
- startup diagnostics and actionable logs

Result:

- state is durable, inspectable, and recoverable

Current notes:

- Settings and auth/session are still JSON-backed in platform config/data directories.
- Library cache uses SQLite for recent searches, track metadata, and artwork refs.
- Playback queue state is persisted in SQLite with queue items, active index, source context, and saved position.
- Restored playback does not autoplay or resolve streams at startup; the stream is resolved on first Play.
- Saved restore seek is applied from playback backend readiness events, not refresh polling.
- My Wave/station queue persistence is bounded around the active item to avoid unbounded queue growth.
- Invalid saved playback queue state is dropped and startup continues from a clean queue.
- The Queue panel has a Clear queue action that clears both in-memory and saved playback queue state.
- If auth/settings are consolidated later, use a durable data-dir SQLite database rather than the current cache SQLite.

## Step 9: Add Packaging

Make the app runnable outside the development machine.

Implement:

- PyInstaller build scripts first
- `libmpv` bundling
- runtime library resolution for packaged builds
- macOS app bundle
- Linux bundle
- CI build pipeline structure
- release smoke checklist

Result:

- the app runs on a clean machine without manual playback backend setup

## Step 10: Improve UX After Core Stability

Do not do this before playback, auth, search, and queue behavior are stable.

Implement later:

- compact or mini mode
- improved queue UI
- keyboard shortcuts
- tray or menu integration where appropriate
- classic desktop player styling
- persistent layout and settings polish

Result:

- the app feels like a proper standalone music player

## Step 11: Stabilize

Run a dedicated stabilization pass before major expansion.

Audit:

- errors
- threading
- cache corruption recovery
- long-session behavior
- contract coverage for infrastructure
- performance in realistic usage

Result:

- the player survives long-running sessions and common recovery flows

## Ongoing Rules During Implementation

- Keep files small and explicit.
- Avoid premature plugin or skin architecture.
- Never let widgets own business logic.
- Add integration tests alongside each critical flow.
- Keep Yandex and `mpv` adapters isolated behind interfaces.
- Prefer “ugly but correct” before styling polish.
