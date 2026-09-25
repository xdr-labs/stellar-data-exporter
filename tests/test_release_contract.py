from pathlib import Path
import subprocess


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
    (dist / "stellar_data_exporter-0.1.0-py3-none-any.whl").write_bytes(b"wheel")
    (dist / "stellar_data_exporter-0.1.0.tar.gz").write_bytes(b"sdist")
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
