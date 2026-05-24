# Вопросы к разработчику pioner-IR-branch

Документ для согласования перед мерджем фрагментов IR-branch в основную ветку
PIONER. Цель — забрать из IR-branch лучшее (ProfileWidget, калибровочный
визард, per-channel input gains, AOStreamSHGenerator, post_hold для
fast-heat, и так далее — см. [README-IR.md](../README-IR.md) §7) без
переноса спорных мест и не сломав физику.

Ссылки на код даны от корня репозитория. Уровень "блокер" = без ответа на
этот вопрос соответствующий кусок нельзя честно портировать.

---

## A. Аппаратная топология и распиновка — БЛОКЕРЫ

### A1. AO ch0 vs ch1: кто куда физически подключён?

В `start_modulation` ток (mA) кладётся на `low_channel`
([daq_controller.py:222](../pioner-IR-branch/pioner_app/hardware/daq_controller.py#L222)),
то есть на AO ch0. В slow-heat worker AC-модуляция уходит на ch0,
DC-нагревочный ramp — на ch1
([daq_controller.py:599-606](../pioner-IR-branch/pioner_app/hardware/daq_controller.py#L599)).
В нашем mainline `HEATER_AO = "ch1"` — то есть именно ch1 управляет
нагревом.

- Это разница в распиновке железа между ветками, или у IR ch0 — это
  "current command" в одну часть цепи, а ch1 — "voltage command" в другую?
- Если разная распиновка — какой физический провод куда подключён в твоей
  лаборатории сейчас?

### A2. `start_modulation` — что физически идёт на AO?

Формула в коде: `voltage = (current_mA / 1000 - ihtr0) / ihtr1`. При
производственном `ihtr1 ≈ 1/R_shunt` это даёт **напряжение на шунте**,
а не на нагревателе. Но кладётся это на AO наружу.

- Между AO и шунтом стоит транс-импедансник / V→I преобразователь?
- Или мы реально подаём `V_shunt` прямо на heater drive (и тогда смысл
  ihtr1 в этом коде другой)?

Это влияет на единицы во всём `apply_fh_cal` и в формулах для Rhtr.

### A3. `R inner` vs `R guard` в калибровочном визарде

`CalibrationSetupDialog`
([calibration_wizard.py:65-67](../pioner-IR-branch/pioner_app/ui/calibration_wizard.py#L65))
пишет их в `calib.rhtr` и `calib.rghtr` соответственно. Продакшен
`rhtr = 1700 Ohm`, `rghtr = 2300 Ohm`.

- Это guarded design (внутренний нагревательный квадрат + охранное
  кольцо)?
- Если да — где в коде они выводятся на разные AO-каналы или
  рассогласовываются по фазе?
- Или это две разные конфигурации одного и того же провода для разных
  чипов?

---

## B. Процедура калибровки — БЛОКЕРЫ для порта визарда

### B1. Что оператор делает в `CalibrationCursorDialog`?

Это центральный шаг визарда. На графике AO_voltage vs (Thtr / Ttpl /
amplitude) оператор расставляет курсоры на реперные точки.

- Куда конкретно ставит курсор: на температуру плато плавления эталона,
  на точку перегиба, на максимум амплитуды AC отклика?
- Сколько курсоров на одну калибровочную точку (один для T, один для R)?
- Используется ли амплитуда AC отклика как индикатор плавления (рост
  C_p на фазовом переходе → пик в амплитуде)?

### B2. Зачем два независимых voltage-ramp'а (stage 1 и stage 2)?

Параметры одинаковые: 0 → safe_voltage, тот же `rate_per_min`. Stage 1
фитит `Thtr/Thtrd`
([calibration_wizard.py:907](../pioner-IR-branch/pioner_app/ui/calibration_wizard.py#L907)),
stage 2 — `Theater`
([calibration_wizard.py:947](../pioner-IR-branch/pioner_app/ui/calibration_wizard.py#L947)).

- Это нужно для независимой воспроизводимости (вырожденная точка после
  stage 1 не должна испортить stage 2)?
- Или можно один прогон использовать на оба фита, если хранить весь
  датасет?

### B3. Дефолтные калибранты In/Sn/Bi/Pb (156.6 / 231.9 / 271.4 / 327.5 °C)

Список в
[calibration_wizard.py:102-106](../pioner-IR-branch/pioner_app/ui/calibration_wizard.py#L102).

- Это стандарт лаборатории или варьируется по чипам?
- Pb (327.5 °C) выше `safe_voltage * theater` для некоторых чипов —
  оператор сам отрезает строку, или предполагается валидация?
- Есть ли смысл иметь предзаготовленные наборы для разных типов чипов?

### B4. Дефолты `rate_per_min = 0.5 V/min` и `temp_rate_per_min = 15 C/min`

Откуда эти числа? Из физики (тепловое время чипа / время отклика
термопары), или просто "удобно работать"? Чувствительность калибровки
к этим параметрам?

---

## C. Алгоритмы с магическими числами — нужно понять перед портом

### C1. `calcaf_lockin` — это порт чего конкретно?

[basemath.py:48](../pioner-IR-branch/pioner_app/core/basemath.py#L48), плюс
двойные циклы O(period × xperiod) и итеративный fit на 50 итераций.

- `xp = floor(1000 / period)`, capped to [1, 100] — magic 1000 откуда?
- 50 итераций fit, `errfmin = 0.0001`, шаги `0.3` (offset) и `0.5`
  (amplitude) — это коэффициенты Levenberg/Marquardt из конкретного
  источника или произвольные релаксации, подобранные на глаз?
- Это порт C++-кода? Если да — есть ли ссылка на оригинал?
- Сравнивался ли он с простым I/Q + Butterworth (как в нашем
  `lockin_demodulate` в `shared/modulation.py`) на реальных данных? На
  каких сигналах он лучше, на каких — эквивалентен?

### C2. Discrete-step ramps в `AOStreamSHGenerator`

[ao_device.py:347](../pioner-IR-branch/pioner_app/hardware/ao_device.py#L347).
Параметры модуляции (freq / amp / phase) меняются ступенчато
`step_index / (steps - 1)`, а не линейно.

- Это специально (нужны стабильные плато на каждой ступени для FFT в
  каждой точке)?
- Или просто упрощение реализации, и линейная интерполяция была бы лучше?

### C3. Два диапазона `samples_per_period`

В `start_modulation` ([daq_controller.py:213](../pioner-IR-branch/pioner_app/hardware/daq_controller.py#L213))
он `[256, 2048]`. В slow-heat AO worker
([daq_controller.py:514-517](../pioner-IR-branch/pioner_app/hardware/daq_controller.py#L514))
он `[32, 256]`. Один и тот же drive — но в slow-heat потолок в 8 раз
ниже.

Почему? Slow-heat ограничен размером буфера (`max_ao_samples = 8M`), а
modulation-only — нет?

### C4. `analysis_chunk_size` в slow-heat

[daq_controller.py:472-477](../pioner-IR-branch/pioner_app/hardware/daq_controller.py#L472):

```
analysis_chunk_size = max(
    samples_per_period * (periods + 1),
    samples_per_period * 3,
    int(fs * min_point_interval_sec),
)
```

Три нижних ограничения. Какое физически отвечает за что?
`(periods + 1)` — почему +1?

---

## D. Мёртвый / экспериментальный код — нужно знать, что выкидывать

### D1. `Calibration.apply_fh_cal` — две версии

Активный код использует pandas и мутирует входной DataFrame. **Прямо над
ним** в файле, в виде закомментированного блока, лежит numpy-версия того
же расчёта
([calibration.py:283-371](../pioner-IR-branch/pioner_app/core/calibration.py#L283)).

- Старая версия которую заменили, или новая на которую переходишь?
- Какая из них верифицировалась на железе?
- Если активная — почему закомментированный numpy-блок не удалён?

### D2. `Calibration.unpack_data_numpy`

[calibration.py:437](../pioner-IR-branch/pioner_app/core/calibration.py#L437).
Не вызывается нигде, в конце есть unreachable код после `return`.

- Это начатый рефакторинг `apply_fh_cal`, заброшенный?
- Если это набросок — какая идея за ним стояла (новая схема единиц,
  multi-harmonic, что-то ещё)?
- Можно удалять при мердже?

### D3. `Calibration.write` целиком закомментирована

- Это сознательно (визард пишет только в память, файлы редактируются
  руками)?
- Или просто не дошли руки сделать персистенс?
- Планируется ли сохранение результатов визарда обратно в JSON?

---

## E. Операционные константы — нужен rationale для документации

### E1. Autogain пороги 0.92 / 0.12 + 500 ms debounce

[ai_device.py:286-298](../pioner-IR-branch/pioner_app/hardware/ai_device.py#L286).

- Пороги (≥ 0.92·FS → up, ≤ 0.12·FS → down) — из реальных наблюдений на
  каких сигналах?
- 500 ms debounce — на типовой `f_mod = 37.5 Hz` это всего ~19 модуляционных
  периодов, лок-ин может ещё не устояться. Это OK?

### E2. Slow-heat pre-pad нулями + `skip_display_points = 1`

[daq_controller.py:592-594](../pioner-IR-branch/pioner_app/hardware/daq_controller.py#L592).
AO стартует с `zero_samples = min_point_interval * fs` нулей перед
реальной программой, дальше первая аналитическая точка скрывается.

- Это чтобы lock-in увидел baseline до начала ramp'а?
- Или это компенсация AO/AI start-skew (AO успевает выйти в ноль пока
  AI initializes)?
- Или что-то третье?

### E3. AI/AO start order: AI первый, потом AO

В `_run_finite_profile`
([experiment_manager.py:432-434](../pioner-IR-branch/pioner_app/core/experiment_manager.py#L432))
и в slow-heat — везде `ai.start_scan()` перед `ao.start_scan()`.

- Это сознательное решение (AI armed раньше, иначе пропустишь leading
  edge AO)?
- Или унаследовано от legacy?
- Замерял ли ты реальный skew между ними на твоём железе?

---

## F. Тестирование / мок

### F1. `FakeDAQDevice` на уровне controller, не uldaq API

[fake_daq.py](../pioner-IR-branch/pioner_app/hardware/fake_daq.py) мокает
только `read()` и `set_modulation()`. То есть `ai_device.py` / `ao_device.py`
всё равно требуют реальный uldaq для импорта.

- Это сознательно (для UI smoke-test'ов достаточно)?
- Или начало нормального мока, которое не закончилось?
- У нас в mainline есть `mock_uldaq.py` на полном API uldaq (~600 строк).
  Есть ли интерес интегрировать его с IR-архитектурой, чтобы виджеты
  тестировались без железа?

### F2. Тесты

В IR-branch их нет. Это потому что разработка шла вживую с железом и
юнит-тесты не имели смысла до стабилизации, или просто времени не нашлось?

Какие сценарии ты считаешь критичными для regression testing после мерджа?

---

## G. Архитектурные намерения — влияют на выбор live-streaming архитектуры

### G1. `DAQController` как Qt-синглтон с `_instance`

[daq_controller.py:21-31](../pioner-IR-branch/pioner_app/hardware/daq_controller.py#L21).

- Это сделано из-за реального use case "несколько виджетов одновременно
  читают AI"?
- Или просто для удобства "один объект на приложение"?
- Конкретно: в продакшен-сценарии — **есть ли** момент, когда `signals` +
  `values` + `slow_heating` *реально одновременно* подписываются на
  acquisition? Или это потенциальная возможность, не используемая?

Этот ответ напрямую влияет на то, какой архитектурный подход для
live-streaming мы выберем в mainline.

### G2. `owner=` тег в `start_acquisition`

[daq_controller.py:340-351](../pioner-IR-branch/pioner_app/hardware/daq_controller.py#L340).
Каждый виджет берёт acquisition с уникальным тегом, проверяется
ownership на stop.

- Был случай, когда два виджета конфликтовали за AI? Что произошло, как
  это было решено?
- Какие пары owner'ов гарантированно несовместимы, какие — нет?

### G3. Tango-бекенд — заглушка

`TangoHardwareBackend.connect()` всегда поднимает `NotImplementedError`.

- Был план довести до рабочего состояния?
- Если да — какой scope: полная замена ULDAQ (через сетевой DAQ-сервер
  на отдельной машине), или прокси/туннелирование?
- Если нет — можно ли просто удалить заглушку, или ты планируешь её
  заполнить?

---

## H. Конфигурация и единицы

### H1. `config.json: InputMode: 2` — что конкретно ты переключал?

`AiInputMode.SINGLE_ENDED = 2`. В предыдущем обсуждении упоминалось, что
переход на "default" что-то починил (по поводу FIFO overrun на быстрых
нагревах, см. [known-issues.md](../known-issues.md) §1).

Контекст: наша плата MCC USB-2637 поддерживает **только** single-ended
(64 SE-канала, differential отсутствует физически — см.
`specs/USB-2637.pdf`). Соответственно `AiInputMode.DIFFERENTIAL` для
этой платы — невозможный вариант. Получается, "default" в твоей фразе
почти наверняка означало `ScanOption.DEFAULTIO` (scan option), а не
input mode.

Можешь подтвердить, что починка была через смену **scan option** на
`DEFAULTIO`, а не через input mode? Если у тебя в памяти была реально
смена input mode — тогда расскажи, на какой плате это происходило: на
USB-2637 это не могло быть DIFFERENTIAL, значит либо другая железка,
либо другая ось настроек.

### H2. `config.json: Modulation.Amplitude = 0.1`

- В виджете модуляции амплитуда трактуется как **mA** (затем конвертируется
  в V через шунт).
- В mainline `apply_modulation` — это **V**.

Если конфиг используется обеими ветками — какая интерпретация дефолтная?
Поле перегружено? Может быть стоит его переименовать (`amplitude_mA` vs
`amplitude_V`)?

### H3. Файлы калибровки в корне `pioner-IR-branch/`

Список: `Newcalibration_01_04_2026.json`, `Newcalibration_01_04_2026_late.json`,
`Newcalibration_16_04_2026_late.json`, `NONcalibration_01_04_2026.json`,
`maybenormcalibration_01_04_2026.json`, `default_calibration.json`,
`default_calibration1.json`, `experiment_profile copy.json`.

- Какие из них валидны для текущего чипа?
- Какие исторические / экспериментальные?
- Какой должен быть выбран как production reference после мерджа?

---

## Топ-5 ответов, которые разблокируют любой реальный мердж

1. **A1** — AO ch0 vs ch1: кто куда подключён физически
2. **A2** — `start_modulation`: V или V_shunt на нагревателе
3. **B1** — Что курсорщик делает в калибровочном визарде
4. **D1** — `apply_fh_cal`: какая из двух версий канон
5. **G1** — `DAQController` singleton: для реального multi-consumer
   use case или просто удобство

Без ответов на эти пять — даже ProfileWidget сложно адаптировать по
конвенциям, а калибровочный визард и live-streaming архитектуру вообще
нельзя проектировать.

---

## Менее срочные, но полезные

Всё остальное (C, E, F, H) можно отвечать post-merge. Это вопросы
документации и валидации, а не блокеров портабельности.

Из них особенно полезно зафиксировать:
- ответ на **E1/E2/E3** — войдёт в `docs/` как rationale за константами;
- ответ на **C1** — определит, оставляем ли мы `calcaf_lockin` как опцию,
  или полностью переходим на наш `lockin_demodulate`;
- ответ на **H2** — поможет переименовать поле в конфиге без неоднозначности.
