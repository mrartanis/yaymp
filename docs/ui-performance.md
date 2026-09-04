# UI performance audit

## Implemented

- Queue fake-waveform: replace 300 ms discrete frames and integer heights with
  elapsed-time animation, a 16 ms precise timer, six bars and antialiased fractional
  geometry. Paint only the small overlay. Stop the timer when hidden, minimized,
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

## Verification

Offscreen Qt tests cover event-loop responsiveness while playback and cover work
are deliberately blocked, volume coalescing, worker-thread persistence, stale
cover results, cached settings/localization, animation visibility and distinct
rendered frames at 60 Hz. These are not end-to-end hardware FPS measurements.

A local raster microbenchmark of 10,000 fake-waveform frames, 18 x 14 logical pixels
at DPR 2, measured approximately 0.055 ms/frame, including image clearing, painter
creation and animation calculation. Compositor and widget propagation costs are
excluded. Real display cadence remains dependent on the platform and UI workload.

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
