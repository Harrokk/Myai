import time

from core.geniex_supervisor import GenieXSupervisor


def wait_for_geniex(
    settings,
    *,
    timeout_seconds=60.0,
    interval_seconds=2.0,
    clock=None,
    sleep=None,
    supervisor=None,
):
    """Wait for the GenieX API without restarting it."""
    clock = clock or time.monotonic
    sleep = sleep or time.sleep
    supervisor = supervisor or GenieXSupervisor(settings)

    timeout_seconds = max(0.0, float(timeout_seconds))
    interval_seconds = max(0.1, float(interval_seconds))
    deadline = clock() + timeout_seconds

    while True:
        result = supervisor.check()

        if result.get("healthy") is True:
            return result

        remaining = deadline - clock()

        if remaining <= 0:
            raise TimeoutError(
                "GenieX blev inte tillgänglig inom "
                f"{timeout_seconds:g} sekunder. "
                f"Senaste status: {result.get('status')}. "
                f"Fel: {result.get('error')}"
            )

        sleep(min(interval_seconds, remaining))
