"""Non-authorizing RAM admission estimate for tiered STT on ARM64.

All inputs must be measured on the actual target and include native helpers.
This does NOT query the machine or open/run STT. Passing is only a planning
screen, not permission to enable voice, deploy models or dispatch tools.
"""

_FAMILIES = frozenset({"parakeet", "canary", "whisper"})


def evaluate_tiered_ram_budget(*, available_mib, stt_peak_rss_mib,
                               future_geniex_peak_mib, headroom_mib,
                               mode="sequential", cleanup_verified=False):
    """Conservative advisory check against measured memory headroom.

    available_mib is fresh MemAvailable before starting the measured task.
    stt_peak_rss_mib includes child+descendant peak per isolated model.
    future_geniex_peak_mib is ADDED peak after STT; avoid counting already
    running GenieX memory twice. No arbitrary default resource measurements.
    """
    def unavailable(reason):
        return {
            "eligible_for_trial": False,
            "reason": reason,
            "required_mib": None,
            "available_mib": available_mib if type(available_mib) is int else None,
        }

    values = (available_mib, future_geniex_peak_mib, headroom_mib)
    if any(type(value) is not int or not 0 < value <= 65536 for value in values):
        return unavailable("missing_or_invalid_measured_budget")
    if (type(stt_peak_rss_mib) is not dict
            or set(stt_peak_rss_mib) != _FAMILIES
            or any(type(n) is not int or not 0 < n <= 65536
                   for n in stt_peak_rss_mib.values())):
        return unavailable("missing_or_invalid_stt_measurements")
    if type(mode) is not str or mode not in ("sequential", "parallel"):
        return unavailable("unsupported_loading_mode")
    if type(cleanup_verified) is not bool:
        return unavailable("invalid_cleanup_status")
    if mode == "sequential":
        if cleanup_verified is not True:
            return unavailable("no_verified_stt_cleanup")
        # Parakeet, Canary and Whisper are assumed mutually exclusive;
        # GenieX starts only once previous STT process RAM has been freed.
        required = max(max(stt_peak_rss_mib.values()),
                       future_geniex_peak_mib) + headroom_mib
    else:
        # If all engines/GenieX may coexist, budget the total worst-case.
        required = (sum(stt_peak_rss_mib.values())
                    + future_geniex_peak_mib + headroom_mib)
    return {
        "eligible_for_trial": required <= available_mib,
        "reason": ("estimated_headroom_available"
                   if required <= available_mib else "insufficient_measured_memory"),
        "required_mib": required,
        "available_mib": available_mib,
    }
