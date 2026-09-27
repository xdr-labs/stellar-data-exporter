from pathlib import Path
import subprocess

from app import __version__


ROOT = Path(__file__).resolve().parents[1]
BASELINE = "c16edb8c2a86f194f21c5ba16e5f75673a15ba5c"


def read(relative: str) -> str:
    return (ROOT / relative).read_text()


def test_release_profile_requires_preflight_and_artifact_hashes():
    profile = read(".engineering/release.yaml")

    assert "exact_head_required: true" in profile
    assert "preflight_required: true" in profile
    assert "artifact_hash_required: true" in profile
    assert 'preflight_command: "scripts/release-preflight.sh"' in profile
    assert 'qualification_command: "scripts/release-qualify.sh dist"' in profile
    assert (
        'artifact_hash_command: "scripts/hash-release-artifacts.sh dist dist/SHA256SUMS"'
        in profile
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
    assert "clears Host, credential, tenant, and connection results from this page" in html


def test_export_without_preview_uses_count_preflight_result():
    javascript = read("app/static/app.js")

    run_start = javascript.index("async function runExport()")
    run_end = javascript.index("function initialize()", run_start)
    run_block = javascript[run_start:run_end]

    assert "const matchedTotal = Number(countResult.total || 0);" in run_block
    assert "state.previewTotal = matchedTotal;" in run_block
    assert "updateSummary();" in run_block
    assert "${matchedTotal.toLocaleString()} records. Creating export job" in run_block
    assert "${state.previewTotal.toLocaleString()} records. Creating export job" not in run_block
