Ниже — большая MD-шка. Она написана как проектный документ, который можно скормить другой LLM почти без правок.

# Desktop Yandex Music Player: архитектура, сборка, тестирование, майлстоуны

## 1. Цель проекта

Сделать локальный desktop music player с классическим интерфейсом в духе Winamp / AIMP / QMMP / старых standalone-плееров, но с поддержкой Яндекс Музыки через неофициальную Python-библиотеку/API.

Ключевые требования:

- кроссплатформенность: минимум macOS + Linux, желательно Windows без радикальной переделки;
- нативный desktop UX, без Electron/WebView как основы приложения;
- UI на `PySide6`;
- воспроизведение через нативный backend, а не через декодирование в Python;
- упаковка приложения в self-contained bundle, чтобы пользователь не ставил отдельно VLC/mpv/прочие системные зависимости;
- архитектура, удобная для итеративной разработки с помощью LLM;
- тестирование в основном интеграционного типа, без упора в мелкие unit tests;
- проект должен быть пригоден для постепенного роста: сначала MVP, потом косметика, плагины, mini-mode, скины, hotkeys, library cache и т.д.

---

## 2. Не-цели

Что не нужно делать на старте:

- не строить браузер внутри приложения;
- не пытаться на первом этапе поддержать все функции Яндекс Музыки;
- не делать сразу полноценную skin engine совместимую с Winamp skins;
- не делать сразу визуализации, DSP-цепочки, радио, Last.fm, lyrics, scrobbling;
- не тратить время на микро-оптимизацию до появления реальных профилей;
- не писать большую систему плагинов до стабилизации ядра;
- не опираться на системно установленный `mpv` или `vlc` как обязательное внешнее требование для пользователя.

---

## 3. Главные архитектурные решения

### 3.1 UI toolkit

Использовать `PySide6`.

Причины:

- Qt 6 как зрелая desktop-платформа;
- нормальная кроссплатформенность;
- хорошая модель сигналов/слотов;
- удобный imperative UI для “плеерных” окон;
- достаточно удобно для LLM-генерации;
- убирает нежелательную зависимость от PyQt.

### 3.2 Audio backend

Использовать `libmpv` через Python binding или собственную узкую обёртку.

Причины:

- Python не участвует в декодировании аудио;
- зрелый playback engine;
- поддержка потоков, буферизации, seek, громкости, паузы, состояния;
- лучше подходит как core playback backend, чем попытки декодировать в Python;
- проще концептуально, чем тащить VLC-центричную архитектуру.

Принцип: приложение должно считать `mpv` внутренним playback engine, а не внешним пользовательским dependency.

### 3.3 API-интеграция

Яндекс Музыка интегрируется через отдельный infrastructure-layer клиент на Python.  
UI не должен напрямую знать про HTTP, токены, JSON и внутренние особенности API.

### 3.4 Архитектурный стиль

Не “чистая архитектура” в религиозном виде и не анемичный enterprise-слоёный монстр. Нужен практический hybrid:

- `domain` — основные сущности и интерфейсы;
- `application` — use cases / orchestration;
- `infrastructure` — API, playback, persistence, cache;
- `presentation` — Qt UI, view models, controllers.

То есть:

- бизнес-логика и сценарии не должны жить в QWidget’ах;
- network/audio/storage не должны протекать в presentation;
- но и не надо превращать проект в десятки абстракций без пользы.

---

## 4. Высокоуровневая схема

```text
+--------------------------+
|      Presentation        |
|  Qt Widgets / Controllers|
|  ViewModels / Commands   |
+------------+-------------+
             |
             v
+--------------------------+
|       Application        |
| Use Cases / Services     |
| Queue / Library / Auth   |
| Search / Playback flow   |
+------+----------+--------+
       |          |
       v          v
+-------------+  +------------------+
|   Domain    |  | Infrastructure   |
| entities    |  | Yandex API       |
| interfaces  |  | libmpv adapter   |
| contracts   |  | cache/db         |
+-------------+  | settings         |
                 | download/artwork |
                 +------------------+


⸻

5. Модули проекта

Предлагаемая структура:

src/
  app/
    bootstrap/
      container.py
      startup.py
      config.py

    domain/
      entities/
        track.py
        album.py
        artist.py
        playlist.py
        queue_item.py
        playback_state.py
        auth_session.py
      value_objects/
        ids.py
        duration.py
        image_ref.py
        paging.py
      interfaces/
        music_service.py
        playback_engine.py
        artwork_service.py
        settings_repo.py
        library_cache_repo.py
        auth_repo.py
        clock.py
        logger.py

    application/
      dto/
        track_dto.py
        playlist_dto.py
        search_result_dto.py
      services/
        queue_service.py
        playback_service.py
        library_service.py
        auth_service.py
        search_service.py
        playlist_service.py
        recommendations_service.py
      use_cases/
        login.py
        logout.py
        refresh_session.py
        play_track.py
        toggle_pause.py
        next_track.py
        previous_track.py
        seek_to.py
        set_volume.py
        load_playlist.py
        search_catalog.py
        like_track.py
        unlike_track.py
        sync_likes.py
        fetch_home.py

    infrastructure/
      yandex/
        client.py
        auth_provider.py
        adapters.py
        mappers.py
        exceptions.py
      playback/
        mpv_engine.py
        mpv_events.py
        mpv_loader.py
      persistence/
        sqlite_db.py
        settings_repo.py
        library_cache_repo.py
        auth_repo.py
      artwork/
        downloader.py
        cache.py
      telemetry/
        logging_impl.py
      time/
        system_clock.py

    presentation/
      qt/
        app.py
        main_window.py
        mini_player_window.py
        playlist_panel.py
        library_panel.py
        search_panel.py
        player_controls.py
        now_playing_bar.py
        queue_view.py
        equalizer_stub.py
        dialogs/
      viewmodels/
        app_view_model.py
        player_view_model.py
        playlist_view_model.py
        search_view_model.py
        auth_view_model.py
      controllers/
        app_controller.py
        playback_controller.py
        search_controller.py
        auth_controller.py
      resources/
        icons/
        qss/
        fonts/

tests/
  integration/
  contract/
  smoke/
tools/
scripts/
build/
docs/


⸻

6. Domain model

Нужны простые, устойчивые сущности.

6.1 Track

@dataclass(frozen=True)
class Track:
    id: str
    title: str
    artists: tuple[str, ...]
    album_title: str | None
    duration_sec: int
    artwork_url: str | None
    stream_ref: str | None
    explicit: bool = False
    available: bool = True

stream_ref — не обязательно прямой URL. Это может быть внутренний идентификатор, из которого infrastructure умеет получить playable stream.

6.2 Playlist

@dataclass(frozen=True)
class Playlist:
    id: str
    title: str
    description: str | None
    track_count: int
    artwork_url: str | None

6.3 QueueItem

@dataclass(frozen=True)
class QueueItem:
    track: Track
    source_type: str | None   # playlist / album / search / radio / likes
    source_id: str | None

6.4 PlaybackState

@dataclass(frozen=True)
class PlaybackState:
    current: Track | None
    is_playing: bool
    position_sec: float
    duration_sec: float
    volume: int
    is_muted: bool
    queue_index: int | None


⸻

7. Интерфейсы

Это важная часть, потому что через них делаются “интеграционные юниты” с фейками.

7.1 MusicService

Контракт с Яндекс Музыкой.

class MusicService(Protocol):
    def get_home(self) -> HomePageData: ...
    def search(self, query: str, limit: int = 50) -> SearchResults: ...
    def get_track(self, track_id: str) -> Track: ...
    def get_album_tracks(self, album_id: str) -> list[Track]: ...
    def get_playlist(self, playlist_id: str) -> Playlist: ...
    def get_playlist_tracks(self, playlist_id: str) -> list[Track]: ...
    def get_liked_tracks(self) -> list[Track]: ...
    def like_track(self, track_id: str) -> None: ...
    def unlike_track(self, track_id: str) -> None: ...
    def resolve_stream(self, track_id: str) -> ResolvedStream: ...

7.2 PlaybackEngine

class PlaybackEngine(Protocol):
    def load(self, stream_url: str, *, metadata: dict | None = None) -> None: ...
    def play(self) -> None: ...
    def pause(self) -> None: ...
    def stop(self) -> None: ...
    def seek(self, position_sec: float) -> None: ...
    def set_volume(self, value: int) -> None: ...
    def get_state(self) -> PlaybackState: ...
    def subscribe(self, listener: PlaybackEventListener) -> None: ...
    def shutdown(self) -> None: ...

7.3 Репозитории и системные зависимости

class SettingsRepo(Protocol):
    def load(self) -> AppSettings: ...
    def save(self, settings: AppSettings) -> None: ...

class LibraryCacheRepo(Protocol):
    def save_tracks(self, tracks: list[Track]) -> None: ...
    def search_cached(self, query: str, limit: int) -> list[Track]: ...
    def clear(self) -> None: ...

class AuthRepo(Protocol):
    def load_session(self) -> AuthSession | None: ...
    def save_session(self, session: AuthSession) -> None: ...
    def clear(self) -> None: ...


⸻

8. Application layer

Здесь живут use cases и orchestration. Именно этот слой должен быть главным объектом тестирования.

8.1 PlaybackService

Должен знать:
	•	текущую очередь;
	•	текущий индекс;
	•	repeat/shuffle;
	•	взаимодействие с MusicService.resolve_stream;
	•	взаимодействие с PlaybackEngine;
	•	синхронизацию состояния для UI.

Пример обязанностей:
	•	play_track(track)
	•	play_tracks(tracks, start_index=0, source=...)
	•	toggle_pause()
	•	next_track()
	•	previous_track()
	•	seek_to(sec)
	•	set_volume(value)
	•	replace_queue(items)
	•	append_to_queue(items)

8.2 SearchService

Обязанности:
	•	поиск по API;
	•	возможно fallback в локальный cache;
	•	объединение и нормализация результатов.

8.3 LibraryService

Обязанности:
	•	likes;
	•	сохранённые плейлисты;
	•	кэш недавно открытых сущностей;
	•	возможно offline metadata cache.

8.4 AuthService

Обязанности:
	•	стартовая загрузка сессии;
	•	refresh/проверка;
	•	logout;
	•	выдача валидной авторизации infrastructure-слою.

⸻

9. Presentation layer

9.1 Почему не QML

QML можно использовать, но для такого проекта на старте лучше Widgets:
	•	проще контролировать layout “олдскульного” плеера;
	•	проще LLM-генерация;
	•	меньше магии;
	•	меньше вероятность, что UI-логика утечёт в декларативный слой и станет хуже тестироваться.

9.2 UI-композиция

Основное окно может состоять из:
	•	top bar / title;
	•	transport controls;
	•	seek bar;
	•	volume;
	•	current track info;
	•	left panel: library / navigation;
	•	center panel: playlist/search/home;
	•	bottom status / queue / mini controls.

Отдельные режимы:
	•	main window;
	•	compact / mini mode;
	•	возможно отдельное queue window позднее.

9.3 ViewModel pattern

ViewModel должен быть тонким адаптером application state к Qt.

Он не должен:
	•	сам ходить в API;
	•	сам решать playback orchestration;
	•	сам читать БД.

Он должен:
	•	принимать DTO/state snapshots;
	•	держать observable-like state для UI;
	•	прокидывать команды controller/use case слою.

9.4 Controller pattern

Контроллер связывает Qt events и application use cases:
	•	кнопка Play -> playback_service.toggle_pause()
	•	двойной клик по track -> playback_service.play_tracks(...)
	•	поиск -> search_service.search(...)

⸻

10. Потоки и concurrency

Это один из самых неприятных участков, поэтому нужно задать правила сразу.

10.1 Базовые правила
	•	Qt main thread только для UI;
	•	network и тяжёлые операции вне UI thread;
	•	callbacks от mpv не должны напрямую мутировать QWidget;
	•	все переходы из background в UI — через сигналы/queued calls;
	•	никакой самодельной многопоточности “по месту” без общего подхода.

10.2 Практический подход

Минимально достаточно:
	•	UI thread — Qt;
	•	background executor для API/IO;
	•	playback engine внутри своей обёртки, события переводятся в thread-safe signals.

Варианты реализации:
	•	QThreadPool + QRunnable;
	•	либо concurrent.futures.ThreadPoolExecutor, если аккуратно завернуть результаты в Qt signals;
	•	asyncio я бы на старте не смешивал с Qt без жёсткой необходимости.

10.3 Рекомендация

Не строить приложение вокруг asyncio.
Для такого проекта это часто только повышает хрупкость. Лучше обычная синхронная бизнес-логика + controlled background execution.

⸻

11. Сборка и packaging

11.1 Цель

Пользователь скачивает приложение и запускает его без ручной установки внешнего playback backend.

11.2 Варианты

Вариант A: PyInstaller

Плюсы:
	•	простой старт;
	•	привычен;
	•	быстро собрать MVP.

Минусы:
	•	иногда грязная возня с hiddenimports, plugins, бинарями;
	•	на macOS может быть неприятен при сложных зависимостях.

Вариант B: Nuitka

Плюсы:
	•	может дать более аккуратный runtime bundle;
	•	часто лучше для production-дистрибуции Python desktop app.

Минусы:
	•	сложнее сборка;
	•	длиннее feedback loop.

Рекомендация

На старте:
	•	локальная разработка без упаковки;
	•	первые distributable-билды через PyInstaller;
	•	если проект становится серьёзным и packaging болит — оценить переход на Nuitka.

11.3 Bundling libmpv

Ключевой принцип:
	•	libmpv должен ехать внутри приложения;
	•	путь к библиотеке должен резолвиться через app runtime path;
	•	никакой обязательной зависимости на системно установленный mpv для обычного пользователя.

Нужно сделать отдельный mpv_loader.py, который:
	•	знает, где искать bundled library;
	•	умеет fallback на dev-environment path;
	•	логирует понятную ошибку при отсутствии backend.

11.4 Ресурсы

В bundle должны попасть:
	•	Qt runtime;
	•	Python runtime;
	•	иконки;
	•	QSS/стили;
	•	libmpv и связанные бинарные зависимости;
	•	возможно лицензии third-party;
	•	базовые шрифты, если они реально нужны.

11.5 CI build matrix

Желательно:
	•	macOS latest;
	•	Ubuntu latest;
	•	Windows latest.

Сразу можно не собирать релизы на все платформы, но структура CI должна это допускать.

⸻

12. Конфиг и данные приложения

12.1 Что хранить
	•	auth/session data;
	•	settings;
	•	volume;
	•	repeat/shuffle;
	•	window geometry;
	•	cache index;
	•	recent entities;
	•	artwork cache;
	•	library metadata cache.

12.2 Где хранить

Использовать platform-correct app dirs.

Например через platformdirs:
	•	config dir;
	•	data dir;
	•	cache dir.

12.3 Форматы
	•	settings: JSON или TOML;
	•	structured cache: SQLite;
	•	artwork: files in cache dir;
	•	auth/session: отдельный JSON/SQLite blob.

12.4 Почему SQLite

SQLite лучше, чем “всё в json файликах”, когда появляются:
	•	кэш поиска;
	•	recent items;
	•	offline metadata;
	•	indexed library data.

⸻

13. Стратегия тестирования

13.1 Общий принцип

Не строить пирамиду из сотен unit tests на приватные методы.
Основной упор на:
	•	integration-style tests;
	•	contract tests;
	•	narrow fake-based tests через интерфейсы;
	•	smoke tests для приложения.

То, что ты называешь “интеграционные юниты”, здесь как раз основной инструмент.

13.2 Что тестировать

Главный объект тестирования — не QWidget и не отдельные dataclass’ы, а application/use-case слой.

Пример хорошего тест-кейса

“Когда пользователь запускает playlist, сервис должен:
	•	загрузить список треков через MusicService,
	•	заменить очередь,
	•	разрешить stream для первого трека,
	•	передать URL в PlaybackEngine,
	•	перевести состояние в playing.”

Это не unit test в микро-смысле, но и не end-to-end через настоящий UI. Это и есть основной рабочий формат.

13.3 Типы тестов

A. Contract tests

Проверяют, что fake и real implementation obey одинаковый контракт.

Примеры:
	•	MusicService fake возвращает те же shape/ошибки, что ожидает приложение;
	•	PlaybackEngine fake генерирует события в том же порядке, что нужен application слою.

B. Application integration tests

Тесты use cases / services с dependency injection.

Зависимости подменяются на:
	•	FakeMusicService
	•	FakePlaybackEngine
	•	InMemorySettingsRepo
	•	InMemoryAuthRepo
	•	FakeClock

Это основной пласт.

C. Infrastructure tests

Ограниченно тестируют реальные адаптеры:
	•	SQLiteLibraryCacheRepo на временной БД;
	•	YandexMusicClient на recorded responses / sandbox;
	•	MpvEngine smoke test при наличии окружения.

D. UI smoke tests

Минимальные проверки:
	•	окно создаётся;
	•	основные контролы подключены;
	•	viewmodel binding не падает;
	•	базовые команды вызываются.

Не нужно пытаться полноценно E2E-водить UI на каждую кнопку.

13.4 Что не тестировать подробно
	•	trivial dataclass value objects;
	•	Qt layout spacing;
	•	каждый getter/setter;
	•	косметические методы без логики.

13.5 Dependency injection стратегия

Нужен простой composition root, а не DI framework.

Пример

class AppContainer:
    def __init__(self):
        self.settings_repo = JsonSettingsRepo(...)
        self.auth_repo = SqliteAuthRepo(...)
        self.music_service = YandexMusicService(...)
        self.playback_engine = MpvPlaybackEngine(...)
        self.playback_service = PlaybackService(
            music_service=self.music_service,
            playback_engine=self.playback_engine,
            settings_repo=self.settings_repo,
        )

В тестах:

container = TestContainer(
    music_service=FakeMusicService(...),
    playback_engine=FakePlaybackEngine(),
    settings_repo=InMemorySettingsRepo(),
)

13.6 Фейки вместо моков

Предпочтение fake implementations, а не dynamic mocks.

Плохо:
	•	тесты на то, что “метод вызван 1 раз с exact arg structure” без проверки поведения.

Хорошо:
	•	FakePlaybackEngine.loaded_urls
	•	FakeMusicService.request_log
	•	проверка итогового состояния и observable side effects.

13.7 Пример тестов

PlaybackService
	•	play single track;
	•	play playlist from index;
	•	next/previous with queue edges;
	•	repeat-one/repeat-all;
	•	shuffle;
	•	resolve stream failure;
	•	playback engine error;
	•	seek and volume persistence.

SearchService
	•	search success;
	•	empty results;
	•	API error mapping;
	•	cancellation/late result ignore.

AuthService
	•	startup with saved session;
	•	invalid session refresh;
	•	logout clears storage;
	•	auth failure produces UI-safe state.

LibraryService
	•	load likes;
	•	optimistic like/unlike;
	•	cache refresh;
	•	stale cache fallback.

13.8 Инструменты
	•	pytest
	•	pytest-qt для минимальных Qt tests
	•	tmp_path для временных файлов/БД
	•	возможно respx/VCR-like recorders, если API-слой HTTP-based и это реально полезно

Но recorded HTTP tests не должны стать основой всей системы. Их ровно столько, сколько нужно для проверки адаптера.

⸻

14. Обработка ошибок

Это нужно продумать сразу, иначе LLM нагенерирует хаос.

14.1 Категории ошибок
	•	auth errors;
	•	network errors;
	•	unavailable track/region restriction;
	•	stream resolve failure;
	•	playback backend failure;
	•	storage corruption;
	•	invalid config;
	•	unexpected API response.

14.2 Правила
	•	domain/application не должны работать с сырыми исключениями requests/httpx/OSError;
	•	infrastructure переводит ошибки в свои типы;
	•	application решает, recoverable это или нет;
	•	presentation показывает безопасочное сообщение.

14.3 Пример

class MusicServiceError(Exception): ...
class AuthExpiredError(MusicServiceError): ...
class TrackUnavailableError(MusicServiceError): ...
class StreamResolveError(MusicServiceError): ...


⸻

15. Логирование и наблюдаемость

Нужен нормальный debug trail, иначе потом трудно чинить playback и API.

Логировать:
	•	startup;
	•	loading settings;
	•	auth/session lifecycle;
	•	search requests;
	•	playlist loads;
	•	stream resolution;
	•	playback events;
	•	queue transitions;
	•	recoverable errors.

Не логировать:
	•	чувствительные токены в явном виде;
	•	приватные пользовательские данные без надобности.

Формат

Обычный structured-ish logging достаточно.
Не надо на старте тащить полноразмерную telemetry систему.

⸻

16. UI/UX стратегия

16.1 Приоритеты

Сначала функциональная ясность, потом стилизация.

Этапы:
	1.	ugly but correct;
	2.	usable classic layout;
	3.	polished retro aesthetic;
	4.	mini-mode / detachable panels / advanced UX.

16.2 Почему не начинать со скинов

Потому что skin engine:
	•	ломает layout assumptions;
	•	умножает сложность;
	•	замедляет стабилизацию ядра.

На старте достаточно:
	•	фиксированная классическая компоновка;
	•	theme via QSS;
	•	несколько предопределённых режимов.

16.3 Реалистичный scope UI для MVP
	•	main window;
	•	queue/list panel;
	•	current track info;
	•	play/pause/next/prev;
	•	seek;
	•	volume;
	•	search;
	•	likes;
	•	playlist open;
	•	basic home/library.

⸻

17. Слои абстракции, которые стоит ограничить

Не нужно делать заранее:
	•	generic event bus на весь проект;
	•	plugin system;
	•	command framework уровня IDE;
	•	universal repository abstraction “на всё”;
	•	5 разных state manager’ов;
	•	отдельные presenter/interactor/coordinator/facade на каждый чих.

LLM любит раздувать архитектуру. Надо сознательно резать лишнее.

⸻

18. Практические кодовые правила

18.1 Общие
	•	Python 3.12+ если нет blockers;
	•	typing везде, кроме совсем мелких скриптов;
	•	dataclass / attrs для DTO и entity-like структур;
	•	явные интерфейсы через Protocol или ABC;
	•	без циклических импортов;
	•	без бизнес-логики в Qt widgets.

18.2 Стиль
	•	одна ответственность на класс;
	•	use case либо service должен быть читаем целиком;
	•	не делать “god service” на 2500 строк;
	•	модули до ~300-500 строк держать по возможности;
	•	сложные методы дробить по смыслу, а не механически.

18.3 Для LLM-совместимости
	•	держать файлы небольшими;
	•	интерфейсы формулировать явно;
	•	оставлять docstring на public classes/use cases;
	•	иметь ARCHITECTURE.md, TESTING.md, BUILDING.md.

⸻

19. Риски проекта

19.1 Основные риски
	1.	Нестабильность неофициального API Яндекс Музыки.
	2.	Сложности packaging libmpv на macOS/Windows.
	3.	Потоковые баги между Qt и playback callbacks.
	4.	Переусложнение архитектуры под влиянием LLM.
	5.	UI начинает напрямую зависеть от инфраструктуры.
	6.	Кэш/сессия/авторизация становятся грязным слоем состояния.

19.2 Как снижать риски
	•	изолировать Yandex API в одном infrastructure-модуле;
	•	изолировать mpv в одном playback adapter;
	•	держать application слой максимально независимым;
	•	с первого дня иметь 10-20 сильных integration tests на критические сценарии;
	•	не делать скины/плагины до стабилизации MVP;
	•	регулярно прогонять smoke build.

⸻

20. Предлагаемые майлстоуны

Milestone 0 — Skeleton / bootstrap

Цель: пустой, но правильно разложенный проект.

Сделать:
	•	структура каталогов;
	•	базовый app bootstrap;
	•	main window “hello player”;
	•	container/composition root;
	•	settings loading;
	•	logging;
	•	CI lint/test skeleton;
	•	smoke run script.

Definition of Done:
	•	приложение запускается;
	•	окно открывается;
	•	проект собирается локально;
	•	есть базовый каркас тестов.

⸻

Milestone 1 — Playback core без Яндекса

Цель: доказать, что архитектура плеера живая.

Сделать:
	•	PlaybackEngine интерфейс;
	•	MpvPlaybackEngine реализация;
	•	FakePlaybackEngine;
	•	PlaybackService;
	•	queue model;
	•	basic controls: play/pause/next/prev/seek/volume;
	•	загрузка локального тестового URL/файла.

Definition of Done:
	•	можно воспроизводить тестовый аудиопоток;
	•	очередь работает;
	•	состояние playback отображается в UI;
	•	есть integration tests на playback orchestration.

⸻

Milestone 2 — Интеграция с Яндекс Музыкой: auth + track resolve

Цель: получить playable track из реального сервиса.

Сделать:
	•	MusicService интерфейс;
	•	YandexMusicService реализация;
	•	auth/session repo;
	•	получение/восстановление сессии;
	•	resolve track -> stream;
	•	play single track by id.

Definition of Done:
	•	можно авторизоваться/подцепить сессию;
	•	можно воспроизвести один трек из Яндекс Музыки;
	•	ошибки auth и unavailable tracks обрабатываются предсказуемо.

⸻

Milestone 3 — Search + library basics

Цель: минимально полезный пользовательский сценарий.

Сделать:
	•	поиск треков;
	•	отображение результатов;
	•	double click -> play;
	•	likes;
	•	“My Tracks” / liked tracks;
	•	recent searches;
	•	metadata/artwork cache.

Definition of Done:
	•	пользователь может искать, запускать и лайкать;
	•	UI уже похож на рабочий плеер, а не на демку;
	•	тесты покрывают основные сценарии поиска и запуска.

⸻

Milestone 4 — Playlist/album flows

Цель: полноценная навигация по музыкальному каталогу.

Сделать:
	•	open album;
	•	open playlist;
	•	replace queue / append queue;
	•	source-aware playback;
	•	next/prev по source queue;
	•	basic shuffle/repeat.

Definition of Done:
	•	можно открыть плейлист/альбом и слушать как нормальный music player;
	•	переходы между треками корректны;
	•	queue semantics стабильна.

⸻

Milestone 5 — Packaging и реальные дистрибутивы

Цель: убрать “works on my machine”.

Сделать:
	•	PyInstaller или Nuitka build scripts;
	•	bundling libmpv;
	•	macOS app bundle;
	•	Linux bundle;
	•	basic release artifacts;
	•	startup diagnostics screen/logs.

Definition of Done:
	•	приложение запускается на чистой машине без ручной установки playback backend;
	•	есть документированный build pipeline;
	•	есть smoke-checklist для релизного артефакта.

⸻

Milestone 6 — Классический UX

Цель: довести продукт до желаемого характера.

Сделать:
	•	compact mode / mini mode;
	•	улучшенный queue UI;
	•	keyboard shortcuts;
	•	tray/menu integration where relevant;
	•	styling в духе classic desktop audio player;
	•	persistent layout and settings.

Definition of Done:
	•	приложение ощущается как настоящий standalone music player;
	•	ежедневный usage не раздражает;
	•	UX ближе к AIMP/QMMP/Winamp-подобной модели.

⸻

Milestone 7 — Stabilization

Цель: убрать хрупкость.

Сделать:
	•	error audit;
	•	threading audit;
	•	cache corruption recovery;
	•	better logging;
	•	contract tests for infra;
	•	performance profiling of long sessions;
	•	crash-prone flows cleanup.

Definition of Done:
	•	многочасовая работа без деградации;
	•	переключения, поиск, playback и reopen app не ломаются;
	•	проект готов к дальнейшему расширению.

⸻

21. Что можно отложить до после MVP
	•	полноценный equalizer;
	•	visualizations;
	•	plugin system;
	•	remote control API;
	•	Discord/Last.fm integration;
	•	lyrics;
	•	download/offline mode;
	•	skin engine;
	•	waveform rendering;
	•	gapless fine-tuning beyond what mpv gives by default.

⸻

22. Минимальный технический backlog

Core
	•	app bootstrap
	•	settings storage
	•	logging
	•	playback engine interface
	•	mpv adapter
	•	playback service
	•	queue model

Yandex
	•	auth/session persistence
	•	search
	•	track resolve
	•	likes
	•	playlists
	•	albums

UI
	•	main window
	•	player controls
	•	now playing bar
	•	search panel
	•	playlist/library panel
	•	queue view
	•	mini mode

Persistence
	•	settings repo
	•	auth repo
	•	sqlite cache
	•	artwork cache

Testing
	•	fake music service
	•	fake playback engine
	•	in-memory repos
	•	integration tests for playback
	•	integration tests for search/library
	•	smoke UI tests

Build
	•	dev bootstrap script
	•	PyInstaller spec
	•	bundle libmpv
	•	CI pipeline
	•	release checklist

⸻

23. Рекомендуемая последовательность разработки

Правильный порядок примерно такой:
	1.	bootstrap + main window
	2.	queue + playback service + fake playback
	3.	real mpv backend
	4.	play test stream/file
	5.	Yandex auth/session
	6.	resolve single track
	7.	search UI
	8.	play from search results
	9.	liked tracks
	10.	playlists/albums
	11.	packaging
	12.	visual polish

Не наоборот.
Если начинать со сложного UI и “почти полного продукта”, получится повторяемая ошибка desktop pet-project’ов: красиво, но хрупко.

⸻

24. Что просить у LLM

LLM лучше использовать на конкретных задачах.

Хорошие запросы:
	•	“реализуй интерфейс PlaybackEngine и fake-реализацию для тестов”;
	•	“написать PlaybackService с очередью и тестами на repeat/shuffle”;
	•	“сделай QWidget для списка треков, который принимает TrackListViewModel”;
	•	“сделай SqliteLibraryCacheRepo и integration tests через tmp_path”.

Плохие запросы:
	•	“сделай весь плеер целиком”;
	•	“придумай лучшую архитектуру”;
	•	“добавь ещё всё что нужно”.

LLM надо держать в узких задачах и опираться на этот документ как на ground truth.

⸻

25. Антипаттерны, которых надо избегать
	•	QWidget напрямую вызывает Yandex API client;
	•	playback callbacks напрямую меняют UI state;
	•	singleton-сервисы по всему проекту;
	•	логика очереди размазана между UI и backend;
	•	auth/session логика размазана по 6 классам;
	•	моки всего подряд вместо fake implementations;
	•	giant main_window.py на 3000 строк;
	•	попытка сделать skin/plugin engine до MVP;
	•	reliance on system-installed mpv/vlc for end users;
	•	смешивание asyncio, Qt threads и ad-hoc callbacks без жёсткой модели.

⸻

26. Опорный технический тезис проекта

Этот проект должен быть не “Python-скрипт с музыкой”, а нормальное desktop-приложение:
	•	Python отвечает за приложение и логику;
	•	PySide6 отвечает за UI;
	•	libmpv отвечает за воспроизведение;
	•	Yandex API слой отвечает за каталог и stream resolution;
	•	тестируются в первую очередь use cases и orchestration;
	•	сборка должна паковать нативные зависимости внутрь приложения.

Если эта дисциплина сохраняется, проект имеет шанс вырасти в стабильный личный плеер, а не в очередной полурабочий prototype.

⸻

27. Краткий итог

Оптимальная стратегия:
	•	PySide6 вместо PyQt;
	•	libmpv вместо декодирования в Python и вместо внешнего ручного VLC;
	•	архитектура: domain + application + infrastructure + presentation;
	•	тестирование: integration-first, fake implementations через интерфейсы;
	•	сборка: self-contained bundle;
	•	сначала playback core и API-интеграция, потом polish;
	•	не переусложнять проект абстракциями и не пытаться сделать “всё сразу”.

Это достаточная база для MVP, который потом можно расширять без полной переписки.

