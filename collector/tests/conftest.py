def pytest_addoption(parser):
    parser.addoption('--run-live',action='store_true',default=False,help='Run tests against the explicitly configured Supabase project')

def pytest_collection_modifyitems(config, items):
    if config.getoption('--run-live'):
        return
    import pytest
    for item in items:
        if 'live' in item.keywords:
            item.add_marker(pytest.mark.skip(reason='Live Supabase access not enabled'))
