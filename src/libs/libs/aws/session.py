import aioboto3

aws_session = aioboto3.Session()


def bind_task_role_to_aws_session(
    *,
    region: str,
    access_key_id: str | None,
    secret_access_key: str | None,
    session_token: str | None,
) -> None:
    if access_key_id is not None and secret_access_key is not None:
        aws_session._session.set_credentials(
            access_key=access_key_id,
            secret_key=secret_access_key,
            token=session_token,
        )

    aws_session._session.set_config_variable("region", region)
