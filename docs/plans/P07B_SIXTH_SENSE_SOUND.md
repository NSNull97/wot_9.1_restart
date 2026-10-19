# P07B — проектный звук лампы 6-го чувства

Ветка `codex/p07b-sixth-sense-sound` от `codex/full-test-20261019` (вся цепочка
P07B ещё не в main). Факты и команды — [P07B_AUDIO_BOUNDARY](../research/P07B_AUDIO_BOUNDARY_20261018.md).

1. Исследование #717: чем GUI играет 2D-звук, список FX в `gui.fev` — сделано.
2. `client_patch/project_sixth_sense_sound.py` + флаг `prepare --sixth-sense-sound`
   (по умолчанию выключен): обёртка `Battle.showSixthSenseIndicator`, один FX на
   загорание лампы, без повторов, без очередей уведомлений — сделано.
3. Тесты Python 3 и CPython 2.7.3, реальный `prepare` — PASS.
4. Владелец выбирает звук (`gun_intuition` рекомендован), после FULL-TEST
   переустанавливает a/b и проверяет звук в бою — NOT_RUN.

Приёмка: native-проверка владельцем. Откат: `interactive_client.py rollback`
установки; без флага патч оставляет оригинальную беззвучную лампу.
