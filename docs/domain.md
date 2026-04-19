# Domain Contracts

The domain layer defines the stable records and protocols that future application services depend on.

## Current surface

- Entities: `Track`, `Playlist`, `QueueItem`, `PlaybackState`, `AuthSession`
- Bounded playback state: `PlaybackStatus`, `RepeatMode`
- Contracts: `MusicService`, `PlaybackEngine`, `SettingsRepo`, `LibraryCacheRepo`, `AuthRepo`, `Clock`, `Logger`
- Domain-facing error categories for auth, network, stream resolution, playback, and storage failures

## Boundaries

- `src/app/domain/` contains records, enums, protocols, and domain-facing errors only.
- Real Yandex Music clients, playback adapters, and persistence implementations belong in `src/app/infrastructure/`.
- Orchestration logic such as queue behavior and playback flows belongs in `src/app/application/`.

## Notes

- Entities are frozen dataclasses to keep state explicit and easy to reason about.
- Protocols are intentionally small so in-memory fakes stay easy to write in tests.
- LLMs may record important local-only operational notes in `mem.md` when those notes help future implementation or debugging.
- `mem.md` is for local memory and workflow context, not for committed product or architecture documentation.
