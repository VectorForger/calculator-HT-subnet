import argparse
import hashlib

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa

from mesh.p2p.p2p_daemon import P2P
from mesh.p2p.p2p_daemon_bindings.datastructures import PeerID
from mesh.proto import crypto_pb2
from mesh.utils import multihash
from mesh.utils.logging import get_logger

logger = get_logger(__name__)

# python -m subnet.cli.crypto.key --path private_key.key
# python -m subnet.cli.crypto.key --path private_key2.key

def main():
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--path", type=str, required=False, default="private_key.key", help="File location of private key. ")
    parser.add_argument("--key_type", type=str, required=False, default="ed25519", help="Key type used in subnet. ed25519, rsa")

    args = parser.parse_args()

    path = args.path
    key_type = args.key_type.lower()

    if key_type == "rsa":
        with open(path, "rb") as f:
            data = f.read()
            key_data = crypto_pb2.PrivateKey.FromString(data).data

            private_key = serialization.load_der_private_key(key_data, password=None)

            encoded_public_key = private_key.public_key().public_bytes(
                encoding=serialization.Encoding.DER,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            logger.info(f"DER RSA Public Key: {encoded_public_key}")

            encoded_public_key = crypto_pb2.PublicKey(
                key_type=crypto_pb2.RSA,
                data=encoded_public_key,
            ).SerializeToString()

            encoded_digest = multihash.encode(
                hashlib.sha256(encoded_public_key).digest(),
                multihash.coerce_code("sha2-256"),
            )
    elif key_type == "ed25519":
        with open(path, "rb") as f:
            data = f.read()
            key_data = crypto_pb2.PrivateKey.FromString(data).data
            private_key = ed25519.Ed25519PrivateKey.from_private_bytes(key_data[:32])
            public_key = private_key.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )

            combined_key_bytes = private_key.private_bytes_raw() + public_key

            encoded_public_key = crypto_pb2.PublicKey(
                key_type=crypto_pb2.Ed25519,
                data=public_key,
            ).SerializeToString()

            encoded_digest = b"\x00$" + encoded_public_key
    else:
        raise ValueError("Invalid key type. Supported types: rsa, ed25519")

    peer_id = PeerID(encoded_digest)
    logger.info(f"Peer ID {peer_id}")

if __name__ == "__main__":
    main()
