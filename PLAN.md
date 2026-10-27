# План реализации (от текущего состояния)

## Текущее состояние
- Экран 960×640 (поле) + полоса HUD 640..720: сетка 6×6, ячейка 160×106.7.
- Уровень **не прописан статически** в [`main.collection`](main/main.collection:1): его
  генерирует [`main/level/level.script`](main/level/level.script:1) из метаданных
  [`main/levels.json`](main/levels.json:1) (100 уровней оригинала, извлекаются
  [`tools/extract_levels.py`](tools/extract_levels.py:1) из `BUMPY.TAP`).
- [`main/ball/ball.script`](main/ball/ball.script:1): шар 32 px, ритм прыжка, высокий прыжок,
  привязка к колонке, столкновения с платформами/перегородками/кладкой.
- Платформы/стены/предметы/выход создаются фабриками через реестр
  [`main/level/level_state.lua`](main/level/level_state.lua:1).
- HUD-карман [`main/pocket/pocket.script`](main/pocket/pocket.script:1): капли, ключи, молотки, жизни.

## Этап 1. Сетка 6×6 и привязка шара — ВЫПОЛНЕНО

## Этап 2. Высокий прыжок — ВЫПОЛНЕНО

## Этап 3. Платформы и их типы — ВЫПОЛНЕНО
- Прототипы по типам: `default`, `sloped/left`, `sloped/right`, `shrinkable`, `sticky`,
  `spike`, `burning`, `burning_sticky` (вместо единого `platform.go` со свойством типа).
- Наклонные — [`sloped.script`](main/platforms/sloped/sloped.script:1) + `slope_direction` в ball.
- Уменьшающиеся — [`shrinkable.script`](main/platforms/shrinkable/shrinkable.script:1).
- Липкие — [`sticky.script`](main/platforms/sticky/sticky.script:1) + `sticky_rest` в ball.
- Шипы — [`spike.script`](main/platforms/spike/spike.script:1) + `is_spike`/`lose_life("spikes")`.
- Горящие — [`burning.script`](main/platforms/burning/burning.script:1) + `is_burning`/`extinguish_burning`.
- Опасность (шипы/огонь) проверяется скриптово при приземлении, а не через trigger-коллизии.

## Этап 4. Перегородки и кирпичи — ВЫПОЛНЕНО
- `indestructible` / `destructible` — [`main/walls/`](main/walls/destructible/destructible.script:1),
  удар расходует ключ (`hit_destructible_wall` в ball).
- Кирпичная кладка (block, код `lo = 10`) — [`main/walls/block/block.script`](main/walls/block/block.script:1).

## Этап 5. Снаряжение и инвентарь — ВЫПОЛНЕНО
- Прототипы предметов: [`drop`](main/goodies/drop/drop.go:1), [`key`](main/goodies/key/key.go:1),
  [`hammer`](main/goodies/hammer/hammer.go:1), [`heart`](main/goodies/heart/heart.go:1) (жизнь).
- Общее состояние: `shared_state = 1` в [`game.project`](game.project:5); счётчики — в ball,
  реестр уровня — в [`level_state.lua`](main/level/level_state.lua:1), HUD — в
  [`pocket.script`](main/pocket/pocket.script:1) (отдельного `state.script` нет).
- Снапшот инвентаря на старте уровня и откат при потере жизни —
  `start_pocket`/`start_keys`/`start_hammers` в ball, `set_items` в pocket.

## Этап 6. Жизни и игровой цикл — ЧАСТИЧНО
- ВЫПОЛНЕНО: 3 стартовые жизни; смерть от шипов, горящей платформы без капли,
  падения за нижний край (`lose_life`); GAME OVER при 0 жизней
  ([`main/ui/game_over.script`](main/ui/game_over.script:1)); победа в уровне —
  сбор `timer` объектов открывает выход, касание выхода → следующий уровень.
- **ОСТАЛОСЬ (п. 19): условие проигрыша при нехватке снаряжения** (невозможность
  пройти уровень вне зависимости от числа жизней — `tz.txt` [3][5][7][8]).
  Сейчас нигде не реализовано: нет проверки, что собранного/имеющегося в кармане
  снаряжения хватает на обязательные для уровня преграды (кладка/разрушаемые
  перегородки/горящие платформы) и что выход достижим.

## Этап 7. Уровни — ВЫПОЛНЕНО
- Формат данных — [`main/levels.json`](main/levels.json:1) (генерируется скриптом).
- Загрузка/генерация экземпляров — [`level.script`](main/level/level.script:1)
  (`build_level`, очистка и пересборка между уровнями).

## Этап 8. Плашка READY перед уровнем — ВЫПОЛНЕНО
- Перед началом каждого уровня показывается плашка «READY FOR LEVEL N?» (N —
  номер уровня). Ждёт нажатия любой клавиши; пока она на экране, мяч заморожен
  (коллизия выключена, `update` не выполняется) и игра не начинается.
- UI: [`main/ui/ready.go`](main/ui/ready.go:1) (спрайт-подложка + label +
  скрипт), [`ready.script`](main/ui/ready.script:1) (сообщения `show`/`hide`,
  подстановка номера уровня), фон [`main/ui/ready.png`](main/ui/ready.png:1)
  (генерируется [`tools/gen_ready_sign.py`](tools/gen_ready_sign.py:1) в стиле
  GAME OVER), шрифт [`ready.font`](main/ui/ready.font:1).
- Экземпляр `ready` добавлен в [`main.collection`](main/main.collection:1)
  (z=0.95, поверх остальных объектов).
- [`ball.script`](main/ball/ball.script:1): флаг `ready_wait`; по `level_start`
  мяч замораживается и постится `show`; по первому нажатию клавиши плашка
  скрывается, коллизия включается и уровень стартует.

## Этап 10. Сохранение прогресса между сессиями (HTML5) — ВЫПОЛНЕНО
- При закрытии вкладки/браузера с игрой состояние сохраняется: пока не
  потрачены все жизни, переоткрытие возвращает игрока на текущий уровень с тем
  же числом жизней и содержимым кармана (капли/ключи/молотки).
- Хранилище — [`main/save.lua`](main/save.lua:1) поверх `sys.save`/`sys.load`.
  Записываются: номер уровня, жизни, карман. Версия формата защищает от
  несовместимых сохранений; `lives = 0` означает «жизни кончились → новая игра».
- **Ключ к работе на HTML5** (без этого игра начиналась с 1-го уровня):
  - [`game.project`](game.project:32) `[html5] use_indexeddb = 1` — монтирует
    постоянный каталог приложения (`/data`) на IndexedDB (IDBFS с
    `autoPersist`); вне него файловая система Emscripten живёт в памяти MEMFS
    и теряется при перезагрузке вкладки;
  - путь к файлу сохранения берётся через `sys.get_save_file("bumpy", "bumpy_save")`
    в [`main/save.lua`](main/save.lua:1) — только он указывает внутрь
    смонтированного на IndexedDB каталога. «Голое» имя файла (как было раньше)
    на HTML5 попадало в корень MEMFS вне точки монтирования, поэтому сохранение
    не переживало перезагрузку. Отдельной функции синхронизации в API нет
    (`sys.sync_fs` не существует): движок сбрасывает IDBFS в IndexedDB
    автоматически при закрытии файла, т.е. сразу после `sys.save`.
- [`level.script`](main/level/level.script:1): в `init` читает сохранение и, если
  `lives > 0`, стартует с сохранённого уровня вместо `go.property("level")`.
- [`ball.script`](main/ball/ball.script:1): в `init` восстанавливает жизни и
  карман из сохранения; в `level_start` пишет снимок начала уровня
  (`start_*` — то же состояние, к которому карман откатывается при смерти);
  в `lose_life` обновляет жизни до перезапуска; при GAME OVER обнуляет
  сохранение (`lives = 0`), при рестарте — пишет начало новой игры.

## Этап 9. Спрайты-фрукты для собираемых goodies — ВЫПОЛНЕНО
- Для собираемых объектов (коды >= 5, ранее — единый спрайт-ромб
  `collectible`) сгенерированы 12 отдельных спрайтов-фруктов 32×32 RGBA:
  гриб, клубника, яблоко, груша, вишня, банан, апельсин, виноград, слива,
  лимон, морковь, арбуз. Генератор —
  [`tools/gen_fruit_sprites.py`](tools/gen_fruit_sprites.py:1).
- Один атлас [`main/goodies/fruit/fruit.atlas`](main/goodies/fruit/fruit.atlas:1)
  (12 images + 12 animations, id = имя фрукта) и спрайт
  [`fruit.sprite`](main/goodies/fruit/fruit.sprite:1). Изображения переименованы
  с префиксом `fr_`, чтобы неявные id images не конфликтовали с id анимаций.
- Прототип [`main/goodies/fruit/fruit.go`](main/goodies/fruit/fruit.go:1):
  спрайт + [`fruit.script`](main/goodies/fruit/fruit.script:1) (kind = 3,
  выбор анимации по свойству `anim`).
- [`level.script`](main/level/level.script:1): `goodie_factory` для кодов >= 5
  возвращает `#goodie_fruit` и имя фрукта (`fruit_for_code` — коды
  распределяются по кругу); `spawn_goodie` передаёт `anim = hash(имя)`.
  Factory `goodie_fruit` добавлен в [`level.go`](main/level/level.go:1).

## Этап 11. Версия билда рядом с «Made with Defold» — ВЫПОЛНЕНО
- В нижнем правом углу HTML5-сборки Defold рисует бейдж «Made with Defold».
  Рядом с ним теперь показывается версия игры и номер сборки: **«Made with
  Defold — v1.0.0 (build 123)»**. Та же строка подставляется в `<title>`
  вкладки (шаблон рендерит `{{project.title}} {{project.version}}`).
- **Версия игры** (semver) — источник истины в
  [`game.project`](game.project:30) (`[project] version`). Меняется вручную
  при релизе: `1.0.0` → `1.1.0` и т. п.
- **Номер сборки** — число коммитов в истории
  (`git rev-list --count HEAD`), растёт автоматически на каждом деплое.
  Для этого [`deploy-master.yml`](.github/workflows/deploy-master.yml:73)
  делает checkout с `fetch-depth: 0` (иначе счётчик всегда был бы 1).
- Подстановка — шаг «Подстановка версии игры в index.html» в
  [`deploy-master.yml`](.github/workflows/deploy-master.yml:184): после сборки
  бандла шаг читает `version` из `game.project`, считает номер сборки и
  заменяет в `dist/web/bumpy/index.html` бейдж и `<title>` на версионированные.
  Правка безопасна: `dmloader.js` сверяет sha1/size только wasm и архива, а не
  самого `index.html`.

## Этап 12. Альтернативное управление тапом по ячейкам — ВЫПОЛНЕНО
- Вариант управления выбирается настройкой `bumpy.controls_mode` в
  [`game.project`](game.project:34): `"buttons"` (прежние экранные кнопки),
  `"cells"` (тап по игровым ячейкам), `"auto"` (cells на тач-устройствах,
  buttons на остальных).
- [`controls.gui_script`](main/controls/controls.gui_script:1): режим `cells` —
  тап в координатах окна переводится в игровую ячейку через видимую область
  мира из [`camera_state.lua`](main/render/camera_state.lua:1) (см. этап 13);
  нажатая ячейка подсвечивается тонкой рамкой (узел `cell_highlight`), тап за
  боковой границей поля (не дальше одной ячейки) подсвечивает только стенку
  (узел `wall_highlight`). Команда уходит в мяч сообщением `cell_tap`.
- [`controls.gui`](main/controls/controls.gui:1): узлы подсветки; текстуры
  `white.png` и `cell_frame.png` генерируются
  [`tools/gen_controls_ui.py`](tools/gen_controls_ui.py:1).
- [`ball.script`](main/ball/ball.script:1): обработка `cell_tap` —
  намерение (`cell_cmd`) выполняется, когда мяч готов к действию:
  ячейка выше мяча → высокий прыжок с запрыгиванием в сторону нажатия
  (`cell_jump` применяется на уровне нажатой ячейки при подъёме), тот же ряд
  или ниже → обычный подскок в сторону нажатия. Тап за границей поля даёт
  только боковой прыжок.
- [`input/game.input_binding`](input/game.input_binding:1): к действию `touch`
  добавлен `MOUSE_BUTTON_1`, чтобы режим можно было проверять и на настольной
  сборке.
- **Смена траектории в высоком прыжке (запрыгивание).** Пока мяч летит вверх,
  тап по ячейке меняет траекторию: на уровне этой ячейки мяч уходит на одну
  колонку в сторону нажатия (`cell_jump`) и падает. Раньше работал только тап
  за боковой границей поля — у тапа по ячейке `dir = 0`, а ветка полёта в
  `try_cell_command` требовала `dir ~= 0`.
  - Команда действует, только пока мяч не долетел до нажатой ячейки: нижняя
    часть мяча (`y - RADIUS`) не пересекла уровень отскока этого ряда
    (`BOUNCE_Y[row]`) и `cmd.row >= hj_row`. Тап по уже пройденной ячейке
    игнорируется, но ранее назначенный соскок сохраняется.
  - В полёте тап отправляется сразу при нажатии (`motion_state` от `/ball` →
    `high_flying` в [`controls.gui_script`](main/controls/controls.gui_script:1)):
    мяч проходит ячейку меньше чем за 0.2 с, отпускание пальца опаздывало.
    Вне полёта команда по-прежнему уходит по отпусканию, чтобы свайп-
    панорамирование не превращался в команду; начатый свайп отменяет ещё не
    исполненную команду сообщением `cell_cancel` (по `id` касания).
  - В полёте команда исполняется тем же кадром (`try_cell_command` прямо из
    `on_message`), цель допрыгивания по ряду (`target_col`) не ставится.

## Этап 13. Камера: масштаб по длинному краю и плавный фокус — ВЫПОЛНЕНО
- Поле больше не вписывается целиком в окно: на мобильных (тач-устройствах)
  оно масштабируется так, чтобы заполнить экран по длинному краю — одна из
  сторон поля видна полностью, вторая обрезается. На плашке «READY FOR LEVEL»
  по-прежнему виден весь уровень целиком, а после старта масштаб плавно
  меняется к игровому.
- Камера — [`camera.script`](main/render/camera.script:1): каждый кадр
  считает масштаб и видимый прямоугольник мира, плавно (экспоненциальное
  сглаживание, ≈0.4 с) подводит масштаб к цели и следует за мячом с «мёртвой
  зоной» (24% видимого размера) и небольшой задержкой. Центр ограничен полем,
  поэтому за его краем не показывается пустота.
- Собственный рендер-скрипт [`game.render_script`](main/render/game.render_script:1)
  (форк `builtins/render/default.render_script`) принимает границы видимой
  области числами через сообщение `set_camera_rect` и строит по ним
  ортопроекцию. Матрицу (`matrix4`) в сообщении передать нельзя — отсюда
  именно прямоугольник. Подключён через
  [`game.render`](main/render/game.render:1) и `bootstrap.render` в
  [`game.project`](game.project:3). GUI рисуется отдельной stretch-проекцией,
  поэтому интерфейс не «раздувается» вместе с полем.
- Общее состояние — [`camera_state.lua`](main/render/camera_state.lua:1):
  видимый прямоугольник мира и трансформ полосы HUD. По нему
  [`controls.gui_script`](main/controls/controls.gui_script:1) переводит тапы
  в мировые координаты (раньше считался fixed-fit от размера окна), а
  [`pocket_item.script`](main/pocket/pocket_item.script:1) каждый кадр
  переводит локальные координаты полосы в мировые — карман остаётся
  закреплённым за экраном и не уезжает вместе с полем.
- Плашки READY / GAME OVER / TRAPPED камера держит по центру видимой части
  поля и сохраняет их экранный размер (`scale = fit_zoom / zoom`).
- Переключение режима — сообщения `ready` / `play` из
  [`ball.script`](main/ball/ball.script:1) (по `level_start` и по первому
  нажатию на плашке READY).
- Настройка `bumpy.camera_mode` в [`game.project`](game.project:37):
  `"auto"` (cover на тач-устройствах, fit на десктопе), `"cover"` (всегда
  заполнять экран по длинному краю), `"fit"` (прежнее поведение — вся сцена
  целиком).
- Прежний [`projection.script`](main/render/projection.script:1) (fixed-fit
  через `use_fixed_fit_projection`) удалён вместе с `projection.go`.
- **Проверка в HTML5/Docker.** Бандл собирается через Defold Editor HTTP API
  (`/bob`: `build` с `archive=true`, затем `bundle` с
  `architectures=wasm-web` и `bundle-output=dist/web`), образ —
  `docker build -f docker/Dockerfile -t bumpy-web .`, запуск —
  `docker run -d --name bumpy-web -p 8080:80 bumpy-web:latest`,
  игра открывается на <http://localhost:8080>. Проверено: на плашке READY
  виден весь уровень, в режиме `cover` поле заполняет экран по длинному краю,
  HUD-полоса растянута на всю ширину и прижата к верху.
  Примечание: `docker compose build` на этой машине падает на баге BuildKit
  (`changes out of order`), поэтому образ собирается с `DOCKER_BUILDKIT=0`.

## Что осталось
1. **П. 19: проверка нехватки снаряжения → проигрыш.** Нужно на старте уровня
   (или при потере ресурса) вычислять, хватает ли капель/ключей/молотков на
   обязательные преграды уровня, и если нет — завершать игру. Требует:
   - оценки «потребности» уровня в снаряжении (сколько горящих платформ без
     возможности обхода, обязательных разрушаемых перегородок, кладки);
   - учёта текущего кармана + доступных на уровне предметов;
   - перевода в состояние GAME OVER без ожидания потери жизней.
2. **Актуализация `PLAN.md`** (сделано в этой правке): этапы 3–5, 7 были
   фактически выполнены, но не отмечены; «Текущее состояние» описывало старую
   статическую лесенку платформ.

## Валидация
- После изменений: `POST /command/compile` (Defold Editor HTTP API,
  порт из `.internal/editor.port`), прогон через `/command/run`, проверка `/console`.
