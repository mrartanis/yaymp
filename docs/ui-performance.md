# UI performance audit

## Implemented

- System media: MPRIS publishes only changed properties and never includes
  Position in PropertiesChanged. Seek revisions survive deferred snapshot
  coalescing and trigger Seeked. Position and seek methods use signed 64-bit
  microseconds; track IDs use valid, collision-free object path components.
- macOS Now Playing: reuse artwork across position/status updates and publish
  metadata only on changes, seeks or a playback-clock discrepancy above 1.5 s.
  Cache write revisions make newly downloaded covers visible without polling
  the filesystem. Windows SMTC updates metadata, playback state and timeline
  independently; repeated empty snapshots clear system metadata only once.
- Transport icons: compare QIcon cache keys before calling setIcon, avoiding
  unnecessary geometry invalidation and ancestor repaints while retaining
  updates for status, color and icon size changes.
- Queue fake-waveform: replace 300 ms discrete frames and integer heights with
  elapsed-time animation, a 42 ms precise timer (approximately 24 FPS), six bars
  and antialiased fractional geometry. The overlay paints an opaque background
  matching the row, preventing Qt from repainting the delegate and ancestors on
  each animation frame. Stop the timer when hidden, minimized,
  paused or outside the viewport. Do not replay missed frames after a stall.
- Settings: load one runtime snapshot instead of reading and parsing JSON in row
  painting, theme access and translations. Serialize writes, but release the
  in-memory cache lock before disk IO so render-time readers do not wait for it.
  Runtime preference changes go through SettingsService; external edits to the
  settings file become visible after restarting the application.
- Localization: resolve the system language once per selected language preference.
  This removes repeated reads of macOS GlobalPreferences.plist for every string.
- Volume: persist on the existing playback worker. Keep one command in flight
  and the latest pending value, preventing slider movement from building a long
  backlog. Preserve the latest requested setting at shutdown. While dragging,
  playback snapshots do not move the slider back to an older value.
- Playback polling: allow at most one refresh in flight, including queued refreshes;
  slow network/backend operations cannot accumulate periodic polling requests.
- Main cover: decode QImage, compute accent and read/write its accent cache on the
  existing library task runner. Convert to QPixmap and update widgets on the UI
  thread. Cancel pending preparations and reject stale results on track changes.
- Cover resizing: retain the original pixmap in ArtworkLabel. Rescale it on size
  or device-pixel-ratio changes without rereading the file or recomputing the
  accent, and discard it when the cover is cleared.

## Verification

Regression tests cover quiet position polls, paused/empty snapshots, short
seeks, late artwork, Windows timeline updates and transport paint events.
macOS/Windows native calls are tested with substitutes on Linux. A private
D-Bus session verified Position(x), Seek(x), SetPosition(ox), thirty quiet polls
and one Seeked(x) for a seek. PySide6 still infers the variant type of
mpris:length: int32 for small values, int64 for large ones. Strict int64 typing
of that metadata entry remains a compatibility limitation; no overflow was
observed and no new D-Bus dependency was introduced for this field.

Offscreen Qt tests cover event-loop responsiveness while playback and cover work
are deliberately blocked, volume coalescing, worker-thread persistence, stale
cover results, cached settings/localization, animation visibility and distinct
rendered frames at 60 Hz. These are not end-to-end hardware FPS measurements.

A local raster microbenchmark of 10,000 fake-waveform frames, 18 x 14 logical pixels
at DPR 2, measured approximately 0.055 ms/frame, including image clearing, painter
creation and animation calculation. Compositor and widget propagation costs are
excluded. Real display cadence remains dependent on the platform and UI workload.

A subsequent full-window offscreen profile exposed an important limitation of
the isolated raster benchmark: the transparent overlay caused 94 paints of the
active row and each ancestor in 1.5 seconds at the former 16 ms cadence. With the
opaque overlay, the same experiment recorded 94 overlay paints and zero ancestor
or row paints. CPU time in that instrumented interval fell from 0.122 to 0.073 s.
The timer was then reduced to approximately 24 FPS as requested. Regression tests
check background matching in both themes and selection states, absence of viewport
paints on animation updates, and resizing from the original cover. These results
do not predict a specific CPU percentage on another desktop/compositor.

## Remaining synchronous work

| Path | Current cost / next change |
| --- | --- |
| Thumbnail cache miss during list painting | File existence checks, image decoding and resizing still occur on the UI thread. Move thumbnail cache reads/decoding to a bounded asset task queue with request deduplication and stale-consumer handling. |
| Artwork network completion | Network itself is asynchronous; downloaded bytes are still written to disk on the UI thread. Move cache writes together with thumbnail decoding. |
| Main cover lookup | A file-existence check remains before background preparation. Preparation shares the library lane, so a slow library request can delay cover display without blocking UI. |
| Preference changes / My Wave history | Writes other than volume remain synchronous; history writes run every five seconds during playback. A serialized settings writer must preserve immediate in-memory changes and flush final state before shutdown. |
| System media integration | Platform artwork loading and cache existence checks remain synchronous. Profile each OS before moving calls that may have native thread-affinity requirements. |
| Window closing | Playback/library shutdown waits for worker threads. This is outside normal rendering but can delay exit; a separate asynchronous shutdown lifecycle is needed, including handling network timeouts safely. |

API operations and playback commands already use background workers. They should
remain serialized where queue and playback state depend on command ordering.
