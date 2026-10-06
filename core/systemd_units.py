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
    python = Path(
        python_executable
    ).resolve()
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

    common_service = (
        f"User={user}\n"
        f"WorkingDirectory={_quote(root)}\n"
        f"Environment={_quote(f'MYAI_SETTINGS={profile}')}\n"
        "Environment=PYTHONUNBUFFERED=1\n"
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
