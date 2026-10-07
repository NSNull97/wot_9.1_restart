# Источники исследовательских зависимостей

Эти зависимости пока используются в локальных P01/P02 spikes. Клиентские ресурсы,
EXE, байткод, извлечённые материалы и приватные тестовые ключи не включены в Git.
Право на распространение предоставленного клиента не установлено.

| Компонент | Закрепление | Проверенный license/source |
|---|---|---|
| wg-toolkit-rs | `5b879f0b960ccb4a3b799ede952256e253ef74cb` | MIT, LICENSE в этом commit |
| serde-pickle fork | `bb098cafb6775604614000d58a885a72dd5c495f` | LICENSE-MIT / LICENSE-APACHE в локальном checkout |
| JoltPhysicsSharp NuGet | 2.22.0; repository commit `77a5be2dd30d587c1981dfcaf15851f18041b39c` | nuspec MIT |
| JoltPhysics.Native NuGet | 1.1.0; joltc commit `59f7d63ff7760981b771b6b161346fcc007f4dfd` | package LICENSE.MIT.txt, Copyright 2021 Jorrit Rouwe |
| CPython format reference | v2.7.18, import.c/marshal.c/opcode.py | PSF source reference; downloaded only to local/vendor, not executed |
| CPython diagnostic compiler | official 2.7.3 x86 MSI, SHA-256 `05bf3b9686a64a413eeb6efb03b591f8a6f2d9c5496898f367e9cef79e4b2c02` | Original LICENSE.txt retained with extraction in local/toolchains/cpython-2.7.3-x86; only own source compilation |
| pefile | installed 2024.8.26 | MIT in installed package metadata; static PE reads only |
| capstone | installed 5.0.9 | Installed package/license retained; static disassembly only; not vendored |
| cryptography | installed 48.0.0 | Apache-2.0 OR BSD-3-Clause in metadata; independent RSA/Blowfish corpus verifier and negative mutants; backend uses Rust crypto |
| RustCrypto blowfish | 0.9.1, already pinned transitive dependency, now direct | MIT OR Apache-2.0; Cargo.toml and both licenses retained in ignored Cargo registry |
| Rust / LLVM-MinGW | Rust 1.90.0 GNU / LLVM-MinGW 20250910 | Toolchain packages in ignored local; retained upstream notices |

`tools/packed_xml.py`, `geometry_spike.py` используют описание формата,
прочитанное в MIT-коде wg-toolkit; реализация ограничений и проверок собственная.
`py27_static.py` использует структуру marshal из CPython, создавая только
обычные записи данных. C# spike написан по API примерам JoltPhysicsSharp;
исходники примеров не скопированы в проект.

Полный production license/security review всех транзитивных зависимостей
не выполнен. Lockfiles фиксируют версии/registry checksums; это не утверждение
о безопасности всех зависимостей. Подробные локальные metadata/hashes —
`local/evidence/20261002-p00-p01/dependencies.json`.
Дополнение: `local/evidence/20261002-p01-bootstrap/dependencies.json`.
Собственный login091 profile использует public APIs wg-toolkit для packet/reply
framing; наблюдаемые поля и исторические коды подтверждены локальным клиентом.
Vendor source не изменён и не скопирован в profile. SHA1 0.10.7 уже был в
закреплённом dependency graph; теперь он явно указан для RSA OAEP исследования.
В P02 переиспользован public LoginSuccess encoder и Blowfish writer; корректность
ограниченного ответа подтверждена redirect настоящего клиента и echo токена.
Modern BaseApp codec не принят. Дополнение dependency metadata —
`local/evidence/20261002-p02-login-redirect/dependencies.json`.
Карточка 2026-10-04 не добавляет зависимостей. `baseapp091.rs` использует
public BlowfishReader/Writer для блочной операции, собственные проверки
packet size/footer/token и измеренный legacy reply envelope. Полный modern
PacketSocket/Account/dispatch не принят. Реальные packet evidence и новый
binary hash — `local/evidence/20261004-p02-baseapp-reply/`.

## MIT notice: wg-toolkit-rs

Copyright (c) 2022 Théo Rozier

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
