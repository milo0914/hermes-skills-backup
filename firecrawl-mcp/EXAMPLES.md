# Firecrawl MCP Skill - Примеры использования

## Базовые примеры

### 1. Поиск с извлечением контента

```typescript
// Поиск информации о Python
const result = await tools.firecrawl_search({
  query: "Python web scraping best practices 2024",
  limit: 5,
  lang: "en",
  scrapeOptions: {
    formats: ["markdown"],
    onlyMainContent: true
  }
});
```

### 2. Скрапинг с JSON извлечением

```typescript
// Извлечение данных о продукте
const result = await tools.firecrawl_scrape({
  url: "https://example.com/product",
  formats: ["json"],
  onlyMainContent: true,
  schema: {
    type: "object",
    properties: {
      name: { type: "string" },
      price: { type: "number" },
      description: { type: "string" },
      features: { type: "array", items: { type: "string" } }
    },
    required: ["name", "price"]
  }
});
```

### 3. Пакетный скрапинг

```typescript
// Скрапинг нескольких страниц
const result = await tools.firecrawl_batch_scrape({
  urls: [
    "https://example.com/page1",
    "https://example.com/page2",
    "https://example.com/page3"
  ],
  options: {
    formats: ["markdown"],
    onlyMainContent: true
  }
});
```

### 4. Краулинг сайта

```typescript
// Краулинг блога
const result = await tools.firecrawl_crawl({
  url: "https://example.com/blog",
  maxDepth: 2,
  limit: 50,
  allowExternalLinks: false,
  deduplicateSimilarURLs: true
});

// Проверка статуса
const status = await tools.firecrawl_check_crawl_status({
  id: result.id
});
```

### 5. Картирование сайта

```typescript
// Получение всех URL
const result = await tools.firecrawl_map({
  url: "https://example.com",
  search: "*.pdf"  // только PDF файлы
});
```

## Браузерная автоматизация

### 6. Создание сессии

```typescript
const session = await tools.firecrawl_browser_create({
  ttl: 600,  // 10 минут
  activityTtl: 60,  // 1 минута бездействия
  profile: {
    name: "my-session",
    saveChanges: true
  }
});

const sessionId = session.sessionId;
```

### 7. Навигация и скриншот

```typescript
// Открытие страницы
await tools.firecrawl_browser_execute({
  sessionId,
  code: "agent-browser open https://example.com",
  language: "bash"
});

// Скриншот
await tools.firecrawl_browser_screenshot({
  sessionId,
  fullPage: true
});
```

### 8. Форма входа

```typescript
// Заполнение формы
await tools.firecrawl_browser_type({
  sessionId,
  selector: "#email",
  text: "user@example.com"
});

await tools.firecrawl_browser_type({
  sessionId,
  selector: "#password",
  text: "secretpassword"
});

// Клик по кнопке
await tools.firecrawl_browser_click({
  sessionId,
  selector: "#login-button"
});

// Ожидание загрузки
await tools.firecrawl_browser_wait({
  sessionId,
  time: 3000
});
```

### 9. Скроллинг

```typescript
// Прокрутка вниз
await tools.firecrawl_browser_scroll({
  sessionId,
  direction: "down",
  amount: 3
});

// Прокрутка вверх
await tools.firecrawl_browser_scroll({
  sessionId,
  direction: "up",
  amount: 1
});
```

### 10. Ожидание элемента

```typescript
// Ожидание появления элемента
await tools.firecrawl_browser_wait({
  sessionId,
  selector: ".loaded-content"
});
```

### 11. Удаление сессии

```typescript
await tools.firecrawl_browser_delete({
  sessionId
});
```

## LLM Извлечение данных

### 12. Извлечение с кастомным промптом

```typescript
const result = await tools.firecrawl_extract({
  urls: [
    "https://example.com/article1",
    "https://example.com/article2"
  ],
  prompt: "Extract the main topic, key points, and author name",
  systemPrompt: "You are a data extraction specialist. Be precise and concise.",
  schema: {
    type: "object",
    properties: {
      topic: { type: "string" },
      keyPoints: { type: "array", items: { type: "string" } },
      author: { type: "string" }
    }
  }
});
```

## Сложные сценарии

### 13. Полный pipeline: Поиск → Скрапинг → Анализ

```typescript
// Шаг 1: Поиск
const searchResults = await tools.firecrawl_search({
  query: "best Python web frameworks 2024",
  limit: 5
});

// Шаг 2: Извлечение URL из результатов
const urls = searchResults.data.map(r => r.url);

// Шаг 3: Пакетный скрапинг
const scraped = await tools.firecrawl_batch_scrape({
  urls,
  options: {
    formats: ["markdown"],
    onlyMainContent: true
  }
});

// Шаг 4: Извлечение структурированных данных
const analysis = await tools.firecrawl_extract({
  urls,
  prompt: "Extract framework name, pros, cons, and use cases",
  schema: {
    type: "object",
    properties: {
      frameworks: {
        type: "array",
        items: {
          type: "object",
          properties: {
            name: { type: "string" },
            pros: { type: "array", items: { type: "string" } },
            cons: { type: "array", items: { type: "string" } },
            useCases: { type: "array", items: { type: "string" } }
          }
        }
      }
    }
  }
});
```

### 14. Мониторинг цен с браузером

```typescript
// Создание сессии
const session = await tools.firecrawl_browser_create({
  ttl: 300,
  profile: { name: "price-monitor", saveChanges: true }
});

// Навигация
await tools.firecrawl_browser_execute({
  sessionId: session.sessionId,
  code: "agent-browser open https://shop.example.com/product",
  language: "bash"
});

// Ожидание загрузки цены
await tools.firecrawl_browser_wait({
  sessionId: session.sessionId,
  selector: ".price"
});

// Скрапинг через execute
const priceData = await tools.firecrawl_browser_execute({
  sessionId: session.sessionId,
  code: `agent-browser eval "document.querySelector('.price').textContent"`,
  language: "bash"
});

// Скриншот для проверки
await tools.firecrawl_browser_screenshot({
  sessionId: session.sessionId,
  selector: ".product-card"
});

// Закрытие
await tools.firecrawl_browser_delete({
  sessionId: session.sessionId
});
```

### 15. Обход защиты с кастомными заголовками

```typescript
const result = await tools.firecrawl_scrape({
  url: "https://protected-site.com",
  headers: {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
  },
  waitFor: 5000,  // Ждем 5 секунд для загрузки JS
  onlyMainContent: true
});
```

## Оптимизация

### 16. Только основной контент (экономия токенов)

```typescript
const result = await tools.firecrawl_scrape({
  url: "https://example.com/article",
  formats: ["markdown"],
  onlyMainContent: true,  // Убирает навигацию, футер, рекламу
  excludeTags: ["nav", "footer", "aside", ".ads"]
});
```

### 17. Batch для экономии

```typescript
// Дешевле, чем отдельные scrape
const urls = [
  "https://example.com/1",
  "https://example.com/2",
  // ... 50 URL
];

const result = await tools.firecrawl_batch_scrape({
  urls,
  options: {
    formats: ["json"],
    onlyMainContent: true
  }
});

// Проверка статуса
const status = await tools.firecrawl_check_batch_status({
  id: result.id
});
```

## Обработка ошибок

### 18. Retry с кастомной логикой

```typescript
async function scrapeWithRetry(url: string, maxAttempts = 3) {
  for (let i = 0; i < maxAttempts; i++) {
    try {
      return await tools.firecrawl_scrape({
        url,
        formats: ["markdown"],
        onlyMainContent: true
      });
    } catch (error) {
      if (i === maxAttempts - 1) throw error;
      await new Promise(r => setTimeout(r, 2000 * (i + 1)));
    }
  }
}
```

## Интеграция с OpenClaw

### 19. Использование в SKILL.md

```markdown
---
name: my_research_skill
description: Research skill using Firecrawl
---

# Research Skill

## Tools

Use firecrawl_search to find information:
- Query: research topic
- Limit: 5 results
- Scrape options: markdown, onlyMainContent

## Workflow

1. Search for relevant sources
2. Batch scrape top results
3. Extract structured data
4. Analyze and summarize
```

### 20. Использование в агенте

```typescript
// В коде агента
const firecrawlTools = skillContext.tools.filter(
  t => t.name.startsWith("firecrawl_")
);

// Делегирование задачи
const result = await skillContext.callTool("firecrawl_search", {
  query: userQuery,
  limit: 10
});
```
