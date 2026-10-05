"""Explicit runtime inputs; unrelated credentials never reach media/model tools."""
import os


def runtime_environment():
    allowed = (
        'PATH', 'HOME', 'CODEX_HOME', 'XDG_CONFIG_HOME', 'XDG_DATA_HOME',
        'XDG_CACHE_HOME', 'LANG', 'LC_ALL', 'LC_CTYPE', 'SSL_CERT_FILE',
        'SSL_CERT_DIR', 'TMPDIR', 'OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS',
        'MKL_NUM_THREADS', 'HF_HOME', 'HF_HUB_CACHE', 'HF_HUB_OFFLINE',
        'TRANSFORMERS_OFFLINE', 'HF_HUB_DISABLE_TELEMETRY',
    )
    return {key: os.environ[key] for key in allowed if key in os.environ}
