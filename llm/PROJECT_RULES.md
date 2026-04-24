# Project Rules

This file is the authoritative LLM context for architecture and implementation constraints.

## Product Goal

Build a local desktop Yandex Music player with a classic standalone-player UX inspired by Winamp, AIMP, QMMP, and similar apps.

Core product constraints:

- Cross-platform first: macOS and Linux are required; Windows should stay feasible without a rewrite.
- Base UI stack: `PySide6`.
- Playback must use a native backend, not Python audio decoding.
- The final app must be distributable as a self-contained desktop bundle.
- Architecture must stay small, explicit, and easy to extend with LLM help.
- Testing should focus on integration-style behavior, not micro unit tests.

## Non-Goals

Do not optimize for these in the first stages:

- No Electron or embedded browser as the main app shell.
- No full Yandex Music feature parity.
- No skin engine, plugin system, DSP chain, visualizations, lyrics, radio, Last.fm, or download/offline mode in MVP.
- No premature optimization or architecture inflation.
- No mandatory reliance on a system-installed `mpv` or `vlc` for end users.

## Mandatory Technology Choices

- UI: `PySide6` with Qt Widgets.
- Playback backend: `libmpv` through Python bindings or a small local adapter.
- API integration: isolated Python infrastructure client for Yandex Music.
- Runtime architecture: practical layered design, not “pure clean architecture”.

## Layer Boundaries

Use exactly these layers:

- `domain`: entities, value objects, interfaces, contracts.
- `application`: use cases, orchestration, queue/playback/auth/search/library flows.
- `infrastructure`: Yandex API, playback adapter, persistence, cache, logging, time.
- `presentation`: Qt widgets, view models, controllers, resources.

Rules:

- Business logic must not live in Qt widgets.
- Presentation must not directly access HTTP, persistence, or playback internals.
- Infrastructure details must not leak into UI state models.
- Do not create extra abstraction layers unless they remove real complexity.

## Recommended Repository Shape

Target structure:

```text
src/app/bootstrap/
src/app/domain/
src/app/application/
src/app/infrastructure/
src/app/presentation/
tests/integration/
tests/contract/
tests/smoke/
tools/
scripts/
docs/
```

## Domain Rules

Use small stable entities and explicit protocols.

Core entities:

- `Track`
- `Playlist`
- `QueueItem`
- `PlaybackState`
- `AuthSession`

Design rules:

- Prefer `dataclass(frozen=True)` for entity-like records.
- Use `Protocol` or `ABC` for external-facing interfaces.
- `stream_ref` is an internal stream identifier, not necessarily a direct URL.
- Keep value objects simple and typed.

## Required Interfaces

At minimum, define explicit contracts for:

- `MusicService`
- `PlaybackEngine`
- `SettingsRepo`
- `LibraryCacheRepo`
- `AuthRepo`
- `Clock`
- `Logger`

Rules:

- Application code depends on these interfaces, not concrete infrastructure.
- Fakes used in tests must obey the same behavior contracts as real adapters.

## Application Layer Rules

The application layer is the main place for behavior and orchestration.

Primary services/use cases:

- `PlaybackService`
- `SearchService`
- `LibraryService`
- `AuthService`
- focused use-case modules for login, playback control, playlist loading, search, likes, home fetch

Rules:

- `PlaybackService` owns queue semantics, active index, repeat/shuffle, stream resolution, and interaction with `PlaybackEngine`.
- View models may adapt state, but they do not orchestrate playback, auth, search, or storage.
- Controllers connect UI events to application services/use cases.

## UI Rules

Use Qt Widgets, not QML, for the initial product.

Reasons:

- Better fit for old-school desktop player layout.
- Easier to control window composition and widget behavior.
- Easier to generate and maintain with LLM assistance.

Rules:

- Keep view models thin.
- No API calls from widgets or view models.
- No persistence calls from widgets.
- Main window should support classic player composition: controls, seek, volume, track info, library/navigation, content panel, queue/status area.

## Concurrency Rules

These rules are mandatory:

- Qt main thread is only for UI.
- Network and heavy IO must run outside the UI thread.
- `mpv` callbacks must never mutate widgets directly.
- Background-to-UI transitions must go through Qt signals or queued calls.
- Do not add ad hoc threading patterns.
- Do not build the app around `asyncio` unless a hard requirement appears later.

Preferred approach:

- Qt main thread for UI.
- One controlled background executor for API/IO.
- Playback wrapper converts backend events into thread-safe signals.

## Packaging Rules

Packaging target:

- User downloads and runs the app without manually installing playback backends.

Rules:

- Bundle `libmpv` with the app.
- Resolve backend library paths from app runtime location.
- Allow a development fallback path only for local development.
- Keep a dedicated `mpv_loader.py`.

Practical recommendation:

- Start with local development without bundling.
- Use `Nuitka` as the primary distributable build path.
- Keep `PyInstaller` as a fallback only if Nuitka exposes blocker-level packaging issues.
- Prefer a debuggable standalone/app-bundle build before attempting one-file packaging.
- For Linux AppImage verification in CI, prefer `APPIMAGE_EXTRACT_AND_RUN=1` over assuming FUSE is available on the runner.
- Release publication should be tag-driven and reproducible from workflow inputs; do not depend on interactive local release creation.

Bundle contents must include:

- Qt runtime
- Python runtime
- icons and styles
- `libmpv` and required binary dependencies
- required fonts if used
- third-party licenses if needed

Operational packaging notes:

- macOS packaged runtime lookup should resolve bundled `libmpv` from inside `.app/Contents/MacOS/lib`.
- Linux packaged runtime lookup should resolve bundled `libmpv` from both `usr/bin/lib` and `usr/lib`.
- Packaging smoke checks should verify not only that `mpv` is used, but also that the resolved library path points into the packaged bundle/AppDir/AppImage environment.

## Persistence Rules

Use platform-correct app directories via `platformdirs`.

Storage targets:

- settings
- auth/session
- playback preferences such as volume, repeat, shuffle
- window geometry
- cache index
- recent entities
- artwork cache
- library metadata cache

Formats:

- settings: JSON or TOML
- structured cache: SQLite
- artwork: cache files
- auth/session: isolated JSON or SQLite-backed storage

## Testing Rules

Testing philosophy:

- Prefer integration-style tests over many fine-grained unit tests.
- Test behavior and state transitions, not implementation trivia.
- Prefer fakes over dynamic mocks.

Primary test groups:

- `tests/contract`
- `tests/integration`
- `tests/smoke`

Priority targets:

- application services and use cases
- queue/playback orchestration
- auth/session lifecycle
- search and library flows
- limited infrastructure adapter coverage
- minimal Qt smoke tests

Do not spend time on:

- trivial dataclasses
- getters/setters
- layout spacing
- cosmetic-only helpers

## Error Handling Rules

Never leak raw infrastructure exceptions into application or presentation.

Rules:

- Infrastructure converts low-level exceptions into project-specific errors.
- Application decides whether errors are recoverable and how state changes.
- Presentation shows user-safe messages only.

Expected error categories:

- auth errors
- network errors
- unavailable track or region restriction
- stream resolve failure
- playback backend failure
- storage corruption
- invalid config
- unexpected API response

## Logging Rules

Always preserve a useful debug trail.

Log:

- startup
- settings load
- auth/session lifecycle
- search requests
- playlist loads
- stream resolution
- playback events
- queue transitions
- recoverable errors

Do not log:

- raw tokens
- sensitive user data unless strictly required

## Code Style Rules

- Python `3.12+` unless blocked.
- Use type hints almost everywhere.
- Prefer `dataclass` or `attrs` for DTO/entity-like structures.
- Keep files reasonably small.
- Avoid cyclic imports.
- One class, one responsibility.
- Avoid “god services”.
- Prefer modules roughly within `300-500` lines when practical.
- Add docstrings to public classes and use cases.

## Anti-Bloat Rules

Explicitly avoid these unless a later milestone proves they are needed:

- generic global event bus
- full plugin framework
- heavy command framework
- universal repository abstraction “for everything”
- multiple competing state-management systems
- extra presenter/interactor/coordinator/facade layers with no concrete benefit

## Project Risks

Main risks:

1. Unofficial Yandex Music API instability.
2. `libmpv` packaging complexity on macOS and Windows, especially with Nuitka binary dependency handling.
3. Threading bugs between Qt and playback callbacks.
4. Overengineering caused by LLM-generated code.
5. UI leaking into infrastructure or vice versa.
6. Session/cache/auth state turning into an unstructured mess.

Mitigations:

- Keep Yandex integration isolated.
- Keep `mpv` integration isolated.
- Keep application services independent from infrastructure.
- Maintain strong integration tests from the start.
- Delay skins/plugins until core behavior is stable.
- Run packaging smoke checks regularly.
