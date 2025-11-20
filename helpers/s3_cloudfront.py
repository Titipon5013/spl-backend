import boto3
from botocore.exceptions import NoCredentialsError

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

    def upload_file(self, file, file_name):
        try:
            self.s3_client.upload_fileobj(file, self.bucket_name, file_name)
            return f"{self.cloudfront_domain}/{file_name}"
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
