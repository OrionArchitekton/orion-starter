"""Owned, isolated, serial adapter over the installed public Results API."""
import importlib.metadata
import json
import sys


def main():
    command = sys.argv[1]
    if command != 'version':
        raise ValueError('unsupported_command')
    return {'package_version': importlib.metadata.version('orion-results'), 'reference_version': 1}


if __name__ == '__main__':
    try:
        result = {'command': sys.argv[1], 'state': 'ok', 'data': main()}
        status = 0
    except Exception:
        result, status = {'state': 'unknown'}, 7
    print(json.dumps(result, ensure_ascii=True, allow_nan=False))
    raise SystemExit(status)
