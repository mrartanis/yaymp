from app.domain import WaveOption, WaveSetting, WaveSettings
from app.presentation.qt.main_window_wave import WaveSettingsPopup


def test_wave_settings_popup_selects_last_server_wave(qtbot) -> None:
    texts = {
        "wave.settings.title": "My Wave settings",
        "wave.settings.station": "Wave",
        "wave.settings.loading": "Loading",
        "wave.settings.error": "Error: {message}",
        "wave.settings.any": "Any",
        "wave.settings.play": "Play",
        "action.reset": "Reset",
    }

    def translate(key: str, **params: object) -> str:
        return texts[key].format(**params)

    popup = WaveSettingsPopup(translate=translate)
    qtbot.addWidget(popup)
    popup.set_settings(
        WaveSettings(
            stations=(
                WaveOption("user:onyourwave", "My Wave", unspecified=True),
                WaveOption("activity:work", "Work"),
            ),
            settings=(
                WaveSetting(
                    id="diversity",
                    title="Diversity",
                    options=(
                        WaveOption(
                            "settingDiversity:any",
                            "Any",
                            unspecified=True,
                        ),
                        WaveOption("settingDiversity:discover", "Discover"),
                    ),
                ),
                WaveSetting(
                    id="energy",
                    title="Energy",
                    options=(
                        WaveOption("settingEnergy:calm", "Calm"),
                        WaveOption("settingEnergy:active", "Active"),
                    ),
                    optional=True,
                ),
            ),
            selected_seeds=("activity:work", "settingDiversity:discover"),
        )
    )

    assert popup._station_combo.currentText() == "Work"
    assert popup._setting_combos[0].currentText() == "Discover"
    assert popup._setting_combos[1].currentText() == "Any"
    assert popup.selected_seeds() == (
        "activity:work",
        "settingDiversity:discover",
    )
