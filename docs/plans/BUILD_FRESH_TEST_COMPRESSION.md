# BUILD: fresh output compression — 17.10.2026

Ветка codex/build-fresh-test-compression от NET checkpoint33d964e; mainffce8cb
сохранён. Full1573/runtime442ce7d и actual ownLAN Login/Base2 PASS сохранены.
На D около35MiB: даже retained-C exe оставляет около39MiB новых SQL/fixtures
на каждый full. Нельзя удалять/перемещать/сжимать существующие данные.

1. Только test-only Rust helper перед первыми writes в fresh empty owned
   ROOT/local/test-runs/closed-namespace/run-PID-NONCE. Проверить абсолютный
   путь, no reparse, точный namespace/currentPID, свежесть/empty/handle identity.
   Win32FSCTL_SET_COMPRESSION для NTFS directory, затем verify attribute;
   не запускать recursive compact, не менять production Web localPath guard.
2. Подключить helper после create_dir, до parent-control в трёх существующих
   actual HTTP compositions; Node/seed/output contracts сохранить. Подготовить
   тот же call для отдельной будущей Hold5 composition.
3. Meaningful isolated test: real new empty dir→compression→1MiB authored
   data→read SHA unchanged/actual allocated smaller. Nonempty/foreign/reparse
   отказ до изменения; старые receipts/bytes не трогать. Fresh dirs retained.
4. Canonical focused build, raw source before/after и реальные results. Полный
   regression повторить на следующем dependent Hold head; пока он не запущен,
   full этого helper NOT_RUN. Сохранить checkpoint/доказательства/push.

Операционный Python sibling предназначен только для четырёх фиксированных
новых утренних stand dirs, с теми же fresh/empty/NTFS checks и SHA-pinned reuse.
Он не делает backup/activation сам и не расширяет сервисные paths.

Prototype22 уже OBSERVED на новом tiny owned D каталоге:1MiB zeros/0allocated/
SHA equal, nonempty/foreign/existingjunction refused. Это не Rust/full PASS.
Откат — predecessor33d964e либо revert test-only source commit; оставить все
старые/новые outputs и retained C targets. Native/UI NOT_RUN.

Actual checkpoint cc2a94d: canonical4PASS/0FAIL/0ignored/buildPASS/877rawsource
exact,0.06stest/48.40driver. Полный combined runtime ещё NOT_RUN и будет
проверен на следующем Hold head. Факты research/BUILD_FRESH_TEST_COMPRESSION.md.
