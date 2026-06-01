import sys

def when_ready(server):
    """
    Hook called just after the server is started.
    We use this to run our startup health checks before accepting requests.
    """
    try:
        from hankox_executor import check_startup_health
        check_startup_health()
    except Exception as e:
        print(f"CRITICAL: Failed to run startup health check: {e}")
        sys.exit(3)

def post_worker_init(worker):
    """
    Hook called after a worker is initialized.
    We use this to start background threads safely after the fork.
    """
    try:
        from hankox_executor import start_daemon
        start_daemon()
    except Exception as e:
        print(f"Failed to start daemon in worker: {e}")
