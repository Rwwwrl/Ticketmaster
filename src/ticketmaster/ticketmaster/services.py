from libs.aws.session import aws_session
from sqlmodel.ext.asyncio.session import AsyncSession

from ticketmaster.repositories import TicketRepository, UserRepository
from ticketmaster.schemas.dtos import BaseUserDTO


class UserService:
    @classmethod
    async def delete_user(cls, session: AsyncSession, user: BaseUserDTO) -> None:
        await TicketRepository.release_reserved_for_user(session=session, user_id=user.id)
        await TicketRepository.anonymize_booked_for_user(session=session, user_id=user.id)
        await UserRepository.delete_by_id(session=session, user_id=user.id)

        async with aws_session.client(service_name="cognito-idp") as cognito:
            try:
                await cognito.admin_delete_user(UserPoolId=user.pool_id, Username=user.external_id)
            except cognito.exceptions.UserNotFoundException:
                pass
