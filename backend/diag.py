"""A self-test for the file storage, for the Owner/admins: shows step by step what works and what does not."""
from flask import Blueprint, jsonify

import config
import objstore
from security import perm_required

bp = Blueprint("diag", __name__, url_prefix="/api/admin")


def _step(name, ok, hint=""):
    return {"name": name, "ok": ok, "hint": hint}


@bp.get("/storage-check")
@perm_required("admin.settings")
def storage_check():
    steps = []
    missing = [n for n, v in (("S3_ENDPOINT_URL", config.S3_ENDPOINT_URL), ("S3_BUCKET", config.S3_BUCKET),
                              ("S3_ACCESS_KEY_ID", config.S3_ACCESS_KEY_ID), ("S3_SECRET_ACCESS_KEY", config.S3_SECRET_ACCESS_KEY)) if not v]
    steps.append(_step("All storage settings are filled in", not missing, "Missing on the server: " + ", ".join(missing) if missing else ""))
    if missing:
        return jsonify({"steps": steps})
    steps.append(_step("The address starts with https://", config.S3_ENDPOINT_URL.startswith("https://"),
                       "S3_ENDPOINT_URL must look like https://s3.eu-central-003.backblazeb2.com"))
    try:
        url = objstore.presign_put("diagnose/check.txt", "text/plain")
        steps.append(_step("A signed upload link can be created", True))
    except Exception as e:                                           # shows the reason, never the secret values
        steps.append(_step("A signed upload link can be created", False, f"{type(e).__name__}: {str(e)[:200]}"))
        return jsonify({"steps": steps})
    steps.append(_step("The region fits the address", config.S3_REGION == "auto" or config.S3_REGION in config.S3_ENDPOINT_URL,
                       f"S3_REGION is '{config.S3_REGION}', the address is {config.S3_ENDPOINT_URL}. For Backblaze the region is the middle part, e.g. eu-central-003."))
    try:
        from botocore.exceptions import ClientError
        try:
            objstore._c().head_object(Bucket=config.S3_BUCKET, Key="diagnose/does-not-exist")
        except ClientError as e:
            code = str(e.response.get("Error", {}).get("Code"))
            ok = code in ("404", "NoSuchKey", "NotFound")
            hint = "" if ok else f"Storage answered '{code}'. 403 = key id/key wrong or not allowed for this bucket; 404 for a bucket = wrong bucket name."
            steps.append(_step("The storage accepts the key and finds the bucket", ok, hint))
    except Exception as e:
        steps.append(_step("The storage accepts the key and finds the bucket", False, f"{type(e).__name__}: {str(e)[:200]}"))
    try:
        rules = objstore._c().get_bucket_cors(Bucket=config.S3_BUCKET).get("CORSRules", [])
        origins = [o for r in rules for o in r.get("AllowedOrigins", [])]
        methods = {m for r in rules for m in r.get("AllowedMethods", [])}
        ok = bool(origins) and "PUT" in methods
        steps.append(_step("A CORS rule allows PUT (browser uploads)", ok,
                           "" if ok else "Run backend/setup_cors.py once (see README, 'File storage'). Rules found: " + str(rules)[:200]))
    except Exception as e:
        steps.append(_step("A CORS rule allows PUT (browser uploads)", False,
                           "Could not read the rules (the server key may not be allowed to): " + str(e)[:160] +
                           ". If uploads fail with 'The upload failed', run backend/setup_cors.py once."))
    return jsonify({"steps": steps, "allowed_origins_setting": config.ALLOWED_ORIGINS})
