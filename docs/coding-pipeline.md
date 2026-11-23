# Кодинг-пайплайн с независимым viewer

Пайплайн проверяет конкретный commit SHA до merge:

```text
local tests -> commit -> PR -> Ubuntu/Windows CI -> PR-Agent
           -> Independent Viewer -> branch protection -> squash merge
```

Viewer работает на `claude-opus-5.5` с reasoning effort `high`, не меняет код и
выдаёт JSON по контракту `pipeline/viewer/verdict.schema.json`.

## CI на GitHub

Для pull request из ветки этого же repository workflow `Tests` запускает:

1. `Python 3.11 on ubuntu-latest`;
2. `Python 3.11 on windows-latest`;
3. `Independent Viewer (Claude Opus 5.5)` только после успеха обеих платформ.

Workflow `PR Agent` добавляет check `PR Agent review`. Fork PR не получает
`APIHOST_API_KEY`: viewer guard завершает job ошибкой. Для внешнего вклада
поддерживаемый путь — same-repository branch после ручной проверки владельцем.

Перед HTTP-запросом viewer проверяет:

- полный `reviewed_sha` из GitHub event;
- `git rev-parse HEAD == reviewed_sha`;
- связь base/head SHA;
- лимит diff;
- непустой статус матрицы tests.

API error, timeout, неверный SHA, превышение diff, broken JSON и ответ модели
вне schema дают non-zero exit. `PASS` — единственный verdict с exit code 0.
`PASS_WITH_RISKS` и `FAIL` блокируют merge.

Viewer сохраняет `viewer-verdict.json` и `viewer-summary.md` в artifact на 14 дней.
В PR обновляется один комментарий с маркером `<!-- independent-viewer-verdict -->`;
старые копии того же bot-комментария удаляются.

## Трактовка verdict

| Verdict | Действие кодера |
| --- | --- |
| `PASS` | Передавать PR к merge после остальных обязательных checks |
| `PASS_WITH_RISKS` | Разобрать P3-риски или явно исправить их; merge остаётся закрыт |
| `FAIL` | Исправить P0–P2 findings и отправить новый commit; новый SHA запускает новый review |

Результат для старого SHA не переиспользуется после push.

## Первичная настройка на Windows

1. Создайте GitHub Actions secret без записи значения в файл или command history:

```powershell
gh secret set APIHOST_API_KEY --repo lobarevds333333333-hash/vpf09-vk-ai-bot
```

2. Задайте тот же ключ в User environment для интерактивного Codex viewer.
   Используйте защищённый prompt или оснастку Environment Variables; значение
   не должно попадать в repository, TOML, JSON и сообщения агента.

3. Установите канонический agent config и watchdog:

```powershell
.venv\Scripts\python.exe -m pipeline.viewer.install_coder_viewer --install-startup
```

Установщик записывает:

- `C:\Users\<user>\.codex\agents\coder-viewer.toml`;
- отдельный случайный token в `C:\Users\<user>\.codex\viewer-proxy-token`;
- `VIEWER_PROXY_TOKEN` в User environment;
- задачу `CodexApiHostProxyWatchdog`, которая раз в минуту проверяет health.

4. Перезапустите Codex, чтобы provider получил актуальный
   `VIEWER_PROXY_TOKEN`. Запустите adapter и проверьте health:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\pipeline\viewer\start_proxy.ps1
Invoke-RestMethod http://127.0.0.1:8791/health
```

Ожидаемый ответ: `ok=True`. `start_proxy.ps1` запускает Python скрыто и ждёт
health; scheduled task повторяет эту проверку после падения процесса.

5. Проверьте, что `coder-viewer.toml` совпадает с repository contract:

```powershell
.venv\Scripts\python.exe -m pipeline.viewer.install_coder_viewer --check
```

## Локальная диагностика

Полные offline tests:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Compile check:

```powershell
.venv\Scripts\python.exe -m compileall -q bot config keyboards models services storage utils pipeline scripts main.py tests
```

Если health недоступен:

1. Проверьте наличие `APIHOST_API_KEY` и `VIEWER_PROXY_TOKEN` в User environment.
2. Запустите `install_coder_viewer` без `--check` и перезапустите Codex.
3. Выполните `start_proxy.ps1`; при ошибке процесс останавливается, а в stdout
   отсутствует значение ключей.
4. Запустите задачу вручную:

```powershell
Start-ScheduledTask -TaskName CodexApiHostProxyWatchdog
Get-ScheduledTaskInfo -TaskName CodexApiHostProxyWatchdog
```

Proxy принимает только loopback `127.0.0.1`, требует Bearer token или
`X-Viewer-Proxy-Token`, принимает только `application/json` и принудительно
переключает Responses request в нестриминговый JSON. Function tools сохраняются;
несовместимые top-level metadata и web-search tools удаляются.

## Branch protection

Перед включением protection первый same-repository PR должен получить реальный
viewer `PASS`. Dry-run не обращается к GitHub:

```powershell
.venv\Scripts\python.exe -m scripts.configure_branch_protection `
  --repository lobarevds333333333-hash/vpf09-vk-ai-bot --branch main --dry-run
```

После Checkpoint A примените конфигурацию:

```powershell
.venv\Scripts\python.exe -m scripts.configure_branch_protection `
  --repository lobarevds333333333-hash/vpf09-vk-ai-bot --branch main --apply
gh api repos/lobarevds333333333-hash/vpf09-vk-ai-bot/branches/main/protection
```

Защита требует pull request, актуальную base branch, четыре checks и разрешение
обсуждений; force-push, удаление `main` и admin bypass запрещены.

Удаляйте `TEST_CODEX` только после проверки, что workflows его не используют:

```powershell
rg -n "TEST_CODEX" .github pipeline docs
gh secret delete TEST_CODEX --repo lobarevds333333333-hash/vpf09-vk-ai-bot
gh secret list --repo lobarevds333333333-hash/vpf09-vk-ai-bot
```

## Положительный и отрицательный E2E

Положительный сценарий начинается от актуального `main`, содержит полезное
изменение и проходит все четыре checks. Перед squash merge убедитесь, что
viewer artifact содержит `reviewed_sha`, равный текущему `headRefOid` PR.

Отрицательный сценарий выполняется в throwaway branch. Внесите логическое
нарушение требования при зелёных unit tests, убедитесь, что viewer вернул `FAIL`
и GitHub не разрешает merge, затем исправьте дефект. `PASS` для нового SHA должен
заменить старый red check. Throwaway PR закрывается без merge, если в нём нет
полезного изменения.

## Ограничения и откат

- `claude-opus-5.5` может отсутствовать в model catalog Codex; CLI использует
  fallback metadata с предупреждением.
- Fork PR штатно блокируются.
- Diff больше `250000` bytes требует разделить PR.
- PR-Agent хранит историю findings в служебном state и иногда оставляет уже
  resolved finding в старом JSON; актуальный verdict смотрите в обновлённом
  комментарии и check run текущего SHA.

Порядок отката: снять viewer check с branch protection, отключить job, сохранив
код, остановить scheduled task и proxy, восстановить предыдущий
`coder-viewer.toml`, затем при отказе от pipeline удалить secret и token file.
