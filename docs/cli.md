# CLI

```
sipl parse|check FILE [--json]
sipl run|trace FILE [-s X=1,Y=2]... [--max-steps N] [--ext] [--json]
sipl term FILE [--ascii] [--ext] [--json]
sipl eval-term FILE [-s ...] [--max-steps N] [--ascii] [--ext] [--json]
```
`FILE` = `-` читає stdin. Без `--ext` приймається рівно БНФ курсу; `--ext` додає SIPL-ext (`docs/language.md`). `--state/-s` повторюється, значення розділяються комами.

## Коди завершення
| Код | Значення |
|-----|----------|
| 0 | успіх |
| 1 | синтаксична помилка програми |
| 2 | помилка використання/вводу-виводу (немає файлу, поганий `--state`, невідома команда) |
| 3 | програма коректна, але виконання завершилось помилкою / терм невизначений (⊥) |

## JSON-схема `sipl-cli/1`
У режимі `--json` stdout — один JSON-документ:
```json
{"schema": "sipl-cli/1", "command": "run", "file": "...", "ok": true,
 "diagnostics": [{"severity": "error", "code": "...", "message": "...",
                  "span": {"start": 0, "end": 1, "line": 1, "col": 1, "end_line": 1, "end_col": 2}}],
 "result": null}
```
`result` за командами:
- `parse`: `{"ast": {...}}` — вузли `{"kind": "Assign", ..., "span": {...}}`.
- `check`: `{"inputs": [...], "assigned": [...]}`.
- `run`: `{"status": "terminated"|"error", "state": {...}, "steps": n, "error": Diagnostic|null}`.
- `trace`: як `run` + `"events": [{"type": "BeforeStatement"|..., "seq", "step", "state", "span", ...}]`.
- `term`: `{"text", "ascii", "term": {...}}`.
- `eval-term`: `{"status": "defined"|"undefined", "state", "kind", "reason", "rule_applications", "steps": [...], "rules": {...}}`.

При синтаксичній помилці або помилці вводу `result` = `null`, а `diagnostics` містить причину.
Зміна форми цих документів потребує нового значення `schema`.
