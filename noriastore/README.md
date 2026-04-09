# `noriastore`

Configurable object storage client for S3-compatible providers, with first-class support for AWS S3 and Cloudflare R2.

The package gives you a single Python API for:

- storing objects
- reading object metadata
- deleting objects
- creating presigned upload and download URLs
- generating public URLs
- customizing key resolution and URL generation
- normalizing storage failures into one error type

## Install

```bash
pip install noriastore
```

Python requirement: `>=3.11`

## Main Exports

```python
from noriastore import (
    DEFAULT_DOWNLOAD_EXPIRES_IN,
    DEFAULT_R2_REGION,
    DEFAULT_S3_REGION,
    DEFAULT_UPLOAD_EXPIRES_IN,
    MAX_PRESIGN_EXPIRES_IN,
    DeleteObjectResult,
    HeadObjectResult,
    PresignedRequest,
    PutObjectResult,
    ResolvedStoragePublicUrlInput,
    StorageClient,
    StorageError,
    StorageObjectDescriptor,
    StorageOperationContext,
    create_storage_client,
    join_storage_key,
)
```

## Quick Start

```python
from noriastore import StorageClient

storage = StorageClient(
    bucket="documents",
    region="eu-west-1",
    key_prefix="tenant-a",
    public_base_url="https://cdn.example.com",
)

result = storage.put_object(
    key=["invoices", "march-2026.pdf"],
    body=b"hello",
    content_type="application/pdf",
    metadata={"source": "admin"},
)

upload = storage.create_presigned_upload_url(
    key=["uploads", "avatar.png"],
    content_type="image/png",
)
```

## Constructor

```python
storage = StorageClient(
    bucket="documents",
    provider="s3",
    region="eu-west-1",
    endpoint=None,
    account_id=None,
    credentials=None,
    public_base_url="https://cdn.example.com",
    key_prefix="tenant-a",
    force_path_style=None,
    url_style=None,
    default_metadata={"source": "api"},
    default_tags={"project": "noria"},
    default_content_type="application/octet-stream",
    default_cache_control=None,
    default_content_disposition=None,
    default_content_encoding=None,
    default_content_language=None,
    default_upload_expires_in=900,
    default_download_expires_in=3600,
    client=None,
    presign_url=None,
    s3_client_config=None,
    resolve_key=None,
    build_public_url=None,
)
```

### Constructor Options

- `bucket`: required default bucket
- `provider`: `s3` or `r2`, default `s3`
- `region`: optional; defaults depend on provider
- `endpoint`: optional explicit S3-compatible endpoint
- `account_id`: optional; used to derive the R2 endpoint when `provider="r2"`
- `credentials`: optional mapping with `access_key_id`, `secret_access_key`, `session_token`
- `public_base_url`: optional base URL used when building public URLs
- `key_prefix`: optional prefix prepended to every key
- `force_path_style`: legacy-style addressing switch
- `url_style`: explicit addressing style, `path` or `virtual-hosted`
- `default_metadata`: default object metadata merged into uploads
- `default_tags`: default object tags merged into uploads
- `default_content_type`
- `default_cache_control`
- `default_content_disposition`
- `default_content_encoding`
- `default_content_language`
- `default_upload_expires_in`: default `900`
- `default_download_expires_in`: default `3600`
- `client`: optional prebuilt boto S3 client
- `presign_url`: optional custom presign function
- `s3_client_config`: optional boto client options
- `resolve_key`: optional hook for custom key rewriting
- `build_public_url`: optional hook for custom public URL generation

There is also a convenience alias:

```python
from noriastore import create_storage_client

storage = create_storage_client(bucket="documents")
```

## Provider Defaults

### AWS S3 Defaults

- `provider="s3"`
- default region: `us-east-1`
- default URL style: `virtual-hosted`

### Cloudflare R2 Defaults

- `provider="r2"`
- default region: `auto`
- default URL style: `path`
- if `account_id` is set and `endpoint` is not, the endpoint becomes:

```text
https://{account_id}.r2.cloudflarestorage.com
```

## Key Normalization

Keys can be passed as:

- a plain string
- a list or tuple of string segments
- nested sequences of string segments

Use `join_storage_key()` when you want the same normalization outside the client:

```python
from noriastore import join_storage_key

key = join_storage_key(" invoices/ ", ["2026", "/march/"], "statement.pdf")
# invoices/2026/march/statement.pdf
```

Normalization rules:

- strips surrounding whitespace
- strips leading and trailing `/` from each segment
- joins segments with `/`
- ignores non-string nested values
- raises `TypeError` when the final key is empty for an operation that requires one

## Operations

### `put_object()`

```python
result = storage.put_object(
    key="exports/data.json",
    body='{"ok": true}',
    metadata={"source": "dashboard"},
    tags={"env": "prod", "kind": "report"},
    content_type="application/json",
    cache_control="public, max-age=300",
    content_disposition="inline",
    content_encoding="gzip",
    content_language="en",
    content_md5=None,
    expires=None,
    public_url=True,
    command_input=None,
)
```

`put_object()` returns a `PutObjectResult` with:

- `bucket`
- `key`
- `provider`
- `public_url`
- `etag`
- `version_id`
- `checksum_crc32`
- `checksum_crc32c`
- `checksum_sha1`
- `checksum_sha256`

Behavior:

- `key_prefix` is applied before the request is built
- `resolve_key` runs after prefixing
- metadata and tags merge defaults with per-call values
- explicit method arguments override `command_input`
- `command_input` overrides constructor defaults

### `head_object()`

```python
result = storage.head_object(
    key="images/logo.png",
    not_found="null",
    public_url=True,
    command_input=None,
)
```

`head_object()` returns `HeadObjectResult | None`.

`HeadObjectResult` includes:

- `bucket`
- `key`
- `provider`
- `public_url`
- `exists`
- `etag`
- `version_id`
- `last_modified`
- `expires_at`
- `content_length`
- `content_type`
- `cache_control`
- `content_disposition`
- `content_encoding`
- `content_language`
- `metadata`
- `raw`

`not_found` behavior:

- `not_found="null"` returns `None`
- `not_found="error"` raises `StorageError`

### `object_exists()`

```python
exists = storage.object_exists(key="images/logo.png")
```

This is a convenience wrapper over `head_object(..., not_found="null", public_url=False)`.

### `delete_object()`

```python
result = storage.delete_object(
    key="private/report.pdf",
    public_url=False,
    command_input=None,
)
```

Returns `DeleteObjectResult` with:

- `bucket`
- `key`
- `provider`
- `public_url`
- `version_id`
- `delete_marker`
- `raw`

### `create_presigned_upload_url()`

```python
request = storage.create_presigned_upload_url(
    key="avatars/user-1.png",
    expires_in=600,
    metadata={"uploadedBy": "admin"},
    tags={"kind": "avatar"},
    content_type="image/png",
    command_input={"ACL": "public-read"},
)
```

Returns `PresignedRequest` with:

- `bucket`
- `key`
- `provider`
- `public_url`
- `method`
- `url`
- `headers`
- `expires_in`
- `expires_at`

Upload requests always return:

- `method == "PUT"`

The returned `headers` include any upload headers that the signed request expects, including:

- standard content headers
- `x-amz-meta-*` metadata headers
- ACL and encryption headers from `command_input`
- checksum headers from `command_input`

### `create_presigned_download_url()`

```python
request = storage.create_presigned_download_url(
    key=["reports", "march report.pdf"],
    expires_in=60,
)
```

Returns a `PresignedRequest` with:

- `method == "GET"`
- empty `headers`
- `expires_in` and `expires_at`

### `create_public_url()`

```python
url = storage.create_public_url("images/logo.png")
```

Public URL generation uses this precedence:

1. `build_public_url` hook
2. `public_base_url`
3. explicit `endpoint`
4. built-in AWS S3 URL rules
5. built-in R2 URL rules when enough information exists

If a storage operation sets `public_url=True` but URL generation fails, the operation still succeeds and returns `public_url=None`.

Calling `create_public_url()` directly is stricter: failures are wrapped as `StorageError`.

## Customization Hooks

### `resolve_key`

Use `resolve_key` to transform every normalized key before requests are sent:

```python
from noriastore import StorageClient

storage = StorageClient(
    bucket="documents",
    key_prefix=["tenant-a", "uploads"],
    resolve_key=lambda key, ctx: f"v1/{key}",
)
```

The hook receives:

- `key`: normalized key after `key_prefix` has been applied
- `ctx`: `StorageOperationContext(operation, bucket, provider)`

Available `StorageOperationContext` fields:

- `operation`
- `bucket`
- `provider`

### `build_public_url`

Use `build_public_url` when the built-in URL rules do not match your CDN or proxy layout:

```python
storage = StorageClient(
    bucket="assets",
    build_public_url=lambda resolved: (
        f"https://cdn.example.com/{resolved.provider}/{resolved.bucket}/{resolved.key}"
    ),
)
```

The hook receives `ResolvedStoragePublicUrlInput` with:

- `bucket`
- `key`
- `provider`
- `region`
- `endpoint`
- `account_id`
- `url_style`
- `public_base_url`

### `client`

Inject a custom boto client when you want full control over transport, credentials, or tests:

```python
storage = StorageClient(bucket="assets", client=my_boto_client)
```

### `presign_url`

Inject a custom presigner when you need to route signing through your own code:

```python
storage = StorageClient(
    bucket="assets",
    presign_url=lambda client, operation, params, expires_in: "https://signed.example.com",
    client=my_boto_client,
)
```

### `s3_client_config`

Pass boto `session.client("s3", ...)` options through `s3_client_config`.

Use this for lower-level client options such as retry configuration, endpoint options, or a custom `botocore.config.Config`.

## Metadata, Tags, and Command Overrides

Per-call upload inputs are merged like this:

1. constructor defaults
2. `command_input`
3. explicit method arguments

Examples:

- `default_metadata={"source": "api"}` merged with `metadata={"source": "dashboard"}` gives `{"source": "dashboard"}`
- `default_tags={"project": "noria"}` merged with `tags={"env": "prod"}` includes both
- `content_type="image/png"` overrides both `command_input["ContentType"]` and `default_content_type`

Tags are URL encoded into the S3 `Tagging` request field.

## Public URL Rules

### `public_base_url`

```python
storage = StorageClient(
    bucket="assets",
    key_prefix="tenant-a",
    public_base_url="https://cdn.example.com/base/",
)

storage.create_public_url(["documents", "report.pdf"])
# https://cdn.example.com/base/tenant-a/documents/report.pdf
```

### Explicit Endpoint

Path style:

```python
storage = StorageClient(
    bucket="assets",
    endpoint="https://objects.example.com/root/",
    url_style="path",
)
```

Produces:

```text
https://objects.example.com/root/assets/images/logo.png
```

Virtual-hosted style:

```python
storage = StorageClient(
    bucket="assets",
    endpoint="https://objects.example.com/root/",
    url_style="virtual-hosted",
)
```

Produces:

```text
https://assets.objects.example.com/root/images/logo.png
```

### AWS S3 Built-in URLs

`us-east-1` virtual-hosted:

```text
https://bucket.s3.amazonaws.com/key
```

Regional path style:

```text
https://s3.eu-west-1.amazonaws.com/bucket/key
```

Regional virtual-hosted:

```text
https://bucket.s3.eu-west-1.amazonaws.com/key
```

### Cloudflare R2 Built-in URLs

R2 public URL generation requires one of:

- `public_base_url`
- `endpoint`
- `account_id`
- `build_public_url`

If none of those exist, `create_public_url()` raises a wrapped error.

## Error Handling

All normalized failures raise `StorageError`.

`StorageError` fields:

- `code`
- `operation`
- `provider`
- `bucket`
- `key`
- `status_code`
- `retryable`
- `details`
- `cause`

Error codes by operation:

- `putObject` -> `STORAGE_PUT_FAILED`
- `headObject` -> `STORAGE_HEAD_FAILED`
- `deleteObject` -> `STORAGE_DELETE_FAILED`
- `createPresignedUploadUrl` -> `STORAGE_PRESIGN_UPLOAD_FAILED`
- `createPresignedDownloadUrl` -> `STORAGE_PRESIGN_DOWNLOAD_FAILED`
- `createPublicUrl` -> `STORAGE_PUBLIC_URL_FAILED`

Retry behavior:

- `retryable=True` when status is `None`, `429`, or `>= 500`
- `retryable=False` for typical client errors such as `400` and `403`

Existing `StorageError` instances are passed through without being wrapped again.

## Expiry Rules

Constants:

- `DEFAULT_UPLOAD_EXPIRES_IN = 900`
- `DEFAULT_DOWNLOAD_EXPIRES_IN = 3600`
- `MAX_PRESIGN_EXPIRES_IN = 604800`
- `DEFAULT_S3_REGION = "us-east-1"`
- `DEFAULT_R2_REGION = "auto"`

Validation:

- expiry values must be positive integers
- expiry values must not exceed `604800` seconds

## Common Usage Patterns

### AWS S3

```python
storage = StorageClient(
    bucket="media",
    provider="s3",
    region="eu-west-1",
)
```

### Cloudflare R2

```python
storage = StorageClient(
    bucket="assets",
    provider="r2",
    account_id="acc-123",
)
```

### Fixed CDN URL Base

```python
storage = StorageClient(
    bucket="assets",
    public_base_url="https://cdn.example.com",
)
```

### Test Double Client

```python
class MockClient:
    def put_object(self, **kwargs): ...
    def head_object(self, **kwargs): ...
    def delete_object(self, **kwargs): ...
    def generate_presigned_url(self, operation_name, *, Params, ExpiresIn): ...

storage = StorageClient(bucket="assets", client=MockClient())
```

## Notes and Caveats

- `provider` is a free string internally, but the built-in defaults and URL rules are only defined for `s3` and `r2`
- direct `create_public_url()` calls fail fast when configuration is incomplete
- regular object operations degrade gracefully to `public_url=None` if public URL generation fails
- non-string nested key parts are ignored during key normalization
- datetime metadata such as `LastModified` and `Expires` are normalized to UTC ISO strings when present

## Development

Run tests:

```bash
uv sync --extra dev
uv run pytest
```

Run lint:

```bash
uv run ruff check .
```
