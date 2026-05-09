# PIONER — пошаговый план работ (non-front)

Файл — сжатый, **исполнимый по очереди** список открытых задач. Каждый пункт
самодостаточен (что сделать, где, почему, как проверить). **P0** делать
первыми, **P3** — мелочи.

Ссылки на файлы — формат `path/to/file.py:line` или `path/to/file.py`.
Тесты: `PYTHONPATH=src .venv/bin/pytest -q`.

## Состояние сейчас

- Полный pytest: **33 passed** (включая 6 новых юнит-тестов на
  `apply_calibration`). 3 итерации валидации back-кода.
- Все «не запустится» баги закрыты, остались архитектурные шероховатости
  и физические уточнения.
- Полная картина пайплайна — в `spec.md`.

## Сделано в последнем проходе (8 мая 2026)

- ✅ FIX A — `apply_calibration`: `Uref` тилится по AI-длине, корректно для
  iso (CONTINUOUS AO) и DC. Тесты:
  `tests/test_apply_calibration.py::test_uref_is_tiled_*`.
- ✅ FIX B — `apply_calibration`: `Thtr` теперь NaN, когда ток нагревателя
  ≈ 0 (а не призрачные −1070 °C). Тест:
  `test_thtr_is_nan_when_heater_current_is_zero`.
- ✅ FIX C — `_collect_finite_ai` / `_ring_loop`: `half_buf_len` выводится
  из `half_per_channel * n_ai_chans` (был `len(buf) // 2` — ломалось при
  не-кратных размерах).
- ✅ FIX D — `_program_to_voltage`: warning при `peak |V| > safe_voltage`
  для сырых `volt`-программ (для `temp` уже клип в
  `temperature_to_voltage`).
- ✅ P0-1 — `nanocontrol_tango`: пути к calibration.json через
  `*_REL_PATH` (предыдущий коммит).

## Отменено / явно не делать

- ❌ **P0-2** (rename `Uref → Uheater`): пользователь сказал «эти все U…
  не трогаем». Колонка остаётся `Uref`, документировать смысл в `spec.md`.
- ❌ **P1-7** (вынести `HEATER_CHANNEL_KEY` в constants): не менять
  hardcoded имена. `"ch1"` остаётся литералом.
- 💤 **P0-6** (1-секундный буфер ⇒ `total_ms % 1000 == 0`): принят как
  software constraint до отдельной задачи. Не трогать сейчас.

---

## P0 — критические корректность-баги (открытые)

### P0-3. `apply_calibration`: размерности Ihtr/Uhtr нужно валидировать с физиком

**Где:** `src/pioner/back/modes.py:209-227`

**Что:** `ih = ihtr0 + ihtr1 * df[0]` использует канал 0 как сырое
напряжение на shunt-резисторе (V), а далее идёт в формулу `Rhtr =
... / ih` как ток. С дефолтной калибровкой `ihtr1 = 1.0` это
безразмерное «1 V» — `Rhtr` оказывается в [Ом·V/A], не в Омах.
В production-калибровке скорее всего `ihtr1 = 1/Rshunt ≈ 1/1700`, но
явных тестов на это нет.

**Действие:**
1. Уточнить у Алексея: какой физический смысл у `ihtr1` в production?
   Если действительно `1/Rshunt` — в production-`calibration.json`
   должно стоять `≈5.88e-4`.
2. Добавить в `apply_calibration` явные комментарии о размерностях
   каждой величины (`# ih: amperes`, `# df[5]: millivolts`).
3. Юнит-тест: подать синтетический `V_shunt = 1mA × 1700Ω = 1.7V` и
   `V_heater_raw = ...`, проверить, что `Rhtr ≈ 1700 Ω` при
   правильно настроенной калибровке.

**Не менять** дефолтную калибровку (identity) — она нужна для тестов.

### P0-5. `ExperimentManager`: AI стартует перед AO ⇒ leading-edge skew

**Где:** `src/pioner/back/experiment_manager.py:179-194` (TODO inline)

**Что:** AI запускается на ~100мкс раньше AO; для fast-режима 1000 K/s
это ≤ 1 °C на первом образце. Решается только hardware-тригерами
(`RETRIGGER + EXTTRIGGER`) на реальном железе.

**Действие:** при апгрейде до production-DAQ — настроить общий
trigger source и перевести AO/AI на него. Альтернатива (workaround):
помечать первые N сэмплов как `pre_trigger=True` и обрезать в
`apply_calibration`.

**Проверка:** на реальном железе — генератор 1кГц на AO ch1 → читать
обратно с AI ch1, скейл смещения должен быть < 1 сэмпла.

---

## P1 — важные архитектурные / логические улучшения

### P1-1. `IsoMode.run`: нет `stop()` API для длинных прогонов

**Где:** `src/pioner/back/modes.py:492-547`, `src/pioner/back/iso_mode.py`
(уже есть `TODO(global)`).

**Что:** для iso 30+ минут единственный способ остановить — ждать
`time.sleep(duration)` или убить процесс.

**Действие:** добавить `threading.Event` (или `stop()`) на `IsoMode`,
прокинуть в Tango (`@command def stop_iso(self)`), цикл ожидания
заменить на `event.wait(duration)`.

**Проверка:** запустить iso в фоновом потоке на `duration=10`, через
0.5с вызвать `stop()`, убедиться что `run()` вернулся за <1с.

### P1-3. `apply_calibration`: мутация raw-frame по месту хрупка

**Где:** `src/pioner/back/modes.py:195-225`

**Что:** код делает `df[4] = df[4] * (1000.0 / hw.gain_utpl)` — пишет
в сырую колонку. Затем читает `df[5] - df[0] * 1000.0`. Зависимо от
порядка вызовов; если кто-то поменяет порядок blocks — silent bug.

**Действие:** ввести локальные переменные `u_tpl_mv = df[4] * 1000.0 /
hw.gain_utpl`, не трогать сырые `df[N]`. Финальный `df.drop` уже есть
и продолжит работать.

**Проверка:** существующие 33 теста + новый юнит-тест, что raw-колонки
до `drop` не модифицируются.

### P1-4. Молчаливое clipping модуляции к `safe_voltage`

**Где:** `src/pioner/back/modes.py:380-385, 487-488`

**Что:** `np.clip(profile, 0, safe_voltage, out=...)` без warning.
Если пользователь задал `Amplitude = 2V` поверх `DC = 8.5V` при
`safe = 9V`, половина периода молча обрежется → синусоида превратится
в трапецию, lock-in выдаст неправильную амплитуду.

**Действие:** до clipping проверить `peak/min` и `logger.warning` если
выходим за safe-envelope. (Аналог FIX D, но для модулированных
профилей.)

**Проверка:** unit-тест с профилем за пределы safe → ожидать запись в
лог.

### P1-5. `legacy IsoMode.run(do_ai=False)` теряет «hold voltage forever»

**Где:** `src/pioner/back/iso_mode.py:91-102`

**Что:** старый GUI-сценарий «Set 0.5V и держать пока не нажмут Off»
сейчас стартует AO + start_ring_buffer + sleep(0) + stop. Напряжение
уходит сразу же. **Tango-путь не использует** этот режим (он идёт
через `_IsoMode`), но прямой Python-скрипт пользователя ломается.

**Действие:** при `do_ai=False` в legacy facade использовать
`em.ao_set(ch, V)` без `start_ring_buffer / stop`, хранить EM в self
до явного `ai_stop()`. Метод `ai_stop` сейчас pass — должен звать
`em.stop()`.

**Проверка:** интеграционный тест: `IsoMode(...).run(do_ai=False)` →
читаем `_shared.iso_voltages` через mock → видим заданное напряжение.
Затем `ai_stop()` → видим, что `iso_voltages` сброшен.

### P1-6. Mode-state в Tango: `select_mode` + `arm` рассогласованы

**Где:** `src/pioner/back/nanocontrol_tango.py:183-203`

**Что:** `select_mode` хранит `self._mode_name`, но реально что-то
делает только `arm()`. Если пользователь забыл `select_mode` —
берётся прошлое значение. Не fail-loud.

**Действие:** новый `arm(name, programs_json)` — single command. Старые
`select_mode` + `arm(programs_json)` оставить как deprecated алиасы.

### P1-8. AI-start без проверки RUNNING в `start_ring_buffer`

**Где:** `src/pioner/back/experiment_manager.py:240-254`

**Что:** `ai_handler.scan(...)` возвращает rate, но не подтверждает,
что scan реально запустился. Worker-поток сразу видит `ScanStatus !=
RUNNING` и тихо выходит. `snapshot_ring_buffer()` отдаёт пустой
массив без объяснений.

**Действие:** после `ai_handler.scan(...)` ждать ≤ 100мс пока
`get_scan_status()[0] == RUNNING`, иначе `raise RuntimeError`.

### P1-9. Lock-in: scipy `sosfiltfilt` transient на краях

**Где:** `src/pioner/shared/modulation.py:153-165`

**Что:** filtfilt — zero-phase, но переходные ~10 периодов модуляции
на каждом крае. Тест уже это маскирует через `slice(2000, -2000)`.
Для коротких scan (<0.5с при 37.5Hz) — это >50% сигнала.

**Действие:** возвращать вместе с `(amp, phase)` маску `valid`
(boolean) с `False` в transient-зонах. Документировать минимальную
длину сигнала (`>= 20 / frequency` секунд).

**Проверка:** unit-test: lockin на сигнале 0.3с при 37.5Hz должен
возвращать маску с >=80% False по краям.

### P1-10. `AiDeviceHandler.__init__` мутирует общий `AiParams`

**Где:** `src/pioner/back/ai_device.py:59-60`

**Что:** если SINGLE_ENDED не поддерживается, переключаемся на
DIFFERENTIAL. Это меняет `params.input_mode` на самом объекте, который
может быть shared между двумя handler-ами.

**Действие:** `self._params = copy.copy(params)` в конструкторе, либо
ввести `self._input_mode_override` локально.

### P1-11. `BackSettings.parse_*`: смешанная валидация (immediate vs deferred)

**Где:** `src/pioner/shared/settings.py:104-243`

**Действие:** унифицировать на batch-collect (helper возвращает
`(value, ok)`, не raise) — пользователь увидит все проблемы одной
строкой.

### P1-12. `ScanDataGenerator` молча zero-fill отсутствующих каналов

**Где:** `src/pioner/back/ao_data_generators.py:60-69`

**Действие:** `logger.info("AO ch%d not provided, holding at 0V", ch)`.

### P1-13. `_collect_finite_ai` busy-poll @ 1ms

**Где:** `src/pioner/back/experiment_manager.py:357`

**Что:** `time.sleep(0.001)` × тысячи итераций = 100% одного ядра CPU
на Raspberry Pi.

**Действие:** заменить на `time.sleep(half_per_channel / sample_rate
/ 4)` — просыпаться в 4× от частоты flip-events. На 20kHz это ~125мс.
Альтернатива — driver event если uldaq поддерживает.

### P1-14. `mock_uldaq._fill_loop` чистый Python, медленный

**Где:** `src/pioner/back/mock_uldaq.py:320-353`

**Что:** для каждого сэмпла отдельный `math.sin` вызов. На 60-секундном
прогоне 20kHz × 6ch = 7.2M итераций ⇒ ~3с CPU.

**Действие:** буферизовать `chunk_samples` через numpy:
`np.sin(omega * t_arr)` + broadcasting на каналы. Записывать в
`buf[base:base+n_chans*chunk] = result.tolist()` одним вызовом.

### P1-15. `mock_uldaq._synthesise_sample` — когерентный «шум» 196 Hz

**Где:** `src/pioner/back/mock_uldaq.py:362`

**Что:** `math.sin(t * 1234.5 + channel) * 0.5e-3` — детерминирован,
что хорошо для тестов, но это **чистый тон ~196 Hz**, виден в lock-in
и спектре. Может ввести в заблуждение при отладке.

**Действие:** заменить на `np.random.default_rng(seed=hash(channel))`
гауссовский шум того же RMS. Сделать seed-able через переменную
окружения `PIONER_MOCK_NOISE_SEED`.

### P1-16. `Calibration.read` форматные ошибки малоинформативны

**Где:** `src/pioner/shared/calibration.py:177-209`

**Что:** прямой индексинг `coeffs[U_TPL_FIELD]["0"]` — `KeyError`
без контекста.

**Действие:** обернуть блок в `try/except KeyError as exc: raise
ValueError(f"Missing field {exc} in calibration file {path}")`.

---

## P2 — code quality / dx

### P2-1. `pyproject.toml`: убрать неиспользуемые runtime-зависимости

**Где:** `pyproject.toml:25-34`

**Что:** `matplotlib`, `requests`, `sortedcontainers` не импортируются
в `src/`. `tables` нужен только для `_prime_pandas` (отказоустойчиво).

**Действие:** перенести в `optional-dependencies`:
- `matplotlib` → `dev`.
- `requests` → `gui`.
- `sortedcontainers` → удалить.
- `tables` → `optional-dependencies.hdf5`.

### P2-2. Опечатка `(former Nanocal)` → `(formerly Nanocal)`

**Где:** `pyproject.toml:11`, возможно `README.md`.

### P2-3. `pyproject.toml`: добавить console_script для Tango-сервера

**Действие:** `pioner-tango = "pioner.back.nanocontrol_tango:NanoControl.run_server"`.

### P2-4. Логирование: единая точка конфигурации

**Действие:** `pioner/logging_setup.py` с `configure(level=INFO,
file=None)`. Вызывать из CLI/Tango entry points.

### P2-5. Конфликт стилей type hints

**Действие:** `ruff format` + явная стиль-гайд. PEP 604 (`X | None`)
+ `from __future__ import annotations` везде.

### P2-6. `BackSettings.get_str` собирает str через `dict→str→replace`

**Действие:** `json.dumps({"DAQ": vars(self.daq_params), ...})`.

### P2-7. `is_int_or_raise` название vs поведение

**Действие:** переименовать в `validate_int(value, *, name="value")`.
Сохранить старое имя как алиас.

### P2-8. Дубликаты HDF5-сохранения в legacy facades

**Где:** `src/pioner/back/fastheat.py:86-107`,
`src/pioner/back/slow_mode.py:65-95`

**Действие:** вытянуть в `pioner.back.hdf5_export.save_experiment(...)`.

### P2-9. `iso_mode.IsoMode` не сохраняет результат на диск

**Где:** `src/pioner/back/iso_mode.py`

**Что:** асимметрия: fast/slow → exp_data.h5; iso → ничего.

**Действие:** после `P2-8` использовать общий экспортер во всех трёх
режимах.

### P2-10. Удалить `FAST_HEAT_CUSTOM_FLAG` или реализовать

**Где:** `src/pioner/back/fastheat.py:55-68`

**Что:** параметр принимается, сохраняется, но не читается.

### P2-11. `AiDeviceHandler` test coverage

**Действие:** `tests/test_ai_device.py`:
- buffer re-allocation при изменении samples_per_channel
- `scan()` без allocate_buffer → ValueError
- INPUT_MODE fallback к DIFFERENTIAL

### P2-12. Legacy `fastheat.FastHeat` / `slow_mode.SlowMode` без тестов

**Действие:** `tests/test_legacy_facades.py`: запустить fast/slow
через legacy class, проверить что HDF5 файл создан с ожидаемой
структурой.

### P2-13. `_collect_finite_ai`: прямой юнит-тест half-buffer flip

**Действие:** запустить `_collect_finite_ai` на mock с детерминированным
синтез-буфером (linear ramp 0..N), проверить что после 5с прогона все
N×5 сэмплов на месте, нет дублей и пропусков.

### P2-14. Тест round-trip `Calibration.get_str → json.loads → fields`

### P2-15. `tests/conftest.py`: убрать sys.path хак

**Где:** `tests/conftest.py:11-12`

**Что:** дублирует `pyproject.toml [tool.pytest.ini_options].pythonpath
= ["src"]`.

### P2-16. `parse_modulation` лишний `import` внутри функции

**Где:** `src/pioner/shared/settings.py:114`

**Действие:** перенести `from pioner.shared.modulation import
ModulationParams` наверх файла.

### P2-17. `IsoMode._build_profiles` без модуляции возвращает 1-точечный профиль

**Где:** `src/pioner/back/modes.py:472-476`

**Что:** `{ch: np.array([prog.values[0]])}` — одна точка. Любой код,
читающий `voltage_profiles` без знания о DC-iso, удивится. (FIX A
теперь корректно тилит до AI-длины — разрулил для `apply_calibration`,
но проблема в типе данных остаётся.)

**Действие:** либо вернуть полную линию длиной `n = sample_rate`, либо
**не возвращать profile вообще** для DC-only (отдельная ветка
`_dc_voltages: Dict[str, float]` и проверять её в `run()`).

### P2-18. `ChannelProgram` не ловит NaN/Inf

**Где:** `src/pioner/back/modes.py:79-94`

**Действие:** `if not np.all(np.isfinite(values)): raise
ValueError("program values contain NaN/Inf")`.

### P2-19. `temperature_to_voltage` rounding 4 знака → 0.1мВ

**Где:** `src/pioner/shared/utils.py:118`

**Что:** `np.round(volt_calib[idx], 4)`. На 16-битном DAC ±10V LSB ≈
0.305мВ — округление ниже разрешения DAC.

**Действие:** убрать `np.round` (DAC сам квантует) или сделать
резолюцию параметром.

---

## P3 — документация / observability

### P3-1. Документировать размерности в `apply_calibration`

См. `P0-3`. Доктрина: каждая числовая операция помечена комментарием
(`# input: V, output: mV`).

### P3-2. README ссылается на spec.md

**Действие:** добавить раздел «Pipeline overview» с одной фразой и
линком на `spec.md`.

### P3-3. Sphinx autodoc обновить под текущую структуру

**Действие:** `cd docs && make html` — проверить что не падает.

### P3-4. Docstrings на public API

**Где:** `DaqDeviceHandler.get`, `Calibration.write`,
`IsoMode.ai_stop`, `AiParams/AoParams.channel_count` — пустые.

### P3-5. `spec.md` обновить под последние фиксы

**Где:** `spec.md`, секции «Outstanding TODO» и «AI half-buffer».

### P3-6. Пример скрипта для bench-эксперимента

**Действие:** `examples/run_slow_with_modulation.py` — настройка
программы, модуляции, запуск SlowMode, сохранение HDF5 + plot.

### P3-7. Mock_uldaq логирует в INFO на каждом импорте

**Где:** `src/pioner/back/mock_uldaq.py:50`

**Действие:** уровень DEBUG (один раз на процесс), либо warning только
если явно `PIONER_DEBUG=1`.

---

## Порядок выполнения (рекомендация)

1. **P0-3** — требует разговора с физиком; до этого не двигать
   калибровочные коэффициенты.
2. **P0-5** — на реальном железе, при апгрейде trigger.
3. **P1-1, P1-3, P1-4, P1-5** — параллельно, независимы.
4. **P1-6..P1-16** — по два-три за раз.
5. **P2-всё** — после P0/P1 как «code quality round».
6. **P3-всё** — последним, или вшить в каждый PR из P0/P1.

## Примечания

- При каждом изменении гонять `PYTHONPATH=src .venv/bin/pytest -q`
  (≤10s).
- Не трогать GUI (`front/`) пока не закроем P0/P1 в back/.
- **Не менять hardcoded имена/значения** (Uref, ch1, и т. д.) без
  явного запроса пользователя.
- Перед production-запуском **обязательно** прогнать на реальном
  железе: fast 1с (ramp), slow 2с с модуляцией, iso 10с с модуляцией.
  Сравнить с эталонными данными прошлых экспериментов.
