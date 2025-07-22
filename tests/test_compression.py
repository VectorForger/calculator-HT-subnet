import pytest
import torch

import mesh
from mesh.compression import (
    deserialize_torch_tensor,
    serialize_torch_tensor,
)
from mesh.proto.runtime_pb2 import CompressionType
from mesh.utils.streaming import combine_from_streaming, split_for_streaming

# pytest tests/test_compression.py -rP
# may need to run `pip install bitsandbytes`

@pytest.mark.forked
def test_tensor_compression(size=(128, 128, 64), alpha=5e-08, beta=0.0008):
    torch.manual_seed(0)
    X = torch.randn(*size)
    assert torch.allclose(deserialize_torch_tensor(serialize_torch_tensor(X, CompressionType.NONE)), X)
    error = deserialize_torch_tensor(serialize_torch_tensor(X, CompressionType.MEANSTD_16BIT)) - X
    assert error.square().mean() < alpha
    error = deserialize_torch_tensor(serialize_torch_tensor(X, CompressionType.FLOAT16)) - X
    assert error.square().mean() < alpha
    error = deserialize_torch_tensor(serialize_torch_tensor(X, CompressionType.QUANTILE_8BIT)) - X
    assert error.square().mean() < beta
    error = deserialize_torch_tensor(serialize_torch_tensor(X, CompressionType.UNIFORM_8BIT)) - X
    assert error.square().mean() < beta
    error = deserialize_torch_tensor(serialize_torch_tensor(X, CompressionType.BLOCKWISE_8BIT)) - X
    assert error.square().mean() < beta

    zeros = torch.zeros(5, 5)
    for compression_type in CompressionType.values():
        # 8-bit compression produces segmentation faults on zero tensors with latest bitsandbytes
        if compression_type != CompressionType.BLOCKWISE_8BIT:
            assert deserialize_torch_tensor(serialize_torch_tensor(zeros, compression_type)).isfinite().all()


def _check(tensor, compression, rtol=1e-5, atol=1e-8, chunk_size=30 * 1024):
    serialized_tensor = serialize_torch_tensor(tensor, compression)
    chunks = list(split_for_streaming(serialized_tensor, chunk_size))
    assert len(chunks) == max((len(serialized_tensor.buffer) - 1) // chunk_size + 1, 1)
    restored = combine_from_streaming(chunks)
    result = deserialize_torch_tensor(restored)
    assert result.dtype == tensor.dtype, compression
    assert result.requires_grad == tensor.requires_grad
    assert torch.allclose(result, tensor, rtol=rtol, atol=atol)


@pytest.mark.forked
def test_serialize_tensor():
    tensor = torch.randn(512, 12288, requires_grad=True)
    for chunk_size in [1024, 64 * 1024, 64 * 1024 + 1, 10**9]:
        _check(tensor, CompressionType.NONE, chunk_size=chunk_size)

    _check(tensor, CompressionType.FLOAT16, rtol=0.0, atol=1e-2)
    _check(torch.randint(0, 100, (512, 1, 1)), CompressionType.NONE)
    _check(torch.randn(10, 20), CompressionType.MEANSTD_16BIT, atol=0.1)
    _check(torch.tensor(1.0), CompressionType.NONE)
    _check(torch.tensor(1.0), CompressionType.FLOAT16)


@pytest.mark.parametrize(
    "dtype",
    [
        torch.float32,
        torch.float16,
        torch.bfloat16,
        torch.float64,
        torch.complex64,
        torch.int64,
        torch.int32,
        torch.uint8,
        torch.bool,
    ],
)
@pytest.mark.parametrize("requires_grad", [False, True])
@pytest.mark.forked
def test_serialize_tensor_properties(dtype: torch.dtype, requires_grad: bool):
    tensor = torch.randn(123, 45, requires_grad=requires_grad).to(dtype)
    if dtype == torch.bfloat16:
        compression_types = [
            type
            for type in CompressionType.values()
            if type not in (CompressionType.FLOAT16, CompressionType.MEANSTD_16BIT)
        ]
    elif torch.is_floating_point(tensor):  # nb: complex and qint data types are not is_floating_point
        compression_types = CompressionType.values()
    else:
        compression_types = [CompressionType.NONE]

    for compression_type in compression_types:
        _check(tensor, compression_type, atol=float("inf"))


@pytest.mark.parametrize("use_legacy_bfloat16", [True, False])
@pytest.mark.parametrize("tensor_size", [(4096, 16), (0, 0)])
@pytest.mark.forked
def test_serialize_bfloat16(use_legacy_bfloat16: bool, tensor_size: tuple):
    mesh.compression.base.USE_LEGACY_BFLOAT16 = use_legacy_bfloat16
    tensor = torch.randn(tensor_size, dtype=torch.bfloat16)
    _check(tensor, CompressionType.NONE)
    _check(tensor, CompressionType.BLOCKWISE_8BIT, rtol=0.1, atol=0.01, chunk_size=1024)
