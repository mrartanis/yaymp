# Delivery Plan

This file is the milestone-level execution plan with Definition of Done for each phase.

## Milestone 0: Skeleton / Bootstrap

Status: done

Goal:

- establish the correct project shape and startup path

Deliverables:

- repository structure
- app bootstrap
- main window placeholder
- composition root
- settings loading
- logging setup
- CI lint/test skeleton
- smoke run script

Definition of Done:

- the application launches
- the main window opens
- the project runs locally
- test scaffolding exists

## Milestone 1: Playback Core Without Yandex

Status: done

Goal:

- prove the player architecture and playback core

Deliverables:

- `PlaybackEngine` contract
- `MpvPlaybackEngine`
- fake playback engine for tests
- `PlaybackService`
- queue model
- play/pause/next/previous/seek/volume controls
- local test media loading

Definition of Done:

- audio playback works
- queue transitions work
- playback state is reflected in the UI
- playback orchestration has integration tests

## Milestone 2: Yandex Auth and Track Resolve

Status: done

Goal:

- play a real Yandex Music track end to end

Deliverables:

- `MusicService` contract
- `YandexMusicService`
- auth/session persistence
- startup session recovery
- track resolve to stream
- single-track playback by id

Definition of Done:

- authentication works
- saved session recovery works
- a real track can be played
- auth and unavailable-track errors are handled predictably

## Milestone 3: Search and Library Basics

Status: done

Goal:

- make the app minimally useful for real listening

Deliverables:

- search flow
- results list UI
- double-click to play
- liked tracks flow
- liked-tracks view
- recent searches
- artwork cache
- metadata cache

Definition of Done:

- the user can search, play, and like tracks
- the UI feels like a working player, not a demo
- main search/play flows are covered by tests

## Milestone 4: Playlists and Albums

Status: done

Goal:

- support real catalog navigation and source-aware queue behavior

Deliverables:

- open album
- open playlist
- replace queue
- append queue
- queue semantics tied to source
- next/previous over source queue
- basic shuffle and repeat

Definition of Done:

- playlists and albums play correctly
- transitions between tracks are stable
- queue behavior is predictable

Current additions:

- Library navigation includes My Tracks, My Albums, My Artists, Playlists, and My Wave.
- Search and artist pages use dynamic tabs; plain library lists hide tabs.
- Artist pages expose Top Tracks, Albums, Singles, Compilations, and Radio.
- Current playback queue and position survive restarts, including bounded My Wave/station queues.

## Milestone 4.5: Persistence and Resume

Status: done

Goal:

- preserve daily listening context across restarts

Deliverables:

- SQLite playback queue state
- saved active index and source context
- saved playback position
- restore without autoplay or startup stream resolution
- event-driven mpv restore seek
- bounded My Wave/station queue persistence
- corrupted saved queue reset
- clear queue action

Definition of Done:

- restarting the player restores the previous queue
- pressing Play resumes from the saved track and position
- My Wave can resume without unbounded queue growth
- restore seek waits for backend readiness instead of polling retries
- broken saved queue state is dropped instead of blocking startup

## Milestone 5: Packaging and Distributables

Status: done

Goal:

- remove “works on my machine” assumptions

Deliverables:

- Nuitka build scripts
- PyInstaller fallback notes if Nuitka blocks release packaging
- bundled `libmpv`
- macOS bundle
- Linux bundle
- release artifacts
- startup diagnostics/log visibility
- documented build pipeline

Definition of Done:

- the app starts on a clean machine
- no manual playback-backend install is required
- build and release steps are documented
- release smoke checklist exists

Current notes:

- macOS release artifact is `YAYMP-<tag>-macos-arm64.zip`.
- Linux release artifact is `YAYMP-<tag>-linux-x86_64.AppImage`.
- `Release` workflow supports both tag push (`v*`) and `workflow_dispatch`.
- Manual debug loop can skip release publication; tag push or `publish_release=true` publishes the GitHub Release.
- Publish job now checks out the repository before `gh release ...` commands.
- Release creation should rely on the existing tag name, not `GITHUB_SHA`, when re-running publish for an already-pushed tag.

## Milestone 6: Classic UX

Goal:

- move from functional player to intentional standalone product

Deliverables:

- compact or mini mode
- improved queue UI
- keyboard shortcuts
- tray or menu integration where relevant
- classic desktop player styling
- persistent layout and settings polish

Definition of Done:

- the app feels like a real standalone music player
- regular daily usage is not annoying
- UX direction is aligned with classic desktop audio players

## Milestone 7: Stabilization

Goal:

- remove fragility before broader expansion

Deliverables:

- error audit
- threading audit
- cache corruption recovery
- stronger logging
- infrastructure contract tests
- long-session profiling
- cleanup of crash-prone flows

Definition of Done:

- the app stays stable during long sessions
- playback, search, queue transitions, and reopen flows stay reliable
- the codebase is ready for post-MVP expansion

## Deferred Until After MVP

Do not pull these into the core roadmap early:

- equalizer
- visualizations
- plugin system
- remote control API
- Discord or Last.fm integration
- lyrics
- offline mode
- skin engine
- waveform rendering
- gapless fine-tuning beyond default `mpv` behavior

## Minimum Backlog Snapshot

Core:

- app bootstrap
- settings storage
- logging
- playback engine interface
- `mpv` adapter
- playback service
- queue model

Yandex:

- auth/session persistence
- search
- track resolve
- likes
- playlists
- albums

UI:

- main window
- player controls
- now playing bar
- search panel
- playlist/library panel
- queue view
- mini mode

Persistence:

- settings repo
- auth repo
- SQLite cache
- artwork cache

Testing:

- fake music service
- fake playback engine
- in-memory repos
- playback integration tests
- search/library integration tests
- UI smoke tests

Build:

- dev bootstrap script
- Nuitka build script
- PyInstaller fallback path
- bundled `libmpv`
- CI pipeline
- release checklist
