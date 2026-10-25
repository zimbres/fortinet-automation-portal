from django.shortcuts import redirect
from django.urls import reverse


class RequiredPasswordChangeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and request.user.password_change_needed:
            allowed = {reverse('password_change_required'), reverse('logout'), reverse('profile_picture'), reverse('health')}
            if request.path not in allowed:
                return redirect('password_change_required')
        return self.get_response(request)
