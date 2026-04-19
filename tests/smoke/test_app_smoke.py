from app.bootstrap.startup import build_startup_context


def test_main_window_can_be_constructed(qtbot, qapp, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("YAYMP_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("YAYMP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("YAYMP_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("YAYMP_LOG_DIR", str(tmp_path / "logs"))

    context = build_startup_context(argv=["yaymp-test"], existing_qt_app=qapp)

    qtbot.addWidget(context.main_window)
    context.main_window.show()

    assert context.main_window.windowTitle() == "YAYMP"
    assert context.container.config.settings_file.name == "settings.json"
    assert context.main_window.isVisible()
