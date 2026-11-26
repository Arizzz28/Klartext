"""One-time helper: tells Backblaze (or any S3-compatible storage) that your website may upload to your bucket.

Why: the browser sends the file straight to the bucket. Without a CORS rule the browser refuses and the chat shows
"The upload failed. Check your connection."

Run it ONCE (for example in a GitHub Codespace, or on your PC). It needs an application key that may change bucket
settings - the restricted key of the server usually can not. Create a temporary key in Backblaze (Application Keys,
access to all buckets or just this one, read AND write) and delete it afterwards.

    pip install boto3
    python setup_cors.py --origin https://arizzz28.github.io --bucket klartext-storage \\
        --endpoint https://s3.eu-central-003.backblazeb2.com --key-id YOUR_KEY_ID --key YOUR_APPLICATION_KEY

Without --key-id/--key it uses the S3_* values of backend/.env.  Add --show to only print the current rules.
This script never changes whether the bucket is private or public.
"""
import argparse
import sys


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--origin", help="your website, e.g. https://arizzz28.github.io (no path, no slash at the end)")
    p.add_argument("--bucket")
    p.add_argument("--endpoint")
    p.add_argument("--region")
    p.add_argument("--key-id")
    p.add_argument("--key")
    p.add_argument("--show", action="store_true", help="only show the current CORS rules")
    a = p.parse_args()

    import config
    import boto3
    from botocore.config import Config
    from botocore.exceptions import ClientError

    endpoint = a.endpoint or config.S3_ENDPOINT_URL
    bucket = a.bucket or config.S3_BUCKET
    key_id = a.key_id or config.S3_ACCESS_KEY_ID
    key = a.key or config.S3_SECRET_ACCESS_KEY
    region = a.region or config.S3_REGION
    if region in ("", "auto") and ".s3." in endpoint:
        region = endpoint.split(".s3.")[0].rsplit("//", 1)[-1]
    if "://" not in endpoint and endpoint:
        endpoint = "https://" + endpoint
        print("Note: the endpoint needs https:// in front - added it for this run.")
    if not (endpoint and bucket and key_id and key):
        sys.exit("Missing values: endpoint, bucket, key id and key are needed (arguments or backend/.env).")
    if region == "auto" and "backblazeb2.com" in endpoint:
        region = endpoint.split("s3.")[1].split(".")[0]

    s3 = boto3.client("s3", endpoint_url=endpoint, region_name=region, aws_access_key_id=key_id, aws_secret_access_key=key,
                      config=Config(signature_version="s3v4", s3={"addressing_style": "path"}))
    try:
        if a.show or not a.origin:
            try:
                print(s3.get_bucket_cors(Bucket=bucket)["CORSRules"])
            except ClientError as e:
                print("Current rules:", e.response["Error"].get("Code"), e.response["Error"].get("Message"))
            if not a.origin:
                return
            if a.show:
                return
        origin = a.origin.rstrip("/")
        if "/" in origin.split("://", 1)[-1]:
            sys.exit("The origin must be only the address up to .io / .com, without a path (no /Klartext).")
        rules = [{"ID": "chatisfying-upload", "AllowedOrigins": [origin], "AllowedMethods": ["PUT", "GET", "HEAD"],
                  "AllowedHeaders": ["*"], "ExposeHeaders": ["ETag"], "MaxAgeSeconds": 3600}]
        s3.put_bucket_cors(Bucket=bucket, CORSConfiguration={"CORSRules": rules})
        print("Done. Rule saved for", origin)
        print("Backblaze may need a few minutes. Check:", s3.get_bucket_cors(Bucket=bucket)["CORSRules"])
    except ClientError as e:
        err = e.response["Error"]
        print("Backblaze answered:", err.get("Code"), "-", err.get("Message"))
        print("Most likely this key is not allowed to change bucket settings. Create a temporary application key with "
              "access to this bucket and the rights to read AND write, and try again.")
        sys.exit(1)


if __name__ == "__main__":
    main()
