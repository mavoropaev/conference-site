# Развёртывание на сервере

Инструкция по развёртыванию на голом Linux-сервере (Debian/Ubuntu) без
Docker: gunicorn за nginx, systemd, права, обновление пакетов. Это описание
процесса, а не отчёт о выполненном развёртывании — реальный сервер под
проект не поднимался; каждая команда проверяется по документации
соответствующего пакета.

Через Docker Compose (для разработки и демонстрации) см. основной
[README](../README.md#как-запустить).

## 1. Подготовка сервера

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.12 python3.12-venv postgresql-16 nginx git
```

Обновление пакетов системы — отдельная регулярная задача
(`apt update && apt upgrade`), не связанная с деплоем самого проекта;
на проде — через окно обслуживания, не «на лету».

### Пользователь для приложения

Проект не должен работать от `root`. Создаём отдельного системного
пользователя без домашнего логина для интерактивного входа:

```bash
sudo useradd --system --home-dir /srv/conference-site --shell /usr/sbin/nologin conference
sudo mkdir -p /srv/conference-site
sudo chown conference:conference /srv/conference-site
```

## 2. База данных

```bash
sudo -u postgres createuser --pwprompt conference
sudo -u postgres createdb --owner=conference conference
```

Пароль — в секрет-хранилище окружения (переменная `POSTGRES_PASSWORD`),
не в репозитории. `pg_hba.conf` должен разрешать подключение только с
`localhost` (приложение и БД на одном сервере) или из подсети приложения,
не `0.0.0.0/0`.

## 3. Код и зависимости

```bash
sudo -u conference git clone <url-репозитория> /srv/conference-site/app
cd /srv/conference-site/app
sudo -u conference python3.12 -m venv /srv/conference-site/venv
sudo -u conference /srv/conference-site/venv/bin/pip install .
```

Обратите внимание: `pip install .` (без `[dev]`) — на проде не нужны pytest
и ruff.

### `.env`

```bash
sudo -u conference cp .env.example /srv/conference-site/app/.env
sudo -u conference chmod 600 /srv/conference-site/app/.env
```

Заполнить `DJANGO_SECRET_KEY` (случайная строка, не из примера), `DJANGO_DEBUG=0`,
`DJANGO_ALLOWED_HOSTS` (домен сайта), параметры БД. Право доступа `600` —
файл с секретами читает только владелец.

## 4. Миграции и статика

```bash
cd /srv/conference-site/app
sudo -u conference /srv/conference-site/venv/bin/python manage.py migrate
sudo -u conference /srv/conference-site/venv/bin/python manage.py compilescss
sudo -u conference /srv/conference-site/venv/bin/python manage.py collectstatic --noinput
```

`compilescss` обязателен до `collectstatic`: в боевом режиме
(`DJANGO_DEBUG=0`) SCSS не компилируется на лету (см.
`SASS_PROCESSOR_ENABLED` в `config/settings.py`), CSS должен быть собран
заранее.

## 5. gunicorn как systemd-сервис

`/etc/systemd/system/conference-site.service`:

```ini
[Unit]
Description=Conference site (gunicorn)
After=network.target postgresql.service

[Service]
User=conference
Group=conference
WorkingDirectory=/srv/conference-site/app
EnvironmentFile=/srv/conference-site/app/.env
ExecStart=/srv/conference-site/venv/bin/gunicorn config.wsgi:application \
    --bind unix:/run/conference-site/gunicorn.sock \
    --workers 3
RuntimeDirectory=conference-site
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

`RuntimeDirectory` создаёт `/run/conference-site` с правами процесса при
каждом запуске — сокет не нужно готовить руками. Число воркеров — по
формуле `2 × ядра + 1`, для маленького сервера 3 разумный старт.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now conference-site
sudo systemctl status conference-site
```

## 6. nginx как обратный прокси

`/etc/nginx/sites-available/conference-site`:

```nginx
server {
    listen 80;
    server_name conference.example.org;

    location /static/ {
        alias /srv/conference-site/app/staticfiles/;
    }

    location /media/ {
        alias /srv/conference-site/app/media/;
    }

    location / {
        proxy_pass http://unix:/run/conference-site/gunicorn.sock;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/conference-site /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

Статику и медиа отдаёт nginx напрямую (быстрее, не грузит gunicorn),
остальное — по сокету в gunicorn.

### HTTPS

Для реального домена — `certbot --nginx`, дальше обновление сертификата
автоматическое (systemd-таймер, ставится вместе с certbot). Без домена
(демонстрация по IP) этот шаг пропускается.

## 7. Обновление кода (следующий деплой)

```bash
cd /srv/conference-site/app
sudo -u conference git pull
sudo -u conference /srv/conference-site/venv/bin/pip install .
sudo -u conference /srv/conference-site/venv/bin/python manage.py migrate
sudo -u conference /srv/conference-site/venv/bin/python manage.py compilescss
sudo -u conference /srv/conference-site/venv/bin/python manage.py collectstatic --noinput
sudo systemctl restart conference-site
```

Кратковременный простой на `restart` есть; для нулевого простоя нужен
второй набор воркеров и переключение nginx между ними — вне минимального
объёма этого проекта.

## 8. Права и файлы

- Весь код и `.venv` — от пользователя `conference`, не `root`.
- `media/` (загруженные файлы заявок) должен быть доступен на запись
  пользователю `conference` и на чтение nginx (обычно `www-data`), но
  закрыт от произвольных пользователей: `chmod 750`.
- `.env` — `600`, читает только владелец.
- Логи gunicorn/nginx — через `journalctl -u conference-site` и
  `/var/log/nginx/`, ротация — штатная (`logrotate`, уже настроен в Debian
  для nginx; для gunicorn под systemd ротирует journald по своим правилам).

## 9. Проверка после деплоя

```bash
sudo systemctl status conference-site nginx postgresql
curl -I http://localhost/
sudo -u conference /srv/conference-site/venv/bin/python manage.py check --deploy
```

`check --deploy` — штатная команда Django, показывает предупреждения
безопасности конкретно для боевого окружения (HTTPS-заголовки, `DEBUG`,
`SECRET_KEY` и т.д.).
