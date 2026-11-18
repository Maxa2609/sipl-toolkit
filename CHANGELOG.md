# Changelog
Формат: [Keep a Changelog](https://keepachangelog.com), версіонування: [SemVer](https://semver.org).

## [0.6.3] - 2026-11-18
### Fixed
- Файли з BOM (Блокнот, PowerShell `-Encoding utf8`) давали `SYN-UNEXPECTED-CHAR`; тепер BOM ігнорується.

## [0.6.2] - 2026-11-18
### Fixed
- `mypy src` падав у CI на `cli.py` (8 помилок типів у друку trace): тепер події розрізняються через `isinstance`.

## [0.6.1] - 2026-11-17
### Fixed
- Windows: вивід CLI у канал (pipe) падав через кодову сторінку cp1251 на символах `·` і `⇒`
  (ламав `conformance/run_conformance.py`). Тепер вивід у pipe — UTF-8, JSON — лише ASCII,
  stdin читається як UTF-8. Додано регресійні тести з `PYTHONIOENCODING=cp1251`.

## [0.6.0] - 2026-11-17
### Changed (breaking)
- Граматика за замовчуванням — рівно БНФ курсу (обов'язкові `begin…end` і `else`, лише `+ - * = > ∨ ¬`).
  Раніше прийняті `div`, `mod`, `< <= >= <>`, `and`, `true/false`, `if` без `else` і програма без `begin/end`
  тепер — розширення SIPL-ext: `--ext` / `extensions=True`; без нього помилка `SYN-EXTENSION`.
- Прапорець `check --strict` видалено (його роль виконує поведінка за замовчуванням).
- Приклади: 14 коректних за курсом, 26 некоректних, `examples/ext/` для SIPL-ext; conformance — 26 кейсів.

## [0.5.1] - 2026-11-17
### Changed
- Нотація семантичних термів приведена до практикуму: `AS_x(a)`, `S1 · S2` (S1 першим), `x⇒`, `S²(op, …)`,
  `id`; назви формул `AF_*`.
### Added
- `sipl check --strict` — перевірка за БНФ курсу; приймаються `∨` та `¬`; від'ємні числа як константи.

## [0.5.0] - 2026-11-16
### Added
- Граматика EBNF, лексер, парсер, типізоване AST зі `SourceSpan` (0.1).
- Інтерпретатор зі станом, ліміт кроків, виявлення нескінченного циклу, події виконання (0.2).
- CLI `parse/check/run/trace` + JSON-режим `sipl-cli/1` (0.3).
- Семантичні терми та обчислення терму з трасою правил (0.5).
- Conformance-набір (`conformance/`), CI (GitHub Actions).
