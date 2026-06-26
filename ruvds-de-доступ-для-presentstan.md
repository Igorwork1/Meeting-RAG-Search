# Доступ к ruvds-de — инструкция для нового участника

## Что такое ruvds-de

Сервер `195.133.94.48` (Германия), используется как LLM-прокси (LiteLLM), там же
PostgreSQL, n8n и Redis. Доступ — только по SSH-ключу, парольный вход отключён.

---

## Шаг 1. Проверка SSH-клиента

Открой PowerShell и убедись, что SSH установлен:

```powershell
ssh -V
```

Должно быть что-то вроде `OpenSSH_for_Windows_8.6p1, LibreSSL 3.4.3`.
Если команда не найдена — установи OpenSSH Client через
«Параметры → Приложения → Дополнительные компоненты».

---

## Шаг 2. Генерация SSH-ключа с passphrase

В PowerShell выполни (замени `your_email@example.com` на свою почту):

```powershell
ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\id_ruvds_de_presentstan" -C "presentstan@codoproject.ru"
```

Когда спросит `Enter passphrase` — введи парольную фразу (passphrase). Запомни её.

**Важно:** не оставляй passphrase пустым. Даже простое предложение из 4-5 слов
на русском языке надёжнее, чем короткий пароль, и его легко запомнить.

После выполнения появятся два файла:
- `~/.ssh/id_ruvds_de_presentstan` — **приватный ключ** (никому не передавай)
- `~/.ssh/id_ruvds_de_presentstan.pub` — **публичный ключ** (передай администратору)

---

## Шаг 3. Передача публичного ключа администратору

Отправь содержимое файла `~/.ssh/id_ruvds_de_presentstan.pub` администратору.

Вывести содержимое:

```powershell
Get-Content "$env:USERPROFILE\.ssh\id_ruvds_de_presentstan.pub"
```

Администратор добавит этот ключ на сервер в `/root/.ssh/authorized_keys`.

---

## Шаг 4. Настройка SSH-конфига

Открой (или создай) файл `~/.ssh/config`:

```powershell
notepad "$env:USERPROFILE\.ssh\config"
```

Добавь в конец файла блок:

```
Host ruvds-de
    HostName 195.133.94.48
    User root
    Port 22
    IdentityFile ~/.ssh/id_ruvds_de_presentstan
    IdentitiesOnly yes
    AddKeysToAgent yes
    ServerAliveInterval 60
    ServerAliveCountMax 3
    RemoteCommand cd /srv && bash
    RequestTTY yes
```

**Пояснение полей:**
- `IdentityFile` — путь к твоему приватному ключу
- `IdentitiesOnly yes` — использовать только этот ключ, не перебирать все
- `AddKeysToAgent yes` — автоматически добавлять ключ в ssh-agent при первом использовании
- `ServerAliveInterval 60` — пинговать сервер каждые 60 секунд, чтобы SSH-сессия не рвалась по таймауту
- `RemoteCommand cd /srv && bash` — при входе сразу переходить в рабочую директорию
- `RequestTTY yes` — запрашивать терминал (нужно для RemoteCommand)

---

## Шаг 5. Настройка автозапуска ssh-agent

Без ssh-agent passphrase придётся вводить при каждом подключении.
С ssh-agent — один раз за сессию Windows.

### 5.1. Создай скрипт запуска агента

```powershell
notepad "$env:USERPROFILE\.ssh\start-ssh-agent.ps1"
```

Содержимое скрипта:

```powershell
$agentPid = (Get-Process -Name ssh-agent -ErrorAction SilentlyContinue).Id
if (-not $agentPid) {
    Start-Service ssh-agent
    Write-Host "ssh-agent started" -ForegroundColor Green
}
else {
    Write-Host "ssh-agent already running (PID $agentPid)" -ForegroundColor Cyan
}

ssh-add "$env:USERPROFILE\.ssh\id_ruvds_de_presentstan"
```

### 5.2. Проверь, что служба ssh-agent настроена на автозапуск

```powershell
Get-Service ssh-agent | Select-Object Name, Status, StartType
```

Если `StartType` не `Automatic`, исправь:

```powershell
Set-Service ssh-agent -StartupType Automatic
Start-Service ssh-agent
```

### 5.3. Добавь скрипт в автозагрузку Windows (опционально)

Чтобы не запускать скрипт вручную при каждом входе в систему:

1. Нажми `Win + R`, введи `shell:startup` и нажми Enter
2. В открывшейся папке создай ярлык:
   - ПКМ → Создать → Ярлык
   - Расположение: `powershell.exe -WindowStyle Hidden -File "%USERPROFILE%\.ssh\start-ssh-agent.ps1"`
   - Название: `SSH Agent`

Теперь после входа в Windows откроется окно PowerShell, запросит passphrase
один раз — и ключ будет в агенте до перезагрузки.

---

## Шаг 6. Проверка подключения

После того как администратор подтвердит добавление ключа на сервер:

```powershell
ssh ruvds-de
```

При первом подключении SSH-клиент спросит подтверждение отпечатка (fingerprint) —
сверь его:

```
SHA256:WFI6vtCggh0dBmfsYP9N4mCwy+/VNYaH9YU85szYU6U
```

Если совпадает — введи `yes`. Если passphrase ещё не в агенте, спросит его —
введи один раз, дальше `AddKeysToAgent yes` запомнит.

После успешного входа ты окажешься в `/srv` на сервере. Введи `exit` для выхода.

---

## Шаг 7. Повседневное использование

### Интерактивная сессия

```powershell
ssh ruvds-de
```

### Выполнение одиночной команды

```powershell
ssh -A -o RemoteCommand=none ruvds-de "команда"
```

Флаг `-A` пробрасывает твой ssh-agent на сервер (нужно для git clone и т.п.).

### SSH-туннель (для доступа к сервисам)

```powershell
Start-Process powershell -ArgumentList '-NoExit', '-Command',
  'Write-Host "SSH tunnel to ruvds-de" -ForegroundColor Green;
   Write-Host "  LiteLLM UI : https://localhost:8443/ui" -ForegroundColor Cyan;
   Write-Host "  LiteLLM API: http://localhost:4000" -ForegroundColor Cyan;
   Write-Host "  n8n        : http://localhost:5678" -ForegroundColor Cyan;
   Write-Host "  Postgres   : localhost:15432 -> server:5432" -ForegroundColor Cyan;
   Write-Host "Close this window to stop the tunnel." -ForegroundColor DarkGray;
   Write-Host "";
   ssh -N -o RequestTTY=no -o RemoteCommand=none `
     -L 8443:127.0.0.1:443 `
     -L 4000:127.0.0.1:4000 `
     -L 5678:127.0.0.1:5678 `
     -L 15432:127.0.0.1:5432 `
     ruvds-de'
```

После этого доступны:
- LiteLLM Admin UI: `https://localhost:8443/ui`
- LiteLLM API: `http://localhost:4000`
- n8n: `http://localhost:5678`
- PostgreSQL: `localhost:15432` (пользователь `plegkody`, БД `litellm_db`)

---

## Краткая справка

| Что | Команда |
|---|---|
| Проверить ключи в агенте | `ssh-add -l` |
| Добавить ключ в агент | `ssh-add ~/.ssh/id_ruvds_de_presentstan` |
| Удалить все ключи из агента | `ssh-add -D` |
| Проверить соединение | `ssh -T ruvds-de` |
| Вывести публичный ключ | `Get-Content ~/.ssh/id_ruvds_de_presentstan.pub` |
