"""Durable artifact storage for deployed spawnd runs."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlparse
from uuid import uuid4

from spawnd.config import ArtifactStorageConfig
from spawnd.artifacts.redaction import redact_freeform_text, stable_hash


@dataclass(frozen=True)
class ArtifactBlob:
    """Stored artifact metadata."""

    uri: str
    sha256: str
    size_bytes: int
    content_type: str
    redaction_policy: str


class ArtifactNotFoundError(KeyError):
    """Raised when artifact metadata points to an object that is not present."""


class ArtifactStore(Protocol):
    def put_text(self, key: str, text: str, *, content_type: str = "text/plain") -> ArtifactBlob:
        raise NotImplementedError

    def get_text(self, uri: str) -> str:
        raise NotImplementedError

    def iter_bytes(self, uri: str, *, chunk_size: int = 64 * 1024) -> Iterable[bytes]:
        raise NotImplementedError


class S3ArtifactStore:
    """S3 API artifact store."""

    def __init__(self, config: ArtifactStorageConfig) -> None:
        if not config.bucket:
            raise ValueError('SPAWND_ARTIFACTS_BUCKET is required for S3 artifact storage')
        import boto3

        self.config = config
        self.client = boto3.client(
            's3',
            endpoint_url=config.endpoint,
            region_name=config.region,
        )

    def put_text(self, key: str, text: str, *, content_type: str = 'text/plain') -> ArtifactBlob:
        data = text.encode('utf-8')
        full_key = '/'.join(part for part in [self.config.prefix, key.lstrip('/')] if part)
        self.client.put_object(Bucket=self.config.bucket, Key=full_key, Body=data, ContentType=content_type)
        return ArtifactBlob(
            uri=f's3://{self.config.bucket}/{full_key}',
            sha256=stable_hash(data),
            size_bytes=len(data),
            content_type=content_type,
            redaction_policy='redacted',
        )

    def get_text(self, uri: str) -> str:
        return b"".join(self.iter_bytes(uri)).decode("utf-8")

    def iter_bytes(self, uri: str, *, chunk_size: int = 64 * 1024) -> Iterable[bytes]:
        parsed = urlparse(uri)
        if parsed.scheme != "s3" or parsed.netloc != self.config.bucket:
            raise ValueError(f"Artifact URI is not in configured bucket: {uri}")
        key = parsed.path.lstrip("/")
        from botocore.exceptions import ClientError

        try:
            response = self.client.get_object(Bucket=self.config.bucket, Key=key)
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code in {"404", "NoSuchKey", "NoSuchVersion"}:
                raise ArtifactNotFoundError(uri) from exc
            raise
        body = response["Body"]

        def chunks() -> Iterable[bytes]:
            try:
                while chunk := body.read(chunk_size):
                    yield chunk
            finally:
                body.close()

        return chunks()


class InMemoryArtifactStore:
    """Test artifact store."""

    def __init__(self) -> None:
        self.objects: dict[str, str] = {}

    def put_text(self, key: str, text: str, *, content_type: str = 'text/plain') -> ArtifactBlob:
        self.objects[key] = text
        data = text.encode('utf-8')
        return ArtifactBlob(
            uri=f'memory://{key}',
            sha256=stable_hash(data),
            size_bytes=len(data),
            content_type=content_type,
            redaction_policy='redacted',
        )

    def get_text(self, uri: str) -> str:
        return b"".join(self.iter_bytes(uri)).decode("utf-8")

    def iter_bytes(self, uri: str, *, chunk_size: int = 64 * 1024) -> Iterable[bytes]:
        parsed = urlparse(uri)
        if parsed.scheme != "memory":
            raise ValueError(f"Unsupported in-memory artifact URI: {uri}")
        key = parsed.netloc + parsed.path
        if key.startswith("/"):
            key = key[1:]
        try:
            data = self.objects[key].encode("utf-8")
        except KeyError as exc:
            raise ArtifactNotFoundError(uri) from exc
        return (data[offset:offset + chunk_size] for offset in range(0, len(data), chunk_size))


def artifact_key(run_id: str, agent: str | None, kind: str, suffix: str = 'txt') -> str:
    agent_part = agent or '_system'
    return f'runs/{run_id}/{agent_part}/{kind}-{uuid4().hex}.{suffix}'


def store_redacted_text_artifact(
    store: ArtifactStore,
    *,
    run_id: str,
    agent: str | None,
    kind: str,
    text: str,
    capture_raw: bool = False,
    content_type: str = 'text/plain',
) -> ArtifactBlob:
    """Store raw text only when explicitly allowed; otherwise store redacted text."""

    body = text if capture_raw else redact_freeform_text(text)
    policy = 'raw' if capture_raw else 'redacted'
    blob = store.put_text(artifact_key(run_id, agent, kind), body, content_type=content_type)
    return ArtifactBlob(
        uri=blob.uri,
        sha256=blob.sha256,
        size_bytes=blob.size_bytes,
        content_type=blob.content_type,
        redaction_policy=policy,
    )
