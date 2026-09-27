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
