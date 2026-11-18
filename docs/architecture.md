# Архітектура

```
source text ─lexer─▶ tokens ─parser─▶ AST (sipl.ast, SourceSpan)
                                        ├─▶ interpreter ─▶ events / RunResult / Diagnostic
                                        └─▶ semantics.builder ─▶ Term ─▶ evaluator ─▶ EvalResult + RuleStep[]
cli.py: тонкий шар, що викликає лише публічні API вище та серіалізує результат у текст/JSON
```

- **Стабільні моделі даних:** `Diagnostic`/`SourceSpan` (`source.py`), AST (`ast.py`), `Event` (`interpreter/events.py`),
  `Term` (`semantics/terms.py`). Усі мають `to_dict()` для JSON.
- Парсер створює **власні** вузли AST (не дерево сторонньої бібліотеки); рівність вузлів ігнорує `span`,
  тому `parse(unparse(p)) == p` — перевіряється тестами.
- Інтерпретатор повідомляє про події через callback-спостерігач (`Interpreter(observer=...)`);
  `trace()` лише збирає їх у список — так само може підключитися налагоджувач чи візуалізатор.
- Інтерпретатор і обчислювач термів — незалежні реалізації; тест перехресної перевірки порівнює їх
  на випадкових програмах.
- Розширення (IDE, LSP, візуалізація) мають імпортувати `sipl`, а не копіювати парсер.
