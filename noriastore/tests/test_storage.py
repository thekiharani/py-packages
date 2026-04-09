from __future__ import annotations

from datetime import UTC, datetime

import pytest
from botocore.exceptions import ClientError

from noriastore import StorageClient, StorageError, create_storage_client, join_storage_key


class MockClient:
    def __init__(self, **handlers):
        self.handlers = handlers

    def put_object(self, **kwargs):
        return self.handlers["put_object"](**kwargs)

    def head_object(self, **kwargs):
        return self.handlers["head_object"](**kwargs)

    def delete_object(self, **kwargs):
        return self.handlers["delete_object"](**kwargs)

    def generate_presigned_url(self, operation_name, *, Params, ExpiresIn):
        return self.handlers["generate_presigned_url"](
            operation_name, Params=Params, ExpiresIn=ExpiresIn
        )


def test_storage_error_stores_metadata():
    with_cause = StorageError(
        "boom",
        code="STORAGE_TEST",
        operation="putObject",
        provider="s3",
        bucket="files",
        key="a.txt",
        retryable=True,
        details={"status": 500},
        cause=RuntimeError("upstream"),
    )
    without_cause = StorageError(
        "plain",
        code="STORAGE_TEST",
        operation="deleteObject",
        provider="r2",
    )
    assert with_cause.bucket == "files"
    assert with_cause.key == "a.txt"
    assert with_cause.retryable is True
    assert with_cause.details == {"status": 500}
    assert without_cause.retryable is False
    assert without_cause.details is None
    assert str(with_cause) == "boom"


def test_join_storage_key_normalizes_repeated_separators_and_arrays():
    assert (
        join_storage_key(" invoices/ ", ["2026", "/march/"], "statement.pdf")
        == "invoices/2026/march/statement.pdf"
    )
    assert join_storage_key("docs", object(), "file.txt") == "docs/file.txt"


def test_constructor_applies_default_provider_region_url_style_and_ttls():
    s3 = StorageClient(bucket="documents")
    r2 = StorageClient(bucket="documents", provider="r2", account_id="acct-1")
    forced_path = StorageClient(
        bucket="documents",
        force_path_style=True,
        default_upload_expires_in=60,
        default_download_expires_in=120,
    )
    assert s3.provider == "s3"
    assert s3.region == "us-east-1"
    assert s3.url_style == "virtual-hosted"
    assert r2.region == "auto"
    assert r2.url_style == "path"
    assert r2.endpoint == "https://acct-1.r2.cloudflarestorage.com"
    assert forced_path.url_style == "path"
    assert forced_path.default_upload_expires_in == 60
    assert forced_path.default_download_expires_in == 120


def test_constructor_validates_bucket_and_default_expiry_inputs():
    with pytest.raises(TypeError, match="Storage bucket is required"):
        StorageClient(bucket="   ")
    with pytest.raises(TypeError, match="default_upload_expires_in must be a positive integer"):
        StorageClient(bucket="files", default_upload_expires_in=0)
    with pytest.raises(
        ValueError, match="default_download_expires_in must not exceed 604800 seconds"
    ):
        StorageClient(bucket="files", default_download_expires_in=604801)


def test_put_object_applies_defaults_prefixes_tags_and_custom_key_resolution():
    sent = []
    client = create_storage_client(
        bucket="documents",
        key_prefix=["tenant-a", "uploads"],
        default_metadata={"visibility": "private", "source": "api"},
        default_tags={"project": "noria", "env": "test"},
        default_content_type="application/octet-stream",
        resolve_key=lambda key, _ctx: f"v1/{key}",
        public_base_url="https://cdn.example.com",
        client=MockClient(
            put_object=lambda **kwargs: (
                sent.append(kwargs)
                or {
                    "ETag": '"abc123"',
                    "VersionId": "3",
                    "ChecksumSHA256": "sum-1",
                }
            ),
        ),
    )
    result = client.put_object(
        key=["reports", "2026", "march.pdf"],
        body="file-contents",
        metadata={"source": "dashboard"},
        tags={"env": "prod", "kind": "invoice"},
    )
    assert sent[0] == {
        "Bucket": "documents",
        "Key": "v1/tenant-a/uploads/reports/2026/march.pdf",
        "Metadata": {"visibility": "private", "source": "dashboard"},
        "Tagging": "project=noria&env=prod&kind=invoice",
        "ContentType": "application/octet-stream",
        "Body": "file-contents",
    }
    assert result.key == "v1/tenant-a/uploads/reports/2026/march.pdf"
    assert result.public_url == "https://cdn.example.com/v1/tenant-a/uploads/reports/2026/march.pdf"
    assert result.checksum_sha256 == "sum-1"


def test_put_object_supports_raw_command_input_overrides_and_optional_public_url_suppression():
    sent = []
    client = StorageClient(
        bucket="files",
        default_cache_control="public, max-age=300",
        client=MockClient(put_object=lambda **kwargs: sent.append(kwargs) or {}),
    )
    result = client.put_object(
        key="exports/data.json",
        body='{"ok":true}',
        public_url=False,
        command_input={
            "ContentType": "application/json",
            "ChecksumAlgorithm": "SHA256",
            "ServerSideEncryption": "AES256",
        },
    )
    assert result.public_url is None
    assert sent[0]["ChecksumAlgorithm"] == "SHA256"
    assert sent[0]["ServerSideEncryption"] == "AES256"
    assert sent[0]["ContentType"] == "application/json"
    assert sent[0]["CacheControl"] == "public, max-age=300"


def test_put_object_wraps_upstream_failures_with_status_based_retryability():
    class BadRequestError(RuntimeError):
        status_code = 400

    client = StorageClient(
        bucket="files",
        client=MockClient(
            put_object=lambda **_kwargs: (_ for _ in ()).throw(BadRequestError("bad request"))
        ),
    )
    with pytest.raises(StorageError) as exc:
        client.put_object(key="bad.txt", body="x")
    assert exc.value.code == "STORAGE_PUT_FAILED"
    assert exc.value.status_code == 400
    assert exc.value.retryable is False


def test_head_object_returns_normalized_metadata_for_existing_objects():
    client = StorageClient(
        bucket="media",
        client=MockClient(
            head_object=lambda **_kwargs: {
                "ETag": '"etag-1"',
                "VersionId": "7",
                "LastModified": datetime(2026, 3, 29, tzinfo=UTC),
                "Expires": datetime(2026, 3, 30, tzinfo=UTC),
                "ContentLength": 128,
                "ContentType": "image/png",
                "CacheControl": "public, max-age=60",
                "ContentDisposition": "inline",
                "ContentEncoding": "gzip",
                "ContentLanguage": "en",
                "Metadata": {"source": "webhook"},
            }
        ),
    )
    result = client.head_object(key="images/logo.png")
    assert result is not None
    assert result.public_url == "https://media.s3.amazonaws.com/images/logo.png"
    assert result.content_length == 128
    assert result.metadata == {"source": "webhook"}


def test_head_object_defaults_missing_metadata_to_empty_object():
    client = StorageClient(
        bucket="media",
        client=MockClient(
            head_object=lambda **_kwargs: {
                "ContentLength": 42,
                "LastModified": datetime(2026, 3, 30, 12, 0, 0),
            }
        ),
    )
    result = client.head_object(key="images/raw.bin", public_url=False)
    assert result is not None
    assert result.metadata == {}
    assert result.last_modified == "2026-03-30T12:00:00Z"


def test_head_object_returns_null_for_not_found_and_wraps_when_requested():
    class NotFound(Exception):
        name = "NotFound"

    class Http404(Exception):
        def __init__(self):
            self.response = {"ResponseMetadata": {"HTTPStatusCode": 404}}

    calls = {"count": 0}

    def handler(**_kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise NotFound()
        raise Http404()

    client = StorageClient(bucket="media", client=MockClient(head_object=handler))
    assert client.head_object(key="missing/file.txt") is None
    with pytest.raises(StorageError) as exc:
        client.head_object(key="missing/file.txt", not_found="error")
    assert exc.value.code == "STORAGE_HEAD_FAILED"
    assert exc.value.status_code == 404


def test_head_object_treats_botocore_not_found_as_missing():
    client = StorageClient(
        bucket="media",
        client=MockClient(
            head_object=lambda **_kwargs: (_ for _ in ()).throw(
                ClientError(
                    {"Error": {"Code": "NoSuchKey"}},
                    "HeadObject",
                )
            )
        ),
    )
    assert client.head_object(key="missing/from-botocore.txt") is None


def test_head_object_wraps_generic_failures_and_object_exists_uses_null_path():
    class NoSuchKey(Exception):
        code = "NoSuchKey"

    calls = {"count": 0}

    def handler(**_kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return {"Metadata": {}}
        if calls["count"] == 2:
            raise NoSuchKey()
        raise RuntimeError("network-down")

    client = StorageClient(bucket="media", client=MockClient(head_object=handler))
    assert client.object_exists(key="present.txt") is True
    assert client.object_exists(key="missing.txt") is False
    with pytest.raises(StorageError) as exc:
        client.head_object(key="boom.txt")
    assert exc.value.code == "STORAGE_HEAD_FAILED"
    assert exc.value.retryable is True
    assert exc.value.status_code is None


def test_delete_object_returns_normalized_output_and_suppresses_public_url_when_requested():
    client = StorageClient(
        bucket="private-assets",
        client=MockClient(delete_object=lambda **_kwargs: {"VersionId": "9", "DeleteMarker": True}),
    )
    result = client.delete_object(key="top-secret.txt", public_url=False)
    assert result.public_url is None
    assert result.version_id == "9"
    assert result.delete_marker is True


def test_delete_object_wraps_failures_consistently():
    class Forbidden(Exception):
        def __init__(self):
            self.response = {"ResponseMetadata": {"HTTPStatusCode": 403}}

    client = StorageClient(
        bucket="private-assets",
        client=MockClient(delete_object=lambda **_kwargs: (_ for _ in ()).throw(Forbidden())),
    )
    with pytest.raises(StorageError) as exc:
        client.delete_object(key="top-secret.txt")
    assert exc.value.code == "STORAGE_DELETE_FAILED"
    assert exc.value.operation == "deleteObject"
    assert exc.value.status_code == 403
    assert exc.value.bucket == "private-assets"
    assert exc.value.key == "top-secret.txt"


def test_wrapped_storage_error_instances_pass_through_unchanged():
    original = StorageError(
        "already wrapped",
        code="STORAGE_DELETE_FAILED",
        operation="deleteObject",
        provider="s3",
        bucket="private-assets",
        key="same.txt",
    )
    client = StorageClient(
        bucket="private-assets",
        client=MockClient(delete_object=lambda **_kwargs: (_ for _ in ()).throw(original)),
    )
    with pytest.raises(StorageError) as exc:
        client.delete_object(key="same.txt")
    assert exc.value is original


def test_create_presigned_upload_url_returns_signed_headers_and_uses_custom_presigner():
    client = StorageClient(
        bucket="assets",
        provider="r2",
        account_id="acc-123",
        default_upload_expires_in=600,
        default_metadata={"app": "noria"},
        presign_url=lambda _client, operation, params, expires_in: (
            "https://signed.example.com/upload"
            if operation == "put_object" and expires_in == 600 and params["Bucket"] == "assets"
            else ""
        ),
        client=MockClient(generate_presigned_url=lambda *_args, **_kwargs: ""),
    )
    result = client.create_presigned_upload_url(
        key=["avatars", "user-1.png"],
        content_type="image/png",
        metadata={"uploadedBy": "admin"},
        command_input={
            "ACL": "public-read",
            "ChecksumCRC32": "crc32",
            "ChecksumCRC32C": "crc32c",
            "ChecksumSHA1": "sha1",
            "ChecksumSHA256": "sha256",
            "ServerSideEncryption": "AES256",
            "SSEKMSKeyId": "kms-key",
            "SSECustomerAlgorithm": "AES256",
            "SSECustomerKey": "secret-key",
            "SSECustomerKeyMD5": "secret-md5",
            "StorageClass": "STANDARD",
            "WebsiteRedirectLocation": "/next",
        },
    )
    assert result.method == "PUT"
    assert result.url == "https://signed.example.com/upload"
    assert result.public_url == "https://acc-123.r2.cloudflarestorage.com/assets/avatars/user-1.png"
    assert result.headers["content-type"] == "image/png"
    assert result.headers["x-amz-meta-app"] == "noria"
    assert result.headers["x-amz-meta-uploadedBy"] == "admin"


def test_create_presigned_upload_url_validates_expiry_bounds_and_wraps_failures():
    class TooManyRequests(Exception):
        status = 429

    client = StorageClient(
        bucket="assets",
        presign_url=lambda *_args, **_kwargs: (_ for _ in ()).throw(TooManyRequests()),
        client=MockClient(generate_presigned_url=lambda *_args, **_kwargs: ""),
    )
    with pytest.raises(TypeError, match="expires_in must be a positive integer"):
        client.create_presigned_upload_url(key="bad.txt", expires_in=-1)
    with pytest.raises(ValueError, match="expires_in must not exceed 604800 seconds"):
        client.create_presigned_upload_url(key="bad.txt", expires_in=604801)
    with pytest.raises(StorageError) as exc:
        client.create_presigned_upload_url(key="rate-limited.txt")
    assert exc.value.code == "STORAGE_PRESIGN_UPLOAD_FAILED"
    assert exc.value.status_code == 429
    assert exc.value.retryable is True


def test_create_presigned_download_url_uses_default_presigner_with_mock_client():
    client = StorageClient(
        bucket="signed-assets",
        client=MockClient(
            generate_presigned_url=lambda operation_name, *, Params, ExpiresIn: (
                f"https://signed.example.com/{operation_name}"
                f"?bucket={Params['Bucket']}&key={Params['Key']}&expires={ExpiresIn}"
            )
        ),
    )
    result = client.create_presigned_download_url(key="reports/march.pdf", expires_in=120)
    assert result.url == (
        "https://signed.example.com/get_object"
        "?bucket=signed-assets&key=reports/march.pdf&expires=120"
    )
    assert result.headers == {}
    assert result.expires_in == 120


def test_create_presigned_download_url_wraps_failures():
    client = StorageClient(
        bucket="signed-assets",
        presign_url=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("signing failed")),
        client=MockClient(generate_presigned_url=lambda *_args, **_kwargs: ""),
    )
    with pytest.raises(StorageError) as exc:
        client.create_presigned_download_url(key="reports/march.pdf")
    assert exc.value.code == "STORAGE_PRESIGN_DOWNLOAD_FAILED"
    assert exc.value.operation == "createPresignedDownloadUrl"
    assert exc.value.retryable is True


def test_create_presigned_download_url_supports_default_presigner_with_boto_client():
    client = StorageClient(
        bucket="signed-assets",
        region="us-east-1",
        credentials={
            "access_key_id": "AKIAEXAMPLE",
            "secret_access_key": "secret",
        },
    )
    result = client.create_presigned_download_url(
        key=["reports", "march report.pdf"], expires_in=60
    )
    assert result.method == "GET"
    assert result.bucket == "signed-assets"
    assert result.key == "reports/march report.pdf"
    assert result.public_url == "https://signed-assets.s3.amazonaws.com/reports/march%20report.pdf"
    assert result.headers == {}
    assert "X-Amz-Signature=" in result.url


def test_create_public_url_supports_custom_builders_explicit_endpoints_and_path_styles():
    custom = StorageClient(
        bucket="assets",
        build_public_url=lambda resolved: (
            f"https://cdn.example.com/{resolved.provider}/{resolved.bucket}/{resolved.key}"
        ),
    )
    endpoint_path = StorageClient(
        bucket="assets", endpoint="https://objects.example.com/root/", url_style="path"
    )
    endpoint_hosted = StorageClient(
        bucket="assets",
        endpoint="https://objects.example.com/root/",
        url_style="virtual-hosted",
    )
    prefixed = StorageClient(
        bucket="assets",
        key_prefix="tenant-a",
        public_base_url="https://cdn.example.com/base/",
    )
    regional_path_style = StorageClient(bucket="assets", region="eu-west-1", url_style="path")
    explicit_false_path_style = StorageClient(
        bucket="assets", region="eu-west-1", force_path_style=False
    )
    assert custom.create_public_url("hero.png") == "https://cdn.example.com/s3/assets/hero.png"
    assert (
        endpoint_path.create_public_url("images/logo.png")
        == "https://objects.example.com/root/assets/images/logo.png"
    )
    assert (
        endpoint_hosted.create_public_url("images/logo.png")
        == "https://assets.objects.example.com/root/images/logo.png"
    )
    assert (
        prefixed.create_public_url(["documents", "report.pdf"])
        == "https://cdn.example.com/base/tenant-a/documents/report.pdf"
    )
    assert (
        regional_path_style.create_public_url("images/logo.png")
        == "https://s3.eu-west-1.amazonaws.com/assets/images/logo.png"
    )
    assert (
        explicit_false_path_style.create_public_url("images/logo.png")
        == "https://assets.s3.eu-west-1.amazonaws.com/images/logo.png"
    )


def test_create_public_url_wraps_missing_provider_configuration():
    client = StorageClient(bucket="assets", provider="r2", endpoint="   ")
    with pytest.raises(TypeError, match="Storage key must contain at least one path segment"):
        client.create_public_url("   ")
    with pytest.raises(StorageError) as exc:
        client.create_public_url("report.pdf")
    assert exc.value.code == "STORAGE_PUBLIC_URL_FAILED"
    assert exc.value.operation == "createPublicUrl"
    assert exc.value.provider == "r2"


def test_create_public_url_re_raises_storage_errors_from_custom_builder():
    original = StorageError(
        "already normalized",
        code="STORAGE_PUBLIC_URL_FAILED",
        operation="createPublicUrl",
        provider="s3",
        bucket="assets",
        key="report.pdf",
    )
    client = StorageClient(
        bucket="assets",
        build_public_url=lambda _resolved: (_ for _ in ()).throw(original),
    )
    with pytest.raises(StorageError) as exc:
        client.create_public_url("report.pdf")
    assert exc.value is original


def test_non_string_nested_key_parts_are_ignored_during_normalization():
    client = StorageClient(bucket="assets", public_base_url="https://cdn.example.com")
    assert (
        client.create_public_url(["safe", 123, "file.txt"])
        == "https://cdn.example.com/safe/file.txt"
    )


def test_operations_degrade_to_public_url_null_when_public_url_generation_fails():
    client = StorageClient(
        bucket="assets",
        provider="r2",
        endpoint="   ",
        client=MockClient(
            delete_object=lambda **_kwargs: {"VersionId": "1", "DeleteMarker": False}
        ),
    )
    result = client.delete_object(key="private/report.pdf")
    assert result.public_url is None
