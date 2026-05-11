import aioboto3

aws_session = aioboto3.Session()


def bind_task_role_to_aws_session(*, region: str, access_key_id: str, secret_access_key: str) -> None:
    aws_session._session.set_credentials(access_key_id, secret_access_key)
    aws_session._session.set_config_variable("region", region)
