from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver
from .services import record_event


@receiver(user_logged_in)
def login_success(sender, request, user, **kwargs):
    record_event(actor=user, event_type='login.succeeded')


@receiver(user_logged_out)
def logout(sender, request, user, **kwargs):
    record_event(actor=user, event_type='logout')


@receiver(user_login_failed)
def login_failure(sender, credentials, request, **kwargs):
    # Do not persist untrusted credentials, including username fields containing secrets.
    record_event(actor=None, event_type='login.failed')
