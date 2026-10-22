# SDT Manager with timestamps

This is the timestamp-instrumented version of `../SDT-Manager`, synchronized with
branch `quantum_sdt`, commit `de8cb30`. The current V2 adapter (including MUD), MQTT
failure reporting, credential handling, and automatic SDT template upload are
preserved. Watchtower and DLT/CCMLedger workflows remain disabled, as in that source.
The main manager directory is not changed.

## Build, deploy, destroy

Run on the `sdtm` k3s node with Docker, k3s, kubectl, and Python 3 available.
The scripts resolve their paths relative to themselves and can run from any directory.
Use the same tag for build and deploy; the default tag is `latest`.

```bash
cd /home/sdtm/SDTM/SDT-Manager/timestamps_component
./build.sh experiment-1
./deploy.sh experiment-1
./destroy.sh
```

- Image: `sdt-manager-timestamps:experiment-1` (imported into local k3s by build).
- Deployment: `sdt-manager-timestamps-deployment`, namespace `default`.
- Service: `sdt-manager-timestamps-service:8008`; NodePort `30012`.
- Data: `sdt-manager-timestamps-data-pvc` (1 GiB), separate from the quantum manager's PVC.
- Timing archive inside the pod: `/app/data/performance_events.jsonl`.

`SKIP_K3S_IMPORT=1 ./build.sh experiment-1` builds without importing.
`NODE_PORT=30112 ./deploy.sh experiment-1` selects another NodePort.
`./deploy.sh experiment-1 --dry-run` renders the manifest without contacting Kubernetes.
Deployment uses `Recreate` and triggers a new pod even when reusing the same image tag.
The image must be imported on the scheduled node (`sdtm`); image pull policy is `Never`.

Review `.env` for the MQTT broker and IAM settings before deploying. The deploy script
loads it as a Kubernetes Secret without sourcing it as shell code. Use `ENV_FILE=/path/.env`
to select another file. Keep values unquoted (`KEY=value`), as required by kubectl's
env-file reader. The deployment ConfigMap overrides local paths, service addresses,
and timing retention with their cluster values. The timestamp MQTT component ID is
`sdt-manager-timestamps-01`. The image excludes `.env`, databases, old logs, caches,
historical samples, and plotting results.

The manager has separate resources, but its SDT and IDS deployment targets are the
same shared targets used by the current quantum manager. Run deployment/deletion
experiments through one manager at a time. This is not a separate downstream test cluster.
The timestamp destroy script never deletes those downstream SDT/IDS resources or
the quantum manager. Delete test twins through their managing API before teardown
if downstream cleanup is wanted.

`./destroy.sh` preserves the data PVC. `./destroy.sh --purge-data` also deletes that
PVC, which can permanently remove the timing archive and credential database.
The destroy script leaves the locally built Docker/k3s image available for reuse.

## Recorded events

Each record contains UTC start/end timestamps (ISO and Unix epoch), elapsed seconds
from a monotonic clock, category, label, status, safe identifying metadata, a parent
record ID, and a trace ID. Background authentication inherits the originating
deployment request's trace and SDT ID.

Coverage includes:

- Component construction and manager startup/shutdown operations.
- Every incoming HTTP request, including health checks, performance API calls,
  failures, and streamed responses through their final body.
- SDT and IDS deployment, readiness polling, deletion, and Kubernetes command calls.
- Wallet registration, credential polling, OAuth token acquisition, and each
  outgoing HTTP call (including individual polling attempts).
- Credential database operations, token distribution, and SDT template upload.
- V2 validation, transformation, multi-file processing, and forwarding to the SDT.
- MQTT report enqueueing and each publish attempt, including retries.

Instrumentation wraps component methods; it does not profile every Python statement,
OS event, or activity inside remote SDT/IDS services. Long-lived server and MQTT
worker loops are excluded. Nested durations overlap: do not sum all events to obtain
end-to-end time. The deployment HTTP record ends at the response; the background
authentication record measures work that may finish later. MQTT worker publish
records have their own trace and carry `mqtt_event_id` for correlation.

Explicit failures and exceptions produce `failed`; completed parents with failed
substeps produce `partial_failure` (including recovered retries). Cancellation is
recorded as `cancelled`. An absent credential lookup may be normal and is not
automatically treated as failure. Arguments, results, auth headers, request bodies,
query strings, and exception messages are not copied into timing records.

Every completed event is appended to JSONL under a lock. The API retains active
events and the latest 10,000 completed events by default (`PERFORMANCE_MAX_RECORDS`).
The archive persists across pod restarts, while the in-memory query window resets.
Archiving is synchronous and adds measurement overhead. Monitor disk usage and
archive/rotate files between experiments: the append-only archive has no automatic
size limit. `archive_errors` reports write failures; in that case events remain in
memory until evicted, but persistence is not guaranteed. Events interrupted by a
process crash before completion are not archived.

## Query and export

```bash
curl http://localhost:30012/api/SDTM/performance
curl 'http://localhost:30012/api/SDTM/performance?category=token_distribution&sdt_id=TWIN_ID'
curl http://localhost:30012/api/SDTM/performance/summary
curl http://localhost:30012/api/SDTM/performance/RECORD_ID
curl -o performance.csv http://localhost:30012/api/SDTM/performance/export
```

Records and CSV export accept `category`, `sdt_id`, and exact `label` filters together.
The records endpoint also accepts `limit`; `count` is the number of matching retained
records, while `returned_count` is the number returned. Summary reports per-category
count, total, average, minimum, maximum, and failure count for retained completed
records. To download the full cross-restart archive:

```bash
kubectl exec -n default deployment/sdt-manager-timestamps-deployment -- \
  cat /app/data/performance_events.jsonl > performance_events.jsonl
```

`DELETE /api/SDTM/performance` clears completed in-memory records only. Active events
and the archive remain; the clear request itself is recorded when it finishes.

Generate current per-operation CDF plots and a summary CSV:

```bash
pip install -r plot_timestamps/plot_packages_requirements.txt
python3 plot_timestamps/plot_events.py performance_events.jsonl --output plots
# CSV exported from the API is also accepted:
python3 plot_timestamps/plot_events.py performance.csv --output plots
```

The old spreadsheets, plots, SBOM/VEX examples, credential database, and standalone
`post_certificate_ccm.py` are historical experiment artifacts. They are not included
in the image or executed by the manager. `adapter_all.py` is now a compatibility
import for V2; new code should import `adapter_all_v2`.

## Verification and future synchronization

```bash
python3 -m venv /tmp/sdt-timestamps-tests
/tmp/sdt-timestamps-tests/bin/pip install -r requirements-dev.in
/tmp/sdt-timestamps-tests/bin/python -m pytest -q tests --confcutdir=tests
```

Tests mock outgoing services, Docker, and Kubernetes. They do not deploy resources.
They cover timing correctness/concurrency, current API compatibility, auth/token/template
flows, MQTT behavior, manifest configuration, and build/deploy/destroy scope.

Business logic is copied from the main directory. Timing-specific changes are in
core initialization, interface middleware/routes and background context propagation,
and the requests imports in the adapter/auth/interface. The timing implementation is
in `sdt_performance_tracker.py`, `performance_instrumentation.py`, and `performance_http.py`.
When updating from main again, preserve these integration points and rerun the tests.
