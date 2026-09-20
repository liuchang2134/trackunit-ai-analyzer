"""Start the existing local web app without PowerShell or system policy changes."""
import argparse
import json
from pathlib import Path
import socket
import subprocess
import sys
from urllib.error import URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.assistant_version import ASSISTANT_BUILD
from scripts.check_local_runtime import check

HOST = '127.0.0.1'


class StartupError(ValueError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, target):
        return None


def read_local_json(port, path):
    # Ignore proxy settings and do not follow even a localhost redirect externally.
    opener = build_opener(ProxyHandler({}), NoRedirect())
    with opener.open(f'http://{HOST}:{port}{path}', timeout=3) as response:
        content = response.read(2_000_001)
    if len(content) > 2_000_000:
        raise ValueError('Local response is too large')
    return json.loads(content)


def loopback_probe(host, port):
    """Report whether a loopback listener answered.

    A refused connection means nothing is listening. A *timeout* means the SYN
    was dropped, which on loopback is the normal signature of a closed port on
    hosts where the stack filters it instead of refusing it; treating that as
    "occupied but unverifiable" made the launcher refuse to start at all, so a
    timeout is reported as "no listener". Both families are still probed, so a
    service bound only to ::1 is found rather than shadowed by an IPv4 timeout.
    """
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except ConnectionRefusedError:
        return False
    except TimeoutError:
        return False
    except OSError as error:
        raise StartupError(
            f'Cannot verify local port {port} ({host}): {error.strerror or error}. No server was started.') from None


def existing_service(port):
    listening = False
    for host in (HOST, '::1'):
        if loopback_probe(host, port):
            listening = True
            break
    if not listening:
        return False
    try:
        metadata = read_local_json(port, '/openapi.json')
        if not isinstance(metadata, dict) or metadata.get('info', {}).get('title') != 'Trackunit AI Analyzer':
            raise StartupError(f'Port {port} belongs to another application. Choose a free port; it was not stopped.')
        runtime = read_local_json(port, '/assistant/runtime')
        if not isinstance(runtime, dict) or runtime.get('backend_build') != ASSISTANT_BUILD:
            raise StartupError(f'Port {port} has an older or different build. Choose another free port; it was not restarted.')
    except (OSError, URLError, ValueError, AttributeError) as error:
        if isinstance(error, StartupError):
            raise
        raise StartupError(f'Port {port} is occupied but its application could not be verified. It was not stopped.') from None
    return True


def port_number(value):
    port = int(value)
    if not 1024 <= port <= 65535:
        raise argparse.ArgumentTypeError('Port must be between 1024 and 65535')
    return port


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=port_number, default=8890)
    parser.add_argument('--check-only', action='store_true', help='Check locally without starting a server')
    args = parser.parse_args(argv)
    url = f'http://{HOST}:{args.port}/assistant-ui/'
    try:
        if existing_service(args.port):
            print(f'Assistant already running: {url} ({ASSISTANT_BUILD})')
            print('AI provider availability was not tested. No process was started or restarted.')
            return 0
        readiness = check(demo_only=True)
        if not readiness['local_ready']:
            missing = ', '.join(readiness['missing_dependencies']) or 'supported Python 3.11-3.13'
            raise StartupError(f'Local prerequisites missing: {missing}. Nothing was installed or started.')
        print('Local data features are available.')
        cloud_name = {'gemini': 'Gemini', 'deepseek': 'DeepSeek'}.get(readiness['provider'])
        if cloud_name and not readiness.get('api_key_configured'):
            print(f'{cloud_name} key is not configured; AI analysis remains unavailable.')
        elif cloud_name and readiness.get('official_endpoint'):
            print(f'{cloud_name} is configured locally; live availability and quota were not tested.')
        else:
            print('AI configuration is not verified; only local prerequisites were checked.')
        if args.check_only:
            print(f'Check complete. No server started. Selected URL: {url}')
            return 0
        print(f'Starting assistant: {url}', flush=True)
        return subprocess.call([sys.executable, '-m', 'uvicorn', 'app.main:app',
                                '--host', HOST, '--port', str(args.port)], cwd=ROOT)
    except StartupError as error:
        print(f'Cannot start assistant: {error}', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
