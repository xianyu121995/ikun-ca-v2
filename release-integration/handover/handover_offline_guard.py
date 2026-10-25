"""Pytest-only handover fence: no supplier network or live AI configuration."""
import socket

import pytest


@pytest.fixture(autouse=True)
def handover_offline_guard(monkeypatch, tmp_path):
    monkeypatch.setenv('IKUN_AI_CONFIG', str(tmp_path / 'no-live-ai.json'))
    connect, resolve = socket.socket.connect, socket.getaddrinfo

    def guarded_connect(sock, address):
        if isinstance(address, tuple) and address[0] not in ('127.0.0.1', '::1', 'localhost'):
            raise AssertionError('External network forbidden during handover tests')
        return connect(sock, address)

    def guarded_resolve(host, *args, **kwargs):
        if host not in ('127.0.0.1', '::1', 'localhost', None):
            raise AssertionError('External DNS forbidden during handover tests')
        return resolve(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, 'connect', guarded_connect)
    monkeypatch.setattr(socket, 'getaddrinfo', guarded_resolve)
