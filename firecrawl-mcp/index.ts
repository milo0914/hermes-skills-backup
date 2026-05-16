/**
 * Firecrawl MCP Skill for OpenClaw
 * 
 * Нативная интеграция Firecrawl MCP Server с поддержкой:
 * - STDIO транспорта
 * - Browser automation
 * - Retry logic с exponential backoff
 * - Fallback на HTTP API
 */

import { z } from "zod";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import type { Skill, Tool, ToolContext } from "@openclaw/core";

// ===== Configuration =====
const CONFIG = {
  retry: {
    maxAttempts: 3,
    initialDelay: 1000,
    maxDelay: 10000,
    backoffFactor: 2,
  },
  mcp: {
    command: "npx",
    args: ["-y", "firecrawl-mcp"],
    timeout: 30000,
  },
  http: {
    baseUrl: "https://api.firecrawl.dev/v1",
    timeout: 30000,
  },
};

// ===== Types =====
interface FirecrawlResponse {
  success: boolean;
  data?: any;
  error?: string;
}

interface BrowserSession {
  id: string;
  cdpUrl?: string;
  liveViewUrl?: string;
  createdAt: number;
}

// ===== MCP Client Manager =====
class MCPClientManager {
  private client: Client | null = null;
  private transport: StdioClientTransport | null = null;
  private isConnected = false;
  private connectionPromise: Promise<void> | null = null;

  async connect(): Promise<void> {
    if (this.isConnected) return;
    if (this.connectionPromise) return this.connectionPromise;

    this.connectionPromise = this.doConnect();
    return this.connectionPromise;
  }

  private async doConnect(): Promise<void> {
    try {
      const apiKey = process.env.FIRECRAWL_API_KEY;
      if (!apiKey) {
        throw new Error("FIRECRAWL_API_KEY not set in environment");
      }

      this.transport = new StdioClientTransport({
        command: CONFIG.mcp.command,
        args: CONFIG.mcp.args,
        env: {
          ...process.env,
          FIRECRAWL_API_KEY: apiKey,
          FIRECRAWL_RETRY_MAX_ATTEMPTS: String(CONFIG.retry.maxAttempts),
          FIRECRAWL_RETRY_INITIAL_DELAY: String(CONFIG.retry.initialDelay),
          FIRECRAWL_RETRY_MAX_DELAY: String(CONFIG.retry.maxDelay),
          FIRECRAWL_RETRY_BACKOFF_FACTOR: String(CONFIG.retry.backoffFactor),
        },
      });

      this.client = new Client(
        {
          name: "openclaw-firecrawl-skill",
          version: "1.0.0",
        },
        {
          capabilities: {
            tools: {},
          },
        }
      );

      await this.client.connect(this.transport);
      this.isConnected = true;
      console.log("[INFO] Firecrawl MCP client connected successfully");
    } catch (error) {
      console.error("[ERROR] Failed to connect to Firecrawl MCP:", error);
      this.isConnected = false;
      throw error;
    }
  }

  async callTool(name: string, args: any): Promise<any> {
    await this.connect();
    if (!this.client) throw new Error("MCP client not initialized");

    return this.client.callTool({
      name,
      arguments: args,
    });
  }

  async listTools(): Promise<any> {
    await this.connect();
    if (!this.client) throw new Error("MCP client not initialized");
    return this.client.listTools();
  }

  async disconnect(): Promise<void> {
    if (this.client) {
      await this.client.close();
      this.client = null;
    }
    if (this.transport) {
      await this.transport.close();
      this.transport = null;
    }
    this.isConnected = false;
    this.connectionPromise = null;
  }

  get isHealthy(): boolean {
    return this.isConnected;
  }
}

// ===== HTTP Fallback Client =====
class HTTPFallbackClient {
  private apiKey: string;
  private baseUrl: string;

  constructor() {
    this.apiKey = process.env.FIRECRAWL_API_KEY || "";
    this.baseUrl = process.env.FIRECRAWL_API_URL || CONFIG.http.baseUrl;

    if (!this.apiKey) {
      throw new Error("FIRECRAWL_API_KEY not set");
    }
  }

  private async request(endpoint: string, method: string, body?: any): Promise<any> {
    const url = `${this.baseUrl}${endpoint}`;
    const response = await fetch(url, {
      method,
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${this.apiKey}`,
      },
      body: body ? JSON.stringify(body) : undefined,
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`HTTP ${response.status}: ${error}`);
    }

    return response.json();
  }

  async scrape(url: string, options: any = {}): Promise<any> {
    return this.request("/scrape", "POST", { url, ...options });
  }

  async batchScrape(urls: string[], options: any = {}): Promise<any> {
    return this.request("/batch/scrape", "POST", { urls, ...options });
  }

  async crawl(url: string, options: any = {}): Promise<any> {
    return this.request("/crawl", "POST", { url, ...options });
  }

  async checkCrawlStatus(id: string): Promise<any> {
    return this.request(`/crawl/${id}`, "GET");
  }

  async map(url: string, options: any = {}): Promise<any> {
    return this.request("/map", "POST", { url, ...options });
  }

  async search(query: string, options: any = {}): Promise<any> {
    return this.request("/search", "POST", { query, ...options });
  }

  async extract(urls: string[], options: any = {}): Promise<any> {
    return this.request("/extract", "POST", { urls, ...options });
  }
}

// ===== Retry Utility =====
async function withRetry<T>(
  operation: () => Promise<T>,
  context: string
): Promise<T> {
  let lastError: Error | null = null;
  let delay = CONFIG.retry.initialDelay;

  for (let attempt = 1; attempt <= CONFIG.retry.maxAttempts; attempt++) {
    try {
      console.log(`[INFO] ${context} - attempt ${attempt}/${CONFIG.retry.maxAttempts}`);
      return await operation();
    } catch (error) {
      lastError = error as Error;
      console.warn(`[WARNING] ${context} failed (attempt ${attempt}): ${lastError.message}`);

      if (attempt < CONFIG.retry.maxAttempts) {
        console.log(`[INFO] Retrying in ${delay}ms...`);
        await new Promise((resolve) => setTimeout(resolve, delay));
        delay = Math.min(delay * CONFIG.retry.backoffFactor, CONFIG.retry.maxDelay);
      }
    }
  }

  throw lastError || new Error(`${context} failed after ${CONFIG.retry.maxAttempts} attempts`);
}

// ===== Global Instances =====
let mcpManager: MCPClientManager | null = null;
let httpClient: HTTPFallbackClient | null = null;

function getMCPManager(): MCPClientManager {
  if (!mcpManager) {
    mcpManager = new MCPClientManager();
  }
  return mcpManager;
}

function getHTTPClient(): HTTPFallbackClient {
  if (!httpClient) {
    httpClient = new HTTPFallbackClient();
  }
  return httpClient;
}

// ===== Tool Definitions =====

const searchSchema = z.object({
  query: z.string().describe("Search query"),
  limit: z.number().min(1).max(10).optional().describe("Number of results (1-10)"),
  lang: z.string().optional().describe("Language code (en, ru, etc.)"),
  country: z.string().optional().describe("Country code (us, ru, etc.)"),
  scrapeOptions: z.object({
    formats: z.array(z.enum(["markdown", "html", "screenshot"])).optional(),
    onlyMainContent: z.boolean().optional(),
  }).optional(),
});

const scrapeSchema = z.object({
  url: z.string().url().describe("URL to scrape"),
  formats: z.array(z.enum(["markdown", "json", "html", "branding"])).optional().describe("Output formats"),
  onlyMainContent: z.boolean().default(true).describe("Extract only main content"),
  includeTags: z.array(z.string()).optional().describe("Include only these tags"),
  excludeTags: z.array(z.string()).optional().describe("Exclude these tags"),
  headers: z.record(z.string()).optional().describe("Custom HTTP headers"),
  waitFor: z.number().optional().describe("Wait time in ms before scraping"),
  schema: z.object({}).optional().describe("JSON schema for structured extraction"),
});

const batchScrapeSchema = z.object({
  urls: z.array(z.string().url()).describe("URLs to scrape"),
  options: z.object({
    formats: z.array(z.enum(["markdown", "json", "html"])).optional(),
    onlyMainContent: z.boolean().optional(),
  }).optional(),
});

const crawlSchema = z.object({
  url: z.string().url().describe("Starting URL"),
  maxDepth: z.number().min(1).max(10).default(2).describe("Maximum crawl depth"),
  limit: z.number().min(1).max(1000).default(10).describe("Page limit"),
  allowExternalLinks: z.boolean().default(false).describe("Allow external links"),
  deduplicateSimilarURLs: z.boolean().default(true).describe("Deduplicate similar URLs"),
});

const mapSchema = z.object({
  url: z.string().url().describe("Website URL to map"),
  search: z.string().optional().describe("Search filter"),
});

const extractSchema = z.object({
  urls: z.array(z.string().url()).describe("URLs to extract from"),
  prompt: z.string().optional().describe("Extraction prompt"),
  systemPrompt: z.string().optional().describe("System prompt"),
  schema: z.object({}).optional().describe("JSON schema for structured output"),
  allowExternalLinks: z.boolean().default(false),
  enableWebSearch: z.boolean().default(false),
});

const browserCreateSchema = z.object({
  ttl: z.number().min(30).max(3600).optional().describe("Session lifetime in seconds"),
  activityTtl: z.number().min(10).max(3600).optional().describe("Idle timeout in seconds"),
  streamWebView: z.boolean().optional().describe("Enable live view streaming"),
  profile: z.object({
    name: z.string(),
    saveChanges: z.boolean().default(true),
  }).optional().describe("Profile for state persistence"),
});

const browserExecuteSchema = z.object({
  sessionId: z.string().describe("Browser session ID"),
  code: z.string().describe("Code to execute"),
  language: z.enum(["bash", "python", "javascript"]).default("bash").describe("Language"),
});

const browserClickSchema = z.object({
  sessionId: z.string().describe("Browser session ID"),
  selector: z.string().describe("CSS selector or @ref"),
  x: z.number().optional().describe("X coordinate"),
  y: z.number().optional().describe("Y coordinate"),
});

const browserTypeSchema = z.object({
  sessionId: z.string().describe("Browser session ID"),
  selector: z.string().describe("CSS selector"),
  text: z.string().describe("Text to type"),
  submit: z.boolean().default(false).describe("Press Enter after typing"),
});

const browserScrollSchema = z.object({
  sessionId: z.string().describe("Browser session ID"),
  direction: z.enum(["up", "down", "left", "right"]).describe("Scroll direction"),
  amount: z.number().default(1).describe("Scroll amount"),
});

const browserScreenshotSchema = z.object({
  sessionId: z.string().describe("Browser session ID"),
  fullPage: z.boolean().default(false).describe("Capture full page"),
  selector: z.string().optional().describe("Element selector"),
});

const browserWaitSchema = z.object({
  sessionId: z.string().describe("Browser session ID"),
  selector: z.string().optional().describe("Element to wait for"),
  time: z.number().optional().describe("Time to wait in ms"),
});

const browserDeleteSchema = z.object({
  sessionId: z.string().describe("Browser session ID to delete"),
});

const checkStatusSchema = z.object({
  id: z.string().describe("Operation ID"),
});

// ===== Tool Handlers =====

async function handleSearch(args: z.infer<typeof searchSchema>): Promise<string> {
  return withRetry(async () => {
    try {
      const manager = getMCPManager();
      const result = await manager.callTool("firecrawl_search", args);
      return JSON.stringify(result, null, 2);
    } catch (mcpError) {
      console.log("[INFO] MCP failed, falling back to HTTP API");
      const client = getHTTPClient();
      const result = await client.search(args.query, args);
      return JSON.stringify(result, null, 2);
    }
  }, "firecrawl_search");
}

async function handleScrape(args: z.infer<typeof scrapeSchema>): Promise<string> {
  return withRetry(async () => {
    try {
      const manager = getMCPManager();
      const result = await manager.callTool("firecrawl_scrape", args);
      return JSON.stringify(result, null, 2);
    } catch (mcpError) {
      console.log("[INFO] MCP failed, falling back to HTTP API");
      const client = getHTTPClient();
      const { schema, ...rest } = args;
      const result = await client.scrape(args.url, rest);
      return JSON.stringify(result, null, 2);
    }
  }, "firecrawl_scrape");
}

async function handleBatchScrape(args: z.infer<typeof batchScrapeSchema>): Promise<string> {
  return withRetry(async () => {
    try {
      const manager = getMCPManager();
      const result = await manager.callTool("firecrawl_batch_scrape", args);
      return JSON.stringify(result, null, 2);
    } catch (mcpError) {
      console.log("[INFO] MCP failed, falling back to HTTP API");
      const client = getHTTPClient();
      const result = await client.batchScrape(args.urls, args.options);
      return JSON.stringify(result, null, 2);
    }
  }, "firecrawl_batch_scrape");
}

async function handleCrawl(args: z.infer<typeof crawlSchema>): Promise<string> {
  return withRetry(async () => {
    try {
      const manager = getMCPManager();
      const result = await manager.callTool("firecrawl_crawl", args);
      return JSON.stringify(result, null, 2);
    } catch (mcpError) {
      console.log("[INFO] MCP failed, falling back to HTTP API");
      const client = getHTTPClient();
      const result = await client.crawl(args.url, args);
      return JSON.stringify(result, null, 2);
    }
  }, "firecrawl_crawl");
}

async function handleMap(args: z.infer<typeof mapSchema>): Promise<string> {
  return withRetry(async () => {
    try {
      const manager = getMCPManager();
      const result = await manager.callTool("firecrawl_map", args);
      return JSON.stringify(result, null, 2);
    } catch (mcpError) {
      console.log("[INFO] MCP failed, falling back to HTTP API");
      const client = getHTTPClient();
      const result = await client.map(args.url, args);
      return JSON.stringify(result, null, 2);
    }
  }, "firecrawl_map");
}

async function handleExtract(args: z.infer<typeof extractSchema>): Promise<string> {
  return withRetry(async () => {
    const manager = getMCPManager();
    const result = await manager.callTool("firecrawl_extract", args);
    return JSON.stringify(result, null, 2);
  }, "firecrawl_extract");
}

async function handleBrowserCreate(args: z.infer<typeof browserCreateSchema>): Promise<string> {
  return withRetry(async () => {
    const manager = getMCPManager();
    const result = await manager.callTool("firecrawl_browser_create", args);
    return JSON.stringify(result, null, 2);
  }, "firecrawl_browser_create");
}

async function handleBrowserExecute(args: z.infer<typeof browserExecuteSchema>): Promise<string> {
  return withRetry(async () => {
    const manager = getMCPManager();
    const result = await manager.callTool("firecrawl_browser_execute", args);
    return JSON.stringify(result, null, 2);
  }, "firecrawl_browser_execute");
}

async function handleBrowserClick(args: z.infer<typeof browserClickSchema>): Promise<string> {
  return withRetry(async () => {
    const manager = getMCPManager();
    const code = `agent-browser click ${args.selector}`;
    const result = await manager.callTool("firecrawl_browser_execute", {
      sessionId: args.sessionId,
      code,
      language: "bash",
    });
    return JSON.stringify(result, null, 2);
  }, "firecrawl_browser_click");
}

async function handleBrowserType(args: z.infer<typeof browserTypeSchema>): Promise<string> {
  return withRetry(async () => {
    const manager = getMCPManager();
    const code = `agent-browser type ${args.selector} "${args.text}"${args.submit ? " --submit" : ""}`;
    const result = await manager.callTool("firecrawl_browser_execute", {
      sessionId: args.sessionId,
      code,
      language: "bash",
    });
    return JSON.stringify(result, null, 2);
  }, "firecrawl_browser_type");
}

async function handleBrowserScroll(args: z.infer<typeof browserScrollSchema>): Promise<string> {
  return withRetry(async () => {
    const manager = getMCPManager();
    const code = `agent-browser scroll ${args.direction} ${args.amount}`;
    const result = await manager.callTool("firecrawl_browser_execute", {
      sessionId: args.sessionId,
      code,
      language: "bash",
    });
    return JSON.stringify(result, null, 2);
  }, "firecrawl_browser_scroll");
}

async function handleBrowserScreenshot(args: z.infer<typeof browserScreenshotSchema>): Promise<string> {
  return withRetry(async () => {
    const manager = getMCPManager();
    const code = args.fullPage 
      ? "agent-browser screenshot --full-page" 
      : `agent-browser screenshot${args.selector ? ` ${args.selector}` : ""}`;
    const result = await manager.callTool("firecrawl_browser_execute", {
      sessionId: args.sessionId,
      code,
      language: "bash",
    });
    return JSON.stringify(result, null, 2);
  }, "firecrawl_browser_screenshot");
}

async function handleBrowserWait(args: z.infer<typeof browserWaitSchema>): Promise<string> {
  return withRetry(async () => {
    const manager = getMCPManager();
    let code: string;
    if (args.selector) {
      code = `agent-browser wait-for ${args.selector}`;
    } else if (args.time) {
      code = `agent-browser wait ${args.time}`;
    } else {
      throw new Error("Either selector or time must be provided");
    }
    const result = await manager.callTool("firecrawl_browser_execute", {
      sessionId: args.sessionId,
      code,
      language: "bash",
    });
    return JSON.stringify(result, null, 2);
  }, "firecrawl_browser_wait");
}

async function handleBrowserDelete(args: z.infer<typeof browserDeleteSchema>): Promise<string> {
  return withRetry(async () => {
    const manager = getMCPManager();
    const result = await manager.callTool("firecrawl_browser_delete", args);
    return JSON.stringify(result, null, 2);
  }, "firecrawl_browser_delete");
}

async function handleCheckCrawlStatus(args: z.infer<typeof checkStatusSchema>): Promise<string> {
  return withRetry(async () => {
    try {
      const manager = getMCPManager();
      const result = await manager.callTool("firecrawl_check_crawl_status", args);
      return JSON.stringify(result, null, 2);
    } catch (mcpError) {
      console.log("[INFO] MCP failed, falling back to HTTP API");
      const client = getHTTPClient();
      const result = await client.checkCrawlStatus(args.id);
      return JSON.stringify(result, null, 2);
    }
  }, "firecrawl_check_crawl_status");
}

async function handleCheckBatchStatus(args: z.infer<typeof checkStatusSchema>): Promise<string> {
  return withRetry(async () => {
    const manager = getMCPManager();
    const result = await manager.callTool("firecrawl_check_batch_status", args);
    return JSON.stringify(result, null, 2);
  }, "firecrawl_check_batch_status");
}

// ===== Skill Export =====

const skill: Skill = {
  name: "firecrawl_mcp",
  description: "Firecrawl MCP integration with web scraping, crawling, and browser automation",

  tools: [
    {
      name: "firecrawl_search",
      description: "Search the web and extract content from results",
      schema: searchSchema,
      handler: handleSearch,
    },
    {
      name: "firecrawl_scrape",
      description: "Scrape a single URL with advanced options",
      schema: scrapeSchema,
      handler: handleScrape,
    },
    {
      name: "firecrawl_batch_scrape",
      description: "Batch scrape multiple URLs efficiently",
      schema: batchScrapeSchema,
      handler: handleBatchScrape,
    },
    {
      name: "firecrawl_crawl",
      description: "Crawl a website with configurable depth and limits",
      schema: crawlSchema,
      handler: handleCrawl,
    },
    {
      name: "firecrawl_map",
      description: "Map a website to discover all URLs",
      schema: mapSchema,
      handler: handleMap,
    },
    {
      name: "firecrawl_extract",
      description: "Extract structured data using LLM",
      schema: extractSchema,
      handler: handleExtract,
    },
    {
      name: "firecrawl_browser_create",
      description: "Create a browser session for interactive automation",
      schema: browserCreateSchema,
      handler: handleBrowserCreate,
    },
    {
      name: "firecrawl_browser_execute",
      description: "Execute code in a browser session",
      schema: browserExecuteSchema,
      handler: handleBrowserExecute,
    },
    {
      name: "firecrawl_browser_click",
      description: "Click an element in the browser",
      schema: browserClickSchema,
      handler: handleBrowserClick,
    },
    {
      name: "firecrawl_browser_type",
      description: "Type text into an input field",
      schema: browserTypeSchema,
      handler: handleBrowserType,
    },
    {
      name: "firecrawl_browser_scroll",
      description: "Scroll the page",
      schema: browserScrollSchema,
      handler: handleBrowserScroll,
    },
    {
      name: "firecrawl_browser_screenshot",
      description: "Take a screenshot",
      schema: browserScreenshotSchema,
      handler: handleBrowserScreenshot,
    },
    {
      name: "firecrawl_browser_wait",
      description: "Wait for an element or time",
      schema: browserWaitSchema,
      handler: handleBrowserWait,
    },
    {
      name: "firecrawl_browser_delete",
      description: "Delete a browser session",
      schema: browserDeleteSchema,
      handler: handleBrowserDelete,
    },
    {
      name: "firecrawl_check_crawl_status",
      description: "Check the status of a crawl job",
      schema: checkStatusSchema,
      handler: handleCheckCrawlStatus,
    },
    {
      name: "firecrawl_check_batch_status",
      description: "Check the status of a batch scrape job",
      schema: checkStatusSchema,
      handler: handleCheckBatchStatus,
    },
  ],

  async onLoad() {
    console.log("[INFO] Firecrawl MCP Skill loaded");

    // Validate environment
    if (!process.env.FIRECRAWL_API_KEY) {
      console.error("[ERROR] FIRECRAWL_API_KEY not set!");
      console.error("[ERROR] Please set FIRECRAWL_API_KEY in your environment");
    } else {
      console.log("[INFO] FIRECRAWL_API_KEY is configured");
    }
  },

  async onUnload() {
    console.log("[INFO] Firecrawl MCP Skill unloading...");
    if (mcpManager) {
      await mcpManager.disconnect();
      mcpManager = null;
    }
  },
};

export default skill;
