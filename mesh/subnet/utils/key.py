import hashlib
from typing import Optional

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa

from mesh import PeerID
from mesh.dht.crypto import Ed25519SignatureValidator, RSASignatureValidator
from mesh.dht.validation import RecordValidatorBase
from mesh.proto import crypto_pb2
from mesh.utils import get_logger, multihash
from mesh.utils.crypto import Ed25519PrivateKey, Ed25519PublicKey, RSAPrivateKey

logger = get_logger(__name__)

"""
Private keys
"""

"""
Ed25519
"""
def generate_ed25519_private_key_file(path: str):
    private_key = ed25519.Ed25519PrivateKey.generate()

    raw_private_key = private_key.private_bytes(
      encoding=serialization.Encoding.Raw,  # DER format
      format=serialization.PrivateFormat.Raw,  # PKCS8 standard format
      encryption_algorithm=serialization.NoEncryption()  # No encryption
    )

    public_key = private_key.public_key()

    public_key_bytes = public_key.public_bytes(
      encoding=serialization.Encoding.Raw,
      format=serialization.PublicFormat.Raw,
    )

    combined_key_bytes = raw_private_key + public_key_bytes

    protobuf = crypto_pb2.PrivateKey(key_type=crypto_pb2.KeyType.Ed25519, data=combined_key_bytes)

    with open(path, "wb") as f:
      f.write(protobuf.SerializeToString())

    encoded_public_key = crypto_pb2.PublicKey(
      key_type=crypto_pb2.Ed25519,
      data=public_key_bytes,
    ).SerializeToString()

    encoded_public_key = b"\x00$" + encoded_public_key

    peer_id = PeerID(encoded_public_key)

    return private_key, public_key, raw_private_key, public_key_bytes, combined_key_bytes, peer_id

def get_ed25519_private_key(identity_path: str) -> Ed25519PrivateKey:
  with open(f"{identity_path}", "rb") as f:
    data = f.read()
    key_data = crypto_pb2.PrivateKey.FromString(data).data
    raw_private_key = ed25519.Ed25519PrivateKey.from_private_bytes(key_data[:32])
    private_key = Ed25519PrivateKey(private_key=raw_private_key)
    return private_key

"""
RSA
"""

def generate_rsa_private_key_file(path: str):
    # Generate the RSA private key
    private_key = rsa.generate_private_key(
      public_exponent=65537,
      key_size=2048,
    )

    pubkey = private_key.public_key()

    public_bytes = pubkey.public_bytes(
      encoding=serialization.Encoding.DER,
      format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    encoded_public_key = crypto_pb2.PublicKey(
      key_type=crypto_pb2.RSA,
      data=public_bytes,
    ).SerializeToString()

    encoded_digest = multihash.encode(
      hashlib.sha256(encoded_public_key).digest(),
      multihash.coerce_code("sha2-256"),
    )

    peer_id = PeerID(encoded_digest)

    public_key = RSAPrivateKey(private_key).get_public_key()

    # Serialize the private key to DER format
    private_key = private_key.private_bytes(
      encoding=serialization.Encoding.DER,
      format=serialization.PrivateFormat.TraditionalOpenSSL,
      encryption_algorithm=serialization.NoEncryption()
    )

    protobuf = crypto_pb2.PrivateKey(key_type=crypto_pb2.KeyType.RSA, data=private_key)

    with open(path, "wb") as f:
      f.write(protobuf.SerializeToString())

    return private_key, public_key, public_bytes, encoded_public_key, encoded_digest, peer_id

def get_rsa_private_key(identity_path: str) -> RSAPrivateKey:
  with open(f"{identity_path}", "rb") as f:
    data = f.read()
    key_data = crypto_pb2.PrivateKey.FromString(data).data
    private_key = serialization.load_der_private_key(key_data, password=None)
    private_key = RSAPrivateKey(private_key=private_key)
    return private_key

"""
Peer IDs
"""

"""
Extract Ed25519 peer ID from public key
"""
def extract_ed25519_peer_id_from_subkey(record_validator: RecordValidatorBase, key)-> Optional[PeerID]:
  public_keys = Ed25519SignatureValidator._PUBLIC_KEY_RE.findall(key)
  # public_keys = record_validator._PUBLIC_KEY_RE.findall(key)
  pubkey = Ed25519PublicKey.from_bytes(public_keys[0])

  peer_id = get_ed25519_peer_id(pubkey)
  return peer_id

def extract_ed25519_peer_id_from_ssh(ssh_public_key)-> Optional[PeerID]:
  ed25519_public_key = serialization.load_ssh_public_key(ssh_public_key)
  pubkey = ed25519.Ed25519PublicKey.from_public_bytes(ed25519_public_key.public_bytes_raw())
  pubkey = Ed25519PublicKey(pubkey)
  peer_id = get_ed25519_peer_id(pubkey)
  return peer_id

def get_ed25519_peer_id(public_key: Ed25519PublicKey) -> Optional[PeerID]:
  try:
    encoded_public_key = crypto_pb2.PublicKey(
      key_type=crypto_pb2.Ed25519,
      data=public_key.to_raw_bytes(),
    ).SerializeToString()

    encoded_public_key = b"\x00$" + encoded_public_key

    peer_id = PeerID(encoded_public_key)

    return peer_id
  except Exception as e:
    return None

"""
Extract RSA peer ID from ssh public key
"""
def extract_rsa_peer_id(key)-> Optional[PeerID]:
  public_keys = RSASignatureValidator._PUBLIC_KEY_RE.findall(key)

  rsa_public_key = serialization.load_ssh_public_key(public_keys[0])

  public_bytes = rsa_public_key.public_bytes(
    encoding=serialization.Encoding.DER,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
  )

  encoded_public_key = crypto_pb2.PublicKey(
    key_type=crypto_pb2.RSA,
    data=public_bytes,
  ).SerializeToString()

  encoded_digest = multihash.encode(
    hashlib.sha256(encoded_public_key).digest(),
    multihash.coerce_code("sha2-256"),
  )

  return PeerID(encoded_digest)

def extract_rsa_peer_id_from_subkey(key)-> Optional[PeerID]:
  public_keys = RSASignatureValidator._PUBLIC_KEY_RE.findall(key)

  rsa_public_key = serialization.load_ssh_public_key(public_keys[0])

  public_bytes = rsa_public_key.public_bytes(
    encoding=serialization.Encoding.DER,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
  )

  encoded_public_key = crypto_pb2.PublicKey(
    key_type=crypto_pb2.RSA,
    data=public_bytes,
  ).SerializeToString()

  encoded_digest = multihash.encode(
    hashlib.sha256(encoded_public_key).digest(),
    multihash.coerce_code("sha2-256"),
  )

  return PeerID(encoded_digest)

def extract_rsa_peer_id_from_ssh(ssh_public_key) -> Optional[PeerID]:
  rsa_public_key = serialization.load_ssh_public_key(ssh_public_key)

  public_bytes = rsa_public_key.public_bytes(
    encoding=serialization.Encoding.DER,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
  )

  encoded_public_key = crypto_pb2.PublicKey(
    key_type=crypto_pb2.RSA,
    data=public_bytes,
  ).SerializeToString()

  encoded_digest = multihash.encode(
    hashlib.sha256(encoded_public_key).digest(),
    multihash.coerce_code("sha2-256"),
  )

  return PeerID(encoded_digest)

def get_rsa_peer_id(public_bytes: bytes) -> Optional[PeerID]:
    """
    See [1] for the specification of how this conversion should happen.

    [1] https://github.com/libp2p/specs/blob/master/peer-ids/peer-ids.md#peer-ids
    """
    encoded_public_key = crypto_pb2.PublicKey(
        key_type=crypto_pb2.RSA,
        data=public_bytes,
    ).SerializeToString()

    encoded_digest = multihash.encode(
        hashlib.sha256(encoded_public_key).digest(),
        multihash.coerce_code("sha2-256"),
    )
    return PeerID(encoded_digest)

def extract_rsa_peer_id_old(key)-> Optional[PeerID]:
  public_keys = RSASignatureValidator._PUBLIC_KEY_RE.findall(key)

  rsa_public_key = serialization.load_ssh_public_key(public_keys[0])

  public_bytes = rsa_public_key.public_bytes(
    encoding=serialization.Encoding.DER,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
  )

  encoded_public_key = crypto_pb2.PublicKey(
    key_type=crypto_pb2.RSA,
    data=public_bytes,
  ).SerializeToString()

  encoded_digest = multihash.encode(
    hashlib.sha256(encoded_public_key).digest(),
    multihash.coerce_code("sha2-256"),
  )

  return PeerID(encoded_digest)
