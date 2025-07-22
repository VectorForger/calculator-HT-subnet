import asyncio
import functools
import inspect
import secrets
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

from mesh.proto.auth_pb2 import AccessToken, RequestAuthInfo, ResponseAuthInfo
from mesh.utils.asyncio import (
    anext,
)
from mesh.utils.crypto import Ed25519PrivateKey, Ed25519PublicKey, RSAPrivateKey, RSAPublicKey
from mesh.utils.logging import get_logger
from mesh.utils.timed_storage import TimedStorage, get_dht_time

logger = get_logger(__name__)


class AuthorizedRequestBase:
    """
    Interface for protobufs with the ``RequestAuthInfo auth`` field. Used for type annotations only.
    """

    auth: RequestAuthInfo


class AuthorizedResponseBase:
    """
    Interface for protobufs with the ``ResponseAuthInfo auth`` field. Used for type annotations only.
    """

    auth: ResponseAuthInfo


class AuthorizerBase(ABC):
    @abstractmethod
    async def sign_request(
        self, request: AuthorizedRequestBase, service_public_key: Optional[RSAPublicKey]
    ) -> None: ...

    @abstractmethod
    async def validate_request(self, request: AuthorizedRequestBase) -> bool: ...

    @abstractmethod
    async def sign_response(self, response: AuthorizedResponseBase, request: AuthorizedRequestBase) -> None: ...

    @abstractmethod
    async def validate_response(self, response: AuthorizedResponseBase, request: AuthorizedRequestBase) -> bool: ...


class TokenRSAAuthorizerBase(AuthorizerBase):
    """
    Implements the authorization protocol for a moderated/permissioned Subnet network.

    Uses RSA
    """

    def __init__(self, local_private_key: Optional[RSAPrivateKey] = None):
        if local_private_key is None:
            local_private_key = RSAPrivateKey.process_wide()
        self._local_private_key = local_private_key
        self._local_public_key = local_private_key.get_public_key()

        self._local_access_token = None
        self._refresh_lock = asyncio.Lock()

        self._recent_nonces = TimedStorage()

    async def get_token(self) -> AccessToken:
        # Uses the built in template ``AccessToken`` format
        token = AccessToken(
            username='',
            public_key=self._local_public_key.to_bytes(),
            expiration_time=str(datetime.now(timezone.utc) + timedelta(minutes=1)),
        )
        token.signature = self._local_private_key.sign(self._token_to_bytes(token))
        return token

    @staticmethod
    def _token_to_bytes(access_token: AccessToken) -> bytes:
        return f"{access_token.username} {access_token.public_key} {access_token.expiration_time}".encode()

    @property
    def local_public_key(self) -> RSAPublicKey:
        return self._local_public_key

    async def sign_request(self, request: AuthorizedRequestBase, service_public_key: Optional[RSAPublicKey]) -> None:
        auth = request.auth

        local_access_token = await self.get_token()
        auth.client_access_token.CopyFrom(local_access_token)

        if service_public_key is not None:
            auth.service_public_key = service_public_key.to_bytes()
        auth.time = get_dht_time()

        auth.nonce = secrets.token_bytes(8)


        assert auth.signature == b""
        auth.signature = self._local_private_key.sign(request.SerializeToString())

    _MAX_CLIENT_SERVICER_TIME_DIFF = timedelta(minutes=1)

    async def validate_request(self, request: AuthorizedRequestBase) -> bool:
        auth = request.auth

        client_public_key = RSAPublicKey.from_bytes(auth.client_access_token.public_key)
        signature = auth.signature
        auth.signature = b""
        if not client_public_key.verify(request.SerializeToString(), signature):
            logger.debug("Request has invalid signature")
            return False

        if auth.service_public_key and auth.service_public_key != self._local_public_key.to_bytes():
            logger.debug("Request is generated for a peer with another public key")
            return False

        with self._recent_nonces.freeze():
            current_time = get_dht_time()
            if abs(auth.time - current_time) > self._MAX_CLIENT_SERVICER_TIME_DIFF.total_seconds():
                logger.debug("Clocks are not synchronized or a previous request is replayed again")
                return False
            if auth.nonce in self._recent_nonces:
                logger.debug("Previous request is replayed again")
                return False

        if auth.nonce in self._recent_nonces:
            logger.debug("Previous request is replayed again")
            return False

        self._recent_nonces.store(
            auth.nonce, None, current_time + self._MAX_CLIENT_SERVICER_TIME_DIFF.total_seconds() * 3
        )
        return True

    async def sign_response(self, response: AuthorizedResponseBase, request: AuthorizedRequestBase) -> None:
        auth = response.auth

        # auth.service_access_token.CopyFrom(self._local_access_token)
        local_access_token = await self.get_token()
        auth.service_access_token.CopyFrom(local_access_token)
        auth.nonce = request.auth.nonce

        assert auth.signature == b""
        auth.signature = self._local_private_key.sign(response.SerializeToString())

    async def validate_response(self, response: AuthorizedResponseBase, request: AuthorizedRequestBase) -> bool:
        if inspect.isasyncgen(response):
            # asyncgenerator block for inference protocol
            response = await anext(response)
            auth = response.auth
        else:
            auth = response.auth

        service_public_key = RSAPublicKey.from_bytes(auth.service_access_token.public_key)
        signature = auth.signature
        auth.signature = b""
        if not service_public_key.verify(response.SerializeToString(), signature):
            logger.debug("Response has invalid signature")
            return False

        if auth.nonce != request.auth.nonce:
            logger.debug("Response is generated for another request")
            return False

        return True

class TokenEd25519AuthorizerBase(AuthorizerBase):
    """
    Implements the authorization protocol for a moderated/permissioned Subnet network.

    Uses Ed25519
    """

    def __init__(self, local_private_key: Optional[Ed25519PrivateKey] = None):
        if local_private_key is None:
            local_private_key = Ed25519PrivateKey.process_wide()
        self._local_private_key = local_private_key
        self._local_public_key = local_private_key.get_public_key()

        self._local_access_token = None
        self._refresh_lock = asyncio.Lock()

        self._recent_nonces = TimedStorage()

    @abstractmethod
    async def get_token(self) -> AccessToken: ...

    @abstractmethod
    def is_token_valid(self, access_token: AccessToken) -> bool: ...

    @abstractmethod
    def does_token_need_refreshing(self, access_token: AccessToken) -> bool: ...

    async def refresh_token_if_needed(self) -> None:
        if self._local_access_token is None or self.does_token_need_refreshing(self._local_access_token):
            async with self._refresh_lock:
                if self._local_access_token is None or self.does_token_need_refreshing(self._local_access_token):
                    self._local_access_token = await self.get_token()
                    assert self.is_token_valid(self._local_access_token)

    @property
    def local_public_key(self) -> Ed25519PublicKey:
        return self._local_public_key

    async def sign_request(self, request: AuthorizedRequestBase, service_public_key: Optional[Ed25519PublicKey]) -> None:
        await self.refresh_token_if_needed()
        auth = request.auth

        auth.client_access_token.CopyFrom(self._local_access_token)

        if service_public_key is not None:
            auth.service_public_key = service_public_key.to_bytes()
        auth.time = get_dht_time()
        auth.nonce = secrets.token_bytes(8)

        assert auth.signature == b""
        auth.signature = self._local_private_key.sign(request.SerializeToString())

    _MAX_CLIENT_SERVICER_TIME_DIFF = timedelta(minutes=1)

    async def validate_request(self, request: AuthorizedRequestBase) -> bool:
        await self.refresh_token_if_needed()
        auth = request.auth

        if not self.is_token_valid(auth.client_access_token):
            logger.debug("Client failed to prove that it (still) has access to the network")
            return False

        client_public_key = Ed25519PublicKey.from_bytes(auth.client_access_token.public_key)
        signature = auth.signature
        auth.signature = b""
        if not client_public_key.verify(request.SerializeToString(), signature):
            logger.debug("Request has invalid signature")
            return False

        if auth.service_public_key and auth.service_public_key != self._local_public_key.to_bytes():
            logger.debug("Request is generated for a peer with another public key")
            return False

        with self._recent_nonces.freeze():
            current_time = get_dht_time()
            if abs(auth.time - current_time) > self._MAX_CLIENT_SERVICER_TIME_DIFF.total_seconds():
                logger.debug("Clocks are not synchronized or a previous request is replayed again")
                return False
            if auth.nonce in self._recent_nonces:
                logger.debug("Previous request is replayed again")
                return False

        self._recent_nonces.store(
            auth.nonce, None, current_time + self._MAX_CLIENT_SERVICER_TIME_DIFF.total_seconds() * 3
        )
        return True

    async def sign_response(self, response: AuthorizedResponseBase, request: AuthorizedRequestBase) -> None:
        await self.refresh_token_if_needed()
        auth = response.auth

        auth.service_access_token.CopyFrom(self._local_access_token)
        auth.nonce = request.auth.nonce

        assert auth.signature == b""
        auth.signature = self._local_private_key.sign(response.SerializeToString())

    async def validate_response(self, response: AuthorizedResponseBase, request: AuthorizedRequestBase) -> bool:
        if inspect.isasyncgen(response):
            # asyncgenerator block
            response = await anext(response)
            auth = response.auth
        else:
            auth = response.auth

        service_public_key = Ed25519PublicKey.from_bytes(auth.service_access_token.public_key)
        signature = auth.signature
        auth.signature = b""
        if not service_public_key.verify(response.SerializeToString(), signature):
            logger.debug("Response has invalid signature")
            return False

        if auth.nonce != request.auth.nonce:
            logger.debug("Response is generated for another request")
            return False

        return True

class AuthRole(Enum):
    CLIENT = 0
    SERVICER = 1


class AuthRPCWrapper:
    """
    An authentication wrapper around peer stubs.

    This can be used as an authentication mechanism for all peer communications or different types of communication.

    Example: The AuthorizerBase can be used as a proof-of-stake mechanism connected to Hypertensor to ensure all nodes
    that communicate with each other are staked on-chain. For things such as entering the DHT or calling for inference.
    """
    def __init__(
        self,
        stub,
        role: AuthRole,
        authorizer: Optional[AuthorizerBase],
        service_public_key: Optional[RSAPublicKey] = None,
    ):
        self._stub = stub
        self._role = role
        self._authorizer = authorizer
        self._service_public_key = service_public_key

    def __getattribute__(self, name: str):
        if not name.startswith("rpc_"):
            return object.__getattribute__(self, name)

        method = getattr(self._stub, name)

        @functools.wraps(method)
        async def wrapped_rpc(request: AuthorizedRequestBase, *args, **kwargs):
            if self._authorizer is not None:
                if self._role == AuthRole.CLIENT:
                    await self._authorizer.sign_request(request, self._service_public_key)
                elif self._role == AuthRole.SERVICER:
                    if not await self._authorizer.validate_request(request):
                        return None

            response = await method(request, *args, **kwargs)

            if self._authorizer is not None:
                if self._role == AuthRole.SERVICER:
                    await self._authorizer.sign_response(response, request)
                elif self._role == AuthRole.CLIENT:
                    if not await self._authorizer.validate_response(response, request):
                        return None

            return response

        return wrapped_rpc

class AuthRPCWrapperStreamer:
    def __init__(
        self,
        stub,
        role: AuthRole,
        authorizer: Optional[AuthorizerBase],
        service_public_key: Optional[RSAPublicKey] = None
    ):
        self._stub = stub
        self._role = role
        self._authorizer = authorizer
        self._service_public_key = service_public_key

    def __getattribute__(self, name: str):
        if not name.startswith("rpc_"):
            return object.__getattribute__(self, name)

        stub = object.__getattribute__(self, "_stub")
        method = getattr(stub, name)
        role = object.__getattribute__(self, "_role")
        authorizer = object.__getattribute__(self, "_authorizer")
        service_public_key = object.__getattribute__(self, "_service_public_key")

        if inspect.isasyncgenfunction(method):
            @functools.wraps(method)
            async def wrapped_stream_rpc(request, *args, **kwargs):
                if authorizer:
                    if role == AuthRole.CLIENT:
                        await authorizer.sign_request(request, service_public_key)
                    elif role == AuthRole.SERVICER:
                        if not await authorizer.validate_request(request):
                            return

                async for response in method(request, *args, **kwargs):
                    if self._authorizer:
                        if self._role == AuthRole.SERVICER:
                            await self._authorizer.sign_response(response, request)
                        elif self._role == AuthRole.CLIENT:
                            if not await self._authorizer.validate_response(response, request):
                                continue

                    yield response

            return wrapped_stream_rpc
        else:
            @functools.wraps(method)
            async def wrapped_unary_rpc(request, *args, **kwargs):
                if authorizer:
                    if role == AuthRole.CLIENT:
                        await authorizer.sign_request(request, service_public_key)
                    elif role == AuthRole.SERVICER:
                        if not await authorizer.validate_request(request):
                            return None

                response = await method(request, *args, **kwargs)

                if authorizer:
                    if role == AuthRole.SERVICER:
                        await authorizer.sign_response(response, request)
                    elif role == AuthRole.CLIENT:
                        if not await authorizer.validate_response(response, request):
                            return None

                return response

            return wrapped_unary_rpc
