# Firecrawl MCP Skill - Инструкция по установке

## Быстрая установка

### Шаг 1: Создание директории скилла

```bash
mkdir -p /home/deploy/workspace/skills/firecrawl_mcp
cd /home/deploy/workspace/skills/firecrawl_mcp
```

### Шаг 2: Создание файлов

Скопируйте содержимое файлов из этого архива:
- `SKILL.md` — документация скилла
- `index.ts` — основной код интеграции
- `mcp.json` — конфигурация MCP сервера
- `package.json` — зависимости npm
- `tsconfig.json` — конфигурация TypeScript

### Шаг 3: Установка зависимостей

```bash
npm install
```

### Шаг 4: Настройка переменных окружения

**Важно:** API ключ должен быть доступен в окружении OpenClaw Gateway!

Отредактируйте `/home/deploy/openclaw/.env` (или docker-compose.yml):

```bash
# Добавьте в .env файл
FIRECRAWL_API_KEY=fc-your-actual-api-key-here
```

Или в `docker-compose.yml` для Gateway:

```yaml
services:
  openclaw-gateway:
    environment:
      - FIRECRAWL_API_KEY=fc-your-actual-api-key-here
      - FIRECRAWL_RETRY_MAX_ATTEMPTS=3
      - FIRECRAWL_RETRY_INITIAL_DELAY=1000
```

### Шаг 5: Перезапуск Gateway

```bash
cd /home/deploy/openclaw
docker compose restart
```

### Шаг 6: Проверка

В OpenClaw CLI или Telegram боте:

```
Проверь статус firecrawl скилла
```

Или:

```
Используй firecrawl_search для поиска "OpenClaw documentation"
```

## Структура файлов

```
/home/deploy/workspace/skills/firecrawl_mcp/
├── SKILL.md              # Документация
├── index.ts              # Код интеграции MCP
├── mcp.json              # Конфигурация MCP
├── package.json          # Зависимости
├── tsconfig.json         # TypeScript config
└── node_modules/         # Установленные пакеты
```

## Проверка конфигурации

### Проверка переменных окружения

```bash
# Внутри контейнера Gateway
docker exec -it openclaw-openclaw-gateway-1 /bin/sh
echo $FIRECRAWL_API_KEY
```

Должен вывести ваш API ключ.

### Проверка MCP сервера

```bash
# Запуск MCP сервера вручную
docker exec -it openclaw-openclaw-gateway-1 /bin/sh
env FIRECRAWL_API_KEY=your-key npx -y firecrawl-mcp
```

Если запускается без ошибок — всё настроено правильно.

## Использование

### Примеры команд

1. **Поиск:**
```
Поищи информацию о "Python async/await" используя firecrawl_search
```

2. **Скрапинг:**
```
Скрапь https://docs.python.org/3/library/asyncio.html и получи основной контент
```

3. **Браузерная автоматизация:**
```
Создай браузерную сессию, открой https://example.com, сделай скриншот
```

4. **Краулинг:**
```
Крауль https://docs.python.org/3/library/ с глубиной 2 и лимитом 20 страниц
```

## Устранение неполадок

### Ошибка: "FIRECRAWL_API_KEY not set"

**Решение:**
1. Проверьте, что ключ добавлен в `.env` файл
2. Убедитесь, что `.env` файл подключен в docker-compose.yml:
   ```yaml
   env_file:
     - .env
   ```
3. Перезапустите контейнеры: `docker compose restart`

### Ошибка: "MCP client not initialized"

**Решение:**
1. Проверьте, что Node.js доступен в контейнере
2. Проверьте подключение к интернету
3. Проверьте логи: `docker logs openclaw-openclaw-gateway-1`

### Ошибка: "Rate limit exceeded"

**Решение:**
- Скилл автоматически делает retry с exponential backoff
- Увеличьте задержки в конфигурации
- Рассмотрите upgrade тарифа Firecrawl

### Fallback на HTTP API

Если MCP недоступен, скилл автоматически переключается на HTTP API. 
Проверьте логи для подтверждения:
```
[INFO] MCP failed, falling back to HTTP API
```

## Безопасность

- API ключ никогда не хардкодится в файлах
- Ключ берется только из переменных окружения
- Все запросы логируются (без ключа)
- Поддержка self-hosted Firecrawl

## Обновление

```bash
cd /home/deploy/workspace/skills/firecrawl_mcp
npm update
# Перезапустите Gateway
docker compose restart
```

## Полезные ссылки

- Firecrawl Docs: https://docs.firecrawl.dev
- MCP Server GitHub: https://github.com/firecrawl/firecrawl-mcp-server
- OpenClaw Skills Docs: https://docs.openclaw.ai/skills
