import time
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from django.core.exceptions import SuspiciousOperation
from apps.accounts.oidc import PortalOIDCBackend


@pytest.fixture
def identity(settings):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    settings.OIDC_OP_TOKEN_ENDPOINT = 'https://idp.example/token'
    settings.OIDC_OP_USER_ENDPOINT = 'https://idp.example/userinfo'
    settings.OIDC_OP_ISSUER = 'https://idp.example'
    settings.OIDC_RP_CLIENT_ID = 'portal'
    settings.OIDC_RP_CLIENT_SECRET = 'unused'
    settings.OIDC_RP_SIGN_ALGO = 'RS256'
    settings.OIDC_RP_IDP_SIGN_KEY = key.public_key()
    settings.OIDC_CLOCK_SKEW_SECONDS = 60
    claims = dict(iss='https://idp.example',sub='123',aud='portal',nonce='nonce',iat=int(time.time())+30,nbf=int(time.time())+30,exp=int(time.time())+300)
    return PortalOIDCBackend(), key, claims


def test_small_clock_skew_accepts_signed_token(identity):
    backend, key, claims = identity
    assert backend.verify_token(jwt.encode(claims,key,algorithm='RS256'), nonce='nonce')['sub'] == '123'


@pytest.mark.parametrize('claim,value', [('iat',180),('nbf',180),('exp',-1),('iss','https://wrong.example'),('aud','wrong'),('nonce','wrong')])
def test_invalid_token_is_controlled_rejection(identity, claim, value):
    backend,key,claims = identity
    # Compute relative dates at execution, not collection: a full run can take
    # longer than the future-token offset and otherwise turn it into a valid token.
    claims[claim] = time.time() + value if claim in ('iat','nbf','exp') else value
    with pytest.raises(SuspiciousOperation):
        backend.verify_token(jwt.encode(claims,key,algorithm='RS256'),nonce='nonce')


def test_invalid_signature_is_rejected(identity):
    backend,key,claims = identity
    wrong = rsa.generate_private_key(public_exponent=65537,key_size=2048)
    with pytest.raises(SuspiciousOperation):
        backend.verify_token(jwt.encode(claims,wrong,algorithm='RS256'),nonce='nonce')
