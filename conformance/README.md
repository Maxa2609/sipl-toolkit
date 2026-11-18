# SIPL conformance suite (CORE-06)

Набір тестів, який не залежить від конкретної реалізації: runner не імпортує код, а лише викликає
командний рядок за контрактом `sipl-cli/1` (див. `docs/cli.md`) і порівнює JSON.

```bash
python conformance/run_conformance.py                 # реалізація за замовчуванням: python -m sipl
python conformance/run_conformance.py --cmd "sipl"    # будь-яка інша реалізація з тим самим CLI
```

## Формат кейсу (`cases/*.json`)
```json
{"name": "valid/power",
 "source": "текст SIPL-програми",
 "expect": {
   "syntax_error": {"code": "SYN-...", "line": 1, "col": 6},       // АБО далі:
   "ast": {"...": "очікуване AST без полів span"},                    // необов'язково
   "term": "WH(>(Y, 0), ...)",                                        // необов'язково
   "runs": [ {"state": {"X": 2}, "final_state": {"X": 2, "R": 1}},    // успішний запуск
             {"state": {},       "error": "RT-DIV-ZERO"} ]            // або помилка виконання
 }}
```
Реалізація має підтримувати `parse|term|run` з `-` (stdin), `--json`, `--state`. Помилка синтаксису → код
завершення 1, помилка виконання → 3.
