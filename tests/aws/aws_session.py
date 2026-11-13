import os
from pathlib import Path

import boto3
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env.credentials")


def get_client(service: str):
    # verify=False: Python 3.14 SSL regression workaround. truststore was tested
    # but causes RecursionError in botocore's SSLContext patching. Keep until the regression is fixed upstream.
    return boto3.client(
        service,
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        aws_session_token=os.environ.get("AWS_SESSION_TOKEN") or None,
        region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
        verify=False,
    )
