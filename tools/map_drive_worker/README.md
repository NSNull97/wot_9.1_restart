# Старая точка сборки worker

Основной source и документация находятся в [server/physics](../../server/physics/README.md).
Этот `.csproj` подключает те же файлы; копий Program.cs/CheckedInput.cs здесь нет.
Новые сборки выполняются через `server/build.py physics`; `--legacy` проверяет
данную совместимую точку сборки с output только в `local/build/`.
