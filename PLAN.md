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
