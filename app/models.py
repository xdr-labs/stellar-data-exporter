from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator


class ConnectionInput(BaseModel):
    host: HttpUrl
    email: str = Field(min_length=3)
    token: str = Field(min_length=1)
    verify_tls: bool = True
    test_index: str = "aella-ser-*"


class QueryInput(BaseModel):
    host: HttpUrl
    email: str = Field(min_length=3)
    token: str = Field(min_length=1)
    verify_tls: bool = True
    index: str = Field(min_length=1)
    time_field: str = Field(default="timestamp", min_length=1)
    start: datetime
    end: datetime
    query: dict[str, Any]
    preview_limit: int = Field(default=100, ge=1, le=500)
    target_records_per_slice: int = Field(default=5000, ge=100, le=50000)
    minimum_slice_ms: int = Field(default=1, ge=1, le=60000)

    @field_validator("end")
    @classmethod
    def validate_end(cls, end: datetime, info):
        start = info.data.get("start")
        if start is not None and end <= start:
            raise ValueError("end must be later than start")
        return end


class DownloadDestination(BaseModel):
    type: Literal["download"] = "download"


class S3Destination(BaseModel):
    type: Literal["s3"] = "s3"
    endpoint_url: str | None = None
    region: str | None = None
    bucket: str = Field(min_length=1)
    prefix: str = ""
    access_key: str = Field(min_length=1)
    secret_key: str = Field(min_length=1)
    session_token: str | None = None
    force_path_style: bool = False


class SFTPDestination(BaseModel):
    type: Literal["sftp"] = "sftp"
    host: str = Field(min_length=1)
    port: int = Field(default=22, ge=1, le=65535)
    username: str = Field(min_length=1)
    auth_method: Literal["password", "private_key"] = "private_key"
    password: str | None = None
    private_key: str | None = None
    private_key_passphrase: str | None = None
    remote_path: str = Field(default="/", min_length=1)
    verify_host_key: bool = True

    @model_validator(mode="after")
    def validate_auth(self):
        if self.auth_method == "password" and not self.password:
            raise ValueError("SFTP password is required")
        if self.auth_method == "private_key" and not self.private_key:
            raise ValueError("SFTP private key is required")
        return self


Destination = Annotated[
    DownloadDestination | S3Destination | SFTPDestination,
    Field(discriminator="type"),
]


class DestinationTestInput(BaseModel):
    destination: Destination


class ExportInput(QueryInput):
    format: Literal["csv", "json"] = "csv"
    compress: bool = False
    filename: str | None = None
    destination: Destination = Field(default_factory=DownloadDestination)
