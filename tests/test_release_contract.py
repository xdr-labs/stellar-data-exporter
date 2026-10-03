from pathlib import Path
import subprocess

from app import __version__


ROOT = Path(__file__).resolve().parents[1]
def read(relative: str) -> str:
    return (ROOT / relative).read_text()


def yaml_scalar(text: str, key: str) -> str:
    prefix = f"{key}:"
    for raw in text.splitlines():
        line = raw.lstrip()
        if line.startswith(prefix):
            return line.split(":", 1)[1].strip().strip("\"'")
    raise AssertionError(f"missing YAML scalar: {key}")


BASELINE = yaml_scalar(read(".engineering/project.yaml"), "baseline")


def test_release_profile_requires_preflight_and_artifact_hashes():
    profile = read(".engineering/release.yaml")

    assert "exact_head_required: true" in profile
    assert "preflight_required: true" in profile
    assert "artifact_hash_required: true" in profile
    assert yaml_scalar(profile, "preflight_command") == "scripts/release-preflight.sh"
    assert yaml_scalar(profile, "qualification_command") == "scripts/release-qualify.sh dist"
    assert (
        yaml_scalar(profile, "artifact_hash_command")
        == "scripts/hash-release-artifacts.sh dist dist/SHA256SUMS"
    )


def test_release_workflow_is_manual_exact_head_contract():
    workflow = read(".github/workflows/engineering-release.yml")

    assert "workflow_dispatch:" in workflow
    assert "expected_sha:" in workflow
    assert f"release-contract.yml@{BASELINE}" in workflow
    assert "expected_sha: ${{ inputs.expected_sha }}" in workflow
    assert "phase: ${{ inputs.phase }}" in workflow


def test_release_scripts_are_executable():
    for relative in (
        "scripts/release-preflight.sh",
        "scripts/release-qualify.sh",
        "scripts/hash-release-artifacts.sh",
    ):
        assert (ROOT / relative).stat().st_mode & 0o111


def test_hash_release_artifacts_writes_and_verifies_sha256(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / f"stellar_data_exporter-{__version__}-py3-none-any.whl").write_bytes(b"wheel")
    (dist / f"stellar_data_exporter-{__version__}.tar.gz").write_bytes(b"sdist")
    sums = dist / "SHA256SUMS"

    result = subprocess.run(
        [ROOT / "scripts/hash-release-artifacts.sh", dist, sums],
        check=True,
        text=True,
        capture_output=True,
    )

    assert "RELEASE_ARTIFACT_HASHES=PASS" in result.stdout
    lines = sums.read_text().splitlines()
    assert len(lines) == 2
    assert all(str(dist) in line for line in lines)


def test_browser_distinguishes_exporter_outage_and_retries_safe_requests():
    javascript = read("app/static/app.js")

    assert "const TRANSIENT_EXPORTER_STATUSES = new Set([502, 503, 504]);" in javascript
    assert "Exporter backend is temporarily unavailable" in javascript
    assert "reverse proxy is restarting or unreachable" in javascript
    assert "const retryTransient = retryTransientOption ?? method === \"GET\";" in javascript
    assert "Connection failed. Check the host address, network path, and TLS settings." not in javascript

    count_start = javascript.index('const countResult = await api("/api/query/count"')
    count_block = javascript[count_start:count_start + 260]
    assert "retryTransient: true" in count_block

    preview_start = javascript.index('const result = await api("/api/query/preview"')
    preview_block = javascript[preview_start:preview_start + 260]
    assert "retryTransient: true" in preview_block

    connection_start = javascript.index('const result = await api("/api/connection/test"')
    connection_block = javascript[connection_start:connection_start + 320]
    assert "retryTransient: true" in connection_block

    create_start = javascript.index('const result = await api("/api/export/jobs"')
    create_block = javascript[create_start:create_start + 260]
    assert "retryTransient: true" not in create_block


def test_forget_session_clears_browser_memory_and_visible_connection_values():
    javascript = read("app/static/app.js")
    html = read("app/static/index.html")

    clear_start = javascript.index("function clearSavedConnection()")
    clear_end = javascript.index("function loadSavedConnection()", clear_start)
    clear_block = javascript[clear_start:clear_end]

    assert 'sessionStorage.removeItem(CONNECTION_SESSION_STORAGE_KEY);' in clear_block
    assert '$("host").value = "";' in clear_block
    assert '$("email").value = "";' in clear_block
    assert '$("token").value = "";' in clear_block
    assert 'invalidateTenantSelection("Test connection to load tenants");' in clear_block
    assert '"Session forgotten. Host, credential, tenant, and connection results were cleared from this page."' in clear_block
    assert "Current form values are unchanged." not in javascript

    assert ">Forget session</button>" in html
    assert "Forget session immediately clears them from this page" in html


def test_export_without_preview_uses_count_preflight_result():
    javascript = read("app/static/app.js")

    run_start = javascript.index("async function runExport()")
    run_end = javascript.index("function initialize()", run_start)
    run_block = javascript[run_start:run_end]

    assert "const matchedTotal = Number(countResult.total || 0);" in run_block
    assert "state.previewTotal = matchedTotal;" in run_block
    assert "updateSummary();" in run_block
    assert "${matchedTotal.toLocaleString()} records. Creating locked export job" in run_block
    assert "payload.matched_total = matchedTotal;" in run_block
    assert "${state.previewTotal.toLocaleString()} records. Creating export job" not in run_block


def test_adaptive_export_defaults_and_progress_are_visible():
    javascript = read("app/static/app.js")
    html = read("app/static/index.html")

    assert 'id="targetRecords" type="number" min="100" max="50000" value="1000"' in html
    assert '$("targetRecords").value = "1000";' in javascript
    assert 'target_records_per_slice: Number($("targetRecords").value || 1000)' in javascript
    assert "Enabled · source/day partition + target+1 probe" in javascript
    assert 'id="progressSource">—</strong>' in html
    assert 'id="progressPartition">0 / 0</strong>' in html
    assert 'id="progressAdaptiveSplits">0</strong>' in html
    assert 'status.current_source || "—"' in javascript
    assert 'status.adaptive_split_count || 0' in javascript
    assert "Current slice" in html
    assert "windows of at most 24 hours" in html


def test_remembered_session_revalidates_and_restores_saved_tenant_automatically():
    javascript = read("app/static/app.js")
    html = read("app/static/index.html")

    restore_start = javascript.index("async function restoreSavedConnectionTenant()")
    restore_end = javascript.index("function loadSavedConnection()", restore_start)
    restore_block = javascript[restore_start:restore_end]

    assert 'const expectedTenantId = state.savedTenantId;' in restore_block
    assert 'const result = await api("/api/connection/test"' in restore_block
    assert "retryTransient: true" in restore_block
    assert "renderTenants(result.tenants || []);" in restore_block
    assert "selectedTenantId() === expectedTenantId" in restore_block
    assert "restored automatically" in restore_block

    load_start = javascript.index("function loadSavedConnection()")
    load_end = javascript.index("function updateSummary()", load_start)
    load_block = javascript[load_start:load_end]
    assert "state.savedTenantId = saved.tenant_id ||" in load_block
    assert "state.savedTenantName = saved.tenant_name ||" in load_block
    assert "void restoreSavedConnectionTenant();" in load_block
    assert "Test connection to restore tenant" not in load_block

    assert "selected tenant only in the current browser session" in html
    assert "tenant is revalidated and restored automatically" in html
    assert "Browser-session connection" in html
    assert "Interactive connection credentials are never stored on the Exporter server" in html
    assert "Encrypted saved connection" not in html


def test_browser_locks_export_configuration_for_active_export():
    javascript = read("app/static/app.js")
    stylesheet = read("app/static/styles.css")

    assert 'const EXPORT_CONFIGURATION_SCOPE = ".content > .card:not(.final-action-card):not(.export-history-card)";' in javascript
    assert "function setExportConfigurationLocked(locked)" in javascript
    assert 'card.querySelectorAll("input, select, textarea, button")' in javascript
    assert 'setControlExportLocked($("basicMode"), locked)' not in javascript
    assert '[$("basicMode"), $("advancedMode")]' in javascript

    run_start = javascript.index("async function runExport()")
    run_end = javascript.index("function defaultSourceId", run_start)
    run_block = javascript[run_start:run_end]
    assert "const payload = exportPayload();" in run_block
    assert "const countPayload = basePayload();" in run_block
    assert "setExportConfigurationLocked(true);" in run_block
    assert "body: JSON.stringify(countPayload)" in run_block
    assert "else if (!jobStarted && configurationLocked)" in run_block
    assert "finishActiveExport();" in run_block
    assert "activateExport({" in run_block

    resume_start = javascript.index("async function resumeExport(")
    resume_end = javascript.index("function renderExportPreflight", resume_start)
    resume_block = javascript[resume_start:resume_end]
    assert "setExportConfigurationLocked(true);" in resume_block
    assert "else if (!jobStarted && configurationLocked)" in resume_block
    assert "finishActiveExport();" in resume_block

    assert ".configuration-locked::after" in stylesheet
    assert 'content:"LOCKED"' in stylesheet
    assert "ACTIVE_EXPORT_SESSION_STORAGE_KEY" in javascript
    assert "async function restoreActiveExportSession()" in javascript
    assert "void restoreActiveExportSession();" in javascript
    assert "function exportProgressValues(status)" in javascript
    assert 'id="exportProgressMeter"' in read("app/static/index.html")
    assert "function startCountPreflightTimer(button)" in javascript
    assert "Large ranges can take several minutes" in javascript
