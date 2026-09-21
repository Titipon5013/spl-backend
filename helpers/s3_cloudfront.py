import os
import uuid
import boto3
from botocore.exceptions import NoCredentialsError

_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

class S3CloudFront:
    def __init__(self, aws_access_key_id, aws_secret_access_key, region_name, bucket_name, cloudfront_domain):
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=region_name
        )
        self.bucket_name = bucket_name
        self.cloudfront_domain = cloudfront_domain

    def upload_file(self, file, file_name, prefix="uploads/", content_type=None):
        """Upload a file under a server-generated object key.

        The client-supplied ``file_name`` is used only to derive a validated
        extension; it never becomes the S3 key. This prevents callers from
        choosing/overwriting arbitrary object keys.
        """
        ext = os.path.splitext(os.path.basename(file_name or ""))[1].lower()
        if ext not in _ALLOWED_EXTENSIONS:
            ext = ".bin"
        key = f"{prefix}{uuid.uuid4().hex}{ext}"

        try:
            extra_args = {"ContentDisposition": "attachment"}
            if content_type:
                extra_args["ContentType"] = content_type
            self.s3_client.upload_fileobj(
                file, self.bucket_name, key, ExtraArgs=extra_args
            )
            return f"{self.cloudfront_domain}/{key}"
        except NoCredentialsError:
            return "Credentials not available"
        except Exception as e:
            return str(e)

    def delete_file(self, file_name):
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=file_name)
            return True
        except NoCredentialsError:
            return "Credentials not available"
        except Exception as e:
            return str(e)
