from six.moves.urllib_parse import quote

from .utils import sanitize_redirect, user_is_authenticated, \
                   user_is_active, partial_pipeline_data, setting_url


def do_auth(backend, redirect_name='next'):
    # Save any defined next value into session
    data = backend.strategy.request_data(merge=False)

    # Save extra data into session.
    for field_name in backend.setting('FIELDS_STORED_IN_SESSION', []):
        if field_name in data:
            backend.strategy.session_set(field_name, data[field_name])

    if redirect_name in data:
        # Check and sanitize a user-defined GET/POST next field value
        redirect_uri = data[redirect_name]
        if backend.setting('SANITIZE_REDIRECTS', True):
            allowed_hosts = backend.setting('ALLOWED_REDIRECT_HOSTS', []) + \
                            [backend.strategy.request_host()]
            redirect_uri = sanitize_redirect(allowed_hosts, redirect_uri)
        backend.strategy.session_set(
            redirect_name,
            redirect_uri or backend.setting('LOGIN_REDIRECT_URL')
        )
    return backend.start()


# AH - add debug logging
import logging
log = logging.getLogger("social")
def do_complete(backend, login, user=None, redirect_name='next',
                *args, **kwargs):
    print("Actually in do_complete()")
    log.debug("Starting do_complete()")
    log.debug("backend: {}".format(backend))
    log.debug("login: {}".format(login))
    log.debug("user: {}".format(user))
    log.debug("args: {}".format(args))
    log.debug("kwargs: {}".format(kwargs))
    log.debug("backend.strategy: {}".format(backend.strategy))
    data = backend.strategy.request_data()

    is_authenticated = user_is_authenticated(user)
    user = user if is_authenticated else None
    log.debug("1. user becomes {}".format(user))

    partial = partial_pipeline_data(backend, user, *args, **kwargs)
    log.debug("2. partial is {}".format(partial))
    if partial:
        user = backend.continue_pipeline(partial)
    else:
        user = backend.complete(user=user, *args, **kwargs)
    log.debug("3. user becomes {}".format(user))

    # pop redirect value before the session is trashed on login(), but after
    # the pipeline so that the pipeline can change the redirect if needed
    redirect_value = backend.strategy.session_get(redirect_name, '') or \
                     data.get(redirect_name, '')

    # check if the output value is something else than a user and just
    # return it to the client
    user_model = backend.strategy.storage.user.user_model()
    log.debug("4. user model is {}".format(user_model))
    if user and not isinstance(user, user_model):
        log.debug("4.1. User was not an instance of user_model; returning unchanged")
        return user

    if is_authenticated:
        log.debug("4.1. User is authenticated")
        if not user:
            url = setting_url(backend, redirect_value, 'LOGIN_REDIRECT_URL')
        else:
            url = setting_url(backend, redirect_value,
                              'NEW_ASSOCIATION_REDIRECT_URL',
                              'LOGIN_REDIRECT_URL')
            log.debug("4.1.1. url becomes {}".format(url))
    elif user:
        log.debug("4.1. User wasn't authed")
        if user_is_active(user):
            log.debug("4.1.1. User {} is active".format(user))
            # catch is_new/social_user in case login() resets the instance
            is_new = getattr(user, 'is_new', False)
            social_user = user.social_user
            log.debug("4.1.2. about to do login(): user is {}, social_user is {}".format(user, social_user))
            login(backend, user, social_user)
            # store last login backend name in session
            backend.strategy.session_set('social_auth_last_login_backend',
                                         social_user.provider)

            if is_new:
                url = setting_url(backend,
                                  'NEW_USER_REDIRECT_URL',
                                  redirect_value,
                                  'LOGIN_REDIRECT_URL')
            else:
                url = setting_url(backend, redirect_value,
                                  'LOGIN_REDIRECT_URL')
        else:
            log.debug("4.1.1. User isn't active")
            if backend.setting('INACTIVE_USER_LOGIN', False):
                social_user = user.social_user
                login(backend, user, social_user)
            url = setting_url(backend, 'INACTIVE_USER_URL', 'LOGIN_ERROR_URL',
                              'LOGIN_URL')
    else:
        url = setting_url(backend, 'LOGIN_ERROR_URL', 'LOGIN_URL')

    if redirect_value and redirect_value != url:
        redirect_value = quote(redirect_value)
        url += ('&' if '?' in url else '?') + \
               '{0}={1}'.format(redirect_name, redirect_value)

    if backend.setting('SANITIZE_REDIRECTS', True):
        allowed_hosts = backend.setting('ALLOWED_REDIRECT_HOSTS', []) + \
                        [backend.strategy.request_host()]
        url = sanitize_redirect(allowed_hosts, url) or \
              backend.setting('LOGIN_REDIRECT_URL')
    log.debug("4.2. url became {}".format(url))
    log.debug("4.3. returning backend.strategy.redirect(url)")
    return backend.strategy.redirect(url)


def do_disconnect(backend, user, association_id=None, redirect_name='next',
                  *args, **kwargs):
    partial = partial_pipeline_data(backend, user, *args, **kwargs)
    if partial:
        if association_id and not partial.kwargs.get('association_id'):
            partial.extend_kwargs({
                'association_id': association_id
            })
        response = backend.disconnect(*partial.args, **partial.kwargs)
    else:
        response = backend.disconnect(user=user, association_id=association_id,
                                      *args, **kwargs)

    if isinstance(response, dict):
        url = backend.strategy.absolute_uri(
            backend.strategy.request_data().get(redirect_name, '') or
            backend.setting('DISCONNECT_REDIRECT_URL') or
            backend.setting('LOGIN_REDIRECT_URL')
        )
        if backend.setting('SANITIZE_REDIRECTS', True):
            allowed_hosts = backend.setting('ALLOWED_REDIRECT_HOSTS', []) + \
                            [backend.strategy.request_host()]
            url = sanitize_redirect(allowed_hosts, url) or \
                backend.setting('DISCONNECT_REDIRECT_URL') or \
                backend.setting('LOGIN_REDIRECT_URL')
        response = backend.strategy.redirect(url)
    return response
