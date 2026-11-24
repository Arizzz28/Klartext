"""Talks to the object storage (Backblaze B2, Cloudflare R2, any S3-compatible service).

Files never travel through this server. The server only creates short-lived signed links:
- upload link: the browser PUTs the file straight into the bucket
- download link: the browser loads the file straight from the bucket
"""
import urllib.parse

import config

_client = None

INLINE_IMAGE = {"image/png", "image/jpeg", "image/gif", "image/webp", "image/avif", "image/bmp"}
INLINE_VIDEO = {"video/mp4", "video/webm", "video/quicktime", "video/ogg"}
INLINE_AUDIO = {"audio/mpeg", "audio/ogg", "audio/wav", "audio/x-wav", "audio/webm", "audio/mp4", "audio/aac"}


def file_kind(mime):
    """'image', 'video', 'audio' (shown in the chat) or 'file' (always a download)."""
    mime = (mime or "").lower()
    if mime in INLINE_IMAGE:
        return "image"
    if mime in INLINE_VIDEO:
        return "video"
    if mime in INLINE_AUDIO:
        return "audio"
    return "file"


def enabled():
    return bool(config.S3_ENDPOINT_URL and config.S3_BUCKET and config.S3_ACCESS_KEY_ID and config.S3_SECRET_ACCESS_KEY)


def _c():
    global _client
    if _client is None:
        import boto3
        from botocore.config import Config
        _client = boto3.client(
            "s3", endpoint_url=config.S3_ENDPOINT_URL, region_name=config.S3_REGION,
            aws_access_key_id=config.S3_ACCESS_KEY_ID, aws_secret_access_key=config.S3_SECRET_ACCESS_KEY,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}, retries={"max_attempts": 2}))
    return _client


def presign_put(key, mime):
    return _c().generate_presigned_url(
        "put_object", Params={"Bucket": config.S3_BUCKET, "Key": key, "ContentType": mime},
        ExpiresIn=config.UPLOAD_URL_TTL, HttpMethod="PUT")


def presign_get(key, name, mime):
    if file_kind(mime) == "file":
        ascii_name = "".join(c if 32 < ord(c) < 127 and c not in '"\\;' else "_" for c in name) or "file"
        disposition = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{urllib.parse.quote(name)}"
    else:
        disposition = "inline"
    return _c().generate_presigned_url(
        "get_object",
        Params={"Bucket": config.S3_BUCKET, "Key": key, "ResponseContentType": mime, "ResponseContentDisposition": disposition},
        ExpiresIn=config.DOWNLOAD_URL_TTL)


def head(key):
    """Size of the stored object in bytes, or None if it does not exist."""
    from botocore.exceptions import ClientError
    try:
        return _c().head_object(Bucket=config.S3_BUCKET, Key=key)["ContentLength"]
    except ClientError:
        return None


def delete(keys):
    """Deletes objects. Errors are only printed: a leftover file must never break the app."""
    keys = [k for k in keys if k]
    if not keys or not enabled():
        return
    for i in range(0, len(keys), 500):
        try:
            _c().delete_objects(Bucket=config.S3_BUCKET,
                                Delete={"Objects": [{"Key": k} for k in keys[i:i + 500]], "Quiet": True})
        except Exception as e:
            print(f"[STORAGE] Could not delete objects: {type(e).__name__}", flush=True)
