import os

import boto3
from dotenv import load_dotenv

load_dotenv()

B2_CLIENT = boto3.client(
    "s3",
    endpoint_url=os.getenv("B2_ENDPOINT_URL"),
    aws_access_key_id=os.getenv("B2_KEY_ID"),
    aws_secret_access_key=os.getenv("B2_APPLICATION_KEY"),
    region_name="eu-central-003",
)

B2_BUCKET_NAME = os.getenv("B2_BUCKET_NAME")

if not all([
    os.getenv("B2_ENDPOINT_URL"),
    os.getenv("B2_KEY_ID"),
    os.getenv("B2_APPLICATION_KEY"),
    B2_BUCKET_NAME,
]):
    raise ValueError("B2 configuration is incomplete. Check your .env file.")

def upload_file(file_obj, object_key, content_type):
    B2_CLIENT.upload_fileobj(
        file_obj,
        B2_BUCKET_NAME,
        object_key,
        ExtraArgs={"ContentType": content_type},
    )

def download_file(object_key):
    response = B2_CLIENT.get_object(
        Bucket=B2_BUCKET_NAME,
        Key=object_key,
    )

    return response["Body"]

def delete_file(object_key):
    B2_CLIENT.delete_object(
        Bucket=B2_BUCKET_NAME,
        Key=object_key,
    )