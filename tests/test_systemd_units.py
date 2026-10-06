from core.systemd_units import (
    build_ventuno_units,
    write_ventuno_units,
)


def test_systemd_units_use_headless_runtime_and_watchdog(tmp_path):
    units = build_ventuno_units(
        tmp_path / "MyAI",
        "/usr/bin/python3",
        "myai",
    )

    runtime = units[
        "myai-ventuno.service"
    ]
    watchdog = units[
        "myai-geniex-watchdog.service"
    ]

    assert "ventuno_runtime.py" in runtime
    assert "mail.py" not in runtime
    assert "geniex_watchdog.py" in watchdog
    assert "validate_config.py" in runtime
    assert "--ventuno" in runtime


def test_systemd_units_have_bounded_crash_recovery(tmp_path):
    units = build_ventuno_units(
        tmp_path / "MyAI",
        "/usr/bin/python3",
        "myai",
    )

    for name in (
        "myai-ventuno.service",
        "myai-geniex-watchdog.service",
    ):
        content = units[name]
        assert "Restart=on-failure" in content
        assert "RestartSec=5" in content
        assert "StartLimitIntervalSec=300" in content
        assert "StartLimitBurst=5" in content
        assert "NoNewPrivileges=true" in content
        assert "UMask=0077" in content


def test_systemd_generator_does_not_create_install_paths(tmp_path):
    output = tmp_path / "generated"
    written = write_ventuno_units(
        output,
        tmp_path / "MyAI",
        "/usr/bin/python3",
        "myai",
    )

    assert {
        path.name
        for path in written
    } == {
        "myai-ventuno.service",
        "myai-geniex-watchdog.service",
        "myai-ventuno.target",
    }
    assert all(
        path.parent == output
        for path in written
    )


def test_systemd_unit_sets_explicit_runtime_profile(tmp_path):
    root = (
        tmp_path
        / "My AI"
    )
    units = build_ventuno_units(
        root,
        "/usr/bin/python3",
        "myai",
    )

    runtime = units[
        "myai-ventuno.service"
    ]

    assert "MYAI_SETTINGS=" in runtime
    assert "config/profiles/ventuno_q.json" in runtime
    assert 'WorkingDirectory="' in runtime
