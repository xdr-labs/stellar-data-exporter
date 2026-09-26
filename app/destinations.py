from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from pathlib import PurePosixPath

import asyncssh
import boto3
from botocore.config import Config

from .models import S3Destination, SFTPDestination


ProgressCallback = Callable[[int], None]
CancelCheck = Callable[[], bool]
S3_PART_SIZE = 8 * 1024 * 1024


def _s3_client(destination: S3Destination):
    addressing = "path" if destination.force_path_style else "auto"
    return boto3.client(
        "s3",
        endpoint_url=destination.endpoint_url or None,
        region_name=destination.region or None,
        aws_access_key_id=destination.access_key,
        aws_secret_access_key=destination.secret_key,
        aws_session_token=destination.session_token or None,
        config=Config(signature_version="s3v4", s3={"addressing_style": addressing}),
    )


def build_s3_key(prefix: str, filename: str) -> str:
    clean_prefix = prefix.strip("/")
    return f"{clean_prefix}/{filename}" if clean_prefix else filename


def build_sftp_path(remote_path: str, filename: str) -> str:
    return str(PurePosixPath(remote_path) / filename)


async def test_s3(destination: S3Destination) -> None:
    client = _s3_client(destination)
    await asyncio.to_thread(client.head_bucket, Bucket=destination.bucket)


async def upload_s3(
    destination: S3Destination,
    filename: str,
    stream: AsyncIterator[bytes],
    *,
    content_type: str,
    content_encoding: str | None = None,
    on_bytes: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
) -> str:
    client = _s3_client(destination)
    key = build_s3_key(destination.prefix, filename)
    object_args = {"ContentType": content_type}
    if content_encoding:
        object_args["ContentEncoding"] = content_encoding

    buffer = bytearray()
    upload_id: str | None = None
    parts: list[dict[str, object]] = []
    part_number = 1

    try:
        async for chunk in stream:
            if cancel_check and cancel_check():
                raise asyncio.CancelledError
            buffer.extend(chunk)
            if on_bytes:
                on_bytes(len(chunk))

            if upload_id is None and len(buffer) >= S3_PART_SIZE:
                created = await asyncio.to_thread(
                    client.create_multipart_upload,
                    Bucket=destination.bucket,
                    Key=key,
                    **object_args,
                )
                upload_id = created["UploadId"]

            while upload_id is not None and len(buffer) >= S3_PART_SIZE:
                part = bytes(buffer[:S3_PART_SIZE])
                del buffer[:S3_PART_SIZE]
                response = await asyncio.to_thread(
                    client.upload_part,
                    Bucket=destination.bucket,
                    Key=key,
                    UploadId=upload_id,
                    PartNumber=part_number,
                    Body=part,
                )
                parts.append({"ETag": response["ETag"], "PartNumber": part_number})
                part_number += 1

        if cancel_check and cancel_check():
            raise asyncio.CancelledError

        if upload_id is None:
            await asyncio.to_thread(
                client.put_object,
                Bucket=destination.bucket,
                Key=key,
                Body=bytes(buffer),
                **object_args,
            )
        else:
            if buffer:
                response = await asyncio.to_thread(
                    client.upload_part,
                    Bucket=destination.bucket,
                    Key=key,
                    UploadId=upload_id,
                    PartNumber=part_number,
                    Body=bytes(buffer),
                )
                parts.append({"ETag": response["ETag"], "PartNumber": part_number})

            if cancel_check and cancel_check():
                raise asyncio.CancelledError

            await asyncio.to_thread(
                client.complete_multipart_upload,
                Bucket=destination.bucket,
                Key=key,
                UploadId=upload_id,
                MultipartUpload={"Parts": parts},
            )
    except BaseException:
        if upload_id is not None:
            try:
                await asyncio.to_thread(
                    client.abort_multipart_upload,
                    Bucket=destination.bucket,
                    Key=key,
                    UploadId=upload_id,
                )
            except Exception:
                pass
        raise

    return f"s3://{destination.bucket}/{key}"


def sftp_known_hosts_entry(host: str, port: int, public_key: str) -> str:
    target = host if port == 22 else f"[{host}]:{port}"
    return f"{target} {public_key.strip()}"


async def get_sftp_host_key(host: str, port: int) -> dict[str, str]:
    key = await asyncssh.get_server_host_key(host, port)
    if key is None:
        raise RuntimeError("The SFTP server did not present an SSH host key.")
    public_key = key.export_public_key("openssh").decode("utf-8").strip()
    return {
        "algorithm": key.algorithm.decode("ascii") if isinstance(key.algorithm, bytes) else str(key.algorithm),
        "fingerprint": key.get_fingerprint("sha256"),
        "public_key": public_key,
    }


def _sftp_connect_kwargs(destination: SFTPDestination) -> dict:
    kwargs = {
        "host": destination.host,
        "port": destination.port,
        "username": destination.username,
    }

    if not destination.verify_host_key:
        kwargs["known_hosts"] = None
    elif destination.server_host_key:
        entry = sftp_known_hosts_entry(
            destination.host,
            destination.port,
            destination.server_host_key,
        )
        kwargs["known_hosts"] = asyncssh.import_known_hosts(entry)

    if destination.auth_method == "password":
        kwargs["password"] = destination.password
    else:
        key = asyncssh.import_private_key(
            destination.private_key or "",
            passphrase=destination.private_key_passphrase,
        )
        kwargs["client_keys"] = [key]

    return kwargs


async def test_sftp(destination: SFTPDestination) -> None:
    try:
        async with asyncssh.connect(**_sftp_connect_kwargs(destination)) as connection:
            async with connection.start_sftp_client() as sftp:
                await sftp.stat(destination.remote_path)
    except asyncssh.HostKeyNotVerifiable as exc:
        raise RuntimeError(
            "SSH host key is not trusted. Use Get host key, verify the SHA256 fingerprint "
            "with the SFTP server administrator, trust that key, and test again."
        ) from exc


async def upload_sftp(
    destination: SFTPDestination,
    filename: str,
    stream: AsyncIterator[bytes],
    *,
    on_bytes: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
) -> str:
    remote_file = build_sftp_path(destination.remote_path, filename)
    async with asyncssh.connect(**_sftp_connect_kwargs(destination)) as connection:
        async with connection.start_sftp_client() as sftp:
            try:
                async with sftp.open(remote_file, "wb") as handle:
                    async for chunk in stream:
                        if cancel_check and cancel_check():
                            raise asyncio.CancelledError
                        await handle.write(chunk)
                        if on_bytes:
                            on_bytes(len(chunk))
                if cancel_check and cancel_check():
                    raise asyncio.CancelledError
            except BaseException:
                try:
                    await sftp.remove(remote_file)
                except Exception:
                    pass
                raise

    return f"sftp://{destination.host}:{destination.port}{remote_file}"
