from django.conf import settings
from mozilla_django_oidc.auth import OIDCAuthenticationBackend
from .models import User
import time
import jwt
from django.core.exceptions import SuspiciousOperation, ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Q


def validate_id_claims(claims):
    audience = claims.get('aud')
    audiences = [audience] if isinstance(audience,str) else audience
    if (claims.get('iss') != settings.OIDC_OP_ISSUER or not claims.get('sub') or
        not isinstance(audiences,list) or settings.OIDC_RP_CLIENT_ID not in audiences or
        (len(audiences) > 1 and claims.get('azp') != settings.OIDC_RP_CLIENT_ID) or
        ('azp' in claims and claims['azp'] != settings.OIDC_RP_CLIENT_ID) or
        not isinstance(claims.get('exp'),(int,float)) or claims['exp'] <= time.time() or
        claims.get('nbf',0) > time.time() + settings.OIDC_CLOCK_SKEW_SECONDS):
        raise SuspiciousOperation('Identity token claims are invalid.')
    return claims


class PortalOIDCBackend(OIDCAuthenticationBackend):
    def _verify_jws(self, payload, key):
        # Upstream 5.x uses PyJWT without clock leeway. Preserve its algorithm
        # restriction and our explicit issuer/audience validation below.
        try:
            if jwt.get_unverified_header(payload).get('alg') != self.OIDC_RP_SIGN_ALGO:
                raise SuspiciousOperation('Identity token algorithm is invalid.')
            return jwt.decode(payload, key, algorithms=[self.OIDC_RP_SIGN_ALGO],
                              leeway=settings.OIDC_CLOCK_SKEW_SECONDS,
                              options={'verify_aud': False})
        except jwt.InvalidTokenError as exc:
            raise SuspiciousOperation('Identity token validation failed. Check identity-provider clock synchronization.') from exc

    def verify_token(self, token, **kwargs):
        return validate_id_claims(super().verify_token(token, **kwargs))

    def get_userinfo(self, access_token, id_token, payload):
        claims = super().get_userinfo(access_token,id_token,payload)
        if claims.get('sub') != payload.get('sub'):
            raise SuspiciousOperation('Identity provider subject mismatch.')
        # UserInfo need not carry iss; bind it to the verified ID token issuer.
        return {**claims,'iss':payload['iss']}

    def raise_token_response_error(self, response):
        if response.status_code != 200:
            raise SuspiciousOperation('Identity provider token exchange failed.')

    def verify_claims(self, claims):
        email = claims.get('email')
        if not isinstance(email, str) or claims.get('email_verified') is not True:
            return False
        try:
            validate_email(email.strip())
        except ValidationError:
            return False
        return bool(claims.get('sub')) and claims.get('iss') == settings.OIDC_OP_ISSUER

    def filter_users_by_claims(self, claims):
        if not self.verify_claims(claims):
            return User.objects.none()
        users = User.objects.filter(is_active=True, email__iexact=claims['email'].strip()).filter(
            Q(external_issuer='', external_subject='') |
            Q(external_issuer=settings.OIDC_OP_ISSUER, external_subject=claims['sub']))
        # Request-only flag: never accept an account-status hint from a URL/session.
        request = getattr(self, 'request', None)
        if request is not None and not users.exists():
            request._portal_sso_access_denied = True
        return users

    def create_user(self, claims):
        return None

    @transaction.atomic
    def update_user(self, user, claims):
        # Recheck the email and any existing binding before updating provider-owned fields.
        account = self.filter_users_by_claims(claims).select_for_update().filter(pk=user.pk).first()
        if account is None:
            raise SuspiciousOperation('The verified identity does not match this account.')
        account.external_issuer = claims['iss']
        account.external_subject = claims['sub']
        for field, claim in [('first_name','given_name'), ('last_name','family_name')]:
            value = claims.get(claim)
            if isinstance(value, str):
                setattr(account, field, value[:150])
        account.save(update_fields=['external_issuer','external_subject','first_name','last_name'])
        return account
