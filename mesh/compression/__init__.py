"""
Compression strategies that reduce the network communication in .averaging, .optim and .moe
"""

from mesh.compression.adaptive import PerTensorCompression, RoleAdaptiveCompression, SizeAdaptiveCompression
from mesh.compression.base import CompressionBase, CompressionInfo, NoCompression, TensorRole
from mesh.compression.floating import Float16Compression, ScaledFloat16Compression
from mesh.compression.quantization import BlockwiseQuantization, Quantile8BitQuantization, Uniform8BitQuantization
from mesh.compression.serialization import (
    deserialize_tensor_stream,
    deserialize_torch_tensor,
    serialize_torch_tensor,
)
