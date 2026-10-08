# P02 — Tactical Steel UI: фактический pipeline ангара

Дата: 2026-10-08 (Asia/Yekaterinburg).  0.9.1 RU `#717`.  
Статус: **PASS_STATIC_PIPELINE_AUDIT / REPLACEMENT_NOT_RUN**.

## Что именно проверялось

Пользовательский PNG `C:\Users\NSNull\AppData\Local\Temp\codex-clipboard-f1f3a4ad-46e9-4d4e-b6d5-d6f15d872734.png`
имеет SHA-256 `746760ffe2c0360e0f548b665f7cfa5875821d2a9034d5a6f4c808a2e5f4790b`.
Он показывает старый ангар с ИС-7, левым экипажем/задачами, длинным правым
списком ТТХ, сервисными слотами, каруселью и нижней строкой. Это OBSERVED
визуальный референс, а не доказательство внутренних имён или координат.

Приклеенный текст пользователя — 461 строка, SHA-256
`cb5e78cdbfc89a89ab2943e91cc971d0c516e2bc0ca657bc7af5b038a5ee0ba1`; файл
обрывается на имени `EquipmentPresentationAdapter`. Критерии приёмки,
команды установки и окончание code block в нём отсутствуют, поэтому они не
выдумываются в этом отчёте.

## VERIFIED: реальная точка входа

Для разрешённой исследовательской копии
`D:\WoT_9.1_Server\WoT_0.9.1_RU_0717_research` подтверждены:

| Слой | Файл/ресурс | Что видно в bounded records | SHA-256 |
|---|---|---|---|
| Hangar controller | `res/scripts/client/gui/Scaleform/daapi/view/lobby/hangar/Hangar.pyc` | `Hangar`, `_populate`, `_dispose`, update handlers, `onCacheResync`, `onMoneyUpdate`, current-vehicle and state callbacks | `a41a7d728215da53887cd6aa240b3f933b1e1c809ec5ac856ff792b2ba249899` |
| Crew panel | `.../hangar/crew.pyc` | compiled child view; source-level replacement not present | `8defb03050f4d903d40e466e11fed0b04c368f8fc0450263316e0b768edba136` |
| Params panel | `.../hangar/params.pyc` | `update`/`clearHistorical` is called by Hangar | `38edde73ff25f5ec6cc68553834fcc73a49f6bc0bc6bd8d989fa7f6614475030` |
| Tank carousel | `.../hangar/tankcarousel.pyc` | `vehicleChange`, `buySlot`, `buyTankClick`, `setVehiclesFilter`, `showVehicles`, `updateVehicles`, `updateParams`, `showVehicleStats` | `84e023be8befc58478600084811bc753ec670dee0fdf0f1982fa1bd66e596e8a` |
| Lobby owner | `.../lobby/lobbyview.pyc` | compiled `LobbyView` owner for the lobby screen | `6170e0a23b0bacd7c062d2c15452fdd0d03710cd6cb3ecfe447904782f8a2b57` |
| Flash contract | `.../meta/hangarmeta.pyc`, `.../meta/tankcarouselmeta.pyc` | Python-to-Flash method surface is compiled metadata, not an editable ActionScript source tree | `c24df77420080680242bd60a0260bd49e5b4ed0e99d468d4c45589fdf5b26539`, `2fca45923bd3165477f194c7437e38abec31b2cb7f21224091dbf47ee7b3fc3a` |

The Hangar bytecode calls existing child components rather than owning game
rules: `updateAmmoPanel`, `updateParams`, `updateCarouselVehicles`,
`updateCarouselParams`, `updateResearchPanel`, and `updateCrew`. Its state
refresh is driven by the original caches/events (`g_currentVehicle`,
`g_itemsCache`, `g_eventsCache`, `g_clientUpdateManager`, `g_playerEvents`,
prequeue callbacks and lobby event bus). This is the safe seam for a later
presentation adapter; it is not permission to create a parallel network path.

## VERIFIED: compiled Flash/Scaleform resources

The bounded GUI index at
`local/evidence/20261002-p00-p01/static/gui-index.json` lists these relevant
payloads (they are package-index entries, not loose editable source files):

| Resource | Bytes | CRC32 |
|---|---:|---|
| `gui/flash/hangar.swf` | 219258 | `a380d8c3` |
| `gui/flash/TankCarousel.swf` | 274504 | `8f93ec6e` |
| `gui/flash/carousels.swf` | 71260 | `60a10b17` |
| `gui/flash/crew.swf` | 412012 | `047e9246` |
| `gui/flash/AmmunitionPanel.swf` | 374976 | `94f0986a` |
| `gui/flash/vehicleInfo.swf` | 107341 | `06a18559` |
| `gui/flash/lobby.swf` | 472034 | `46d7b5a1` |
| `gui/flash/LobbyMenu.swf` | 82178 | `cf9a8147` |
| `gui/flash/inventory.swf` | 1730630 | `49522ed8` |

The P00/P01 audit confirms 62 `.pkg` containers and no supplied ActionScript/
FLA source tree. The client also uses compiled Python 2.7.3 bytecode and the
historical `res_mods/0.9.1/scripts/client/` loader; `.wotmod` is not a verified
path. Therefore direct SWF/GFX patching is **UNKNOWN/NOT_SAFE_BY_DEFAULT**:
the package entry, compression, CRC, load path, symbol names and Python Flash
contract must all survive a reversible repack. Editing a package member in
place would also destroy the current manifest evidence.

## What can be replaced later

1. **Python presentation shim (candidate):** replace one compiled client
   controller in the research overlay only, preserving the original event
   subscriptions and calling the existing `HangarMeta`/child methods. This
   can change data routing and visibility of existing components, but cannot
   create new vector controls until a compatible SWF symbol/API is supplied.
2. **SWF/GFX replacement (candidate, owner-gated):** build or obtain a
   0.9.1-compatible Flash artifact, inject it as a separate package/overlay,
   prove exact symbol paths and callbacks, then run a native screenshot and
   click matrix. No such artifact or compiler is present in this checkout.
3. **Full visual replacement (blocked):** requires a source-compatible Flash
   build/repack path, localization entries, texture/atlas ownership and a
   measured teardown/recreate path. A web page or Unity scene cannot satisfy
   this client.

## Proposed Tactical Steel mapping (design only)

This maps the requested zones onto the verified seams without inventing data:

| Requested zone | Existing seam | Later acceptance |
|---|---|---|
| Top/navigation/battle | `LobbyView`, `LobbyMenu`, existing event bus and battle/prequeue callbacks | native click opens the same menu/queue path; no direct protocol call |
| Left tasks/crew/warning | `Hangar` crew child + player/events cache | native PNG with complete/incomplete crew fixture and repair action |
| Center tank | `ClientHangarSpace`/existing hangar visual model path | tank remains unobscured across resize and selected-vehicle change |
| Right grouped stats | `params.pyc` + `Hangar.__updateParams` + vehicle descriptor fields | values match native selected vehicle; no painted constants |
| Service slots | ammunition/equipment child panels and fitting callbacks | click/tooltip/disabled states preserve original handlers |
| Narrow carousel | `tankcarousel.pyc` + `TankCarousel.swf` | select/filter/search/buy-slot/buy-tank callbacks remain live |
| Bottom chat | lobby messenger/channel views | channels/contacts/chat still open and teardown is clean |

The mapping is **INFERRED design**, not an implementation claim. The right
stats grouping, compact ribbon, neutral icons and new geometry need a real
Flash artifact and pixel/click evidence before they can be called native.

## Blockers and unknowns

- No editable Hangar/TankCarousel ActionScript or FLA source was found.
- No compatible SWF compiler/repacker and no symbol-level API map are pinned.
- Existing UI11/UI13 evidence proves native hangar observation, not a new
  replacement UI; recruitment/customization had observed errors in the last
  normal package.
- No owner-gated screenshot/click run exists for a new artifact.
- This launch is still bounded by `prompts/FIRST_PROMPT.md` P00–P01; a runtime
  replacement belongs to a separate P02 card and must not be smuggled into
  the research branch.

## Next experiment

The single useful next step is an owner-gated **one-component replacement
spike**: prepare a separate research-copy overlay for the existing `params`
or carousel component, with a hash-pinned compatible Flash artifact (if one
is supplied), preserve the original callbacks, run the native client, and
capture one selected-vehicle screenshot plus click/teardown trace. If no
artifact/compiler is supplied, the correct result is `NOT_RUN`, not a fake
success.

