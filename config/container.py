"""Run the production web server and singleton executor as one lifecycle."""
import signal
import subprocess
import sys
import time


def run_services(services, shutdown_timeout=30):
    children = []
    stopping = False

    def stop(signum, frame):
        nonlocal stopping
        stopping = True

    previous = {sig: signal.signal(sig, stop) for sig in (signal.SIGTERM, signal.SIGINT)}
    result = 1
    try:
        for name, command in services:
            print(f'container: starting {name}', flush=True)
            children.append((name, subprocess.Popen(command, stderr=subprocess.STDOUT)))
        while not stopping:
            for name, child in children:
                code = child.poll()
                if code is not None:
                    print(f'container: {name} exited ({code}); stopping all services', flush=True)
                    return code if code > 0 else 1
            time.sleep(.1)
        result = 0
    except OSError as exc:
        print(f'container: cannot start service: {exc}', flush=True)
    finally:
        for _, child in children:
            if child.poll() is None:
                child.terminate()
        deadline = time.monotonic() + shutdown_timeout
        for _, child in children:
            try:
                child.wait(timeout=max(0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    return result


def main():
    for task in ('migrate', 'collectstatic'):
        code = subprocess.call([sys.executable, 'manage.py', task, '--noinput'],
                               stderr=subprocess.STDOUT)
        if code:
            return code
    return run_services([
        ('web', ['gunicorn', 'config.wsgi:application', '--bind', '0.0.0.0:8000',
                 '--workers', '2', '--timeout', '45', '--access-logfile', '-',
                 '--error-logfile', '-', '--capture-output', '--access-logformat',
                 '%(h)s %(m)s %(U)s %(H)s %(s)s %(b)s']),
        ('runner', [sys.executable, '-u', 'manage.py', 'run_executor']),
    ])


if __name__ == '__main__':
    sys.exit(main())
