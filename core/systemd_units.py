from pathlib import Path


def _quote(value):
    text = str(
        value
    ).replace(
        "\\",
        "\\\\",
    ).replace(
        '"',
        '\\"',
    )
    return (
        '"'
        + text
        + '"'
    )


def build_ventuno_units(
    project_root,
    python_executable,
    user,
):
    root = Path(
        project_root
    ).resolve()
    # Keep virtualenv symlink paths instead of resolving to system Python.
    python = Path(
        python_executable
    ).absolute()
    profile = (
        root
        / "config"
        / "profiles"
        / "ventuno_q.json"
    )
    validator = (
        root
        / "scripts"
        / "validate_config.py"
    )
    runtime = (
        root
        / "scripts"
        / "ventuno_runtime.py"
    )
    watchdog = (
        root
        / "scripts"
        / "geniex_watchdog.py"
    )

    common_unit = """After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=300
StartLimitBurst=5
"""

    geniex_bin_dir = Path.home() / ".local" / "bin"
    service_path = f"{geniex_bin_dir}:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin"

    common_service = (
        f"User={user}\n"
        f"WorkingDirectory={root}\n"
        f"Environment={_quote(f'MYAI_SETTINGS={profile}')}\n"
        "Environment=PYTHONUNBUFFERED=1\n"
        f"Environment={_quote(f'PATH={service_path}')}\n"
        f"ExecStartPre={_quote(python)} "
        f"{_quote(validator)} --ventuno\n"
        "Restart=on-failure\n"
        "RestartSec=5\n"
        "TimeoutStopSec=15\n"
        "KillSignal=SIGTERM\n"
        "UMask=0077\n"
        "NoNewPrivileges=true\n"
    )

    runtime_unit = (
        "[Unit]\n"
        "Description=MyAI VENTUNO headless runtime\n"
        + common_unit
        + "Requires=myai-geniex.service\n"
        "After=myai-geniex.service\n"
        + "\n[Service]\n"
        "Type=simple\n"
        + common_service
        + f"ExecStart={_quote(python)} "
        f"{_quote(runtime)}\n"
        "\n[Install]\n"
        "WantedBy=multi-user.target\n"
    )

    watchdog_unit = (
        "[Unit]\n"
        "Description=MyAI GenieX health watchdog\n"
        + common_unit
        + "\n[Service]\n"
        "Type=simple\n"
        + common_service
        + f"ExecStart={_quote(python)} "
        f"{_quote(watchdog)}\n"
        "\n[Install]\n"
        "WantedBy=multi-user.target\n"
    )

    geniex_unit = (
        "[Unit]\n"
        "Description=GenieX Qualcomm NPU server\n"
        + common_unit
        + "\n[Service]\n"
        "Type=simple\n"
        f"User={user}\n"
        f"WorkingDirectory={Path.home()}\n"
        f"Environment={_quote(f'HOME={Path.home()}')}\n"
        f"ExecStart={_quote(Path.home() / '.local/bin/geniex')} "
        "serve --host 127.0.0.1:18181 --compute npu\n"
        "Restart=on-failure\n"
        "RestartSec=10\n"
        "TimeoutStopSec=30\n"
        "KillSignal=SIGTERM\n"
        "UMask=0077\n"
        "NoNewPrivileges=true\n"
        "\n[Install]\n"
        "WantedBy=multi-user.target\n"
    )

    target_unit = (
        "[Unit]\n"
        "Description=MyAI VENTUNO services\n"
        "Wants=myai-ventuno.service "
        "myai-geniex-watchdog.service\n"
        "After=network-online.target\n"
        "\n[Install]\n"
        "WantedBy=multi-user.target\n"
    )

    return {
        "myai-geniex.service": (
            geniex_unit
        ),
        "myai-ventuno.service": (
            runtime_unit
        ),
        "myai-geniex-watchdog.service": (
            watchdog_unit
        ),
        "myai-ventuno.target": (
            target_unit
        ),
    }


def write_ventuno_units(
    output_dir,
    project_root,
    python_executable,
    user,
):
    target = Path(
        output_dir
    )
    target.mkdir(
        parents=True,
        exist_ok=True,
    )
    units = build_ventuno_units(
        project_root,
        python_executable,
        user,
    )
    written = []

    for name, content in (
        units.items()
    ):
        path = (
            target
            / name
        )
        path.write_text(
            content,
            encoding="utf-8",
        )
        written.append(
            path
        )

    return written
