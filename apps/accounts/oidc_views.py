from django.contrib import messages
from django.shortcuts import redirect
from mozilla_django_oidc.views import OIDCAuthenticationCallbackView


class PortalOIDCCallbackView(OIDCAuthenticationCallbackView):
    def login_failure(self):
        if getattr(self.request, '_portal_sso_access_denied', False):
            message = ('Your SSO account does not have access to this portal. '
                       'Contact your superadministrator to request access.')
        else:
            message = 'SSO sign-in could not be completed. Please try again.'
        messages.error(self.request, message)
        return redirect('login')
