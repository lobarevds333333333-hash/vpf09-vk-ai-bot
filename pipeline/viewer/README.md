# Independent Viewer Contract

`instructions.md` задаёт поведение вьювера, а `verdict.schema.json` и
`contract.validate_verdict()` — машинный формат ответа. Этот контракт общий для
интерактивного Codex-агента и GitHub Actions reviewer.

Обязательные поля: `reviewed_sha`, `verdict`, `evidence`, `findings`,
`limitations`. `reviewed_sha` — полный 40-символьный commit SHA. Вердикты:
`PASS`, `PASS_WITH_RISKS`, `FAIL`. Каждый finding содержит severity `P0`–`P3`,
путь, строку, evidence и action.

Проверка контракта:

```bash
python -m unittest tests.test_viewer_contract -v
```
