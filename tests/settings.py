DATABASE_ENGINE = 'sqlite3'
DATABASE_NAME = '/tmp/test'
ROOT_URLCONF = 'tests.urls'
INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.sites',
    'tests.app',
]
