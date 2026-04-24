import http.server
import os
import random
import string
import subprocess
from contextlib import contextmanager
from threading import Thread
from typing import Dict
from unittest import mock
from zipfile import ZipFile


class ZipForTest:
    def __init__(self, destfile, data=None):
        if data is None:
            self.data = dict(
                file=b"foo",
                dir=dict(
                    f=b"bar"
                )
            )
        else:
            self.data = data

        self._make_zip(destfile)
        self.destfile = destfile

    def content(self, path):
        pass

    def _make_zip(self, destfile):
        pass

    def _write_zip_contents(self, z, stack, data):
        pass


def make_zip(zipfilename, root_dir, base_dir):
    pwd = os.getcwd()
    with ZipFile(zipfilename, "w") as f:
        try:
            os.chdir(root_dir)
            for root, dirs, filenames in os.walk(base_dir):
                for _dir in dirs:
                    path = os.path.normpath(os.path.join(root, _dir))
                    f.write(path)
                for _file in filenames:
                    path = os.path.normpath(os.path.join(root, _file))
                    f.write(path)
        finally:
            os.chdir(pwd)


def make_random_str(n):
    return ''.join([random.choice(string.ascii_letters + string.digits)
                    for i in range(n)])


def randstring(length=16):
    letters = string.ascii_letters + string.digits
    return (''.join(random.choice(letters) for _ in range(length)))


def patch_subprocess(stdout, stderr=b''):
    def decorator(f):
        pass
    return decorator


class OnMemoryHTTPServerForTest(http.server.BaseHTTPRequestHandler):
    files: Dict[str, str] = {}

    def do_GET(self):
        pass

    def do_PUT(self):
        pass


@contextmanager
def make_http_server():
    httpd = None
    httpd_thread = None
    try:
        OnMemoryHTTPServerForTest.files.clear()
        httpd = http.server.HTTPServer(('', 0), OnMemoryHTTPServerForTest)
        httpd_thread = Thread(target=httpd.serve_forever)
        httpd_thread.start()

        yield httpd, httpd.server_address[1]
    finally:
        if httpd is not None:
            httpd.shutdown()
        if httpd_thread is not None:
            httpd_thread.join()
