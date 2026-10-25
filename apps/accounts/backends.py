from django.contrib.auth.backends import ModelBackend
from .models import User


class EmailBackend(ModelBackend):
    def authenticate(self, request=None, username=None, password=None, **kwargs):
        email = username if username is not None else kwargs.get('email')
        if not isinstance(email, str) or password is None:
            return None
        try:
            user = User.objects.get(email__iexact=email.strip())
        except (User.DoesNotExist, User.MultipleObjectsReturned):
            User().set_password(password)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
