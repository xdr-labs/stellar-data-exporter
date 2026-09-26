import asyncio

import asyncssh
import pytest

import app.destinations as destinations
from app.destinations import (
    _sftp_connect_kwargs,
    build_s3_key,
    build_sftp_path,
    sftp_known_hosts_entry,
    upload_s3,
)
from app.main import safe_filename
from app.models import S3Destination, SFTPDestination


class FakeS3:
    def __init__(self):
        self.puts = []
        self.created = []
        self.parts = []
        self.completed = []
        self.aborted = []

    def put_object(self, **kwargs):
        self.puts.append(kwargs)
        return {}

    def create_multipart_upload(self, **kwargs):
        self.created.append(kwargs)
        return {"UploadId": "upload-1"}

    def upload_part(self, **kwargs):
        self.parts.append(kwargs)
        return {"ETag": f"etag-{kwargs['PartNumber']}"}

    def complete_multipart_upload(self, **kwargs):
        self.completed.append(kwargs)
        return {}

    def abort_multipart_upload(self, **kwargs):
        self.aborted.append(kwargs)
        return {}


def s3_destination():
    return S3Destination(
        bucket="exports",
        prefix="stellar/day1",
        access_key="access",
        secret_key="secret",
    )


async def bytes_stream(*chunks):
    for chunk in chunks:
        yield chunk


def test_destination_path_helpers_and_filename():
    assert build_s3_key("/a/b/", "x.json") == "a/b/x.json"
    assert build_sftp_path("/exports", "x.csv") == "/exports/x.csv"
    assert safe_filename("alerts.json.gz", "json", True) == "alerts.json.gz"
    assert safe_filename("alerts", "csv", False) == "alerts.csv"


@pytest.mark.asyncio
async def test_small_s3_export_uses_put_object(monkeypatch):
    fake = FakeS3()
    monkeypatch.setattr(destinations, "_s3_client", lambda _: fake)

    result = await upload_s3(
        s3_destination(),
        "alerts.json",
        bytes_stream(b"one", b"two"),
        content_type="application/json",
    )

    assert result == "s3://exports/stellar/day1/alerts.json"
    assert len(fake.puts) == 1
    assert fake.puts[0]["Body"] == b"onetwo"
    assert not fake.created


@pytest.mark.asyncio
async def test_large_s3_export_uses_multipart(monkeypatch):
    fake = FakeS3()
    monkeypatch.setattr(destinations, "_s3_client", lambda _: fake)
    monkeypatch.setattr(destinations, "S3_PART_SIZE", 4)

    result = await upload_s3(
        s3_destination(),
        "alerts.csv",
        bytes_stream(b"abc", b"def", b"ghi"),
        content_type="text/csv",
    )

    assert result.endswith("/alerts.csv")
    assert len(fake.created) == 1
    assert [part["Body"] for part in fake.parts] == [b"abcd", b"efgh", b"i"]
    assert len(fake.completed) == 1


@pytest.mark.asyncio
async def test_cancelled_multipart_s3_export_aborts_upload(monkeypatch):
    fake = FakeS3()
    monkeypatch.setattr(destinations, "_s3_client", lambda _: fake)
    monkeypatch.setattr(destinations, "S3_PART_SIZE", 4)
    checks = 0

    def cancelled():
        nonlocal checks
        checks += 1
        return checks >= 2

    with pytest.raises(asyncio.CancelledError):
        await upload_s3(
            s3_destination(),
            "cancelled.csv",
            bytes_stream(b"abcd", b"efgh"),
            content_type="text/csv",
            cancel_check=cancelled,
        )

    assert len(fake.created) == 1
    assert len(fake.parts) == 1
    assert len(fake.aborted) == 1
    assert not fake.completed


def test_sftp_known_hosts_entry_uses_openssh_host_format():
    key = asyncssh.generate_private_key("ssh-ed25519").export_public_key("openssh").decode().strip()
    assert sftp_known_hosts_entry("sftp.example.test", 22, key) == f"sftp.example.test {key}"
    assert sftp_known_hosts_entry("sftp.example.test", 2222, key) == f"[sftp.example.test]:2222 {key}"


def test_sftp_pinned_host_key_is_used_for_connection():
    key = asyncssh.generate_private_key("ssh-ed25519").export_public_key("openssh").decode().strip()
    destination = SFTPDestination(
        host="sftp.example.test",
        port=22,
        username="alice",
        auth_method="password",
        password="secret",
        remote_path="/exports",
        verify_host_key=True,
        server_host_key=key,
    )

    kwargs = _sftp_connect_kwargs(destination)

    assert kwargs["host"] == "sftp.example.test"
    assert kwargs["password"] == "secret"
    assert kwargs["known_hosts"] is not None


def test_sftp_pinned_host_key_builds_known_hosts_verifier():
    public_key = (
        "ssh-ed25519 "
        "AAAAC3NzaC1lZDI1NTE5AAAAICL8fIuM1nXvHkG5Jv6AAoSk2gYQ0jL8d1E2n3T4u5V6"
    )
    entry = sftp_known_hosts_entry("sftp.example.test", 2222, public_key)
    assert entry.startswith("[sftp.example.test]:2222 ssh-ed25519 ")

    destination = SFTPDestination(
        host="sftp.example.test",
        port=2222,
        username="exporter",
        auth_method="password",
        password="test-password",
        remote_path="/exports",
        verify_host_key=True,
        server_host_key=public_key,
    )
    kwargs = _sftp_connect_kwargs(destination)
    assert kwargs["host"] == "sftp.example.test"
    assert kwargs["port"] == 2222
    assert kwargs["known_hosts"] is not None


def test_sftp_without_host_key_verification_explicitly_disables_known_hosts():
    destination = SFTPDestination(
        host="sftp.example.test",
        username="exporter",
        auth_method="password",
        password="test-password",
        remote_path="/exports",
        verify_host_key=False,
    )
    assert _sftp_connect_kwargs(destination)["known_hosts"] is None
