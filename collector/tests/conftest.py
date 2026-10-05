import os
import pytest


@pytest.fixture
def codex_available(monkeypatch, tmp_path):
    """Declare executable availability only for tests that mock AI execution."""
    directory = tmp_path / 'mock-bin'
    directory.mkdir()
    command = directory / 'codex'
    command.write_text('#!/bin/sh\n# Model execution must be mocked in this fixture.\nexit 91\n')
    command.chmod(0o700)
    monkeypatch.setenv('PATH', str(directory) + os.pathsep + os.environ.get('PATH', ''))


def pytest_addoption(parser):
    parser.addoption('--run-live',action='store_true',default=False,help='Run tests against the explicitly configured Supabase project')

def pytest_collection_modifyitems(config, items):
    if config.getoption('--run-live'):
        return
    import pytest
    for item in items:
        if 'live' in item.keywords:
            item.add_marker(pytest.mark.skip(reason='Live Supabase access not enabled'))
