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
