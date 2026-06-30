from django.conf import settings
from django.utils import translation


class ProfileLanguageMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        language = None
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and hasattr(user, "profile"):
            language = user.profile.language_preference
        valid_codes = {code for code, _name in settings.LANGUAGES}
        if language in valid_codes:
            translation.activate(language)
            request.LANGUAGE_CODE = language
        response = self.get_response(request)
        translation.deactivate()
        return response
