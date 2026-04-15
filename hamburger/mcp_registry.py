import httpx
import asyncio
from typing import Any, Optional
from dataclasses import dataclass, field


MCP_OFFICIAL_REGISTRY = "https://registry.modelcontextprotocol.io"
SMITHERY_REGISTRY = "https://registry.smithery.ai"


@dataclass
class MCPServerInfo:
    name: str
    qualified_name: str
    description: str
    source: str
    packages: list[dict[str, Any]] = field(default_factory=list)
    remote: Optional[dict[str, Any]] = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result = {
            "name": self.name,
            "qualified_name": self.qualified_name,
            "description": self.description,
            "source": self.source,
        }
        if self.packages:
            result["packages"] = self.packages
        if self.remote:
            result["remote"] = self.remote
        if self.meta:
            result["meta"] = self.meta
        return result


class MCPRegistryClient:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=15.0)

    async def close(self):
        await self.client.aclose()

    async def search_official_registry(
        self, query: str = "", limit: int = 20, offset: int = 0
    ) -> list[MCPServerInfo]:
        results = []
        try:
            params: dict[str, Any] = {"limit": limit, "offset": offset}
            if query:
                params["search"] = query
            resp = await self.client.get(
                f"{MCP_OFFICIAL_REGISTRY}/v0/servers", params=params
            )
            if resp.status_code == 200:
                data = resp.json()
                servers = data if isinstance(data, list) else data.get("servers", [])
                for srv in servers:
                    results.append(
                        MCPServerInfo(
                            name=srv.get("name", ""),
                            qualified_name=srv.get("id", srv.get("name", "")),
                            description=srv.get("description", ""),
                            source="official",
                            packages=srv.get("packages", []),
                            remote=srv.get("remote"),
                            meta=srv,
                        )
                    )
        except Exception as e:
            print(f"[MCP Registry] Official registry search failed: {e}")
        return results

    async def get_official_server(self, server_id: str) -> Optional[MCPServerInfo]:
        try:
            resp = await self.client.get(
                f"{MCP_OFFICIAL_REGISTRY}/v0/servers/{server_id}"
            )
            if resp.status_code == 200:
                srv = resp.json()
                return MCPServerInfo(
                    name=srv.get("name", ""),
                    qualified_name=srv.get("id", srv.get("name", "")),
                    description=srv.get("description", ""),
                    source="official",
                    packages=srv.get("packages", []),
                    remote=srv.get("remote"),
                    meta=srv,
                )
        except Exception as e:
            print(f"[MCP Registry] Get server detail failed: {e}")
        return None

    async def search_smithery(
        self, query: str = "", limit: int = 20
    ) -> list[MCPServerInfo]:
        results = []
        try:
            params: dict[str, Any] = {"pageSize": limit}
            if query:
                params["q"] = query
            resp = await self.client.get(
                f"{SMITHERY_REGISTRY}/v1/servers", params=params
            )
            if resp.status_code == 200:
                data = resp.json()
                servers = data if isinstance(data, list) else data.get("servers", [])
                for srv in servers:
                    results.append(
                        MCPServerInfo(
                            name=srv.get("name", ""),
                            qualified_name=srv.get("qualifiedName", srv.get("name", "")),
                            description=srv.get("description", ""),
                            source="smithery",
                            packages=srv.get("packages", []),
                            remote=srv.get("remote"),
                            meta=srv,
                        )
                    )
        except Exception as e:
            print(f"[MCP Registry] Smithery search failed: {e}")
        return results

    async def search_all(self, query: str = "", limit: int = 20) -> list[MCPServerInfo]:
        official_task = self.search_official_registry(query, limit)
        smithery_task = self.search_smithery(query, limit)
        official_results, smithery_results = await asyncio.gather(
            official_task, smithery_task, return_exceptions=True
        )
        results = []
        if isinstance(official_results, list):
            results.extend(official_results)
        if isinstance(smithery_results, list):
            results.extend(smithery_results)
        seen = set()
        unique = []
        for r in results:
            key = r.qualified_name
            if key not in seen:
                seen.add(key)
                unique.append(r)
        return unique[:limit]


registry_client = MCPRegistryClient()


POPULAR_MCP_SERVERS: list[dict[str, Any]] = [
    {
        "name": "Filesystem",
        "qualified_name": "io.github.modelcontextprotocol/filesystem",
        "description": "文件系统操作：读写文件、浏览目录、搜索文件内容",
        "source": "builtin",
        "category": "文件操作",
        "emoji": "📁",
        "install_hint": "npx @modelcontextprotocol/server-filesystem /path/to/dir",
    },
    {
        "name": "GitHub",
        "qualified_name": "io.github.modelcontextprotocol/github",
        "description": "GitHub API 集成：管理仓库、Issues、PR、代码搜索",
        "source": "builtin",
        "category": "开发工具",
        "emoji": "🐙",
        "install_hint": "npx @modelcontextprotocol/server-github",
        "env_vars": ["GITHUB_PERSONAL_ACCESS_TOKEN"],
    },
    {
        "name": "PostgreSQL",
        "qualified_name": "io.github.modelcontextprotocol/postgres",
        "description": "PostgreSQL 数据库操作：查询、Schema 检查、数据分析",
        "source": "builtin",
        "category": "数据库",
        "emoji": "🐘",
        "install_hint": "npx @modelcontextprotocol/server-postgres postgresql://...",
    },
    {
        "name": "Brave Search",
        "qualified_name": "io.github.modelcontextprotocol/brave-search",
        "description": "Brave 搜索引擎集成：网页搜索、实时信息获取",
        "source": "builtin",
        "category": "搜索",
        "emoji": "🔍",
        "install_hint": "npx @modelcontextprotocol/server-brave-search",
        "env_vars": ["BRAVE_API_KEY"],
    },
    {
        "name": "Google Drive",
        "qualified_name": "io.github.modelcontextprotocol/gdrive",
        "description": "Google Drive 文件管理：搜索、读取、列出文件",
        "source": "builtin",
        "category": "云存储",
        "emoji": "💾",
        "install_hint": "npx @modelcontextprotocol/server-gdrive",
        "env_vars": ["GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET"],
    },
    {
        "name": "Slack",
        "qualified_name": "io.github.modelcontextprotocol/slack",
        "description": "Slack 消息管理：发送消息、读取频道、搜索消息",
        "source": "builtin",
        "category": "通讯",
        "emoji": "💬",
        "install_hint": "npx @modelcontextprotocol/server-slack",
        "env_vars": ["SLACK_BOT_TOKEN", "SLACK_TEAM_ID"],
    },
    {
        "name": "Puppeteer",
        "qualified_name": "io.github.modelcontextprotocol/puppeteer",
        "description": "浏览器自动化：网页截图、表单填写、网页交互",
        "source": "builtin",
        "category": "浏览器",
        "emoji": "🌐",
        "install_hint": "npx @modelcontextprotocol/server-puppeteer",
    },
    {
        "name": "Memory",
        "qualified_name": "io.github.modelcontextprotocol/memory",
        "description": "知识图谱记忆系统：存储和检索对话上下文与实体关系",
        "source": "builtin",
        "category": "记忆",
        "emoji": "🧠",
        "install_hint": "npx @modelcontextprotocol/server-memory",
    },
    {
        "name": "Sequential Thinking",
        "qualified_name": "io.github.modelcontextprotocol/sequential-thinking",
        "description": "结构化思维链：分解复杂问题、逐步推理",
        "source": "builtin",
        "category": "推理",
        "emoji": "🤔",
        "install_hint": "npx @modelcontextprotocol/server-sequential-thinking",
    },
    {
        "name": "SQLite",
        "qualified_name": "io.github.modelcontextprotocol/sqlite",
        "description": "SQLite 数据库操作：建表、查询、数据分析",
        "source": "builtin",
        "category": "数据库",
        "emoji": "🗄️",
        "install_hint": "npx @modelcontextprotocol/server-sqlite --db-path /path/to/db",
    },
    {
        "name": "Fetch",
        "qualified_name": "io.github.modelcontextprotocol/fetch",
        "description": "HTTP 请求工具：获取网页内容、调用 REST API",
        "source": "builtin",
        "category": "网络",
        "emoji": "📡",
        "install_hint": "npx @modelcontextprotocol/server-fetch",
    },
    {
        "name": "Sentry",
        "qualified_name": "io.github.modelcontextprotocol/sentry",
        "description": "Sentry 错误追踪：查看 Issue、分析错误堆栈",
        "source": "builtin",
        "category": "监控",
        "emoji": "🚨",
        "install_hint": "npx @modelcontextprotocol/server-sentry",
        "env_vars": ["SENTRY_AUTH_TOKEN"],
    },
]


def get_popular_servers() -> list[dict[str, Any]]:
    return POPULAR_MCP_SERVERS


def get_servers_by_category() -> dict[str, list[dict[str, Any]]]:
    categories: dict[str, list[dict[str, Any]]] = {}
    for srv in POPULAR_MCP_SERVERS:
        cat = srv.get("category", "其他")
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(srv)
    return categories
