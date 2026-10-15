from libs.context_vars import request_id_var
from sqlmodel.ext.asyncio.session import AsyncSession

from ticketmaster.repositories import OutboxRepository, TicketRepository, UserRepository
from ticketmaster.schemas.dtos import BaseUserDTO
from ticketmaster.schemas.task_messages import DeleteCognitoUserTaskMessage


async def delete_user(session: AsyncSession, user: BaseUserDTO) -> None:
    await TicketRepository.release_reserved_for_user(session=session, user_id=user.id)
    await TicketRepository.anonymize_booked_for_user(session=session, user_id=user.id)
    await UserRepository.delete_by_id(session=session, user_id=user.id)
    await OutboxRepository.add(
        session=session,
        message=DeleteCognitoUserTaskMessage(
            logical_id=request_id_var.get(),
            pool_id=user.pool_id,
            cognito_username=user.cognito_username,
        ),
    )
