# YAYMP Bootstrap

This milestone establishes the project skeleton for the desktop Yandex Music player.

## Local setup

Create an environment with Python 3.12+ and install the bootstrap dependencies:

```bash
python -m pip install -e '.[dev]'
```

## Run the app

```bash
./scripts/run_smoke.sh
```

The app starts through the bootstrap path:

1. load runtime configuration
2. initialize logging
3. build the composition root
4. create the Qt application
5. construct the main window
6. show the window and enter the event loop

## Run checks

```bash
./scripts/run_lint.sh
./scripts/run_tests.sh
```

## Packaging

Local distributable builds use Nuitka:

```bash
./scripts/build_nuitka_macos.sh
./scripts/build_nuitka_linux.sh
```

GitHub release builds are driven by the `Release` workflow:

- push a tag `vX.Y.Z` for a published release
- or use `workflow_dispatch` for a manual packaging/debug run

The workflow produces:

- `YAYMP-<tag>-macos-arm64.zip`
- `YAYMP-<tag>-linux-x86_64.AppImage`

## Notes

- Platform-specific directories are resolved with `platformdirs`.
- Logs are written to the platform log directory for the app.
- The main window is intentionally a placeholder shell without business logic.
