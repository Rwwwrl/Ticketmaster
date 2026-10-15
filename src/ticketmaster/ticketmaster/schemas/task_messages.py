from typing import ClassVar

from libs.taskiq_ext.schemas.task_messages import BaseTaskMessage


class DeleteS3ObjectTaskMessage(BaseTaskMessage):
    code: ClassVar[int] = 100

    bucket: str
    key: str


class DeleteCognitoUserTaskMessage(BaseTaskMessage):
    code: ClassVar[int] = 101

    pool_id: str
    cognito_username: str


class CleanupInboxTaskMessage(BaseTaskMessage):
    code: ClassVar[int] = 102
