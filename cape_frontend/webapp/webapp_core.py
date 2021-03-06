# Copyright 2018 BLEMUNDSBURY AI LIMITED
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
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
from cape_frontend.webapp.welcome_message import WELCOME_MESSAGE
from urllib.parse import urlparse
import subprocess

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
    demo_user_created = not cape_frontend_settings.CREATE_DEMO_ACCOUNT_ON_INIT
    num_backends = len(cape_frontend_settings.BACKENDS_API_URL)
    backends_left = set(cape_frontend_settings.BACKENDS_API_URL)
    while backends_left:
        log(f"Frontend waiting for backends to initialize {len(backends_left)}/{num_backends}")
        current_url = backends_left.pop()
        try:
            reachable = requests.get(current_url[:-4], timeout=1).status_code == 200
        except Exception:
            reachable = False
        if not reachable:
            log(f'Could not reach backend {current_url}, retrying ...')
            backends_left.add(current_url)
            time.sleep(1)
            continue
        if not demo_user_created:
            create_demo_user(current_url)
        client = CapeClient(current_url)
        client.login(cape_frontend_settings.DEMO_USER_LOGIN, cape_frontend_settings.DEMO_USER_PASSWORD)
        client.answer(question="How many people were present ?",
                      text="Yesterday at the demonstration, 500 people assisted the event.")
    log("All backends started")


class NgrokActivator:
    counter: int = 0
    _installed: bool = False

    @staticmethod
    def _install_ngrok():
        if NgrokActivator._installed:
            return
        log(f"Installing ngrok...")
        subprocess.check_call(
            ['wget', '-O', '/tmp/ngrok.zip', 'https://bin.equinox.io/c/4VmDzA7iaHb/ngrok-stable-linux-amd64.zip'],
            stdout=open('/tmp/logfile.log', 'a'),
            stderr=open('/tmp/logfile.log', 'a'),
        )
        subprocess.check_call(['unzip', '-d', '/tmp', '/tmp/ngrok.zip'],
                              stdout=open('/tmp/logfile.log', 'a'),
                              stderr=open('/tmp/logfile.log', 'a'),
                              )
        NgrokActivator._installed = True
        log("Done")

    @staticmethod
    def activate_ngrok_linux(port: int):
        if cape_frontend_settings.ACTIVATE_NGROK_LINUX:
            NgrokActivator._install_ngrok()
            log(f"Activating ngrok forwarding for {port}...")
            subprocess.Popen(['nohup', '/tmp/ngrok', 'http', str(port)],
                             stdout=open('/tmp/logfile.log', 'a'),
                             stderr=open('/tmp/logfile.log', 'a'),
                             preexec_fn=os.setpgrp)
            log("Forwarding activated...")
            log("Waiting for ngrok to initialize...")
            time.sleep(3)
            log("Getting ngrok tunnel...")
            ngrok_local_server = f'http://127.0.0.1:{NgrokActivator.counter+4040}/api/tunnels'
            NgrokActivator.counter += 1
            return requests.get(ngrok_local_server).json()['tunnels'][-1]['public_url']


async def display_welcome():
    global WELCOME_MESSAGE
    api_version = '0.1'
    # http://b8f7208d.ngrok.io/?configuration={%22api%22:{%22backendURL%22:%22https://30a33ee8.ngrok.io/api/0.1%22,%22timeout%22:%2215000%22}}#/

    format_url = lambda base, backend,version: f'{base}/?configuration={{"api":{{"backendURL":"{backend}/{version}","timeout":15000}}}}'
    WELCOME_MESSAGE += f"""
    Frontend locally available at:
        http://localhost:{cape_frontend_settings.CONFIG_SERVER['port']}"""
    if cape_frontend_settings.ACTIVATE_NGROK_LINUX:
        public_url_frontend = NgrokActivator.activate_ngrok_linux(cape_frontend_settings.CONFIG_SERVER['port'])
        backend_urls = [NgrokActivator.activate_ngrok_linux(urlparse(backend_url).port) + '/api'
                        for idx, backend_url in enumerate(cape_frontend_settings.BACKENDS_API_URL)]
        if public_url_frontend:
            WELCOME_MESSAGE += f"""
        Frontend publicly available at (powered by ngrok):
            {format_url(public_url_frontend,backend_urls[0] if backend_urls else cape_frontend_settings.BACKENDS_API_URL[0],api_version)}"""
        if backend_urls:
            WELCOME_MESSAGE += f"""
            Using publicly available backends at (powered by ngrok): {' '.join(backend_urls)}"""
    if cape_frontend_settings.WAIT_FOR_BACKENDS:
        WELCOME_MESSAGE += f"""
            Local backends at: {' '.join(cape_frontend_settings.BACKENDS_API_URL)}"""
    log(WELCOME_MESSAGE)


def run(port: Union[None, int] = None):
    if port is not None:
        cape_frontend_settings.CONFIG_SERVER['port'] = int(port)
    log("Using port", cape_frontend_settings.CONFIG_SERVER['port'])
    wait_for_backend()
    app.config.LOGO = None
    app.add_task(display_welcome)
    app.run(**cape_frontend_settings.CONFIG_SERVER)
