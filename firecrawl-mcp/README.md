# 🔥 Firecrawl MCP Skill для OpenClaw

Полноценная интеграция Firecrawl MCP Server с OpenClaw, включающая веб-скрапинг, краулинг, поиск и браузерную автоматизацию.

## 📦 Включенные файлы

| Файл | Описание | Размер |
|------|----------|--------|
| `SKILL.md` | Полная документация скилла | 13.7 KB |
| `index.ts` | Нативная интеграция MCP (TypeScript) | 22.4 KB |
| `mcp.json` | Конфигурация MCP сервера | 882 B |
| `package.json` | Зависимости npm | 1.1 KB |
| `tsconfig.json` | Конфигурация TypeScript | 493 B |
| `SETUP.md` | Инструкция по установке | 5.3 KB |
| `EXAMPLES.md` | Примеры использования | 8.1 KB |

## ✨ Ключевые возможности

### MCP Интеграция
- ✅ STDIO транспорт для связи с Firecrawl MCP Server
- ✅ Автозапуск через `npx -y firecrawl-mcp`
- ✅ Автоматический fallback на HTTP API при недоступности MCP
- ✅ Retry logic с exponential backoff (3 попытки)

### Веб-скрапинг
- ✅ **firecrawl_search** — поиск с извлечением контента
- ✅ **firecrawl_scrape** — скрапинг одной страницы
- ✅ **firecrawl_batch_scrape** — пакетный скрапинг
- ✅ **firecrawl_crawl** — краулинг сайта
- ✅ **firecrawl_map** — картирование сайта
- ✅ **firecrawl_extract** — LLM-извлечение данных

### Браузерная автоматизация
- ✅ **firecrawl_browser_create** — создание сессии
- ✅ **firecrawl_browser_execute** — выполнение команд
- ✅ **firecrawl_browser_click** — клик по элементу
- ✅ **firecrawl_browser_type** — ввод текста
- ✅ **firecrawl_browser_scroll** — прокрутка
- ✅ **firecrawl_browser_screenshot** — скриншоты
- ✅ **firecrawl_browser_wait** — ожидание
- ✅ **firecrawl_browser_delete** — удаление сессии

### Безопасность
- 🔒 API ключ только из переменных окружения (`FIRECRAWL_API_KEY`)
- 🔒 Нет хардкодов в коде
- 🔒 Поддержка self-hosted Firecrawl
- 🔒 Логирование без раскрытия ключа

## 🚀 Быстрый старт

### 1. Установка

```bash
cd /home/deploy/workspace/skills/
mkdir -p firecrawl_mcp
cd firecrawl_mcp

# Скопируйте все файлы из этого архива
npm install
```

### 2. Настройка окружения

В `/home/deploy/openclaw/.env` добавьте:

```bash
FIRECRAWL_API_KEY=fc-your-actual-api-key-here
```

Или в `docker-compose.yml`:

```yaml
services:
  openclaw-gateway:
    environment:
      - FIRECRAWL_API_KEY=fc-your-actual-api-key-here
```

### 3. Перезапуск

```bash
cd /home/deploy/openclaw
docker compose restart
```

## 📖 Примеры использования

### Поиск

```
Поищи "Python async/await best practices" используя firecrawl_search
```

### Скрапинг

```
Скрапь https://example.com и извлеки заголовок и описание в JSON
```

### Браузерная автоматизация

```
Создай браузерную сессию, открой https://example.com, 
введи "test@example.com" в поле #email, 
кликни по #submit, сделай скриншот
```

### Краулинг

```
Крауль https://docs.python.org/3/library/ с глубиной 2 и лимитом 30 страниц
```

## 🔧 Конфигурация MCP

Файл `mcp.json`:

```json
{
  "mcpServers": {
    "firecrawl": {
      "command": "npx",
      "args": ["-y", "firecrawl-mcp"],
      "transport": "stdio",
      "env": {
        "FIRECRAWL_API_KEY": "${FIRECRAWL_API_KEY}",
        "FIRECRAWL_RETRY_MAX_ATTEMPTS": "3",
        "FIRECRAWL_RETRY_INITIAL_DELAY": "1000",
        "FIRECRAWL_RETRY_MAX_DELAY": "10000",
        "FIRECRAWL_RETRY_BACKOFF_FACTOR": "2"
      },
      "autoStart": true
    }
  }
}
```

## 📊 Оптимизация затрат

| Стратегия | Экономия |
|-----------|----------|
| `onlyMainContent: true` | ~40% токенов |
| JSON вместо markdown | ~60% токенов |
| Batch скрапинг | ~30% времени |
| Fallback на HTTP | бесплатно при сбое MCP |

## 🛠️ Технические детали

### Архитектура

```
OpenClaw Agent
    ↓
Skill: firecrawl_mcp (index.ts)
    ↓
MCP Client (STDIO)
    ↓
Firecrawl MCP Server (npx)
    ↓
Firecrawl API
```

### Fallback механизм

```
MCP запрос → Ошибка → HTTP API запрос → Результат
                ↓
            [Логирование]
```

### Retry логика

- Попытка 1: сразу
- Попытка 2: через 1 сек
- Попытка 3: через 2 сек
- Максимальная задержка: 10 сек

## 🐛 Отладка

### Проверка MCP соединения

```bash
docker exec -it openclaw-openclaw-gateway-1 /bin/sh
env FIRECRAWL_API_KEY=your-key npx -y firecrawl-mcp
```

### Просмотр логов

```bash
docker logs openclaw-openclaw-gateway-1 | grep -i firecrawl
```

### Проверка переменных окружения

```bash
docker exec openclaw-openclaw-gateway-1 env | grep FIRECRAWL
```

## 📚 Документация

- [Firecrawl Docs](https://docs.firecrawl.dev)
- [Firecrawl MCP Server](https://github.com/firecrawl/firecrawl-mcp-server)
- [OpenClaw Skills](https://docs.openclaw.ai/skills)
- [MCP Protocol](https://modelcontextprotocol.io)

## 🤝 Вклад в проект

Этот скилл создан для сообщества OpenClaw. Приветствуются:
- Pull requests
- Issue reports
- Улучшения документации

## 📝 Лицензия

MIT License — свободное использование в любых проектах.

---

**Создано для OpenClaw на Hetzner VPS** | **Версия 1.0.0**
