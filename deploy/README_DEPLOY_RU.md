# Развёртывание AlfaDent на собственном VPS (Ubuntu/Debian)

## Архитектура

На одном VPS работают три отдельных процесса:

| Сервис | Проект | Локальный адрес |
|---|---|---|
| Mini App + FastAPI | `Analdin/mini-app_main` | `127.0.0.1:8001` |
| Telegram-бот | `Analdin/mini-app_main` | polling через Telegram API |
| MAX-бот/webhook | `Analdin/alfa-dent_max` | `127.0.0.1:5000` |

Nginx принимает HTTPS: обычные запросы отправляет в FastAPI, запросы с префиксом `/max/` — в MAX-бот. Оба бота обращаются к одному API авторизации и одной базе `AUTH_DB_PATH`.

Render после переключения больше не нужен. Репозиторий `alfadent-miniapp` не используйте как второй API-сервис: это старая копия.

## Перед началом

Нужны:
- VPS с Ubuntu 22.04/24.04 или совместимым Debian;
- домен с A-записью на публичный IP VPS (либо настроенный Cloudflare Tunnel с публичным hostname);
- доступ по SSH с правами sudo;
- действующие новые токены Telegram и MAX, новый Bitrix24 webhook, новый секрет MAX webhook и общий `INTERNAL_AUTH_SECRET`.

**Важно о ранее опубликованных исходниках:** в старой версии `alfadent-miniapp` в Git-истории были строки, похожие на реальные Telegram/Bitrix/proxy credentials. Считайте ранее опубликованные значения скомпрометированными и замените их в соответствующих кабинетах/сервисах. Не переносите значения из старой копии и не присылайте секреты в чат.

## 1. Сохранить текущие данные

До остановки старых процессов сделайте резервную копию каталогов с текущими SQLite-базами и очередями заявок. Не перезаписывайте существующую базу MAX и резервные файлы.

Найдите фактическое расположение существующих баз (пути могут отличаться):
```bash
sudo find /opt /var/lib -type f \( -name "auth.sqlite3" -o -name "max_bot.sqlite3" -o -name "pending_requests.json" \) -print
```

После штатной остановки старых процессов и до запуска новых сервисов:
- если найдена действующая `auth.sqlite3`, скопируйте её в `/var/lib/alfadent/auth.sqlite3` (только если целевой файл ещё не создан);
- если найдена база MAX `max_bot.sqlite3`, скопируйте её в `/var/lib/alfadent/max/max_bot.sqlite3`;
- если есть `pending_requests.json` у Telegram-бота, сохраните его в `/var/lib/alfadent/telegram/pending_requests.json`; если файл относится к MAX-боту, сохраните его в `/var/lib/alfadent/max/pending_requests.json`;
- после копирования выставьте владельца `alfadent:alfadent` и проверьте наличие файлов.

Пример копирования — замените `/ПОЛНЫЙ/ПУТЬ/` на каталог, который вернул `find`. Выполняйте команды только для тех файлов, которые действительно существуют:
```bash
sudo cp -a /ПОЛНЫЙ/ПУТЬ/auth.sqlite3 /var/lib/alfadent/auth.sqlite3
sudo cp -a /ПОЛНЫЙ/ПУТЬ/max_bot.sqlite3 /var/lib/alfadent/max/max_bot.sqlite3
sudo cp -a /ПОЛНЫЙ/ПУТЬ/pending_requests.json /var/lib/alfadent/telegram/pending_requests.json
sudo chown -R alfadent:alfadent /var/lib/alfadent
sudo chmod 600 /var/lib/alfadent/auth.sqlite3 /var/lib/alfadent/max/max_bot.sqlite3
```
Копируйте только реально существующие файлы; не выполняйте команды с неподтверждёнными путями. Если Render не имел постоянного диска и база не сохранилась, её невозможно восстановить из репозитория — пользователям потребуется создать/восстановить аккаунты отдельно.

Старая локальная сессия MAX с одним флагом `auth=True` не считается серверной авторизацией. После перехода пользователю потребуется повторно войти по телефону и постоянному паролю, если в старой сессии не было действующего access token.

Сначала проверьте текущие unit-файлы и процессы:
```bash
sudo systemctl list-units --type=service | grep -i alfadent
sudo systemctl status alfadent-telegram alfadent-max --no-pager
```
Названия могут отличаться — не останавливайте сервисы по предположению.

## 2. Создать системного пользователя и каталоги

```bash
sudo adduser --system --group --home /opt/alfadent alfadent
sudo mkdir -p /opt/alfadent /var/lib/alfadent/telegram /var/lib/alfadent/max /etc/alfadent
sudo chown -R alfadent:alfadent /opt/alfadent /var/lib/alfadent
sudo chmod 750 /var/lib/alfadent
sudo chmod 750 /etc/alfadent
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip nginx
```

## 3. Получить актуальные исходники

Приватные репозитории клонируйте по SSH-ключу, который имеет read-доступ. Не вставляйте GitHub PAT в URL команды: он попадёт в историю shell.

```bash
sudo -u alfadent git clone --branch main git@github.com:Analdin/mini-app_main.git /opt/alfadent/mini-app_main
sudo -u alfadent git clone --branch main git@github.com:Analdin/alfa-dent_max.git /opt/alfadent/alfa-dent_max
```

Оба PR уже объединены в основные ветки `main`; для VPS используйте `main`.

## 4. Создать виртуальные окружения

Разные окружения уменьшают риск конфликтов зависимостей:
```bash
sudo -u alfadent python3 -m venv /opt/alfadent/venv-app
sudo -u alfadent /opt/alfadent/venv-app/bin/pip install --upgrade pip
sudo -u alfadent /opt/alfadent/venv-app/bin/pip install -r /opt/alfadent/mini-app_main/requirements.txt

sudo -u alfadent python3 -m venv /opt/alfadent/venv-max
sudo -u alfadent /opt/alfadent/venv-max/bin/pip install --upgrade pip
sudo -u alfadent /opt/alfadent/venv-max/bin/pip install -r /opt/alfadent/alfa-dent_max/requirements.txt
```

## 5. Настроить секреты на VPS

Скопируйте шаблон `deploy/alfadent.env.example` в приватный файл. Значения вводите только на сервере:

```bash
sudo cp /opt/alfadent/mini-app_main/deploy/alfadent.env.example /etc/alfadent/alfadent.env
sudo chown root:alfadent /etc/alfadent/alfadent.env
sudo chmod 640 /etc/alfadent/alfadent.env
sudo nano /etc/alfadent/alfadent.env
```

Задайте минимум:
- `TELEGRAM_TOKEN` — новый токен Telegram-бота;
- `MAX_BOT_TOKEN` — токен MAX-бота;
- `BITRIX24_WEBHOOK` — новый webhook Bitrix24;
- `INTERNAL_AUTH_SECRET` — длинная случайная строка, одинаковая для API и обоих ботов;
- `MAX_WEBHOOK_SECRET` — секрет webhook MAX;
- `WEBAPP_URL` и `MAX_MINIAPP_LINK` — один и тот же публичный HTTPS URL `https://ВАШ_ДОМЕН/miniapp.html`;
- `PROMOTIONS_URL` — `https://ВАШ_ДОМЕН/assets/promotions.json`;
- `TELEGRAM_PROXY` — только при необходимости, в полном формате SOCKS5/HTTPS-прокси.

Для создания случайных значений непосредственно на VPS можно выполнить `openssl rand -hex 32` дважды и использовать первое значение как `INTERNAL_AUTH_SECRET`, второе как `MAX_WEBHOOK_SECRET`. Не присылайте эти значения в чат и не храните их в Git.

В `AUTH_DB_PATH` используется единый файл `/var/lib/alfadent/auth.sqlite3`. Не задавайте для MAX и Telegram разные значения. Файл базы создаётся API автоматически.

## 6. Установить systemd units

Скопируйте unit-файлы:
```bash
sudo cp /opt/alfadent/mini-app_main/deploy/alfadent-api.service /etc/systemd/system/
sudo cp /opt/alfadent/mini-app_main/deploy/alfadent-telegram.service /etc/systemd/system/
sudo cp /opt/alfadent/mini-app_main/deploy/alfadent-max.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable alfadent-api alfadent-telegram alfadent-max
sudo systemctl start alfadent-api
sudo systemctl status alfadent-api --no-pager
```

Сначала проверьте API, затем запустите ботов:
```bash
curl -fsS http://127.0.0.1:8001/health
sudo systemctl start alfadent-telegram alfadent-max
sudo systemctl status alfadent-telegram alfadent-max --no-pager
```

## 7. Настроить Nginx и HTTPS

1. Создайте DNS A-запись домена на IP VPS.
2. Скопируйте `deploy/nginx-bootstrap.conf` в `/etc/nginx/sites-available/alfadent`, замените `YOUR_DOMAIN` на домен, включите сайт и проверьте конфигурацию.
3. Выпустите сертификат:
   ```bash
   sudo ln -s /etc/nginx/sites-available/alfadent /etc/nginx/sites-enabled/alfadent
   sudo nginx -t && sudo systemctl reload nginx
   sudo apt install -y certbot python3-certbot-nginx
   sudo certbot --nginx -d YOUR_DOMAIN
   ```
4. После получения сертификата замените bootstrap-конфигурацию содержимым `deploy/nginx-https.conf`, подставьте домен и проверьте `sudo nginx -t`.

На Nginx 1.24 используется форма `listen 443 ssl http2;`. В конфигурации API Nginx явно удаляет входящий от внешнего клиента заголовок `X-Internal-Auth`; этот заголовок используется только локальными процессами ботов при обращении прямо к `127.0.0.1:8001`.

Nginx проксирует `/max/` на локальный MAX webhook. Настройте webhook в кабинете MAX на `https://ВАШ_ДОМЕН/max/webhook` и передайте секрет способом, который позволяет кабинет MAX. Приложение принимает стандартный заголовок `X-Max-Bot-Api-Secret`; секрет в URL не рекомендуется, поскольку URL может попадать в логи.

## 8. Проверить

```bash
curl -fsS https://YOUR_DOMAIN/health
curl -I https://YOUR_DOMAIN/miniapp.html
curl -I https://YOUR_DOMAIN/assets/promotions.json
curl -fsS https://YOUR_DOMAIN/max/health
sudo journalctl -u alfadent-api -n 100 --no-pager
sudo journalctl -u alfadent-telegram -n 100 --no-pager
sudo journalctl -u alfadent-max -n 100 --no-pager
```

Тест регистрации лучше провести с отдельным тестовым номером, потому что система создаёт постоянную запись аккаунта. Проверьте: первая регистрация показывает пароль один раз; повторная регистрация предлагает войти; вход с правильным паролем работает в Mini App, Telegram и MAX; неправильный пароль отклоняется; выход отзывается на сервере; заявки передаются в Bitrix24. Убедитесь, что фактическая запись пациенту не обещается до подтверждения администратором.

## 9. Переключить ссылки и отключить Render

Когда HTTPS, Mini App, API, Telegram и MAX проверены:
- проверьте, что Telegram-кнопка открывает `WEBAPP_URL`;
- проверьте, что MAX-кнопка открывает `MAX_MINIAPP_LINK` внутри MAX-клиента;
- проверьте загрузку акций по `PROMOTIONS_URL`;
- замените webhook MAX на новый VPS URL;
- только после успешной проверки остановите старые процессы и отключите старый Render service.

## Обслуживание

Ежедневно делайте резервную копию `/var/lib/alfadent` и храните её отдельно от VPS. В том числе сохраняйте каталог MAX `/var/lib/alfadent/max`. Не делайте публичный доступ к SQLite, `.env`, логам, резервным копиям и каталогу `data/`. После обновления выполняйте `git pull`, установку изменившихся зависимостей и перезапуск только затронутых сервисов.
