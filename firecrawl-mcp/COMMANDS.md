# Firecrawl MCP Skill - Шпаргалка команд

## 🔍 Поиск

### Базовый поиск
```
firecrawl_search query="Python web scraping" limit=5
```

### Поиск с извлечением контента
```
firecrawl_search query="async/await JavaScript" limit=3 scrapeOptions.formats=["markdown"]
```

### Поиск на русском
```
firecrawl_search query="парсинг сайтов Python" lang="ru" country="ru" limit=5
```

## 📝 Скрапинг

### Простой скрапинг
```
firecrawl_scrape url="https://example.com" formats=["markdown"]
```

### Скрапинг только основного контента
```
firecrawl_scrape url="https://example.com/article" onlyMainContent=true formats=["markdown"]
```

### JSON извлечение
```
firecrawl_scrape url="https://shop.example.com/product" formats=["json"] schema={"type":"object","properties":{"name":{"type":"string"},"price":{"type":"number"}}}
```

### С ожиданием загрузки JS
```
firecrawl_scrape url="https://spa.example.com" waitFor=3000 onlyMainContent=true
```

### С кастомными заголовками
```
firecrawl_scrape url="https://api.example.com" headers={"Authorization":"Bearer token"}
```

## 🕷️ Пакетный скрапинг

### Несколько URL
```
firecrawl_batch_scrape urls=["https://a.com","https://b.com"] options.formats=["markdown"]
```

### Проверка статуса
```
firecrawl_check_batch_status id="batch_123"
```

## 🌐 Краулинг

### Базовый краул
```
firecrawl_crawl url="https://example.com" maxDepth=2 limit=10
```

### С ограничениями
```
firecrawl_crawl url="https://blog.example.com" maxDepth=1 limit=50 allowExternalLinks=false
```

### Проверка статуса
```
firecrawl_check_crawl_status id="crawl_123"
```

## 🗺️ Картирование

### Все URL сайта
```
firecrawl_map url="https://example.com"
```

### С фильтром
```
firecrawl_map url="https://example.com" search="*.pdf"
```

## 🤖 LLM Извлечение

### С промптом
```
firecrawl_extract urls=["https://a.com","https://b.com"] prompt="Extract company name and email"
```

### Со схемой
```
firecrawl_extract urls=["https://example.com"] schema={"type":"object","properties":{"title":{"type":"string"},"author":{"type":"string"}}} systemPrompt="Extract article metadata"
```

## 🌐 Браузерная автоматизация

### Создание сессии
```
firecrawl_browser_create ttl=600 profile={"name":"session1","saveChanges":true}
```

### Выполнение команд (bash)
```
firecrawl_browser_execute sessionId="sess_123" code="agent-browser open https://example.com" language="bash"
```

### Клик
```
firecrawl_browser_click sessionId="sess_123" selector="#button"
```

### Ввод текста
```
firecrawl_browser_type sessionId="sess_123" selector="#email" text="test@example.com" submit=true
```

### Прокрутка
```
firecrawl_browser_scroll sessionId="sess_123" direction="down" amount=3
```

### Скриншот
```
firecrawl_browser_screenshot sessionId="sess_123" fullPage=true
```

### Ожидание
```
firecrawl_browser_wait sessionId="sess_123" time=3000
```

### Ожидание элемента
```
firecrawl_browser_wait sessionId="sess_123" selector=".loaded"
```

### Удаление сессии
```
firecrawl_browser_delete sessionId="sess_123"
```

## 🔧 Сложные сценарии

### Авторизация + скрапинг
```
1. firecrawl_browser_create → sessionId
2. firecrawl_browser_execute sessionId code="agent-browser open https://login.com"
3. firecrawl_browser_type sessionId selector="#user" text="admin"
4. firecrawl_browser_type sessionId selector="#pass" text="secret" submit=true
5. firecrawl_browser_wait sessionId time=2000
6. firecrawl_browser_execute sessionId code="agent-browser open https://protected.com"
7. firecrawl_browser_screenshot sessionId fullPage=true
8. firecrawl_browser_delete sessionId
```

### Поиск → Пакетный скрапинг
```
1. firecrawl_search query="topic" limit=10 → urls
2. firecrawl_batch_scrape urls options.formats=["json"]
```

### Краулинг + мониторинг
```
1. firecrawl_crawl url="https://site.com" maxDepth=2 limit=100
2. [wait 5 min]
3. firecrawl_check_crawl_status id="crawl_id"
```

## 💡 Оптимизация

### Экономия токенов
```
firecrawl_scrape url="..." onlyMainContent=true excludeTags=["nav","footer",".ads"]
```

### Batch для скорости
```
firecrawl_batch_scrape urls=[url1,url2,url3,url4,url5] options.onlyMainContent=true
```

## ⚠️ Обработка ошибок

Если MCP недоступен, скилл автоматически использует HTTP API. 
Проверьте логи: `docker logs openclaw-openclaw-gateway-1 | grep firecrawl`
