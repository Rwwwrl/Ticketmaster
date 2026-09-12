def build_s3_object_public_url(region: str, bucket: str, key: str) -> str:
    return f"https://{bucket}.s3.{region}.amazonaws.com/{key}"
