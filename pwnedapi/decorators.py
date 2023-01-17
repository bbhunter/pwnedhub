from flask import g, request, current_app, abort
from pwnedapi.constants import ROLES
from pwnedapi.models import Config
from pwnedapi.utils import CsrfToken, ParamValidator
from functools import wraps
import base64
import jsonpickle

def token_auth_required(func):
    @wraps(func)
    def wrapped(*args, **kwargs):
        if g.user:
            return func(*args, **kwargs)
        abort(401)
    return wrapped

def key_auth_required(func):
    @wraps(func)
    def wrapped(*args, **kwargs):
        key = request.headers.get(current_app.config['API_CONFIG_KEY_NAME'])
        if key == current_app.config['API_CONFIG_KEY_VALUE']:
            return func(*args, **kwargs)
        abort(401)
    return wrapped

def roles_required(*roles):
    def wrapper(func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            if ROLES[g.user.role] not in roles:
                return abort(403)
            return func(*args, **kwargs)
        return wrapped
    return wrapper

def validate_json(params):
    def wrapper(func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            input_dict = getattr(request, 'json', {})
            v = ParamValidator(input_dict, params)
            v.validate()
            if not v.passed:
                abort(400, v.reason)
            return func(*args, **kwargs)
        return wrapped
    return wrapper

def csrf_protect(func):
    @wraps(func)
    def wrapped(*args, **kwargs):
        if not Config.get_value('BEARER_AUTH_ENABLE'):
            # no Bearer token means cookies (default) are used and CSRF is an issue
            csrf_token = request.headers.get(current_app.config['CSRF_TOKEN_NAME'])
            try:
                untrusted_csrf_obj = jsonpickle.decode(base64.b64decode(csrf_token))
                untrusted_csrf_obj.sign(current_app.config['SECRET_KEY'])
                trusted_csrf_obj = CsrfToken(g.user.id, untrusted_csrf_obj.ts)
                trusted_csrf_obj.sign(current_app.config['SECRET_KEY'])
            except:
                untrusted_csrf_obj = None
            if not untrusted_csrf_obj or trusted_csrf_obj.sig != untrusted_csrf_obj.sig:
                abort(400, 'CSRF detected.')
        return func(*args, **kwargs)
    return wrapped
