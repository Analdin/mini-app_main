# Развёртывание AlfaDent на собственном VPS (Ubuntu/Debian)

## Важно: конфигурация без `.env`

Проект **не использует `.env` и `EnvironmentFile`**. Все настройки, включая действующие токены, Bitrix24 webhook, прокси и общий секрет API, находятся в отдельном файле Python `alfadent_config.py` из приватного репозитория `Analdin/alfadent-miniapp`.

Не копируйте этот файл в публичный `mini-app_main` или в другие публичные репозитории. Не публикуйте его в issue, Pull Request, логах или сообщениях.

Существующие токены и Bitrix24 webhook восстановлены из сохранённых приватных исходников. **Реальную действительность токенов на стороне Telegram/MAX/Bitrix можно подтвердить только пробным запуском с API сервисов.** Значение отдельного MAX webhook secret в сохранённых исходниках отсутствовало; оно оставлено пустым, а прежнее поведение MAX-процессора webhook (без обязательной проверки секрета) сохранено. Настройки webhook в кабинете MAX этой инструкцией не меняются.

## Архитектура

| Сервис | Исходники | Локальный адрес |
|---|---|---|
| Mini App + FastAPI API | `Analdin/mini-app_main` | `127.0.0.1:8001` |
| Telegram-бот | `Analdin/mini-app_main` | Telegram polling |
| MAX-бот | `Analdin/alfa-dent_max` | `127.0.0.1:5000` |

Все три процесса используют один приватный Python-модуль `alfadent_config.py`, одну базу авторизации `/var/lib/alfadent/auth.sqlite3` и общий внутренний секрет. Nginx публикует Mini App/API и webhook MAX.

Репозиторий `Analdin/alfadent-miniapp` содержит старую копию исходников, но в текущей схеме используется только для хранения приватного файла `alfadent_config.py`. Старого Telegram-бота/API из него запускать нельзя.

## 1. Проверить текущий VPS и сохранить данные

До остановки старых процессов сделайте резервную копию каталогов с SQLite-базами, очередями обращений и текущими настройками. Не перезаписывайте действующие данные.

Найдите фактическое расположение баз:
```bash
sudo find /opt /var/lib -type f \\( -name "auth.sqlite3" -o -name "max_bot.sqlite3" -o -name "pending_requests.json" \\) -print
```

Проверьте текущие службы:
```bash
sudo systemctl list-units --type=service | grep -i alfadent
sudo systemctl status alfadent-telegram alfadent-max --no-pager
```
Названия служб могут отличаться. Не останавливайте службы по предположению.

Старые локальные флаги `auth=True` в сессиях MAX/Telegram не являются серверной авторизацией. Пользователю после перехода может потребоваться войти по телефону и постоянному паролю.

## 2. Подготовить каталоги и системного пользователя

```bash
sudo adduser --system --group --home /opt/alfadent alfadent
sudo mkdir -p /opt/alfadent /var/lib/alfadent/telegram /var/lib/alfadent/max /etc/alfadent
sudo chown -R alfadent:alfadent /opt/alfadent /var/lib/alfadent
sudo chmod 750 /var/lib/alfadent /etc/alfadent
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip nginx
```

## 3. Получить три репозитория

Приватные репозитории клонируйте по SSH-ключу, у которого есть read-доступ. Не вставляйте GitHub PAT в URL команды.

```bash
sudo -u alfadent git clone --branch main git@github.com:Analdin/mini-app_main.git /opt/alfadent/mini-app_main
sudo -u alfadent git clone --branch main git@github.com:Analdin/alfa-dent_max.git /opt/alfadent/alfa-dent_max
sudo -u alfadent git clone --branch main git@github.com:Analdin/alfadent-miniapp.git /opt/alfadent/private-config
```

Последний репозиторий приватный. Из него используется только `alfadent_config.py`. Не запускайте старые файлы из этого репозитория.

## 4. Установить приватную конфигурацию Python

Скопируйте приватный модуль в закрытый каталог и подключите его к обоим проектам:

```bash
sudo install -o root -g alfadent -m 0640 \
  /opt/alfadent/private-config/alfadent_config.py \
  /etc/alfadent/alfadent_config.py

sudo ln -s /etc/alfadent/alfadent_config.py \
  /opt/alfadent/mini-app_main/alfadent_config.py

sudo ln -s /etc/alfadent/alfadent_config.py \
  /opt/alfadent/alfa-dent_max/max_bot/alfadent_config.py
```

Проверьте ссылки:
```bash
ls -l /opt/alfadent/mini-app_main/alfadent_config.py
ls -l /opt/alfadent/alfa-dent_max/max_bot/alfadent_config.py
sudo -u alfadent test -r /etc/alfadent/alfadent_config.py && echo "private config readable"
```

Настройки редактируются в Python-файле:
```bash
sudo nano /etc/alfadent/alfadent_config.py
```
Для смены URL Mini App после настройки собственного домена измените в этом файле `WEBAPP_URL`, `MAX_MINIAPP_LINK` и `PROMOTIONS_URL`. Не меняйте Telegram-токен, MAX-токен или Bitrix24 webhook без отдельной необходимости. Не публикуйте приватный файл.

При синхронизации с GitHub обновляйте копию файла осознанно: скачайте новую версию в приватный каталог, проверьте её и только затем замените `/etc/alfadent/alfadent_config.py`. Не запускайте старый код из приватного config-репозитория.

## 5. Перенести существующие базы и очереди

После резервного копирования и штатной остановки старых процессов перенесите только действительно найденные файлы:
- текущую базу авторизации `auth.sqlite3` — в `/var/lib/alfadent/auth.sqlite3`;
- базу MAX `max_bot.sqlite3` — в `/var/lib/alfadent/max/max_bot.sqlite3`;
- очередь Telegram `pending_requests.json` — в `/var/lib/alfadent/telegram/pending_requests.json`;
- очередь MAX, если она существует, — в `/var/lib/alfadent/max/pending_requests.json`.

Пример (замените пути на фактические, которые вернул `find`; копируйте только существующие файлы):
```bash
sudo cp -a /ПОЛНЫЙ/ПУТЬ/auth.sqlite3 /var/lib/alfadent/auth.sqlite3
sudo cp -a /ПОЛНЫЙ/ПУТЬ/max_bot.sqlite3 /var/lib/alfadent/max/max_bot.sqlite3
sudo chown -R alfadent:alfadent /var/lib/alfadent
sudo chmod 600 /var/lib/alfadent/auth.sqlite3 /var/lib/alfadent/max/max_bot.sqlite3
```

Если Render не имел постоянного диска и база не сохранилась, восстановить её из GitHub невозможно. Не удаляйте старый Render service до проверки, есть ли там сохраняемые данные и очереди.

## 6. Создать виртуальные окружения

```bash
sudo -u alfadent python3 -m venv /opt/alfadent/venv-app
sudo -u alfadent /opt/alfadent/venv-app/bin/pip install --upgrade pip
sudo -u alfadent /opt/alfadent/venv-app/bin/pip install -r /opt/alfadent/mini-app_main/requirements.txt

sudo -u alfadent python3 -m venv /opt/alfadent/venv-max
sudo -u alfadent /opt/alfadent/venv-max/bin/pip install --upgrade pip
sudo -u alfadent /opt/alfadent/venv-max/bin/pip install -r /opt/alfadent/alfa-dent_max/requirements.txt
```

## 7. Установить systemd units

```bash
sudo cp /opt/alfadent/mini-app_main/deploy/alfadent-api.service /etc/systemd/system/
sudo cp /opt/alfadent/mini-app_main/deploy/alfadent-telegram.service /etc/systemd/system/
sudo cp /opt/alfadent/mini-app_main/deploy/alfadent-max.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable alfadent-api alfadent-telegram alfadent-max
sudo systemctl start alfadent-api
sudo systemctl status alfadent-api --no-pager
```

Проверьте API до запуска ботов:
```bash
curl -fsS http://127.0.0.1:8001/health
sudo systemctl start alfadent-telegram alfadent-max
sudo systemctl status alfadent-telegram alfadent-max --no-pager
```

## 8. Настроить Nginx и HTTPS

1. Укажите DNS A-запись собственного домена на публичный IP VPS.
2. Скопируйте `deploy/nginx-bootstrap.conf` в `/etc/nginx/sites-available/alfadent`, замените `YOUR_DOMAIN`, включите сайт и выполните `sudo nginx -t`.
3. Выпустите HTTPS-сертификат через Certbot:
   ```bash
   sudo ln -s /etc/nginx/sites-available/alfadent /etc/nginx/sites-enabled/alfadent
   sudo nginx -t && sudo systemctl reload nginx
   sudo apt install -y certbot python3-certbot-nginx
   sudo certbot --nginx -d YOUR_DOMAIN
   ```
4. После получения сертификата настройте `deploy/nginx-https.conf`, подставьте домен и проверьте `sudo nginx -t`.

Nginx проксирует `/max/` на локальный MAX webhook. В кабинете MAX укажите webhook `https://ВАШ_ДОМЕН/max/webhook`. Порт 5000 наружу не открывайте. Текущий исходник сохраняет прежнее поведение: если `MAX_WEBHOOK_SECRET` пуст, проверка заголовка MAX не требуется. Если в кабинете MAX сейчас используется секрет webhook, внесите его в приватный `alfadent_config.py` перед включением обязательной проверки.

## 9. Проверить и только потом переключить

```bash
curl -fsS https://YOUR_DOMAIN/health
curl -I https://YOUR_DOMAIN/miniapp.html
curl -I https://YOUR_DOMAIN/assets/promotions.json
curl -fsS https://YOUR_DOMAIN/max/health
sudo journalctl -u alfadent-api -n 100 --no-pager
sudo journalctl -u alfadent-telegram -n 100 --no-pager
sudo journalctl -u alfadent-max -n 100 --no-pager
```

Проверьте:
- Mini App открывается из Telegram и MAX по новому HTTPS-домену;
- первая регистрация выдаёт постоянный пароль один раз;
- повторный вход с тем же телефоном требует пароль;
- сессия действует в Mini App, Telegram и MAX через общий API;
- неправильный пароль отклоняется;
- заявки приходят в Bitrix24;
- администратор подтверждает фактическую запись, а приложение не обещает забронированный слот.

Только после успешной проверки нового VPS меняйте ссылки Mini App и webhook MAX, затем останавливайте старые процессы и отключайте Render. Не удаляйте прежний сервис до завершения проверки данных.

## Важные ограничения

Без SMS или другого независимого фактора система не доказывает, что введённый номер принадлежит пользователю. Не открывайте таким способом медицинские документы и другие чувствительные данные. Интеграция с МИС «Инфоклиника» не подтверждена: приложение создаёт обращения/лиды в Bitrix24, но не бронирует реальное время.
