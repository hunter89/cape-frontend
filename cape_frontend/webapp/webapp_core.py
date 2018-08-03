import time
from typing import Union
from sanic import Sanic
from cape_frontend import cape_frontend_settings
from cape_frontend.webapp.logs.logs_core import log
from cape_frontend.webapp.configuration.configuration_core import configuration_endpoints
from cape_frontend.webapp.errors.errors_core import errors_endpoints
from cape_frontend.webapp.mocks.full.full_core import mock_full_endpoints
from cape_frontend.webapp.mocks.mocks_core import mocks_endpoints
from cape_frontend.webapp.mocks.unlucky.unlucky_core import mock_unlucky_endpoints
from cape_frontend.webapp.mocks.timeout.timeout_core import mock_timeout_endpoints
from cape_frontend.webapp.mocks.error.error_core import mock_error_endpoints
from cape.client import CapeClient
from pathlib import Path

import asyncio
import requests

app = Sanic(__name__)
app.blueprint(mock_timeout_endpoints)
app.blueprint(mock_error_endpoints)
app.static('/', file_or_directory=cape_frontend_settings.STATIC_FOLDER)
app.static('/', file_or_directory=cape_frontend_settings.HTML_INDEX_STATIC_FILE)
app.blueprint(errors_endpoints)
app.blueprint(configuration_endpoints)
app.blueprint(mocks_endpoints)
app.blueprint(mock_unlucky_endpoints)
app.blueprint(mock_full_endpoints)

print("listing endpoints", app.router.routes_all.keys())


def create_demo_user(api_url):
    log('Creating demo user')
    client = CapeClient(api_url)
    new_user_parameters = {'userId': cape_frontend_settings.DEMO_USER_LOGIN,
                           'password': cape_frontend_settings.DEMO_USER_PASSWORD,
                           'token': cape_frontend_settings.DEMO_USER_TOKEN,
                           'superAdminToken': cape_frontend_settings.BACKEND_SUPER_ADMIN_TOKEN,
                           }
    url = 'user/create-user?'
    for k, v in new_user_parameters.items():
        url += "%s=%s&" % (k, v)
    response = client._raw_api_call(url)
    assert response.status_code == 200, "Could not create demo user"
    client.login(cape_frontend_settings.DEMO_USER_LOGIN, cape_frontend_settings.DEMO_USER_PASSWORD)
    log(f'Demo user created with token {cape_frontend_settings.DEMO_USER_TOKEN}')


def wait_for_backend():
    if not cape_frontend_settings.WAIT_FOR_BACKENDS:
        return
    demo_user_created = False
    num_backends = len(cape_frontend_settings.BACKENDS_API_URL)
    backends_left = set(cape_frontend_settings.BACKENDS_API_URL)
    while backends_left:
        log(f"Frontend waiting for backends to initialize {len(backends_left)}/{num_backends}")
        current_url = backends_left.pop()
        try:
            reachable = requests.get(str(Path(current_url).parent), timeout=1).status_code == 200
        except requests.exceptions.Timeout:
            reachable = False
        if not reachable:
            log(f'Could not reach backend {current_url}, retrying ...')
            backends_left.add(current_url)
            time.sleep(1)
            continue
        if not demo_user_created:
            create_demo_user(current_url)
        client = CapeClient(current_url)
        client.answer(question="How many people were present ?",
                      text="Yesterday at the demonstration, 500 people assisted the event.")
    log("All backends started")


async def welcome_message():
    await asyncio.sleep(0.5)
    print("Welcome to Cape " * 30)


def run(port: Union[None, int] = None):
    if port is not None:
        cape_frontend_settings.CONFIG_SERVER['port'] = int(port)
    log("Using port", cape_frontend_settings.CONFIG_SERVER['port'])
    wait_for_backend()
    app.config.LOGO = None
    app.add_task(welcome_message())
    app.run(**cape_frontend_settings.CONFIG_SERVER)