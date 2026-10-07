"""Official-host acquisition only: no vendor execution or browser qualification."""
import os
import tempfile
import threading
import time
from pathlib import Path

from cft_bundle import (
    ACQUISITION_PHASES,
    MAX_PUBLIC,
    BundleRefusal,
    acquire,
    finish_acquisition,
    packed,
    policy,
    public_bytes,
)
from host_controller import DIRECTORY, child_env, group_members, host_context, source_guard

WORKFLOW = '.github/workflows/chrome-for-testing-acquisition.yml'


def main():
    started = time.monotonic()
    deadline = started + 295
    watchdog = threading.Timer(300, lambda: os._exit(124))
    watchdog.daemon = True
    watchdog.start()
    context = host_context()
    repo = Path(os.environ['GITHUB_WORKSPACE']).resolve(strict=True)
    if DIRECTORY != repo / 'tests' / 'catalogue-browser':
        raise BundleRefusal('cft-source-location-refused')
    output = repo / '.tmp' / 'catalogue-cft-public'
    if output.exists():
        raise BundleRefusal('cft-fresh-public-output-required')
    output.mkdir(mode=0o700, parents=True)
    record = {'schema': 'row.cft-acquisition.v1', 'status': 'refused', 'complete': False,
        'phase': 'source-checks', 'vendor_binary_executed': False, 'genuine_browser_qualification': False,
        'independent_vendor_signature': False, 'publisher_license_approval': False,
        'sandbox_policy_changed': False, 'readiness_credit': 0}
    registry = []
    policy_raw = None
    observed = None
    operation_complete = False
    def checkpoint(phase):
        if phase not in ACQUISITION_PHASES:
            raise BundleRefusal('cft-phase-refused')
        record['phase'] = phase
        raw = public_bytes(packed(record), policy_raw)
        if len(raw) > MAX_PUBLIC:
            raise BundleRefusal('cft-public-size-refused')
        temporary = output / 'acquisition.tmp'
        with temporary.open('wb') as stream:
            stream.write(raw)
        temporary.replace(output / 'acquisition.json')
    checkpoint('source-checks')
    forced = False
    try:
        with tempfile.TemporaryDirectory(prefix='cft-acquisition-', dir=os.environ['RUNNER_TEMP']) as temp:
            private = Path(temp)
            env = child_env(private)
            before = source_guard(repo, context, registry, env, deadline, workflow_path=WORKFLOW)
            record['binding'] = {'source_head': before['head'], 'source_tree': before['tree'],
                'source_bytes_sha256': before['bytes'], 'workflow_sha256': before['workflow'],
                'event_sha': context['event'], 'image_version': context['image_version'], 'image_os': 'ubuntu24',
                'run_id': os.environ['GITHUB_RUN_ID'], 'run_attempt': os.environ['GITHUB_RUN_ATTEMPT']}
            checkpoint('policy')
            policy_raw = (DIRECTORY / 'cft-provider-policy.json').read_bytes()
            policy(policy_raw, enabled=False)
            observed = acquire(policy_raw, private, deadline, progress=checkpoint)
            checkpoint('source-readback')
            after = source_guard(repo, context, registry, env, deadline, workflow_path=WORKFLOW)
            if before != after or any(not owner.finished for owner in registry):
                raise BundleRefusal('cft-source-readback-refused')
            record['source_unchanged'] = True
            # Durable checkpoint remains incomplete while private files exist.
            checkpoint('cleanup')
        record['private_acquisition_root_removed'] = not private.exists()
        if not record['private_acquisition_root_removed']:
            raise BundleRefusal('cft-private-cleanup-refused')
        operation_complete = True
    except Exception:
        record['status'] = 'refused'
        record['complete'] = False
        record.pop('acquisition', None)
        record['refusal_code'] = 'cft-acquisition-refused'
    finally:
        try:
            for owner in reversed(registry):
                if not owner.finished:
                    forced = True
                    try:
                        owner.refuse_cleanup()
                    except Exception:
                        pass
            record['forced_cleanup_attempted'] = forced
            record['all_retained_zero_reaped'] = all(owner.finished and owner.reaped
                and owner.process.returncode == 0 for owner in registry)
            try:
                record['observed_groups_gone'] = all(owner.identity is not None
                    and group_members(owner.identity['group']) == [] for owner in registry)
            except Exception:
                record['observed_groups_gone'] = False
            record['complete_OS_descendants_proved'] = False
            if operation_complete:
                record['elapsed_ms'] = int((time.monotonic() - started) * 1000)
                try:
                    record = finish_acquisition(record, observed, policy_raw)
                except Exception:
                    record.pop('elapsed_ms', None)
                    record['refusal_code'] = 'cft-acquisition-refused'
            # Validate before an atomic replacement; a refused write retains
            # the prior bounded incomplete checkpoint rather than partial bytes.
            checkpoint(record['phase'])
        finally:
            watchdog.cancel()
    return 0 if record['complete'] is True else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        raise SystemExit('cft-host-context-refused') from None
