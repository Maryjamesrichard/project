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

        # The profile view can change the preference during this request, so
        # do not write the stale, pre-view language back to the browser.
        if user is not None and user.is_authenticated and hasattr(user, "profile"):
            user.profile.refresh_from_db(fields=["language_preference"])
            language = user.profile.language_preference
        if language in valid_codes:
            response["Content-Language"] = language
            # Keep Django's normal locale cookie in sync with the profile.
            # This makes the preference survive redirects, page navigation,
            # and requests where authentication has not been resolved yet.
            if request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME) != language:
                response.set_cookie(
                    settings.LANGUAGE_COOKIE_NAME,
                    language,
                    max_age=settings.LANGUAGE_COOKIE_AGE,
                    path=settings.LANGUAGE_COOKIE_PATH,
                    domain=settings.LANGUAGE_COOKIE_DOMAIN,
                    secure=settings.LANGUAGE_COOKIE_SECURE,
                    httponly=settings.LANGUAGE_COOKIE_HTTPONLY,
                    samesite=settings.LANGUAGE_COOKIE_SAMESITE,
                )
        translation.deactivate()
        return response
