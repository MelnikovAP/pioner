# PIONER — пошаговый план работ (non-front)

Файл — отсортированный, **исполнимый по очереди** список задач для следующих
итераций. Каждый пункт самодостаточен (что сделать, где, почему, как
проверить). Пункты **P0** — нужно делать первыми, **P3** — мелочи.

Все ссылки на файлы — в формате `path/to/file.py:line` или `path/to/file.py`.
Тесты прогоняются командой `PYTHONPATH=src .venv/bin/pytest -q`.

## Состояние сейчас

- Полный pytest зелёный: `26 passed`.
- 3 итерации валидации сделаны, критические баги уровня «не запустится»
  закрыты, остались архитектурные шероховатости и неоднозначности
  физической модели.
- Подробная картина пайплайна — в `spec.md`.

---

## P0 — критические корректность-баги

Нельзя оставлять перед production-запуском. Каждый — отдельный коммит.

### P0-1. `nanocontrol_tango`: пути к calibration.json игнорируют папку `settings/`

**Где:** `src/pioner/back/nanocontrol_tango.py:133, 140, 148`

**Что:** в `load_calibration / apply_default_calibration / apply_calibration`
используются короткие имена `CALIBRATION_FILE = "calibration.json"` и
`DEFAULT_CALIBRATION_FILE = "default_calibration.json"`. Они открываются по
относительному пути от **CWD Tango-сервера**, а не из `settings/`.
В `constants.py` уже есть правильные `CALIBRATION_FILE_REL_PATH` и
`DEFAULT_CALIBRATION_FILE_REL_PATH`.

**Действие:** заменить три ссылки на `*_REL_PATH` версии. Также убедиться, что
`load_calibration` пишет в ту же директорию, откуда читает `apply_calibration`.

**Проверка:** запустить `python -m pioner.back.debug` из любого CWD — раньше
работало случайно, теперь должно работать стабильно. Добавить тест, который
читает дефолтную калибровку через `Calibration.read(DEFAULT_CALIBRATION_FILE_REL_PATH)`.

### P0-2. `apply_calibration`: `Uref` берётся с канала heater, а не reference

**Где:** `src/pioner/back/modes.py:228-236`

**Что:** комментарий говорит «guard reference AO trace», но код берёт
`voltage_profiles["ch1"]`. Согласно `spec.md` и фронту (`HEATER_CHANNEL_KEY =
"ch1"`), **ch1 — это нагреватель**. То есть колонка `Uref` сейчас содержит
профиль нагревателя (с модуляцией для slow/iso), а не референс.

**Действие:** уточнить у физика, какой канал он считает референсом
(вероятно `ch0` shunt или `ch2` guard), либо переименовать колонку в
`Uheater` чтобы убрать ложное название. Также в HDF5-сохранении
(`fastheat.py:91`, `slow_mode.py:71`) колонка называется `Uref` — поправить
синхронно.

**Проверка:** добавить assert в e2e-тестах, что `Uref` совпадает с тем
профилем, который реально подаётся на heater (или с reference).

### P0-3. `apply_calibration`: размерности Ihtr/Uhtr подозрительны

**Где:** `src/pioner/back/modes.py:210-225`

**Что:** `ih = ihtr0 + ihtr1 * df[0]`. Канал 0 — это **напряжение на shunt-
резисторе** (V), не ток. С дефолтной калибровкой `ihtr0=0, ihtr1=1.0` (и
такой же в `settings/calibration.json`) формула `ih = 1.0 * V_shunt = V`,
а используется как ток в формуле `Rhtr = ... / ih`. Получается **сопротивление
в [Ohm·V/A]** (ерунда).

Аналогично `df[5] = df[5] * 1000.0` (heater feedback, mV) → `(Uheater_mV -
Ushunt_mV + uhtr0) * uhtr1`. Если `uhtr1 = 1` — получаем мВ. Делим на «ток»
(на самом деле напряжение) — итоговое `Rhtr` в Ом только если кто-то
неявно учёл `1/Rshunt` через `ihtr1`. В текущей калибровке этого нет.

**Действие:**
- Уточнить у Алексея: какой физический смысл у `ihtr1` в production? Если
  `ihtr1` действительно содержит `1/Rshunt`, то стандартная калибровка должна
  это отражать (ставить значение `≈1/1700`).
- Добавить **в `apply_calibration` явные комментарии о размерностях** каждой
  величины (`# ih: amperes`, `# df[5]: millivolts`).
- Добавить юнит-тест, который пропускает синтетические V_shunt = 1mA × 1700Ω =
  1.7V через калибровку и проверяет, что `Rhtr ≈ 1700 Ω`.

### P0-4. `mainWindow.fh_arm` / iso: ch1 vs ch2 inconsistencies в legacy GUI пути

**Где:** хотя front не правим, есть зеркальный риск в Tango пути. Проверить
консистентность ch{N} default между front (`ch1`), `IsoMode(modulation_channel="ch1")`
и `nanocontrol_tango.set_voltage`-эквивалентами. **Если фронт сейчас вызывает
старый Tango command, который писал на ch2 — он сломается.**

**Действие:** прогнать legacy сценарий (set_temp_volt из GUI → Tango → DAQ) и
явно убедиться, что AO-канал, попадающий в `a_out`, совпадает с фронтенд-
ожиданием. Добавить интеграционный тест mock-уровня.

### P0-5. `ExperimentManager`: AI стартует перед AO ⇒ leading-edge skew

**Где:** `src/pioner/back/experiment_manager.py:192-194`

**Что:** комментарий уже есть (`TODO(global): use a hardware trigger`). Для
fast-режима 1000 K/s это даёт ~1°C ошибку на первом образце. Не критично для
прототипов, но критично для публикуемых данных.

**Действие:**
- На реальном железе использовать `ScanOption.RETRIGGER + EXTTRIGGER` или
  software-pacing через общий счётчик. **Прочитать главу uldaq «Trigger
  configuration»** перед изменениями.
- Альтернативный путь: пометить `samples[0:N]` (где N = задержка в сэмплах)
  как `pre_trigger=True` колонкой и обрезать в `apply_calibration`.

**Проверка:** на реальном железе — поставить генератор 1кГц на AO ch1, AI
читать тот же сигнал на AI ch1. Скейл смещения должен быть < 1 сэмпла.

### P0-6. `_collect_finite_ai`: «1-секундный буфер» жестко завязан на programs

**Где:** `src/pioner/back/experiment_manager.py:291-292`,
`src/pioner/back/modes.py:111-122`

**Что:** сейчас `_validate_programs` требует `total_ms % 1000 == 0`, а
`_collect_finite_ai` использует AI-буфер размером ровно `sample_rate` (1с).
Это работает, но не позволяет программы 1.5с / 2.7с и т.п. Пользователь
ловит `ValueError` без подсказки.

**Действие:** реализовать вариант буфера = `ceil(seconds) * sample_rate` с
обрезкой хвоста до `total_samples_per_channel`. Логика half-buffer flip
останется — последний chunk просто берётся через wraparound, излишек
обрезается. **См. spec.md `Outstanding TODO 1`.**

**Проверка:** добавить тест с program 1500 ms (ramp 0→1V), убедиться, что
`len(df) == 1.5 * sample_rate`, нет потерь, последняя точка ≈ 1V.

---

## P1 — важные архитектурные / логические улучшения

### P1-1. `IsoMode.run`: нет `stop()` API для длинных прогонов

**Где:** `src/pioner/back/modes.py:492-547`, `src/pioner/back/iso_mode.py`

**Что:** уже стоит `TODO(global)`. Для iso 30+ минут единственный способ
остановить — ждать `time.sleep(duration)` или убить процесс.

**Действие:** добавить `threading.Event` (или `stop()` метод) на `IsoMode`,
прокинуть в Tango (`@command def stop_iso(self)`). Цикл ожидания заменить на
`event.wait(duration)`.

**Проверка:** тест: запустить iso в фоновом потоке на `duration=10`, через
0.5с вызвать `stop()`, убедиться что `run()` вернулся за <1с и в `df`
не меньше ~0.4с данных.

### P1-2. `IsoMode`: `Uref` в результате — мусор

**Где:** `src/pioner/back/modes.py:228-236`

**Что:** в iso `voltage_profiles["ch1"]` — это **1 секунда** AO (CONTINUOUS,
повторяется бесконечно). При AI длиной 5с `Uref` колонка содержит первую
секунду + 4с NaN. Это не отражает реальное напряжение, которое подавалось.

**Действие:**
1. Либо вычислять `Uref = np.tile(profile, ceil(N/M))[:N]` (повторение AO
   синхронно с AI clock), что физически корректно.
2. Либо убрать колонку `Uref` для iso, оставить только в finite_scan modes.

**Проверка:** добавить assert в `test_iso_mode_streams_into_dataframe`, что
`Uref` либо отсутствует, либо длиной = `len(df)` без NaN.

### P1-3. `apply_calibration`: мутация raw-frame по месту ломаема

**Где:** `src/pioner/back/modes.py:196, 203, 211`

**Что:** код делает `df[4] = df[4] * (1000.0 / hw.gain_utpl)` — **переписывает
сырую колонку** масштабированной. Затем читает `df[5] - df[0] * 1000.0`.
Зависимость от порядка вызовов хрупкая.

**Действие:** локальные переменные `u_tpl_mv = df[4] * 1000.0 / hw.gain_utpl`
и далее работать с ними. Сырые `df[N]` не трогать. В конце `df.drop` уже
есть и продолжит работать.

**Проверка:** существующие тесты должны пройти. Добавить юнит-тест, который
проверяет что после `apply_calibration` колонки `0..5` не были модифицированы
до этапа drop.

### P1-4. Молчаливое clipping модуляции к `safe_voltage`

**Где:** `src/pioner/back/modes.py:380-385, 487-488`

**Что:** `np.clip(profile, 0, safe_voltage, out=...)` без warning. Если
пользователь задал `Amplitude = 2V` поверх `DC = 8.5V` при `safe = 9V`, то
половина периода молча обрежется → синусоида превратится в трапецию,
lock-in выдаст неправильную амплитуду.

**Действие:** до clipping проверять `if (max(profile) > safe or min(profile) < 0):
logger.warning("Modulation clipped: peak=%s, safe=%s")`. Опционально —
`raise ValueError` если `peak > safe + 10%`.

**Проверка:** unit-тест с профилем за пределы safe → ожидать предупреждение.

### P1-5. `legacy IsoMode.run(do_ai=False)` теряет «hold voltage forever»

**Где:** `src/pioner/back/iso_mode.py:91-102`

**Что:** старый GUI-сценарий «Set 0.5V и держать пока не нажмут Off» —
сейчас `_mode.run(duration_seconds=0.0)` стартует AO + start_ring_buffer +
sleep(0) + stop. Напряжение уходит сразу.

**Действие:** в legacy facade при `do_ai=False` использовать `em.ao_set(ch, V)`
напрямую без `start_ring_buffer / stop`, и хранить EM в self до явного
`ai_stop()`. Метод `ai_stop` сейчас pass — должен звать `em.stop()`.

**Проверка:** интеграционный тест: `IsoMode(...).run(do_ai=False)` →
читаем `_shared.iso_voltages` через mock → видим заданное напряжение.
Затем `ai_stop()` → видим, что `_shared.iso_voltages` сброшен.

### P1-6. Mode-state в Tango: `select_mode` + `arm` рассогласованы

**Где:** `src/pioner/back/nanocontrol_tango.py:179-198`

**Что:** `select_mode` хранит `self._mode_name`, но реально что-то делает
только `arm()`. Если пользователь вызвал `select_mode("slow"); arm(...)` —
работает; если просто `arm(...)` — берётся прошлый mode_name. Не устойчиво.

**Действие:** один command `arm(name, programs_json)`. Старые
`select_mode` + `arm(programs_json)` оставить как deprecated алиасы.
Альтернатива — сделать `select_mode` обязательно вызываемым перед `arm`
(raise `RuntimeError` если не выбран).

### P1-7. `MODULATION_CHANNEL` дефолт жёстко = `"ch1"`

**Где:** `src/pioner/back/modes.py:357-363, 441-442, 461`,
`src/pioner/back/iso_mode.py:65, 75`,
`src/pioner/back/slow_mode.py:36`

**Что:** в нескольких местах строка `"ch1"` зашита как modulation_channel.
Если пользователь поменяет AO-маппинг (heater на ch2), все по умолчанию
сломается.

**Действие:** вынести `HEATER_CHANNEL_KEY = "ch1"` в `pioner.shared.constants`,
ссылаться на него везде. Документировать как «канал нагрева; менять
синхронно с проводкой».

### P1-8. Async-старт AI без проверки RUNNING в `start_ring_buffer`

**Где:** `src/pioner/back/experiment_manager.py:240-254`

**Что:** `ai_handler.scan(...)` возвращает rate, но не подтверждает что scan
реально запустился. Worker-поток сразу видит `ScanStatus != RUNNING` и
выходит. `snapshot_ring_buffer()` отдаёт пустой массив без объяснений.

**Действие:** после `ai_handler.scan(...)` ждать до 100мс пока
`get_scan_status()[0] == RUNNING`, иначе `raise RuntimeError("AI failed to
start")`.

**Проверка:** mock-тест: подменить `MockAiDevice.a_in_scan` чтобы он не
запускал worker, ожидать exception.

### P1-9. `scipy.signal.sosfiltfilt` transient на краях ловит lock-in

**Где:** `src/pioner/shared/modulation.py:153-165`

**Что:** filtfilt — zero-phase, но переходные ~10 периодов модуляции на
каждом крае. Test уже это маскирует через `slice(2000, -2000)`. Для
коротких scan (<0.5с при 37.5Hz) — это >50% сигнала.

**Действие:** возвращать вместе с `(amp, phase)` маску `valid` (boolean) с
`False` в transient-зонах. Документировать минимальную длину сигнала
(`>= 20 / frequency` секунд).

**Проверка:** unit-test: lockin на сигнале 0.3с при 37.5Hz должен возвращать
маску с >=80% False.

### P1-10. `AiDeviceHandler.__init__` мутирует общий `AiParams`

**Где:** `src/pioner/back/ai_device.py:59-60`

**Что:** если SINGLE_ENDED не поддерживается, переключаемся на DIFFERENTIAL.
Но это меняет `params.input_mode` на самом объекте, который может быть
shared между двумя handler-ами. Тонкий side-effect.

**Действие:** делать `self._params = copy.copy(params)` в конструкторе, либо
выставлять `self._input_mode_override` как локальное поле, не трогая params.

### P1-11. `BackSettings.parse_*` mixed-validation: half immediate / half deferred

**Где:** `src/pioner/shared/settings.py:104-243`

**Что:** `is_int_or_raise` в одних местах raises immediately, а
`_invalid_fields` собирает ошибки для batch-raise. Пользователь либо видит
первую ошибку, либо все.

**Действие:** унифицировать на batch-collect (вернуть `(value, ok)` из
helper, не raise) — пользователь увидит все проблемы одной строкой.

### P1-12. `ScanDataGenerator` молча zero-fill отсутствующих каналов

**Где:** `src/pioner/back/ao_data_generators.py:60-69`

**Что:** если пользователь забыл указать ch3 в profiles, генератор
заполнит его нулями. Для guard-канала это OK, для случайно пропущенного —
данные молча не подаются.

**Действие:** `logger.info("AO ch%d not provided, holding at 0V", ch)` для
каждого пропущенного канала.

### P1-13. `_collect_finite_ai` busy-poll @ 1ms

**Где:** `src/pioner/back/experiment_manager.py:357`

**Что:** `time.sleep(0.001)` × тысячи итераций = 100% одного ядра CPU и
~1мс jitter в обнаружении half-buffer flip.

**Действие:** заменить на `time.sleep(half_buf_len / sample_rate / 4)` —
просыпаться в 4× от частоты flip-events. Альтернатива — driver event если
uldaq поддерживает.

### P1-14. `mock_uldaq._fill_loop` чистый Python, медленный

**Где:** `src/pioner/back/mock_uldaq.py:320-353`

**Что:** для каждого сэмпла отдельный math.sin вызов. На 60-секундном
прогоне 20kHz × 6ch = 7.2M итераций. ~3с CPU.

**Действие:** буферизовать `chunk_samples` через numpy: `np.sin(omega * t_arr)`
+ broadcasting на каналы. Записывать в `buf[base:base+n_chans*chunk] = result.tolist()`
одним вызовом.

**Проверка:** существующий `test_ai_scan_progresses_and_stops` остаётся
зелёным; добавить benchmark `pytest-benchmark` (опц.).

### P1-15. `mock_uldaq._synthesise_sample` вносит когерентный «шум» 196 Hz

**Где:** `src/pioner/back/mock_uldaq.py:362`

**Что:** `math.sin(t * 1234.5 + channel) * 0.5e-3` — детерминирован, что
хорошо для тестов, но это **чистый тон ~196 Hz**, который виден в lock-in
анализе и спектре. Может ввести в заблуждение при отладке.

**Действие:** заменить на `np.random.default_rng(seed=hash(channel))`
гауссовский шум того же RMS. Сделать seed-able через переменную
окружения `PIONER_MOCK_NOISE_SEED`.

### P1-16. Calibration: `Calibration.read` форматные ошибки малоинформативны

**Где:** `src/pioner/shared/calibration.py:177-209`

**Что:** прямой индексинг `coeffs[U_TPL_FIELD]["0"]` — KeyError без
контекста. Если в файле опечатка, юзер получает `KeyError: 'Utpl'`.

**Действие:** обернуть весь блок в `try/except KeyError as exc: raise
ValueError(f"Missing field {exc} in calibration file {path}")`.

---

## P2 — code quality / dx

### P2-1. `pyproject.toml`: убрать неиспользуемые runtime-зависимости

**Где:** `pyproject.toml:25-34`

**Что:** проверить grep — `matplotlib`, `requests`, `sortedcontainers` не
импортируются нигде в `src/`. `tables` нужен только для `_prime_pandas`,
который уже отказоустойчив.

**Действие:** перенести в `optional-dependencies`:
- `matplotlib` → удалить (или в `dev`).
- `requests` → `gui` (нужен фронту).
- `sortedcontainers` → удалить.
- `tables` → `optional-dependencies.hdf5`.

**Проверка:** `pip install ppioner[hardware]` без перечисленных зависимостей
запускает `python -m pioner.back.debug` без ошибок.

### P2-2. Опечатка `(former Nanocal)` → `(formerly Nanocal)`

**Где:** `pyproject.toml:11`, возможно `README.md`.

### P2-3. `pyproject.toml`: добавить console_script для Tango-сервера

**Где:** `pyproject.toml:46-47`

**Действие:** добавить `pioner-tango = "pioner.back.nanocontrol_tango:NanoControl.run_server"`
(или подобный). Сейчас сервер запускается только `python -m`.

### P2-4. Логирование: единая точка конфигурации

**Где:** `nanocontrol_tango.py`, `debug.py`, тесты не настраивают

**Действие:** создать `pioner/logging_setup.py` с функцией
`configure(level=INFO, file=None)`. Вызывать из CLI/Tango entry points.
Тесты — пропускать (pytest сам капчурит).

### P2-5. Конфликт стилей type hints

**Где:** разные файлы: одни с `from __future__ import annotations` и
`X | None`, другие с `Optional[X]`.

**Действие:** один проход `ruff format` + явная стиль-гайд в
`AGENTS.md` / `pyproject.toml [tool.ruff]`. PEP 604 (`X | None`) +
`from __future__ import annotations` везде.

### P2-6. `BackSettings.get_str` собирает str через `dict→str→replace`

**Где:** `src/pioner/shared/settings.py:245-252`

**Действие:** `json.dumps({"DAQ": vars(self.daq_params), ...})`. Также
`AiParams/AoParams.__str__` — заменить на `to_dict()`.

### P2-7. `is_int_or_raise` название vs поведение

**Где:** `src/pioner/shared/utils.py:37-41`

**Действие:** переименовать в `validate_int(value, *, name="value")` или
просто `_check_int`. Сохранить старое имя как алиас на одну версию.

### P2-8. Дубликаты HDF5-сохранения в legacy facades

**Где:** `src/pioner/back/fastheat.py:86-107`,
`src/pioner/back/slow_mode.py:65-95`

**Что:** `_save_data` и `_add_info_to_file` практически идентичны.

**Действие:** вытянуть в `pioner.back.hdf5_export` модуль с одной функцией
`save_experiment(df, calibration, settings, programs, voltage_profiles, path)`.

### P2-9. `iso_mode.IsoMode` не сохраняет результат на диск

**Где:** `src/pioner/back/iso_mode.py`

**Что:** асимметрия: fast/slow → exp_data.h5; iso → ничего.

**Действие:** после `P2-8` использовать общий экспортер во всех трёх режимах.
Имя файла можно префиксить mode_name.

### P2-10. Удалить `FAST_HEAT_CUSTOM_FLAG` или реализовать

**Где:** `src/pioner/back/fastheat.py:55-68`

**Что:** параметр принимается, сохраняется, но никогда не читается.

**Действие:** либо реализовать (skip apply_calibration → сырой df), либо
удалить из публичного API.

### P2-11. `AiDeviceHandler` test coverage

**Где:** `tests/test_mock_uldaq.py` есть, но `AiDeviceHandler` напрямую не
тестируется.

**Действие:** добавить `tests/test_ai_device.py`:
- buffer re-allocation при изменении samples_per_channel
- `scan()` без allocate_buffer → ValueError
- INPUT_MODE fallback к DIFFERENTIAL

### P2-12. Legacy `fastheat.FastHeat` / `slow_mode.SlowMode` без тестов

**Где:** `tests/test_modes_e2e.py` тестирует только `pioner.back.modes`.
Tango использует именно legacy-обёртки.

**Действие:** `tests/test_legacy_facades.py`: запустить fast/slow через
legacy class, проверить что HDF5 файл создан с ожидаемой структурой.

### P2-13. Половина «1-секунд буфер»: прямые юнит-тесты

**Где:** `tests/test_experiment_manager.py` отсутствует

**Действие:** запустить `_collect_finite_ai` на mock с детерминированным
синтез-буфером (linear ramp 0..N), проверить что после 5с прогона все N×5
сэмплов на месте, нет дублей и пропусков.

### P2-14. Тест round-trip `Calibration.get_str → json.loads → fields`

**Где:** `tests/test_calibration.py`

**Действие:** проверить что front-end видит все нужные поля
(`utpl0, ttpl0, ..., hardware.gain_utpl`).

### P2-15. `tests/conftest.py`: убрать sys.path хак

**Где:** `tests/conftest.py:11-12`

**Что:** `sys.path.insert(0, ...)` дублируется с
`pyproject.toml [tool.pytest.ini_options].pythonpath = ["src"]`.

**Действие:** удалить sys.path-манипуляцию, проверить что pytest всё ещё
находит модули.

### P2-16. `parse_modulation` лишний `import` внутри функции

**Где:** `src/pioner/shared/settings.py:114`

**Что:** комментарий «avoid cycle», но реального цикла нет.

**Действие:** перенести `from pioner.shared.modulation import ModulationParams`
наверх файла.

### P2-17. `IsoMode._build_profiles` без модуляции возвращает 1-точечный профиль

**Где:** `src/pioner/back/modes.py:472-476`

**Что:** `{ch: np.array([prog.values[0]])}` — выглядит как полный профиль,
но это одна точка. Любой код, читающий `voltage_profiles`, сломается.

**Действие:** либо вернуть полную линию длиной `n = sample_rate`, либо
**не возвращать profile вообще** для DC-only (сделать отдельную ветку
`_dc_voltages: Dict[str, float]` и проверять её в `run()`).

### P2-18. `ChannelProgram` не ловит NaN/Inf

**Где:** `src/pioner/back/modes.py:79-94`

**Действие:** добавить `if not np.all(np.isfinite(values)): raise
ValueError("program values contain NaN/Inf")`.

### P2-19. `temperature_to_voltage` rounding 4 знака → 0.1мВ

**Где:** `src/pioner/shared/utils.py:118`

**Что:** `np.round(volt_calib[idx], 4)`. На 16-битном DAC ±10V LSB ≈
0.305мВ. Округление до 0.1мВ — это ниже DAC resolution, но округление
теряет sub-LSB точность.

**Действие:** убрать `np.round` (DAC сам квантует) или сделать резолюцию
параметром.

### P2-20. `Calibration.write` пишет блок `Hardware` всегда

**Где:** `src/pioner/shared/calibration.py:262-266`

**Что:** даже когда юзер не трогал hardware, в файл попадают defaults.
Это OK, но если добавим новое поле в HardwareCalibration, старые файлы
получат его при первом write.

**Действие:** ничего не делать, либо явно фиксировать «calibration files
auto-upgraded on save».

---

## P3 — документация / observability

### P3-1. Документировать размерности в `apply_calibration`

См. `P0-3`. Доктрина: каждая числовая операция помечена комментарием
(`# input: V, output: mV`).

### P3-2. README ссылается на spec.md

**Где:** `README.md`

**Действие:** добавить раздел «Pipeline overview» с одной фразой и линком
на `spec.md`.

### P3-3. Sphinx autodoc обновить под текущую структуру

**Где:** `docs/source/python_api.rst`

**Действие:** проверить, что добавлены `pioner.back.modes`, `pioner.shared.modulation`,
`pioner.back.mock_uldaq`. (По истории изменения уже сделаны, но надо удостовериться
что doc билд не падает: `cd docs && make html`.)

### P3-4. Docstrings на public API

**Где:** `DaqDeviceHandler.get`, `Calibration.write`, `IsoMode.ai_stop`,
`AiParams/AoParams.channel_count` — пустые/тривиальные.

**Действие:** одна-две строки в каждом, с примером где уместно.

### P3-5. `spec.md` обновить под P0/P1 фиксы

**Где:** `spec.md`

**Что:** после реализации P0-1..P0-6 убрать соответствующие пункты из
«Outstanding TODO»; обновить раздел «AO/AI pipeline» если изменили
Uref/clip-warnings.

### P3-6. Пример скрипта для bench-эксперимента

**Где:** новая папка `examples/`

**Действие:** скрипт `examples/run_slow_with_modulation.py`, который
явно настраивает программу, модуляцию, запускает SlowMode и сохраняет
HDF5 + plot. Полезно для онбординга новых пользователей.

### P3-7. Замечание о stderr-noise: модуль mock_uldaq логирует в INFO

**Где:** `src/pioner/back/mock_uldaq.py:50`

**Действие:** уровень DEBUG (один раз на процесс), либо warning только если
явно `PIONER_DEBUG=1`. Сейчас на каждый `import` тест выдаёт строку.

---

## Порядок выполнения (рекомендация)

1. **P0-1** — это правка одной строки, но делает Tango сервер вообще
   функциональным с правильной директорией.
2. **P0-2 + P0-3** — оба требуют разговора с Алексеем (физик); сделать
   первой связкой, чтобы потом не переписывать тесты.
3. **P0-5 + P0-6** — связаны (длительность буфера ⇄ trigger). Делать вместе.
4. **P0-4** — после интеграционного теста по фронту.
5. **P1-1..P1-5** — критичные UX/архитектура, **независимы**, можно
   параллелить.
6. **P1-6..P1-16** — постепенно, по два-три за раз.
7. **P2-всё** — после P0/P1, целиком как «code quality round».
8. **P3-всё** — последним, или вшить мелочи в каждый PR из P0/P1.

## Примечания

- При каждом изменении гонять `PYTHONPATH=src .venv/bin/pytest -q` (≤10s).
- Не трогать GUI (`front/`) пока не закроем P0/P1 в back/.
- Перед продакшен-запуском **обязательно** прогнать на реальном железе:
  fast 1с (rampe), slow 2с с модуляцией, iso 10с с модуляцией. Сравнить
  с эталонными данными прошлых экспериментов.
