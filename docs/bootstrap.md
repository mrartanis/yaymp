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

## Notes

- Platform-specific directories are resolved with `platformdirs`.
- Logs are written to the platform log directory for the app.
- The main window is intentionally a placeholder shell without business logic.
- Step plans are stored in `docs/steps/`.
