from django.shortcuts import redirect
from django.urls import Resolver404, resolve, reverse


class RequiredPasswordChangeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and request.user.password_change_needed:
            # Feed downloads authenticate independently of any browser session.
            try:
                if resolve(request.path_info).url_name == 'threat_feed_download':
                    return self.get_response(request)
            except Resolver404:
                pass
            allowed = {reverse('password_change_required'), reverse('logout'), reverse('profile_picture'), reverse('health')}
            if request.path not in allowed:
                return redirect('password_change_required')
        return self.get_response(request)
