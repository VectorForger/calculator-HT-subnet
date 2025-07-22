from typing import AsyncIterator

import pytest

from mesh.proto import auth_pb2
from mesh.proto.auth_pb2 import ResponseAuthInfo
from mesh.utils.auth import (
    AuthorizedRequestBase,
    AuthorizedResponseBase,
    AuthRole,
    AuthRPCWrapperStreamer,
    TokenRSAAuthorizerBase,
)

# pytest tests/test_auth_streamer_rsa.py -rP

# class DummyRequest:
#     def __init__(self, msg):
#         self.msg = msg
#         self.auth = type("Auth", (), {
#             "client_access_token": type("Token", (), {})(),
#             "service_public_key": b"",
#             "time": 0.0,
#             "nonce": b"",
#             "signature": b""
#         })()

#     def SerializeToString(self):
#         return self.msg.encode()

# class DummyResponse:
#     def __init__(self, reply):
#         self.reply = reply
#         self.auth = type("Auth", (), {
#             "service_access_token": type("Token", (), {})(),
#             "nonce": b"",
#             "signature": b""
#         })()

#     def SerializeToString(self):
#         return self.reply.encode()

# class DummyStub:
#     async def rpc_unary(self, request): return DummyResponse("echo:" + request.msg)
#     async def rpc_stream(self, request) -> AsyncIterator[DummyResponse]:
#         for i in range(2):
#             yield DummyResponse(f"stream:{request.msg}:{i}")

class DummyRequest:
    def __init__(self, msg: str):
        self.msg = msg
        self.auth = auth_pb2.RequestAuthInfo(
            client_access_token=auth_pb2.AccessToken(),
            service_public_key=b"",
            time=0.0,
            nonce=b"",
            signature=b""
        )

    def SerializeToString(self) -> bytes:
        return self.msg.encode()

    # Interface conformance
    @property
    def __class__(self):
        # This trick makes isinstance(..., AuthorizedRequestBase) pass
        class DummyClass(AuthorizedRequestBase): pass  # noqa: E701
        return DummyClass


class DummyResponse:
    def __init__(self, reply: str):
        self.reply = reply
        self.auth = auth_pb2.ResponseAuthInfo(
            service_access_token=auth_pb2.AccessToken(),
            nonce=b"",
            signature=b""
        )

    def SerializeToString(self) -> bytes:
        return self.reply.encode()

    @property
    def __class__(self):
        class DummyClass(AuthorizedResponseBase): pass
        return DummyClass


class DummyStub:
    async def rpc_unary(self, request: DummyRequest) -> DummyResponse:
        return DummyResponse("echo:" + request.msg)

    async def rpc_stream(self, request: DummyRequest) -> AsyncIterator[DummyResponse]:
        for i in range(2):
            yield DummyResponse(f"stream:{request.msg}:{i}")

@pytest.mark.asyncio
async def test_authrpcwrapper_real_authorizer():
    # Use real RSA keys
    authorizer = TokenRSAAuthorizerBase()

    raw_stub = DummyStub()
    servicer_stub = AuthRPCWrapperStreamer(raw_stub, AuthRole.SERVICER, authorizer)
    client_stub = AuthRPCWrapperStreamer(servicer_stub, AuthRole.CLIENT, authorizer)

    # ✅ VALID unary
    req = DummyRequest("test")
    resp = await client_stub.rpc_unary(req)
    assert resp is not None
    assert resp.reply == "echo:test"

    # ✅ VALID streaming
    stream = client_stub.rpc_stream(DummyRequest("streaming"))
    replies = [r.reply async for r in stream]
    assert replies == ["stream:streaming:0", "stream:streaming:1"]

    stream = client_stub.rpc_stream(req)
    replies = []
    async for resp in stream:
        assert isinstance(resp.auth, ResponseAuthInfo)
        replies.append(resp.reply)

    assert replies == ["stream:test:0", "stream:test:1"]
