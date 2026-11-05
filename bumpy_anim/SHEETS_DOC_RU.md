# Документация листов (ТЗ 7.2)
Кадр 144x144 px, прозрачный фон (RGBA PNG), pivot = (72, 107) (центр по x, поверхность платформы по y), диаметр шара 72 px, шар по центру (72, 71). Каждый клип лежит отдельной папкой frames/<имя>/<имя>_NN.png и отдельной полосой в sheets/<имя>.png.

| Клип | Кадров | Длит., с | Кадров/с | Цикл | Держать последний | Переход дальше |
|---|---|---|---|---|---|---|
| contact_feet | 14 | 0.100 | 140 | нет | да | flight_up | flight_feet_to_head (by input at the end of the dwell) |
| contact_head | 14 | 0.100 | 140 | нет | да | flight_head_hop | flight_head_side |
| flight_up | 34 | 0.515 | 66 | нет | нет | contact_feet |
| flight_up_blink | 34 | 0.515 | 66 | нет | нет | contact_feet |
| flight_feet_to_head | 34 | 0.515 | 66 | нет | нет | contact_head |
| flight_feet_to_head_blink | 34 | 0.515 | 66 | нет | нет | contact_head |
| flight_head_hop | 34 | 0.515 | 66 | нет | нет | contact_feet |
| flight_head_hop_blink | 34 | 0.515 | 66 | нет | нет | contact_feet |
| flight_head_side | 34 | 0.515 | 66 | нет | нет | contact_feet |
| flight_head_side_blink | 34 | 0.515 | 66 | нет | нет | contact_feet |
| landing | 18 | 0.300 | 60 | нет | нет | idle (or anticipation if input) - ONLY after a long fall |
| land_head | 18 | 0.300 | 60 | нет | нет | idle (after flip to the feet) |
| idle | 23 | 1.643 | 14 | да | нет | blink (random 1.5-3.5 s) | anticipation | turn_in |
| turn_in | 9 | 0.120 | 75 | нет | да | half_turn_loop |
| turn_out | 9 | 0.120 | 75 | нет | да | idle |
| turn_rl | 15 | 0.200 | 75 | нет | да | half_turn_loop (mirrored) |
| half_turn_loop | 18 | 1.000 | 18 | да | нет | turn_out | turn_rl |
| blink | 12 | 0.160 | 75 | нет | нет | idle |
| anticipation | 14 | 0.156 | 90 | нет | да | flight_up | flight_feet_to_head |
| anticipation_high | 20 | 0.222 | 90 | нет | да | high_jump |
| high_jump | 45 | 0.500 | 90 | нет | да | fall (hold last frame while rising) |
| fall | 12 | 0.400 | 30 | да | нет | contact_feet | landing | hurt | death |
| fall_surprise_in | 9 | 0.120 | 75 | нет | да | fall_surprised |
| fall_surprised | 12 | 0.400 | 30 | да | нет | landing (soft squash) | hurt | death |
| head_hit_top | 20 | 0.400 | 50 | нет | нет | fall / contact_feet (ends upright) |
| feet_hit_top | 20 | 0.400 | 50 | нет | нет | fall / contact_feet (ends upside down -> contact_head) |
| head_hit_side_up | 18 | 0.360 | 50 | нет | нет | fall |
| feet_hit_side_up | 18 | 0.360 | 50 | нет | нет | fall |
| head_hit_side_inv | 18 | 0.360 | 50 | нет | нет | fall |
| feet_hit_side_inv | 18 | 0.360 | 50 | нет | нет | fall |
| hurt | 17 | 0.472 | 36 | нет | нет | idle |
| death | 24 | 0.667 | 36 | нет | да | hold last frame |
| win | 24 | 0.667 | 36 | нет | нет | hold / level exit |
| collect | 18 | 0.300 | 60 | нет | нет | previous state |