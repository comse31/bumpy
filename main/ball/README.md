# main/ball — структура модулей мяча

[`ball.script`](ball.script) — точка входа (компонент в [`ball.go`](ball.go)): только
жизненный цикл Defold (`init/update/on_input/on_message`) и порядок шагов кадра.
Вся специфика разнесена по модулям `.lua`.

## Слои и зависимости

Ниже — направление зависимостей: нижние слои ничего не знают о верхних.

```
        ball.script            жизненный цикл, порядок шагов кадра
       /     |      \
 landing  input   motion       действия (шаги, прыжки, приземление)
      \      |      /
   progress  trap  goodies  obstacles
        \     |     |     /
      world  grid  physics  debug  config    листья: реестр, геометрия, API
```

Листья не требуют других модулей проекта и не хранят состояние:

| Модуль | Ответственность |
|---|---|
| [`ball_config.lua`](ball_config.lua) | все числа баланса: сетка, физика прыжка, тайминги ввода, геометрия |
| [`ball_physics.lua`](ball_physics.lua) | единственная точка доступа к `#collision_object` |
| [`ball_grid.lua`](ball_grid.lua) | преобразования сетки 6×6 (центр колонки, ячейка по позиции) |
| [`ball_debug.lua`](ball_debug.lua) | `dbg.log` (при `bumpy.debug = 1`) и `dbg.always` |
| [`ball_world.lua`](ball_world.lua) | реестр уровня: платформы, перегородки, кладка, свойства поверхностей |

Средний слой знает только листья:

| Модуль | Ответственность |
|---|---|
| [`ball_goodies.lua`](ball_goodies.lua) | касание предметов и таблички EXIT, разбор `kind` |
| [`ball_obstacles.lua`](ball_obstacles.lua) | перегородки и кладка: удары, верхняя грань |
| [`ball_trap.lua`](ball_trap.lua) | детект бесконечной ловушки и отсчёт |
| [`ball_progress.lua`](ball_progress.lua) | жизни, карман, сохранение (`persist`), GAME OVER |

Верхний слой — действия, которые для избежания циклов получают зависимости
внедрением (`bind`), как герои получают `ENV`:

| Модуль | Ответственность |
|---|---|
| [`ball_motion.lua`](ball_motion.lua) | `hop_and_move`, отскоки, высокий прыжок, тайминги полёта |
| [`ball_input.lua`](ball_input.lua) | удержания клавиш/жестов, отложенный тап по ячейке |
| [`ball_landing.lua`](ball_landing.lua) | приземление и swept-тест (зависит от `ball_motion`) |

Связывание выполняется в [`ball.script`](ball.script) один раз:

```lua
input.bind({
    start_high_jump = function(self) start_high_jump(self) end,
    hop_and_move = function(self, dir) return hop_and_move(self, dir) end,
    bounce_off_wall = function(self, dir) bounce_off_wall(self, dir) end,
})

landing.bind({
    motion = motion,
    actions = { settle_or_stick = function(self) settle_or_stick(self) end },
})
```

## Герои

[`hero_ball.lua`](hero_ball.lua) и [`hero_slinky.lua`](hero_slinky.lua) — та же
схема внедрения (`setup(self, env)`): общий код знает только интерфейс героя
(`activate/deactivate/reset/on_action/...`), вся визуальная специфика — в модулях.

## Запуск из редактора на Linux

Если игра не стартует из редактора с ошибкой

```
dmengine: error while loading shared libraries: libopenal.so.1:
cannot open shared object file: No such file or directory
```

— в системе нет библиотек, с которыми слинкован движок (`libopenal.so.1` для
звука, `libsndio.so.7` как его зависимость). Установка требует root, поэтому
есть скрипт, который чинит это без sudo: скачивает `.deb` через `apt-get
download`, распаковывает библиотеки в отдельный каталог и прописывает его в
`RPATH` самого `dmengine`.

```bash
bash tools/fix_engine_libs.sh
```

Скрипт идемпотентен и безопасен при запущенной игре (патч идёт через временную
копию с атомарной подменой файла), оригинал сохраняется рядом как
`dmengine.orig`. После патча игру нужно перезапустить из редактора.

Используется `DT_RPATH` (`patchelf --force-rpath`), а не `DT_RUNPATH`: `libsndio.so.7`
является зависимостью `libopenal.so.1`, а `RUNPATH` на транзитивные зависимости
не распространяется — с ним движок находит `libopenal` и падает на `libsndio`.

## Тесты

| Скрипт | Что проверяет |
|---|---|
| [`tools/smoke_test.lua`](../../tools/smoke_test.lua) | константы, сетку, свойства поверхностей, физику, ввод, ловушку, карман |
| [`tools/scenario_test.lua`](../../tools/scenario_test.lua) | реальный `ball.script`: `init` → `level_start` → шаги, прыжки, шипы, GAME OVER |

Тесты на моках не ловят ошибки загрузки ресурсов (`sys.load_resource`): мок
`sys.get_config_string` возвращает значение без кавычек, а движок — с ними.
Поэтому логику загрузки уровней проверять запуском из редактора или прямым
запуском `dmengine` на каталоге `build/default`.

Запуск (в контейнере с `lua5.1`):

```bash
docker exec -w /work bumpy-web lua5.1 tools/smoke_test.lua
docker exec -w /work bumpy-web lua5.1 tools/scenario_test.lua
```

## Ручной тестовый уровень

Тестовый режим включается одной настройкой в [`game.project`](../../game.project):

```ini
[bumpy]
test_level = 1
```

Выключено (обычная игра) — `test_level = 0`. В тестовом режиме:

- [`level.script`](../level/level.script) грузит `/main/test_levels.json` вместо
  `/main/levels.json` и всегда начинает с первого (единственного) уровня;
- **сохранение полностью игнорируется**: [`save.load`](../save.lua) возвращает
  `nil`, а `save.store`/`save.clear` ничего не пишут. Тестовый прогон не затирает
  прогресс реальной игры и не продолжает её с середины;
- по завершении уровня он перезапускается (переходить некуда), а не уходит на
  уровень 2.

Решение принимает один модуль — [`main/test_mode.lua`](../test_mode.lua),
поэтому проверка режима не дублируется по скриптам.

Тестовый уровень содержит все типы платформ (обычная, сжимающаяся в двух
состояниях, липкая, наклонные в обе стороны, горящая, горящая-липкая, кладка,
шипы), все типы перегородок и все виды предметов.

> **Важно:** `sys.get_config_string` возвращает значение **вместе с кавычками**
> из `game.project` (`""` — это два символа кавычек, а не пустая строка).
> Поэтому все читатели настроек ([`test_mode.lua`](../test_mode.lua),
> [`level.script`](../level/level.script), [`ball_debug.lua`](ball_debug.lua))
> срезают кавычки перед использованием. Без этого `sys.load_resource` получает
> невалидный путь, `level.script` не создаёт платформ, и на экране остаётся
> только мяч. Тот же приём — в [`controls.gui_script`](../controls/controls.gui_script).
