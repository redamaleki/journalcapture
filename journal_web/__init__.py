import os
from flask import Flask
from pathlib import Path
from werkzeug.middleware.proxy_fix import ProxyFix

from .views import bp


def env_path(name: str, default: Path) -> Path:
    return Path(os.environ.get(name, str(default))).expanduser()


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


def create_app():
    base_dir = Path(__file__).resolve().parent.parent
    default_data_dir = base_dir / 'data'
    app = Flask(
        __name__,
        instance_relative_config=True,
        template_folder=str(base_dir / 'templates'),
        static_folder=str(base_dir / 'static'),
    )

    data_dir = env_path('JOURNAL_DATA_DIR', default_data_dir)
    journals_dir = env_path('JOURNAL_JOURNALS_DIR', data_dir / 'journals')
    thumbs_dir = env_path('JOURNAL_THUMBS_DIR', data_dir / '.thumbnails')
    backup_config_path = env_path('JOURNAL_BACKUP_CONFIG_PATH', base_dir / 'instance' / 'backup_config.yml')

    app.config['BASE_DIR'] = base_dir
    app.config['DATA_DIR'] = data_dir
    app.config['JOURNALS_DIR'] = journals_dir
    app.config['THUMBS_DIR'] = thumbs_dir
    app.config['SECRET_KEY'] = os.environ.get('JOURNAL_SECRET_KEY', 'journal-phase1-local')
    app.config['MAX_CONTENT_LENGTH'] = 64 * 1024 * 1024
    app.config['BACKUP_CONFIG_PATH'] = backup_config_path
    app.config['HOST'] = os.environ.get('JOURNAL_HOST', '0.0.0.0')
    app.config['PORT'] = int(os.environ.get('JOURNAL_PORT', '5000'))
    app.config['DEBUG'] = env_bool('JOURNAL_DEBUG', False)

    app.config['JOURNALS_DIR'].mkdir(parents=True, exist_ok=True)
    app.config['THUMBS_DIR'].mkdir(parents=True, exist_ok=True)
    app.config['BACKUP_CONFIG_PATH'].parent.mkdir(parents=True, exist_ok=True)

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1)

    app.register_blueprint(bp)
    return app
