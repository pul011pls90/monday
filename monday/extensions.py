from flask import current_app
from flask_babel import Babel
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()
babel = Babel()
limiter = Limiter(key_func=get_remote_address)


@limiter.request_filter
def _exempt_testing_apps():
    """Prevent shared Limiter singleton state from leaking across test apps while keeping production enforced."""
    return bool(current_app.config.get("TESTING") and not current_app.config.get("RATELIMIT_ENABLED", False))
