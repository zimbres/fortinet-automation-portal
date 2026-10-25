import subprocess
import sys

from config.container import run_services


def test_child_failure_stops_other_service(monkeypatch):
    children = []
    original = subprocess.Popen

    def start(*args, **kwargs):
        child = original(*args, **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(subprocess, "Popen", start)
    slow = [sys.executable, '-c', 'import time; time.sleep(60)']
    fail = [sys.executable, '-c', 'import time; time.sleep(.2); raise SystemExit(7)']
    assert run_services([('web', slow), ('runner', fail)], shutdown_timeout=1) == 7
    assert len(children) == 2
    assert all(child.poll() is not None for child in children)


def test_clean_unexpected_exit_is_failure():
    assert run_services([('web', [sys.executable, '-c', 'pass'])]) == 1


def test_missing_program_is_failure():
    assert run_services([('runner', ['missing-portal-program'])]) == 1


def test_startup_failure_does_not_launch_services(monkeypatch):
    from config import container
    calls = []
    monkeypatch.setattr(container.subprocess, 'call', lambda command, **kwargs: calls.append(command) or 3)
    monkeypatch.setattr(container, 'run_services', lambda *args: (_ for _ in ()).throw(AssertionError('services started')))
    assert container.main() == 3
    assert len(calls) == 1


def test_shutdown_signal_returns_success(monkeypatch):
    import signal
    from config import container
    monkeypatch.setattr(container.time, 'sleep', lambda delay: signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None))
    assert run_services([('runner', [sys.executable, '-c', 'import time; time.sleep(60)'])], shutdown_timeout=1) == 0
