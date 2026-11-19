"""Verify selected PKCS#12 certificate and key associations inside libcrypto."""

from __future__ import annotations

import ctypes
import os
import ssl
from collections import defaultdict
from contextlib import ExitStack

_POINTER = ctypes.c_void_p
_INTEGER = ctypes.c_int
_STRING = ctypes.c_char_p
_ABI = {
    "OSSL_LIB_CTX_new": (_POINTER, ()),
    "OSSL_LIB_CTX_free": (None, (_POINTER,)),
    "OSSL_LIB_CTX_set0_default": (_POINTER, (_POINTER,)),
    "OSSL_PROVIDER_load": (_POINTER, (_POINTER, _STRING)),
    "OSSL_PROVIDER_unload": (_INTEGER, (_POINTER,)),
    "ERR_clear_error": (None, ()),
    "BIO_new_mem_buf": (_POINTER, (_STRING, _INTEGER)),
    "BIO_free": (_INTEGER, (_POINTER,)),
    "d2i_PKCS12_bio": (_POINTER, (_POINTER, _POINTER)),
    "PKCS12_free": (None, (_POINTER,)),
    "PKCS12_verify_mac": (_INTEGER, (_POINTER, _STRING, _INTEGER)),
    "PKCS12_unpack_authsafes": (_POINTER, (_POINTER,)),
    "PKCS12_unpack_p7data": (_POINTER, (_POINTER,)),
    "PKCS12_unpack_p7encdata": (_POINTER, (_POINTER, _STRING, _INTEGER)),
    "PKCS7_free": (None, (_POINTER,)),
    "OPENSSL_sk_num": (_INTEGER, (_POINTER,)),
    "OPENSSL_sk_value": (_POINTER, (_POINTER, _INTEGER)),
    "OPENSSL_sk_free": (None, (_POINTER,)),
    "OBJ_txt2nid": (_INTEGER, (_STRING,)),
    "OBJ_obj2nid": (_INTEGER, (_POINTER,)),
    "PKCS12_SAFEBAG_free": (None, (_POINTER,)),
    "PKCS12_SAFEBAG_get_nid": (_INTEGER, (_POINTER,)),
    "PKCS12_SAFEBAG_get_bag_nid": (_INTEGER, (_POINTER,)),
    "PKCS12_SAFEBAG_get0_attr": (_POINTER, (_POINTER, _INTEGER)),
    "PKCS12_SAFEBAG_get0_attrs": (_POINTER, (_POINTER,)),
    "PKCS12_SAFEBAG_get0_safes": (_POINTER, (_POINTER,)),
    "PKCS12_SAFEBAG_get1_cert": (_POINTER, (_POINTER,)),
    "PKCS12_SAFEBAG_get0_p8inf": (_POINTER, (_POINTER,)),
    "PKCS12_decrypt_skey": (_POINTER, (_POINTER, _STRING, _INTEGER)),
    "PKCS8_PRIV_KEY_INFO_free": (None, (_POINTER,)),
    "ASN1_TYPE_get_octetstring": (_INTEGER, (_POINTER, _POINTER, _INTEGER)),
    "i2d_X509": (_INTEGER, (_POINTER, ctypes.POINTER(_POINTER))),
    "X509_free": (None, (_POINTER,)),
    "X509_check_private_key": (_INTEGER, (_POINTER, _POINTER)),
    "X509_ATTRIBUTE_get0_object": (_POINTER, (_POINTER,)),
    "X509_ATTRIBUTE_count": (_INTEGER, (_POINTER,)),
    "EVP_PKCS82PKEY": (_POINTER, (_POINTER,)),
    "EVP_PKEY_free": (None, (_POINTER,)),
    "EVP_PKEY_CTX_new": (_POINTER, (_POINTER, _POINTER)),
    "EVP_PKEY_CTX_free": (None, (_POINTER,)),
    "EVP_PKEY_pairwise_check": (_INTEGER, (_POINTER,)),
}


def load_crypto() -> ctypes.CDLL:
    try:
        crypto = ctypes.CDLL("libcrypto.so.3")
        for name, (result, arguments) in _ABI.items():
            function = getattr(crypto, name)
            function.restype = result
            function.argtypes = arguments
    except (AttributeError, OSError):
        raise ValueError("system OpenSSL 3 libcrypto is required to check PKCS#12 signing keys") from None
    return crypto


def own(cleanup, pointer, free):
    if not pointer:
        raise ValueError("could not read PKCS#12 signing key data")
    cleanup.callback(free, pointer)
    return pointer


def stack_items(crypto, stack):
    return [crypto.OPENSSL_sk_value(stack, index) for index in range(crypto.OPENSSL_sk_num(stack))]


def own_stack(crypto, cleanup, stack, free):
    items = stack_items(crypto, own(cleanup, stack, crypto.OPENSSL_sk_free))
    for item in items:
        cleanup.callback(free, item)
    return items


def bag_id(crypto, bag, local_key_id):
    attributes = crypto.PKCS12_SAFEBAG_get0_attrs(bag)
    if not attributes:
        return None
    identifiers = [
        attribute for attribute in stack_items(crypto, attributes)
        if crypto.OBJ_obj2nid(crypto.X509_ATTRIBUTE_get0_object(attribute)) == local_key_id
    ]
    if not identifiers:
        return None
    if len(identifiers) != 1 or crypto.X509_ATTRIBUTE_count(identifiers[0]) != 1:
        raise ValueError("PKCS#12 contains an ambiguous signing key identifier")
    attribute = crypto.PKCS12_SAFEBAG_get0_attr(bag, local_key_id)
    if not attribute:
        raise ValueError("could not read a PKCS#12 signing key identifier")
    size = crypto.ASN1_TYPE_get_octetstring(attribute, None, 0)
    if size <= 0:
        raise ValueError("PKCS#12 contains an invalid signing key identifier")
    identifier = ctypes.create_string_buffer(size)
    if crypto.ASN1_TYPE_get_octetstring(attribute, identifier, size) != size:
        raise ValueError("could not read a PKCS#12 signing key identifier")
    return identifier.raw


def certificate_der(crypto, certificate):
    size = crypto.i2d_X509(certificate, None)
    if size <= 0:
        raise ValueError("could not read a PKCS#12 signing certificate")
    encoded = ctypes.create_string_buffer(size)
    cursor = _POINTER(ctypes.addressof(encoded))
    if crypto.i2d_X509(certificate, ctypes.byref(cursor)) != size:
        raise ValueError("could not read a PKCS#12 signing certificate")
    return encoded.raw


def flattened_bags(crypto, bags, nested_type):
    for bag in bags:
        kind = crypto.PKCS12_SAFEBAG_get_nid(bag)
        if kind == nested_type:
            nested = crypto.PKCS12_SAFEBAG_get0_safes(bag)
            if not nested:
                raise ValueError("could not read nested PKCS#12 signing data")
            yield from flattened_bags(crypto, stack_items(crypto, nested), nested_type)
        else:
            yield kind, bag


def verified_password(crypto, bundle, password):
    encoded = os.fsencode(password)
    if crypto.PKCS12_verify_mac(bundle, encoded, len(encoded)) == 1:
        return encoded
    # Follow OpenSSL's bytewise compatibility conversion for older exports.
    legacy = encoded.decode("latin-1").encode("utf-8")
    if crypto.PKCS12_verify_mac(bundle, legacy, len(legacy)) == 1:
        return legacy
    raise ValueError("could not authenticate the PKCS#12 signing keys")


def read_selected_pairs(crypto, cleanup, contents, password, selected):
    bio = own(cleanup, crypto.BIO_new_mem_buf(contents, len(contents)), crypto.BIO_free)
    bundle = own(cleanup, crypto.d2i_PKCS12_bio(bio, None), crypto.PKCS12_free)
    secret = verified_password(crypto, bundle, password)
    safes = own_stack(crypto, cleanup, crypto.PKCS12_unpack_authsafes(bundle), crypto.PKCS7_free)
    nested, cert_type, x509_type, encrypted_key, plain_key, key_id = (
        crypto.OBJ_txt2nid(name) for name in (
            b"safeContentsBag", b"certBag", b"x509Certificate", b"pkcs8ShroudedKeyBag", b"keyBag", b"localKeyID",
        )
    )
    certificates = defaultdict(list)
    keys = defaultdict(list)
    for safe in safes:
        bags = crypto.PKCS12_unpack_p7data(safe)
        if not bags:
            crypto.ERR_clear_error()
            bags = crypto.PKCS12_unpack_p7encdata(safe, secret, len(secret))
        items = own_stack(crypto, cleanup, bags, crypto.PKCS12_SAFEBAG_free)
        for kind, bag in flattened_bags(crypto, items, nested):
            if kind in (encrypted_key, plain_key):
                keys[bag_id(crypto, bag, key_id)].append((kind == encrypted_key, bag))
            elif kind == cert_type and crypto.PKCS12_SAFEBAG_get_bag_nid(bag) == x509_type:
                certificate = own(cleanup, crypto.PKCS12_SAFEBAG_get1_cert(bag), crypto.X509_free)
                encoded = certificate_der(crypto, certificate)
                if encoded in selected:
                    certificates[encoded].append((bag_id(crypto, bag, key_id), certificate))
    return certificates, keys, secret


def pair_matches(crypto, certificate, key_bag, secret) -> bool:
    encrypted, bag = key_bag
    with ExitStack() as cleanup:
        if encrypted:
            pkcs8 = own(cleanup, crypto.PKCS12_decrypt_skey(bag, secret, len(secret)), crypto.PKCS8_PRIV_KEY_INFO_free)
        else:
            pkcs8 = crypto.PKCS12_SAFEBAG_get0_p8inf(bag)
            if not pkcs8:
                raise ValueError("could not read a PKCS#12 private key")
        key = own(cleanup, crypto.EVP_PKCS82PKEY(pkcs8), crypto.EVP_PKEY_free)
        if crypto.X509_check_private_key(certificate, key) != 1:
            crypto.ERR_clear_error()
            return False
        context = own(cleanup, crypto.EVP_PKEY_CTX_new(key, None), crypto.EVP_PKEY_CTX_free)
        return crypto.EVP_PKEY_pairwise_check(context) == 1


def verify_associations(crypto, certificates, keys, secret) -> None:
    for matching_bags in certificates.values():
        for identifier, certificate in matching_bags:
            declared = keys.get(identifier) if identifier is not None else None
            if declared:
                paired = all(pair_matches(crypto, certificate, key, secret) for key in declared)
            else:
                # Native importers can pair an unlabeled key by its public
                # components. A conflicting explicit association takes precedence.
                paired = any(pair_matches(crypto, certificate, key, secret) for key in keys.get(None, ()))
            if not paired:
                raise ValueError("PKCS#12 selected signing certificate lacks a matching private key")


def verify_private_keys(contents: bytes, password: str, selected_pems: list[bytes], *, legacy: bool) -> None:
    selected = {ssl.PEM_cert_to_DER_cert(pem.decode("ascii")) for pem in selected_pems}
    if not selected:
        raise ValueError("no signing certificate was selected for PKCS#12 key verification")
    crypto = load_crypto()
    with ExitStack() as cleanup:
        context = own(cleanup, crypto.OSSL_LIB_CTX_new(), crypto.OSSL_LIB_CTX_free)
        previous = crypto.OSSL_LIB_CTX_set0_default(context)
        if not previous:
            raise ValueError("could not initialize OpenSSL signing key verification")
        cleanup.callback(crypto.OSSL_LIB_CTX_set0_default, previous)
        cleanup.callback(crypto.ERR_clear_error)
        for name in ((b"default", b"legacy") if legacy else (b"default",)):
            own(cleanup, crypto.OSSL_PROVIDER_load(context, name), crypto.OSSL_PROVIDER_unload)
        certificates, keys, secret = read_selected_pairs(crypto, cleanup, contents, password, selected)
        if set(certificates) != selected:
            raise ValueError("PKCS#12 did not contain all selected signing certificates")
        verify_associations(crypto, certificates, keys, secret)
