import asyncio
import functools
import inspect
import secrets
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, Optional
from mesh.utils.asyncio import (
    anext,
)

from mesh.p2p.p2p_daemon_bindings.datastructures import PeerID
from mesh.proto.auth_pb2 import AccessToken
from mesh.subnet.utils.peer_id import get_ed25519_peer_id, get_rsa_peer_id
from mesh.substrate.chain_functions import Hypertensor
from mesh.utils.auth import AuthorizedRequestBase, AuthorizedResponseBase, AuthorizerBase
from mesh.utils.crypto import Ed25519PrivateKey, Ed25519PublicKey, RSAPrivateKey, RSAPublicKey
from mesh.utils.logging import get_logger
from mesh.utils.timed_storage import get_dht_time

# from substrateinterface import SubstrateInterface

logger = get_logger(__name__)


class Ed25519ProofOfStakeAuthorizer(AuthorizerBase):
    """
    Implements a proof-of-stake authorization protocol using Ed25519 keys
    Checks the Hypertensor network for nodes ``peer_id`` is staked.
    The ``peer_id`` is retrieved using the Ed25519 public key
    """

    def __init__(
        self,
        local_private_key: Ed25519PrivateKey,
        subnet_id: int,
        hypertensor: Hypertensor
    ):
        super().__init__()
        self._local_private_key = local_private_key
        self._local_public_key = local_private_key.get_public_key()
        self.subnet_id = subnet_id
        self.hypertensor = hypertensor
        self.peer_id_to_last_successful_pos: Dict[PeerID, float] = {}
        self.pos_success_cooldown = 300
        self.peer_id_to_last_failed_pos: Dict[PeerID, float] = {}
        self.pos_fail_cooldown: float = 300  # 5 minutes default cooldown

    async def get_token(self) -> AccessToken:
        token = AccessToken(
            username="",
            public_key=self._local_public_key.to_bytes(),
            expiration_time=str(datetime.now(timezone.utc) + timedelta(minutes=1)),
        )
        token.signature = self._local_private_key.sign(self._token_to_bytes(token))
        return token

    @staticmethod
    def _token_to_bytes(access_token: AccessToken) -> bytes:
        return f"{access_token.username} {access_token.public_key} {access_token.expiration_time}".encode()

    async def sign_request(
        self, request: AuthorizedRequestBase, service_public_key: Optional[Ed25519PublicKey]
    ) -> None:
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

        # Get public key of signer
        try:
            client_public_key = Ed25519PublicKey.from_bytes(auth.client_access_token.public_key)
        except Exception as e:
            logger.debug(f"Failed to get Ed25519 public key from bytes, Err: {e}", exc_info=True)
            return False

        signature = auth.signature
        auth.signature = b""
        # Verify signature of the request from signer
        if not client_public_key.verify(request.SerializeToString(), signature):
            logger.debug("Request has invalid signature")
            return False

        if auth.service_public_key and auth.service_public_key != self._local_public_key.to_bytes():
            logger.debug("Request is generated for a peer with another public key")
            return False

        # Verify proof of stake
        try:
            proof_of_stake = self.proof_of_stake(client_public_key)
            return proof_of_stake
        except Exception as e:
            logger.debug("Proof of stake failed, validate request", e, exc_info=True)

        return False

    async def sign_response(self, response: AuthorizedResponseBase, request: AuthorizedRequestBase) -> None:
        auth = response.auth

        local_access_token = await self.get_token()
        auth.service_access_token.CopyFrom(local_access_token)

        # auth.service_access_token.CopyFrom(self._local_public_key)
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

        try:
            proof_of_stake = self.proof_of_stake(service_public_key)
            return proof_of_stake
        except Exception as e:
            logger.debug("Proof of stake failed, validate response", e, exc_info=True)

        return False

    def get_peer_id_last_success(self, peer_id: PeerID) -> float:
        return self.peer_id_to_last_successful_pos.get(peer_id, 0)

    def update_peer_id_success(self, peer_id: PeerID):
        self.peer_id_to_last_successful_pos[peer_id] = get_dht_time()
        self.peer_id_to_last_failed_pos.pop(peer_id, None)

    def get_peer_id_last_fail(self, peer_id: PeerID) -> float:
        return self.peer_id_to_last_failed_pos.get(peer_id, 0)

    def update_peer_id_fail(self, peer_id: PeerID):
        self.peer_id_to_last_failed_pos[peer_id] = get_dht_time()
        self.peer_id_to_last_successful_pos.pop(peer_id, None)

    def proof_of_stake(self, public_key: Ed25519PublicKey) -> bool:
        peer_id: Optional[PeerID] = get_ed25519_peer_id(public_key)
        if peer_id is None:
            return False

        now = get_dht_time()

        # Recently failed — reject immediately
        last_fail = self.get_peer_id_last_fail(peer_id)
        if last_fail and now - last_fail < self.pos_fail_cooldown:
            return False

        # Recent success — no need to check again
        last_success = self.get_peer_id_last_success(peer_id)
        if last_success and now - last_success < self.pos_success_cooldown:
            return True

        # On-chain proof of stake check
        peer_id_vec = self.to_vec_u8(peer_id.to_base58())
        proof_of_stake = self.is_staked(peer_id_vec)

        if proof_of_stake:
            self.update_peer_id_success(peer_id)
            return True
        else:
            self.update_peer_id_fail(peer_id)
            return False

    def to_vec_u8(self, string):
        """Get peer_id in Vec<u8> for blockchain"""
        return [ord(char) for char in string]

    def is_staked(self, peer_id_vector) -> bool:
        """
        Each subnet node must be staked
        """
        is_staked = self.is_subnet_node_staked(peer_id_vector)

        return is_staked

    def is_subnet_node_staked(self, peer_id_vector) -> bool:
        """
        Uses the Hypertensor `proof_of_stake` RPC method that checks
        for a subnet nodes peer_id and bootstrap_peer_id being staked
        """
        result = self.hypertensor.proof_of_stake(self.subnet_id, peer_id_vector)

        if "result" not in result:
            return False

        # must be True or False
        if result["result"] is not True and result["result"] is not False:
            return False

        return result["result"]

    @property
    def local_public_key(self) -> Ed25519PublicKey:
        return self._local_public_key


class RSAProofOfStakeAuthorizer(AuthorizerBase):
    """
    Implements a proof-of-stake authorization protocol using RSA keys
    Checks the Hypertensor network for nodes ``peer_id`` is staked.
    The ``peer_id`` is retrieved using the RSA public key
    """

    def __init__(
        self,
        local_private_key: RSAPrivateKey,
        subnet_id: int,
        hypertensor: Hypertensor
    ):
        super().__init__()
        self._local_private_key = local_private_key
        self._local_public_key = local_private_key.get_public_key()
        self.subnet_id = subnet_id
        self.hypertensor = hypertensor
        self.peer_id_to_last_successful_pos: Dict[PeerID, float] = {}
        self.pos_success_cooldown = 300
        self.peer_id_to_last_failed_pos: Dict[PeerID, float] = {}
        self.pos_fail_cooldown: float = 300  # 5 minutes default cooldown

    async def get_token(self) -> AccessToken:
        token = AccessToken(
            username="",
            public_key=self._local_public_key.to_bytes(),
            expiration_time=str(datetime.now(timezone.utc) + timedelta(minutes=1)),
        )
        token.signature = self._local_private_key.sign(self._token_to_bytes(token))
        return token

    @staticmethod
    def _token_to_bytes(access_token: AccessToken) -> bytes:
        return f"{access_token.username} {access_token.public_key} {access_token.expiration_time}".encode()

    async def sign_request(
        self, request: AuthorizedRequestBase, service_public_key: Optional[RSAPublicKey]
    ) -> None:
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

        # Get public key of signer
        try:
            client_public_key = RSAPublicKey.from_bytes(auth.client_access_token.public_key)
        except Exception as e:
            logger.debug(f"Failed to get RSA public key from bytes, Err: {e}", exc_info=True)
            return False

        signature = auth.signature
        auth.signature = b""
        # Verify signature of the request from signer
        if not client_public_key.verify(request.SerializeToString(), signature):
            logger.debug("Request has invalid signature")
            return False

        if auth.service_public_key and auth.service_public_key != self._local_public_key.to_bytes():
            logger.debug("Request is generated for a peer with another public key")
            return False

        # Verify proof of stake
        try:
            proof_of_stake = self.proof_of_stake(client_public_key)
            return proof_of_stake
        except Exception as e:
            logger.debug("Proof of stake failed, validate request", e, exc_info=True)

        return False

    async def sign_response(self, response: AuthorizedResponseBase, request: AuthorizedRequestBase) -> None:
        auth = response.auth

        local_access_token = await self.get_token()
        auth.service_access_token.CopyFrom(local_access_token)

        # auth.service_access_token.CopyFrom(self._local_public_key)
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

        service_public_key = RSAPublicKey.from_bytes(auth.service_access_token.public_key)
        signature = auth.signature
        auth.signature = b""
        if not service_public_key.verify(response.SerializeToString(), signature):
            logger.debug("Response has invalid signature")
            return False

        if auth.nonce != request.auth.nonce:
            logger.debug("Response is generated for another request")
            return False

        try:
            proof_of_stake = self.proof_of_stake(service_public_key)
            return proof_of_stake
        except Exception as e:
            logger.debug("Proof of stake failed, validate response", e, exc_info=True)

        return False

    def get_peer_id_last_success(self, peer_id: PeerID) -> float:
        return self.peer_id_to_last_successful_pos.get(peer_id, 0)

    def update_peer_id_success(self, peer_id: PeerID):
        self.peer_id_to_last_successful_pos[peer_id] = get_dht_time()
        self.peer_id_to_last_failed_pos.pop(peer_id, None)

    def get_peer_id_last_fail(self, peer_id: PeerID) -> float:
        return self.peer_id_to_last_failed_pos.get(peer_id, 0)

    def update_peer_id_fail(self, peer_id: PeerID):
        self.peer_id_to_last_failed_pos[peer_id] = get_dht_time()
        self.peer_id_to_last_successful_pos.pop(peer_id, None)

    def proof_of_stake(self, public_key: RSAPublicKey) -> bool:
        peer_id: Optional[PeerID] = get_rsa_peer_id(public_key)
        if peer_id is None:
            return False

        now = get_dht_time()

        # Recently failed — reject immediately
        last_fail = self.get_peer_id_last_fail(peer_id)
        if last_fail and now - last_fail < self.pos_fail_cooldown:
            return False

        # Recent success — no need to check again
        last_success = self.get_peer_id_last_success(peer_id)
        if last_success and now - last_success < self.pos_success_cooldown:
            return True

        # On-chain proof of stake check
        peer_id_vec = self.to_vec_u8(peer_id.to_base58())
        proof_of_stake = self.is_staked(peer_id_vec)

        if proof_of_stake:
            self.update_peer_id_success(peer_id)
            return True
        else:
            self.update_peer_id_fail(peer_id)
            return False

    def to_vec_u8(self, string):
        """Get peer_id in Vec<u8> for blockchain"""
        return [ord(char) for char in string]

    def is_staked(self, peer_id_vector) -> bool:
        """
        Each subnet node must be staked
        """
        is_staked = self.is_subnet_node_staked(peer_id_vector)

        return is_staked

    def is_subnet_node_staked(self, peer_id_vector) -> bool:
        """
        Uses the Hypertensor `proof_of_stake` RPC method that checks
        for a subnet nodes peer_id and bootstrap_peer_id being staked
        """
        result = self.hypertensor.proof_of_stake(self.subnet_id, peer_id_vector)

        if "result" not in result:
            return False

        # must be True or False
        if result["result"] is not True and result["result"] is not False:
            return False

        return result["result"]

    @property
    def local_public_key(self) -> RSAPublicKey:
        return self._local_public_key
