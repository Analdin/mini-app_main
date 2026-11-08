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

До остановки старых процессов сделайте резервную копию каталогов с текущими SQLite-базами и очередями заявок. Не перезаписывайте существующую базу MAX и резервные файлы. Новая база авторизации будет создана отдельно по пути `AUTH_DB_PATH`.

Сначала проверьте текущие unit-файлы и процессы:
```bash
sudo systemctl list-units --type=service | grep -i alfadent
sudo systemctl status alfadent-telegram alfadent-max --no-pager
```
Названия могут отличаться — не останавливайте сервисы по предположению.

## 2. Создать системного пользователя и каталоги

```bash
sudo adduser --system --group --home /opt/alfadent alfadent
sudo mkdir -p /opt/alfadent /var/lib/alfadent/telegram /etc/alfadent
sudo chown -R alfadent:alfadent /opt/alfadent /var/lib/alfadent
sudo chmod 750 /var/lib/alfadent
sudo chmod 750 /etc/alfadent
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip nginx
```

## 3. Получить актуальные исходники

Приватные репозитории клонируйте по SSH-ключу, который имеет read-доступ. Не вставляйте GitHub PAT в URL команды: он попадёт в историю shell.

```bash
sudo -u alfadent git clone --branch release/alfadent-vps-final git@github.com:Analdin/mini-app_main.git /opt/alfadent/mini-app_main
sudo -u alfadent git clone --branch release/alfadent-vps-final git@github.com:Analdin/alfa-dent_max.git /opt/alfadent/alfa-dent_max
```

После проверки и принятия pull request ветки можно заменить на `main`.

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

Ежедневно делайте резервную копию `/var/lib/alfadent` и храните её отдельно от VPS. Не делайте публичный доступ к SQLite, `.env`, логам, резервным копиям и каталогу `data/`. После обновления выполняйте `git pull`, установку изменившихся зависимостей и перезапуск только затронутых сервисов.
