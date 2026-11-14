"""Reproduce findings from baseline ed9ac95 using a fake driver and temp files.

Run from this checkout with its Python environment. These assertions describe
the observed defects; after a production fix they are expected to fail. No
printer, UI Automation session or network connection is used.
"""
import json
import logging
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from agent import print_agent as agent


def reproduce():
    log = logging.getLogger('rip-study-fake-driver')
    log.handlers = [logging.NullHandler()]
    log.propagate = False
    with tempfile.TemporaryDirectory(prefix='autorip-agent-study-') as directory:
        folder = Path(directory)
        job = folder / 'synthetic.PRT'
        job.write_bytes(b'Synthetic file: fake driver does not decode or print it')
        config = SimpleNamespace(stable_seconds=0, dry_run=False, auto_print=True,
                                 printed_folder=folder / 'printed')

        class FakeDriver:
            starts = 0
            def open_job(self, path):
                pass
            def start_print(self):
                self.starts += 1
            def wait_confirmation(self):
                raise TimeoutError('Synthetic confirmation timeout')

        driver = FakeDriver()
        state = agent.State(folder / 'state.sqlite3')
        original_stable = agent.stable
        agent.stable = lambda *_: True
        try:
            agent.process(job, config, state, driver, log)
            first = state.state_for(job.name, agent.sha256(job))
            agent.process(job, config, state, driver, log)
            second = state.state_for(job.name, agent.sha256(job))
            assert first == second == 'revisao_manual'
            assert driver.starts == 2

            check = agent.PrintExpDriver(SimpleNamespace(
                confirm_timeout=1, confirmation_regexes=['completed']), log)
            check._visible_texts = lambda: ['old-job completed', 'current-job waiting']
            wrong_confirmation = check.wait_confirmation()
            assert wrong_confirmation is True

            original_hash = agent.sha256
            calls = []
            def counted_hash(path):
                calls.append(str(path))
                return original_hash(path)
            agent.sha256 = counted_hash
            config.auto_print = False
            try:
                agent.process(job, config, state, driver, log)
                agent.process(job, config, state, driver, log)
            finally:
                agent.sha256 = original_hash
            assert len(calls) == 2
            return {
                'repository_commit': 'ed9ac95153aa01bb84e461e555866d21e394bf8f',
                'real_hardware_used': False,
                'network_connections': False,
                'manual_review_retried': {
                    'reproduced': True, 'first_state': first, 'second_state': second,
                    'synthetic_print_requests': driver.starts},
                'unrelated_job_confirmed': {
                    'reproduced': True, 'actual_current_job': 'waiting',
                    'wait_confirmation_returned': wrong_confirmation},
                'unchanged_pending_file_rehashed': {
                    'reproduced': True, 'cycles': 2, 'sha256_calls': len(calls)},
                'scope': 'Isolated SQLite/temp files and fake driver; confirms code behavior, not PrintExp compatibility'
            }
        finally:
            agent.stable = original_stable
            state.close()


if __name__ == '__main__':
    print(json.dumps(reproduce(), indent=2))
