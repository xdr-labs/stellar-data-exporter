import asyncio

import pytest

import app.destinations as destinations
from app.destinations import build_s3_key, build_sftp_path, upload_s3
from app.main import safe_filename
from app.models import S3Destination


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
