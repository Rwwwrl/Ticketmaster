from libs.aws.session import aws_session
from taskiq import async_shared_broker

from ticketmaster.schemas import task_messages


@async_shared_broker.task(task_name="delete_s3_object", retry_on_error=True, max_retries=5)
async def delete_s3_object(body: task_messages.DeleteS3ObjectTaskMessage) -> None:
    async with aws_session.client(service_name="s3") as s3:
        await s3.delete_object(Bucket=body.bucket, Key=body.key)


@async_shared_broker.task(task_name="delete_cognito_user", retry_on_error=True, max_retries=5)
async def delete_cognito_user(body: task_messages.DeleteCognitoUserTaskMessage) -> None:
    async with aws_session.client(service_name="cognito-idp") as cognito:
        try:
            await cognito.admin_delete_user(UserPoolId=body.pool_id, Username=body.cognito_username)
        except cognito.exceptions.UserNotFoundException:
            pass
