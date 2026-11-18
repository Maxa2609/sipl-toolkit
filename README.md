# SIPL Language Toolkit

[![CI](https://github.com/Maxa2609/sipl-toolkit/actions/workflows/ci.yml/badge.svg)](https://github.com/Maxa2609/sipl-toolkit/actions/workflows/ci.yml)

Автор: Столяр Марія, група ТК-32

Набір інструментів для простої мови програмування **SIPL** (SImple Programming Language) з курсу
«Теорія програмування»: формальна граматика, парсер, інтерпретатор із трасою виконання, командний
рядок із JSON-режимом, семантичні терми програм і покрокове обчислення термів.
Залежностей немає, потрібен лише Python 3.10 або новіший.

## Обрані завдання

| ID | Завдання | Бали | Де в проєкті |
|----|----------|------|--------------|
| CORE-01 | Формальна граматика (EBNF, збігається з БНФ курсу), 14 коректних і 26 некоректних прикладів | 0.5 | `grammar/`, `examples/` |
| CORE-02 | Парсер, власне типізоване AST із позиціями в тексті (`SourceSpan`), діагностика помилок | 1.5 | `src/sipl/` |
| CORE-03 | Інтерпретатор: стан, присвоювання, композиція, `if`, `while`, `begin/end`, `skip`; ліміт кроків і виявлення нескінченного циклу | 2.0 | `src/sipl/interpreter/` |
| CORE-04 | Події виконання й trace (Before/AfterStatement, VariableChanged, ConditionEvaluated, Finished) | 1.0 | `interpreter/events.py` |
| CORE-05 | CLI `parse`, `check`, `run`, `trace` (+ `term`, `eval-term`), JSON-режим, коди завершення | 1.0 | `src/sipl/cli.py`, `docs/cli.md` |
| SEM-01 | Автоматична побудова семантичного терму з AST (нотація практикуму) | 2.0 | `src/sipl/semantics/builder.py` |
| SEM-02 | Обчислення терму на стані: кінцевий стан або ⊥, trace застосованих формул | 2.0 | `src/sipl/semantics/evaluator.py` |
| CORE-06 | Conformance suite: 26 кейсів і runner, незалежний від реалізації | 1.0 | `conformance/` |
| REL-01 | CI: lint, перевірка типів, тести, збірка пакета | 0.5 | `.github/workflows/ci.yml` |
| REL-02 | SemVer, CHANGELOG, тегований реліз (`v0.6.3`) | 0.5 | `CHANGELOG.md` |
| | **Заявлено** (зараховується не більше 10) | **12.0** | |

## Встановлення

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows;  Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
```

Після цього доступна команда `sipl`.

## Швидкий старт

```bash
sipl run examples/valid/power.sipl --state X=2,Y=10
```
```
{R=1024, X=2, Y=0}
```

Програма `power.sipl` обчислює R = X^Y:

```
begin
  R := 1;
  while Y > 0 do
  begin
    R := R * X;
    Y := Y - 1
  end
end
```

## Команди

| Команда | Що робить |
|---------|-----------|
| `sipl check FILE` | перевіряє синтаксис, показує вхідні змінні |
| `sipl parse FILE` | друкує AST |
| `sipl run FILE --state X=2,Y=3` | виконує програму |
| `sipl trace FILE --state X=2,Y=3` | виконує і друкує події |
| `sipl term FILE` | будує семантичний терм |
| `sipl eval-term FILE --state X=2,Y=3` | застосовує терм до стану, показує застосовані формули |

Усі команди приймають `--json` (структурований вивід для інтеграцій) і `--ext` (див. нижче).
`run` і `trace` приймають ще `--max-steps N`. Файл `-` означає стандартний ввід. Докладно: `docs/cli.md`.

Приклад терму (програма x^y з практикуму, `sipl term examples/valid/power.sipl`):

```
AS_R(1) · WH(S²(gr, Y⇒, 0), AS_R(S²(mult, R⇒, X⇒)) · AS_Y(S²(sub, Y⇒, 1)))
```

Приклад помилки (`sipl check examples/invalid/missing_end.sipl`):

```
examples/invalid/missing_end.sipl:3:1: error[SYN-UNEXPECTED-TOKEN]: expected 'end' or ';', found end of input
```

## Мова

За замовчуванням приймається **рівно БНФ курсу** (практична робота 1): програма має вигляд
`begin ... end`, `if` завжди з `else`, є лише `+ - * = > ∨ ¬` (`or` і `not` теж працюють),
числа можуть бути від'ємними (`-1`).

Додаткові конструкції винесені в окремий діалект **SIPL-ext** і вмикаються прапорцем `--ext`:
`div`, `mod`, `< <= >= <>`, `and`, `true/false`, `if` без `else`, програма без `begin/end`,
унарний мінус перед змінною. Без прапорця вони дають помилку `SYN-EXTENSION`.

```bash
sipl run examples/ext/collatz.sipl --state N=6 --ext
```

Граматика: `grammar/sipl.ebnf`. Опис мови, діагностики й семантичних термів: `docs/language.md`.

## Приклади

- `examples/valid/` — 14 програм за БНФ курсу (степінь, факторіал, НСД, числа Фібоначчі, ...);
- `examples/invalid/` — 26 програм із синтаксичними помилками (очікуваний код у першому рядку);
- `examples/ext/` — програми з розширеннями SIPL-ext;
- `examples/defense/` — додаткові програми за БНФ курсу для демонстрації.

## Використання як бібліотеки

```python
from sipl import parse, run, trace, build_term, evaluate_term, format_term

prog = parse("begin while N > 0 do N := N - 1 end")   # AST: власні вузли зі span
run(prog, {"N": 3}).state                              # {'N': 0}
trace(prog, {"N": 1}).events                           # список подій
t = build_term(prog)
format_term(t)                                         # WH(S²(gr, N⇒, 0), AS_N(S²(sub, N⇒, 1)))
evaluate_term(t, {"N": 2}).steps                       # застосовані формули AF_WH_T, AF_AS, ...
```

Парсер, інтерпретатор, терми й діагностика — це бібліотека. CLI лише викликає її API і не дублює логіку.
Схема потоку даних: `docs/architecture.md`.

## Тести

```bash
pytest                                  # 192 тести
python conformance/run_conformance.py   # 26 кейсів
ruff check src tests conformance        # lint
mypy src                                # типи
```

Тести охоплюють: усі приклади (коректні, некоректні, SIPL-ext); позиції помилок; перетворення
`parse(unparse(p)) == p` на 300 випадкових програмах; виконання всіх прикладів; помилки й ліміти
виконання; послідовності подій; golden-тести термів; збіг результатів «терм ≡ інтерпретатор» на
400 випадкових програмах; запуск CLI як окремого процесу.

## Структура

```
grammar/sipl.ebnf        граматика (БНФ курсу + SIPL-ext)
src/sipl/                ast, lexer, parser, source, analysis, cli
  interpreter/           runtime, events
  semantics/             terms, builder, evaluator
examples/                valid/  invalid/  ext/  defense/
conformance/             набір тестів, незалежний від реалізації
tests/                   тести (golden-файли термів у tests/golden/)
docs/                    language.md, cli.md, architecture.md
```

## Обмеження

- Значення лише цілі числа довільної точності; `div` і `mod` (у SIPL-ext) округлюють до −∞.
- Змінна без значення в початковому стані при читанні дає помилку `RT-UNDEFINED-VAR`.
- Нескінченний цикл визначається точно, коли стан повторився; в іншому випадку спрацьовує ліміт кроків,
  і результат «невизначено в межах ліміту» не є доведенням розбіжності.
- Назви операцій, яких немає в практикумі (`div`, `mod`, `ne`, `ls`, `le`, `ge`, `and`, `uminus`),
  вигадані автором і належать до SIPL-ext (`docs/language.md`).
