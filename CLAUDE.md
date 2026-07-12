# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A Home Assistant add-on ("Home Assistant Google Drive Backup", ~100k users) that creates HA backups on a schedule and syncs them to Google Drive. The same repo also contains a companion OAuth token-broker server (deployed to Cloud Run as habackup.io) that keeps Google's client secret off user machines.

Stack: Python 3.11, asyncio throughout, aiohttp (server and client), `injector` for dependency injection, Jinja2 (via aiohttp-jinja2) for the web UI. The frontend JavaScript in `backup/static/` has no tests and no build step.

Layout quirk: the Python code lives in `hassio-google-drive-backup/` (same name as the repo). Inside it:
- `backup/` — the add-on source (and `backup/server/` — the separately-deployed auth server)
- `tests/` — pytest suite
- `dev/` — simulation server, seed data, and deploy scripts
- `config.json` — the add-on manifest: version, permissions, and the options schema

## Philosophy

This project emphasizes being easy to use, despite doing something complicated.  Never talk down to the user, and provide *uefule* context about errors when possible to help with resolution.  Because it manages backups, which is _super important_ to people, regressions must never introduce problems that stop or unexpectedly delete backups.  Data loss is unacceptable and voliates the trust users have put in this project by using it. 

## Commands

Run everything from the repo root (`pytest.ini` lives here).

```bash
# All tests (takes a while; ~40 test files)
python3 -m pytest hassio-google-drive-backup/tests

# Single file / single test; --no-cov speeds up iteration
python3 -m pytest hassio-google-drive-backup/tests/test_coordinator.py --no-cov
python3 -m pytest hassio-google-drive-backup/tests/test_coordinator.py::test_name --no-cov

# Parallel (pytest-xdist is installed)
python3 -m pytest hassio-google-drive-backup/tests -n auto

# The only lint that can fail CI (syntax errors / undefined names)
flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics

# Dev dependencies (the devcontainer already has them)
python3 -m pip install -r .devcontainer/requirements-dev.txt
```

Line length is NOT enforced in CI (the second CI flake8 pass uses `--exit-zero`). The VSCode editor config ignores E501, E731, W503.

### Running the add-on locally

Two processes: a mock backend simulating Google Drive + the HA Supervisor, and the add-on itself pointed at it. The hyphenated `-m` paths are intentional (namespace-package trick; the VSCode launch configs do the same thing):

```bash
# Terminal 1: mock backend on http://localhost:56153 (debug UI at /debug)
PYTHONPATH=hassio-google-drive-backup python3 -m hassio-google-drive-backup.dev.simulationserver

# Terminal 2: the add-on — web UI on http://localhost:56151, ingress on 56152
PYTHONPATH=hassio-google-drive-backup python3 -m hassio-google-drive-backup.backup --config hassio-google-drive-backup/dev/data/dev_options.json
```

The auth server's entrypoint is `python3 -m backup.server` (reads `PORT`, `CLIENT_ID`, `CLIENT_SECRET` from the environment). Note the "Run Auth Server" launch config in `.vscode/launch.json` points at a stale module path, and the "[Re]create and run local addon" task references a script that no longer exists.

## Architecture

### Boot and dependency injection

Everything is wired with the `injector` library. `backup/__main__.py` builds `Injector([BaseModule(), MainModule()])`, resolves `Starter`, and starts each bound `Startable` in order. `backup/module.py` is the wiring hub — two multiproviders there are load-bearing:

- `List[Startable]` — the boot order of all background services
- `List[Trigger]` — everything the sync loop polls: `[Coordinator, HaSource, DriveSource, Watcher, UiServer]`

Constructor dependencies use `@inject`/`@singleton`; look at any existing class to copy the pattern. `MainModule` loads config from `/data/options.json` (or a `--config` file arg); tests replace it with a `TestModule`.

### The sync engine (the core of the app)

- `Trigger` (`worker/trigger.py`) — a self-resetting "something changed, please sync" flag. UI actions, file-watcher events, saved credentials, and elapsed time all express themselves as triggers.
- `Scyncer` (`model/syncer.py`, misspelling is long-standing) — a `Worker` loop that polls all `Trigger`s every 0.5s and calls `Coordinator.sync()` when any fire. There is no cron; all scheduling is poll-based.
- `Coordinator` (`model/coordinator.py`) — the orchestrator and the API the UI calls (`startBackup`, `delete`, `retain`, `ignore`, `note`, `uploadBackups`...). Owns the sync lock, exponential `Backoff`, and next-sync/next-backup time computation.
- `Model.sync()` (`model/model.py`) — the actual algorithm each pass: read both sources and merge into `Backup` objects → purge per retention scheme (`model/backupscheme.py`: oldest / generational / delete-after-upload) → create a new backup if due → upload anything in HA that isn't in Drive.

### Source/destination abstraction

`BackupSource`/`BackupDestination` (`model/model.py`) define `get/create/save/read/delete/retain`. `HaSource` (`ha/`) is the source — talks to the Supervisor REST API via `HaRequests`, handles pending-backup polling and stopping/restarting addons (`AddonStopper`). `DriveSource` (`drive/`) is the destination — resumable chunked uploads with retry via `DriveRequests`, folder discovery via `FolderFinder`. A `Backup` (`model/backups.py`) aggregates per-source `AbstractBackup` records keyed by source name (`const.py`: `"HomeAssistant"`, `"GoogleDrive"`) and derives its status ("Backed Up", "Drive Only", "HA Only") from which sources hold it.

### Web UI

`ui/uiserver.py` runs two aiohttp servers: the ingress server (port 8099, unauthenticated — trusted behind HA ingress) and an optional exposed server (port 1627, optional SSL + HA-login basic auth). JSON handlers are registered by method name (handler `getstatus` → route `/getstatus`). Templates and all static assets live in `backup/static/`.

### Error handling philosophy

All anticipated failures are `KnownError` subclasses (`exceptions/exceptions.py`) with a stable `code()` (strings in `const.py`), a user-facing `message()`, an `httpStatus()`, and `retrySoon()`. The UI middleware serializes them to JSON and the frontend renders help keyed by code. `retrySoon()` drives the backoff: errors needing user action (expired creds, Drive full) max out the backoff instead of retrying. New failure modes should get a `KnownError` subclass, not a bare exception.

### Time is injected

`backup/time.py` provides an injectable `Time` (now, sleep, timezone). Never call `datetime.now()` or `asyncio.sleep()` directly in app code — tests rely on substituting `FakeTime`.

### Config/settings

Every add-on option is a member of the `Setting` enum in `config/settings.py`, with defaults and validation schemas there; the option must also appear in the `config.json` manifest schema. `Config` handles validation, change subscriptions (e.g. the UI server restarts itself when SSL/port options change), and migration of deprecated option names.

**Terminology legacy**: backups were called "snapshots" until HA renamed them. Old `snapshot`-named config keys, Drive metadata properties, and `const.py`'s `NECESSARY_OLD_*` values are backwards-compatibility surface persisted in users' Drive accounts and supervisor state — do not rename or remove them.

## Tests

The project has near-100% test coverage and the standing rule is that every change lands with tests covering it (JavaScript is the only exception). Test style is integration-flavored: real objects from a real injector, real HTTP against a simulated backend, no mock objects for the most part.

- `tests/conftest.py` builds the production `BaseModule` plus a `TestModule` that swaps in `FakeTime`, test creds, and a config whose every URL points at a `SimulationServer` started on a free port. Fixtures are just `injector.get(...)` — `ha`, `drive`, `coord`, `time`, `config`, `model`, `google`, `supervisor`, `interceptor`, `reader` (HTTP helper against the UI), etc.
- `dev/simulationserver.py` composes fakes of the Google Drive v3 API + OAuth (`simulated_google.py`), the Supervisor API (`simulated_supervisor.py`), HA ingress (`apiingress.py`), and the real auth server — used by both the test suite and interactive dev.
- `RequestInterceptor` (`dev/request_interceptor.py`) is the fault-injection layer: make any URL return an error N requests in, hang, or drop the connection.
- `FakeTime` starts frozen at 1985-12-06; `sleepAsync()` advances fake time instantly instead of sleeping, which is why the suite is fast. Advance time explicitly with `time.advance(...)`.
- `asyncio_mode = auto` (no `@pytest.mark.asyncio` needed), 600s per-test timeout, tests chdir into a temp dir.
- An autouse fixture asserts every Drive HTTP response was closed — resource leaks fail tests.

## Branches, CI, and deployment

- PRs and development happen on **`dev`**; `master` is for releases (see CONTRIBUTING.md).
- Every push/PR runs pytest (Python 3.11 only) + the flake8 syntax gate + the HA add-on config linter + CodeQL.
- Pushing to `dev` auto-builds and publishes the **staging add-on** (`sabeechen/hgdb-dev-staging` repo, talks to dev.habackup.io) — expect real staging users to see it ~25 minutes later.
- Production add-on images (`ghcr.io/sabeechen/hassio-google-drive-backup-{arch}`) and auth-server images are published only via manual `workflow_dispatch` workflows (`prod_push.yaml`, `server_image_push.yml`).
- The add-on version lives in `hassio-google-drive-backup/config.json`; releases also get a `CHANGELOG.md` entry.
