# P03: проверка готовности следующего native capture

Дата: 2026-10-06. Статус: **NOT_READY_NATIVE_LOADOUT**.

Изолированный domain gate готов, native Avatar ammo event ещё не отправляется.
Штатный supervisor запускает старый deployed EXE; его замена, config и restart
исключены из этой карточки. Повторный owner run сейчас не добавит доказательств.

Read-only status/hashes и точная CLI-форма capture зафиксированы в
`local/evidence/20261006-battle-shooting-maintenance-preflight-01/result.json` и
`capture-preflight.md`. Прежняя ошибочная READY-оценка сохранена в rejected-01.
Подготовленный plan017 не установлен и не должен применяться к current016.

Ошибка: активная ordinary016 была неверно принята за незавершённый install и
откачена. Исправление: все 37 research files восстановлены до исходных SHA из
postrun сохранения; receipt — repair016-result.json. Original/сервис не менялись.

Единственный следующий шаг: отдельная offline карточка определения настоящего
Avatar ammo method/serializer/order по закреплённым ресурсам #717 и уже
сохранённому capture345. После проверенного native implementation нужен один
owner-driven вход MS-1 → «В бой!» с capture, без fire/sniper. До этого live test
остаётся NOT_RUN; числовой БК не обещается от доменной проверки.

Откат текущих исходников описан в P03_BATTLE_SHOOTING.md. Evidence ошибки и
восстановления сохранять; research016, original и deployed gateway не менять.
