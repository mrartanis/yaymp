# Step 1 Plan: Skeleton / Bootstrap

## Goal

Create a minimal but correctly structured project skeleton for the desktop Yandex Music player so further work can proceed without reworking the foundation.

## Scope

This step includes only bootstrap and project structure work:

- repository layout
- app entry point
- composition root
- startup config loading
- basic logging
- main window placeholder
- smoke run script
- basic lint/test CI skeleton

This step does not include:

- playback implementation
- Yandex Music API integration
- domain entities beyond what is required for bootstrap wiring
- real persistence logic
- real search/library/player behavior

## Target Directory Structure

Create at least this structure:

```text
src/
  app/
    bootstrap/
    domain/
    application/
    infrastructure/
    presentation/

tests/
  integration/
  contract/
  smoke/

tools/
scripts/
docs/
```

Recommended early substructure:

```text
src/app/
  bootstrap/
    config.py
    container.py
    startup.py
  presentation/
    qt/
      app.py
      main_window.py
```

## Deliverables

The output of Step 1 should include:

- project folders for the main layers
- runnable desktop entry point
- placeholder main window
- startup bootstrap path with config loading
- composition root or app container
- basic logging initialization
- one smoke script for local launch
- one smoke test proving the app/window can start
- CI skeleton for linting and tests
- short bootstrap documentation

## Work Breakdown

## 1. Establish Project Layout

Tasks:

- create the `src/app` layered structure
- create `tests/integration`, `tests/contract`, `tests/smoke`
- create `tools`, `scripts`, `docs`
- ensure imports and package layout are consistent from the start

Output:

- clean directory tree matching the architecture rules

## 2. Set Up Python Project Metadata

Tasks:

- add Python project metadata and dependency definition
- set Python target to `3.12+` unless blocked
- define runtime dependencies needed for bootstrap only
- define dev dependencies for tests and linting

Expected initial dependencies:

- `PySide6`
- `pytest`
- `pytest-qt`
- `platformdirs`

Output:

- reproducible local environment setup

## 3. Add Application Entry Point

Tasks:

- create a single entry point that starts the Qt application
- ensure startup goes through bootstrap code, not directly into widgets
- keep the path simple and explicit

Recommended startup flow:

1. load config
2. initialize logging
3. build container
4. create Qt app
5. create main window
6. show window
7. enter event loop

Output:

- the application can be launched from one command

## 4. Add Bootstrap Modules

Tasks:

- implement `config.py` for app paths and runtime settings
- implement `container.py` for composition root wiring
- implement `startup.py` for startup orchestration

Rules:

- no DI framework
- no hidden global state if it can be passed explicitly
- config should resolve platform-correct directories
- placeholders are acceptable if interfaces are not yet implemented

Output:

- explicit bootstrap path with room for future expansion

## 5. Add Basic Logging

Tasks:

- initialize logging during startup
- log app start, config path resolution, and main startup stages
- make logs readable in local development

Rules:

- do not log secrets
- keep logging simple and structured enough for debugging
- avoid premature telemetry complexity

Output:

- visible startup diagnostics for local runs

## 6. Add Main Window Placeholder

Tasks:

- create a minimal `QMainWindow`
- include placeholder regions for a classic player layout
- set window title and default size
- avoid embedding business logic into the window

Suggested placeholder sections:

- title area
- transport controls placeholder
- left navigation placeholder
- central content placeholder
- status or queue placeholder

Output:

- a visible desktop window that proves the presentation layer is wired

## 7. Add a Minimal App Container

Tasks:

- create a small container object for bootstrap-time dependencies
- wire config, logger, and placeholder services
- keep the container explicit and readable

Rules:

- no service locator sprawl
- no premature abstractions
- use placeholders for later interfaces rather than building fake production logic now

Output:

- one composition root that will own dependency wiring going forward

## 8. Add Local Smoke Run Tooling

Tasks:

- add a local run script in `scripts/`
- optionally add helper scripts for lint and test execution
- keep commands simple and discoverable

Examples:

- run app
- run tests
- run smoke tests

Output:

- one obvious command path for local verification

## 9. Add Initial Tests

Tasks:

- add one smoke test that creates the Qt application and main window
- ensure the app can initialize without real playback or API services
- keep tests focused on startup stability only

Test targets:

- app object creation
- main window creation
- no crash during minimal bootstrap

Output:

- first test coverage for the bootstrap layer

## 10. Add CI Skeleton

Tasks:

- add a minimal CI workflow for linting and tests
- structure it so later expansion to build matrix is easy
- do not overbuild release packaging in this step

Minimum CI responsibilities:

- install dependencies
- run tests
- run lint or static checks if configured

Output:

- baseline CI that prevents the skeleton from drifting

## 11. Add Documentation

Tasks:

- document how to run the app locally
- document the purpose of the bootstrap modules
- document the expected repository shape

Recommended docs:

- `docs/bootstrap.md` or `README` section
- mention future layers without claiming they are implemented

Output:

- short onboarding path for future work

## Suggested Implementation Order

1. Create directory structure.
2. Add Python project metadata and dependencies.
3. Add bootstrap modules and entry point.
4. Add placeholder main window.
5. Add logging and config path resolution.
6. Add container wiring.
7. Add local run scripts.
8. Add smoke test.
9. Add CI skeleton.
10. Add short docs.

## Acceptance Criteria

Step 1 is complete when all of the following are true:

- the repository has the expected layered structure
- the application launches locally
- the main window opens successfully
- startup passes through explicit bootstrap modules
- config loading exists, even if minimal
- logging is initialized during startup
- a smoke script exists for local launch
- at least one smoke test exists and passes
- CI can run the baseline checks
- no playback, API, or business logic is baked into widgets

## Risks in This Step

- overengineering the container before real services exist
- adding domain or infrastructure detail too early
- hiding startup flow inside ad hoc scripts
- putting future business logic into the window because it is convenient

## Guardrails

- keep files small
- prefer placeholders over fake “complete” systems
- keep startup flow linear and obvious
- preserve the architecture boundaries from day one
- optimize for a clean base, not feature count
