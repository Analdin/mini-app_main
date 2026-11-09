# AlfaDent — Mini App, FastAPI API и Telegram-бот

Это основной репозиторий Mini App:
- `web/miniapp.html`, `web/assets/` — интерфейс, фотографии клиники, карточки врачей и акции;
- `webapp_api.py` — FastAPI API, проверка подписей Telegram/MAX и общая авторизация;
- `bot_telegram.py` — Telegram-бот;
- `deploy/` — systemd/Nginx и инструкция для VPS.

MAX-бот находится в отдельном репозитории: [Analdin/alfa-dent_max](https://github.com/Analdin/alfa-dent_max).

## Авторизация

При первой регистрации API генерирует постоянный пароль. В базе хранится только PBKDF2-HMAC-SHA256 hash с уникальной солью. Вход: российский номер телефона + постоянный пароль. Сессия хранится на сервере в виде хеша токена; Mini App держит токен в sessionStorage текущей вкладки. Telegram и MAX проверяют токен через общий API.

**Ограничение:** SMS или другого независимого подтверждения владения номером нет. Введённый номер сам по себе не доказывает, что он принадлежит пользователю. Не показывайте таким способом медицинские документы и другие чувствительные данные.

## Приватная конфигурация Python

Приложение **не использует .env-файлы и EnvironmentFile**. Токены, Bitrix24 webhook, прокси и общий секрет находятся в приватном файле `alfadent_config.py` из закрытого репозитория [Analdin/alfadent-miniapp](https://github.com/Analdin/alfadent-miniapp).

На VPS этот файл размещается в `/etc/alfadent/alfadent_config.py` и подключается к каталогам обоих проектов символическими ссылками. Не копируйте приватный файл в этот публичный репозиторий, Pull Request, CI, issue или логи.

## Установка

Инструкция переноса на Ubuntu/Debian VPS: [deploy/README_DEPLOY_RU.md](deploy/README_DEPLOY_RU.md).

Запуск API (из каталога репозитория, когда приватный config-файл уже подключён):
```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn webapp_api:app --host 127.0.0.1 --port 8001
```

Telegram-бот запускается командой `python bot_telegram.py`. MAX-бот обслуживается через Nginx на локальном порту 5000.

## Поведение записи

Приложение создаёт обращение/лид в Bitrix24. Подтверждённую запись, реальный свободный слот и визиты из МИС «Инфоклиника» оно не имитирует: время подтверждает администратор клиники.
