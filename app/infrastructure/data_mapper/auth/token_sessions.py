from dataclasses import replace

from app.application.domain import TokenSession
from app.application.ports import TokenSessionGateway


class InMemoryTokenSessionDataMapper(TokenSessionGateway):
    def __init__(self) -> None:
        self._sessions: dict[str, TokenSession] = {}
        self._revoked_token_ids: set[str] = set()

    async def register_token_session(self, session: TokenSession) -> None:
        self._sessions[session.token_id] = session

    async def get_token_session(self, token_id: str) -> TokenSession | None:
        return self._sessions.get(token_id)

    async def is_token_known(self, token_id: str) -> bool:
        return token_id in self._sessions

    async def is_token_revoked(self, token_id: str) -> bool:
        session: TokenSession | None = self._sessions.get(token_id)
        return token_id in self._revoked_token_ids or (
            session is not None and session.revoked
        )

    async def revoke_token(self, token_id: str) -> None:
        self._revoked_token_ids.add(token_id)
        session: TokenSession | None = self._sessions.get(token_id)

        if session is not None:
            self._sessions[token_id] = replace(session, revoked=True)
