"""Owned, isolated, serial adapter over the installed public Results API."""
import importlib.metadata
import json
import os
from pathlib import Path
import sys

from orion_results import Session, Reference, Limits, read


def main():
    command = sys.argv[1]
    if command == 'version':
        return {'package_version': importlib.metadata.version('orion-results'), 'reference_version': 1}
    raw = sys.stdin.buffer.read(65537)
    if len(raw) > 65536:
        raise ValueError('input_limit')
    data = json.loads(raw)
    root = Path(data['root'])
    if command == 'create':
        session = Session.create(root, limits=Limits(**data['limits']))
        sid = session.session_id
        session.close()
        return {'session_id': sid, 'closed': True}
    if command == 'capture':
        text = Path(data['report_path']).read_bytes().decode('utf-8')
        expected = Reference.from_text(data['session_id'], text)
        if str(expected) != data['reference']:
            raise ValueError('reference_mismatch')
        session = Session.open(root, data['session_id'])
        try:
            receipt = session.capture('worktree-observation', text)
            snapshot = session.snapshot(budget_bytes=4096, include_content=False)
        finally:
            session.close()
        return {'reference': str(receipt.reference), 'sha256': receipt.sha256, 'utf8_bytes': receipt.utf8_bytes,
                'closed': True, 'snapshot': {'text': snapshot.text, 'utf8_bytes': snapshot.utf8_bytes,
                                            'include_content': False}}
    if command == 'read':
        ref = Reference.parse(data['reference'])
        text = read(root, ref)
        fd = os.open(data['output'], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as f:
            f.write(text.encode('utf-8'))
            f.flush()
            os.fsync(f.fileno())
        return {'reference': str(ref), 'sha256': ref.sha256, 'utf8_bytes': ref.utf8_bytes}
    raise ValueError('unsupported_command')


if __name__ == '__main__':
    try:
        result = {'command': sys.argv[1], 'state': 'ok', 'data': main()}
        status = 0
    except Exception:
        result, status = {'state': 'unknown'}, 7
    print(json.dumps(result, ensure_ascii=True, allow_nan=False))
    raise SystemExit(status)
