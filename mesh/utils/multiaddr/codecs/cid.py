# This code is originally taken from https://github.com/multiformats/py-multiaddr
#
# The MIT License (MIT)
#
# Copyright (c) 2014-2015 Steven Buss
# Copyright (c) 2019-2020 Alexander Schlarb
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
import multibase
import multicodec
from morphys import ensure_bytes, ensure_unicode

import mesh.utils.multihash as mh
from mesh.utils import base58

from . import LENGTH_PREFIXED_VAR_SIZE

SIZE = LENGTH_PREFIXED_VAR_SIZE
IS_PATH = False


# Spec: https://github.com/libp2p/specs/blob/master/peer-ids/peer-ids.md#string-representation
CIDv0_PREFIX_TO_LENGTH = {
    # base58btc prefixes for valid lengths 1 – 42 with the identity “hash” function
    "12": [5, 12, 19, 23, 30, 41, 52, 56],
    "13": [9, 16, 34, 45],
    "14": [27, 38, 49, 60],
    "15": [3, 6, 20],
    "16": [3, 6, 13, 20, 31, 42, 53],
    "17": [3, 13, 42],
    "18": [3],
    "19": [3, 24, 57],
    "1A": [24, 35, 46],
    "1B": [35],
    "1D": [17],
    "1E": [10, 17],
    "1F": [10],
    "1G": [10, 28, 50],
    "1H": [28, 39],
    "1P": [21],
    "1Q": [21],
    "1R": [21, 54],
    "1S": [54],
    "1T": [7, 32, 43],
    "1U": [7, 32, 43],
    "1V": [7],
    "1W": [7, 14],
    "1X": [7, 14],
    "1Y": [7, 14],
    "1Z": [7, 14],
    "1f": [4],
    "1g": [4, 58],
    "1h": [4, 25, 58],
    "1i": [4, 25],
    "1j": [4, 25],
    "1k": [4, 25, 47],
    "1m": [4, 36, 47],
    "1n": [4, 36],
    "1o": [4, 36],
    "1p": [4],
    "1q": [4],
    "1r": [4],
    "1s": [4],
    "1t": [4],
    "1u": [4],
    "1v": [4],
    "1w": [4],
    "1x": [4],
    "1y": [4],
    "1z": [4, 18],
    # base58btc prefix for length 42 with the sha256 hash function
    "Qm": [46],
}

PROTO_NAME_TO_CIDv1_CODEC = {
    # The “p2p” multiaddr protocol requires all keys to use the “libp2p-key” multicodec
    "p2p": "libp2p-key",
}


def to_bytes(proto, string):
    expected_codec = PROTO_NAME_TO_CIDv1_CODEC.get(proto.name)

    if len(string) in CIDv0_PREFIX_TO_LENGTH.get(string[0:2], ()):  # CIDv0
        # Upgrade the wire (binary) representation of any received CIDv0 string
        # to CIDv1 if we can determine which multicodec value to use
        if expected_codec:
            # return cid.make_cid(1, expected_codec, base58.b58decode(string)).buffer
            return make_cid(1, expected_codec, base58.b58decode(string)).buffer # without cid

        return base58.b58decode(string)
    else:  # CIDv1+
        # parsed = cid.from_string(string)
        parsed = from_string(string) # without cid

        # Ensure CID has correct codec for protocol
        if expected_codec and parsed.codec != expected_codec:
            raise ValueError("“{0}” multiaddr CIDs must use the “{1}” multicodec".format(proto.name, expected_codec))

        return parsed.buffer


def _is_binary_cidv0_multihash(buf):
    if buf.startswith(b"\x12\x20") and len(buf) == 34:  # SHA2-256
        return True

    if (buf[0] == 0x00 and buf[1] in range(43)) and len(buf) == (buf[1] + 2):  # Identity hash
        return True

    return False


def to_string(proto, buf):
    expected_codec = PROTO_NAME_TO_CIDv1_CODEC.get(proto.name)

    if _is_binary_cidv0_multihash(buf):  # CIDv0
        if not expected_codec:
            # Simply encode as base58btc as there is nothing better to do
            return base58.b58encode(buf).decode("ascii")

        # “Implementations SHOULD display peer IDs using the first (raw
        #  base58btc encoded multihash) format until the second format is
        #  widely supported.”
        #
        # In the future the following line should instead convert the multihash
        # to CIDv1 and with the `expected_codec` and wrap it in base32:
        #   return cid.make_cid(1, expected_codec, buf).encode("base32").decode("ascii")
        return base58.b58encode(buf).decode("ascii")
    else:  # CIDv1+
        # parsed = cid.from_bytes(buf) # without cid
        parsed = from_bytes(buf)

        # Ensure CID has correct codec for protocol
        if expected_codec and parsed.codec != expected_codec:
            raise ValueError("“{0}” multiaddr CIDs must use the “{1}” multicodec".format(proto.name, expected_codec))

        # “Implementations SHOULD display peer IDs using the first (raw
        #  base58btc encoded multihash) format until the second format is
        #  widely supported.”
        if expected_codec and _is_binary_cidv0_multihash(parsed.multihash):
            return base58.b58encode(parsed.multihash).decode("ascii")

        return parsed.encode("base32").decode("ascii")

class BaseCID(object):
    __hash__ = object.__hash__

    def __init__(self, version, codec, multihash):
        """
        Creates a new CID object. This class should not be used directly, use :py:class:`cid.cid.CIDv0` or
        :py:class:`cid.cid.CIDv1` instead.


        :param int version: CID version (0 or 1)
        :param str codec: codec to be used for encoding the hash
        :param str multihash: the multihash
        """
        self._version = version
        self._codec = codec
        self._multihash = ensure_bytes(multihash)

    @property
    def version(self):
        """ CID version """
        return self._version

    @property
    def codec(self):
        """ CID codec """
        return self._codec

    @property
    def multihash(self):
        """ CID multihash """
        return self._multihash

    @property
    def buffer(self):
        raise NotImplementedError

    def encode(self, *args, **kwargs):
        raise NotImplementedError

    def __repr__(self):
        def truncate(s, length):
            return s[:length] + b'..' if len(s) > length else s

        truncate_length = 20
        return '{class_}(version={version}, codec={codec}, multihash={multihash})'.format(
            class_=self.__class__.__name__,
            version=self._version,
            codec=self._codec,
            multihash=truncate(self._multihash, truncate_length),
        )

    def __str__(self):
        return ensure_unicode(self.encode())

    def __eq__(self, other):
        return (self.version == other.version) and (self.codec == other.codec) and (self.multihash == other.multihash)


class CIDv0(BaseCID):
    """ CID version 0 object """
    CODEC = 'dag-pb'

    def __init__(self, multihash):
        """
        :param bytes multihash: multihash for the CID
        """
        super(CIDv0, self).__init__(0, self.CODEC, multihash)

    @property
    def buffer(self):
        """
        The raw representation that will be encoded.

        :return: the multihash
        :rtype: bytes
        """
        return self.multihash

    def encode(self):
        """
        base58-encoded buffer

        :return: encoded representation or CID
        :rtype: bytes
        """
        return ensure_bytes(base58.b58encode(self.buffer))

    def to_v1(self):
        """
        Get an equivalent :py:class:`cid.CIDv1` object.

        :return: :py:class:`cid.CIDv1` object
        :rtype: :py:class:`cid.CIDv1`
        """
        return CIDv1(self.CODEC, self.multihash)


class CIDv1(BaseCID):
    """ CID version 1 object """

    def __init__(self, codec, multihash):
        super(CIDv1, self).__init__(1, codec, multihash)

    @property
    def buffer(self):
        """
        The raw representation of the CID

        :return: raw representation of the CID
        :rtype: bytes
        """
        return b''.join([bytes([self.version]), multicodec.add_prefix(self.codec, self.multihash)])

    def encode(self, encoding='base58btc'):
        """
        Encoded version of the raw representation

        :param str encoding: the encoding to use to encode the raw representation, should be supported by
            ``py-multibase``
        :return: encoded raw representation with the given encoding
        :rtype: bytes
        """
        return multibase.encode(encoding, self.buffer)

    def to_v0(self):
        """
        Get an equivalent :py:class:`cid.CIDv0` object.

        :return: :py:class:`cid.CIDv0` object
        :rtype: :py:class:`cid.CIDv0`
        :raise ValueError: if the codec is not 'dag-pb'
        """
        if self.codec != CIDv0.CODEC:
            raise ValueError('CIDv1 can only be converted for codec {}'.format(CIDv0.CODEC))

        return CIDv0(self.multihash)


def make_cid(*args):
    """
    Creates a :py:class:`cid.CIDv0` or :py:class:`cid.CIDv1` object based on the given parameters

    The function supports the following signatures:

            make_cid(<base58 encoded multihash CID>) -> CIDv0

            make_cid(<multihash CID>) -> CIDv0

            make_cid(<multibase encoded multihash CID>) -> CIDv1

            make_cid(<version>, <codec>, <multihash>) -> CIDv1

    :param args:
        - base58-encoded multihash (str or bytes)
        - multihash (str or bytes)
        - multibase-encoded multihash (str or bytes)
        - version:int, codec(str), multihash(str or bytes)
    :returns: the respective CID object
    :rtype: :py:class:`cid.CIDv0` or :py:class:`cid.CIDv1`
    :raises ValueError: if the number of arguments is not 1 or 3
    :raises ValueError: if the only argument passed is not a ``str`` or a ``byte``
    :raises ValueError: if the string provided is not a valid base58 encoded hash
    :raises ValueError: if 3 arguments are passed and version is not 0 or 1
    :raises ValueError: if 3 arguments are passed and the ``codec`` is not supported by ``multicodec``
    :raises ValueError: if 3 arguments are passed and the ``multihash`` is not ``str`` or ``byte``
    :raises ValueError: if 3 arguments are passed with version 0 and codec is not *dag-pb*
    """
    if len(args) == 1:
        data = args[0]
        if isinstance(data, str):
            return from_string(data)
        elif isinstance(data, bytes):
            return from_bytes(data)
        else:
            raise ValueError('invalid argument passed, expected: str or byte, found: {}'.format(type(data)))

    elif len(args) == 3:
        version, codec, multihash = args
        if version not in (0, 1):
            raise ValueError('version should be 0 or 1, {} was provided'.format(version))
        if not multicodec.is_codec(codec):
            raise ValueError('invalid codec {} provided, please check'.format(codec))
        if not (isinstance(multihash, str) or isinstance(multihash, bytes)):
            raise ValueError('invalid type for multihash provided, should be str or bytes')

        if version == 0:
            if codec != CIDv0.CODEC:
                raise ValueError('codec for version 0 can only be {}, found: {}'.format(CIDv0.CODEC, codec))
            return CIDv0(multihash)
        else:
            return CIDv1(codec, multihash)
    else:
        raise ValueError('invalid number of arguments, expected 1 or 3')


def is_cid(cidstr):
    """
    Checks if a given input string is valid encoded CID or not.
    It takes same input as `cid.make_cid` method with a single argument


    :param cidstr: input string which can be a

        - base58-encoded multihash
        - multihash
        - multibase-encoded multihash
    :type cidstr: str or bytes
    :return: if the value is a valid CID or not
    :rtype: bool
    """
    try:
        return bool(make_cid(cidstr))
    except ValueError:
        return False


def from_string(cidstr):
    """
    Creates a CID object from a encoded form

    :param str cidstr: can be

        - base58-encoded multihash
        - multihash
        - multibase-encoded multihash
    :return: a CID object
    :rtype: :py:class:`cid.CIDv0` or :py:class:`cid.CIDv1`
    """
    cidbytes = ensure_bytes(cidstr, 'utf-8')
    return from_bytes(cidbytes)


def from_bytes(cidbytes):
    """
    Creates a CID object from a encoded form

    :param bytes cidbytes: can be

        - base58-encoded multihash
        - multihash
        - multibase-encoded multihash
    :return: a CID object
    :rtype: :py:class:`cid.CIDv0` or :py:class:`cid.CIDv1`
    :raises: `ValueError` if the base58-encoded string is not a valid string
    :raises: `ValueError` if the length of the argument is zero
    :raises: `ValueError` if the length of decoded CID is invalid
    """
    if len(cidbytes) < 2:
        raise ValueError('argument length can not be zero')

    # first byte for identity multibase and CIDv0 is 0x00
    # putting in assumption that multibase for CIDv0 can not be identity
    # refer: https://github.com/ipld/cid/issues/13#issuecomment-326490275
    if cidbytes[0] != 0 and multibase.is_encoded(cidbytes):
        # if the bytestream is multibase encoded
        cid = multibase.decode(cidbytes)

        if len(cid) < 2:
            raise ValueError('cid length is invalid')

        data = cid[1:]
        version = int(cid[0])
        codec = multicodec.get_codec(data)
        multihash = multicodec.remove_prefix(data)
    elif cidbytes[0] in (0, 1):
        # if the bytestream is a CID
        version = cidbytes[0]
        data = cidbytes[1:]
        codec = multicodec.get_codec(data)
        multihash = multicodec.remove_prefix(data)
    else:
        # otherwise its just base58-encoded multihash
        try:
            version = 0
            codec = CIDv0.CODEC
            multihash = base58.b58decode(cidbytes)
        except ValueError:
            raise ValueError('multihash is not a valid base58 encoded multihash')

    try:
        mh.decode(multihash)
    except ValueError:
        raise

    return make_cid(version, codec, multihash)
