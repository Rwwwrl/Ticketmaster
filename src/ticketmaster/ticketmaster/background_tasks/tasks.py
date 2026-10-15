import logging
from datetime import timedelta

from libs.aws.session import aws_session
from libs.sqlmodel_ext import SessionPrimary
from taskiq import async_shared_broker

from ticketmaster.repositories import InboxRepository
from ticketmaster.schemas import task_messages

_logger = logging.getLogger(__name__)


@async_shared_broker.task(task_name="delete_s3_object", retry_on_error=True, max_retries=5)
async def delete_s3_object(body: task_messages.DeleteS3ObjectTaskMessage) -> None:
    async with SessionPrimary() as session, session.begin():
        if not await InboxRepository.try_add(session=session, message=body):
            _logger.info("Skipping duplicate code=%s logical_id=%s", body.code, body.logical_id)
            return

        async with aws_session.client(service_name="s3") as s3:
            await s3.delete_object(Bucket=body.bucket, Key=body.key)


@async_shared_broker.task(task_name="delete_cognito_user", retry_on_error=True, max_retries=5)
async def delete_cognito_user(body: task_messages.DeleteCognitoUserTaskMessage) -> None:
    async with SessionPrimary() as session, session.begin():
        if not await InboxRepository.try_add(session=session, message=body):
            _logger.info("Skipping duplicate code=%s logical_id=%s", body.code, body.logical_id)
            return

        async with aws_session.client(service_name="cognito-idp") as cognito:
            try:
                await cognito.admin_delete_user(UserPoolId=body.pool_id, Username=body.cognito_username)
            except cognito.exceptions.UserNotFoundException:
                pass


@async_shared_broker.task(task_name="cleanup_inbox", schedule=[{"cron": "0 3 * * *"}])
async def cleanup_inbox(body: task_messages.CleanupInboxTaskMessage) -> None:
    batch_size = 10_000
    while True:
        async with SessionPrimary() as session, session.begin():
            deleted = await InboxRepository.delete_older_than(
                session=session,
                older_than=timedelta(days=14),
                limit=batch_size,
            )

        if deleted < batch_size:
            return
