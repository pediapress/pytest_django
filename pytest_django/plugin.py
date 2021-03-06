import copy
from django.conf import settings
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core import management
from django.core.urlresolvers import clear_url_caches
from django.test.client import Client
from django.test.testcases import TransactionTestCase, TestCase
from django.test.simple import DjangoTestSuiteRunner
from pytest_django.client import RequestFactory
import py
import sys


class DjangoManager(object):
    """
    A Django plugin for py.test that handles creating and destroying the
    test environment and test database.

    Similar to Django's TransactionTestCase, a transaction is started and
    rolled back for each test. Additionally, the settings are copied before
    each test and restored at the end of the test, so it is safe to modify
    settings within tests.
    """

    def __init__(self, verbosity=0):
        self.verbosity = verbosity

        self._old_database_name = None
        self._old_settings = []
        self._old_urlconf = None

        self.suite_runner = None
        self.old_db_config = None
        self.testcase = None

    def pytest_sessionstart(self, session):
        #capture = py.io.StdCapture()
        # make sure the normal django syncdb command is run (do not run migrations for tests)
        # this is faster and less error prone
        management.get_commands()  # load commands dict
        management._commands['syncdb'] = 'django.core'  # make sure `south` migrations are disabled
        self.suite_runner = DjangoTestSuiteRunner(interactive=False)

        self.suite_runner.setup_test_environment()
        self.old_db_config = self.suite_runner.setup_databases()
        settings.DATABASE_SUPPORTS_TRANSACTIONS = True
        #unused_out, err = capture.reset()
        #srsys.stderr.write(err)

    def pytest_sessionfinish(self, session, exitstatus):
        capture = py.io.StdCapture()
        self.suite_runner.teardown_test_environment()
        self.suite_runner.teardown_databases(self.old_db_config)
        unused_out, err = capture.reset()
        sys.stderr.write(err)

    def pytest_itemstart(self, item):
        # This lets us control the order of the setup/teardown
        # Yuck.
        if _is_unittest(self._get_item_obj(item)):
            item.setup = lambda: None
            item.teardown = lambda: None

    def pytest_runtest_setup(self, item):
        # Set the URLs if the py.test.urls() decorator has been applied
        if hasattr(item.obj, 'urls'):
            self._old_urlconf = settings.ROOT_URLCONF
            settings.ROOT_URLCONF = item.obj.urls
            clear_url_caches()

        item_obj = self._get_item_obj(item)
        testcase = _get_testcase(item_obj)
        # We have to run these here since py.test's unittest plugin skips
        # __call__()
        testcase.client = Client()
        testcase._pre_setup()
        testcase.setUp()

    def pytest_runtest_teardown(self, item):
        item_obj = self._get_item_obj(item)

        testcase = _get_testcase(item_obj)
        testcase.tearDown()
        if not isinstance(item_obj, TestCase):
            testcase._post_teardown()

        if hasattr(item, 'urls') and self._old_urlconf is not None:
            settings.ROOT_URLCONF = self._old_urlconf
            self._old_urlconf = None

    def _get_item_obj(self, item):
        try:
            return item.obj.im_self
        except AttributeError:
            return None

    def pytest_namespace(self):

        def load_fixture(fixture):
            """
            Loads a fixture, useful for loading fixtures in funcargs.

            Example:

                def pytest_funcarg__articles(request):
                    py.test.load_fixture('test_articles')
                    return Article.objects.all()
            """
            call_command('loaddata', fixture, **{
                'verbosity': self.verbosity + 1,
                'commit': not settings.DATABASE_SUPPORTS_TRANSACTIONS
            })

        def urls(urlconf):
            """
            A decorator to change the URLconf for a particular test, similar
            to the `urls` attribute on Django's `TestCase`.

            Example:

                @py.test.urls('myapp.test_urls')
                def test_something(client):
                    assert 'Success!' in client.get('/some_path/')
            """
            def wrapper(function):
                function.urls = urlconf
            return wrapper

        return {'load_fixture': load_fixture, 'urls': urls}


######################################
# funcargs
######################################

def pytest_funcarg__client(request):
    """
    Returns a Django test client instance.
    """
    return Client()

def pytest_funcarg__admin_client(request):
    """
    Returns a Django test client logged in as an admin user.
    """
    try:
        User.objects.get(username='admin')
    except User.DoesNotExist: #@UndefinedVariable
        user = User.objects.create_user('admin', 'admin@example.com',
                                        'password')
        user.is_staff = True
        user.is_superuser = True
        user.save()

    client = Client()
    client.login(username='admin', password='password')

    return client

def pytest_funcarg__rf(request):
    """
    Returns a RequestFactory instance.
    """
    return RequestFactory()

def pytest_funcarg__settings(request):
    """
    Returns a Django settings object that restores any changes after the test
    has been run.
    """
    old_settings = copy.deepcopy(settings)
    def restore_settings():
        for setting in dir(old_settings):
            if setting == setting.upper():
                setattr(settings, setting, getattr(old_settings, setting))
    request.addfinalizer(restore_settings)
    return settings

def _get_testcase(testcase):
    if _is_unittest(testcase):
        return testcase
    return TestCase(methodName='__init__')

def _is_unittest(the_object):
    return issubclass(type(the_object), TransactionTestCase)
