import os
import json
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("Podcast Curator Tools")

# Mock database of recent articles
MOCK_ARTICLES = {
    "google": [
        {
            "title": "Google launches Gemini 2.5 Flash with massive performance upgrades",
            "url": "https://techcrunch.com/google-gemini-2-5",
            "content": "Google has announced Gemini 2.5 Flash, bringing massive speed and efficiency gains to its flagship generative model family, especially targeting developer tooling, multi-agent frameworks, and low-latency API operations."
        },
        {
            "title": "Google DeepMind introduces advanced multi-agent orchestration frameworks",
            "url": "https://blog.google/deepmind-agents",
            "content": "Google DeepMind has introduced a suite of new orchestration libraries for autonomous agents, focusing on graph-based workflows, state persistence, and seamless tool integrations."
        }
    ],
    "ai": [
        {
            "title": "The shift from chat interfaces to agentic AI workflows",
            "url": "https://venturebeat.com/agentic-ai-rise",
            "content": "Artificial intelligence systems are shifting rapidly from static chat interfaces to agentic workflows. Developers are using framework tools to build multi-agent graphs that perform complex, multi-step planning and self-correction."
        },
        {
            "title": "Model Context Protocol (MCP) standardizes LLM-to-tool connections",
            "url": "https://mcp.dev/adoption-gains",
            "content": "Anthropic's open-source Model Context Protocol is seeing rapid industry-wide adoption, standardizing how LLMs securely connect to local resources, databases, and developer environments."
        }
    ],
    "python": [
        {
            "title": "Python 3.13 released with experimental JIT compiler",
            "url": "https://python.org/python-313",
            "content": "Python 3.13 is officially here, featuring an experimental JIT compiler, improved tracebacks, and advancements in removing the Global Interpreter Lock (GIL) to enable true multi-core parallel processing."
        },
        {
            "title": "Astral uv package manager introduces project workflow features",
            "url": "https://astral.sh/uv-release",
            "content": "uv, the extremely fast Python package manager written in Rust, has introduced workflow commands supporting project scaffolding, workspace management, and reproducible locked environments."
        }
    ]
}


@mcp.tool()
def fetch_news_headlines(topic: str) -> str:
    """Fetch recent tech news headlines and metadata for a given topic.

    Args:
        topic: The search term or subject (e.g. 'google', 'ai', 'python').
    """
    topic_clean = topic.lower().strip()
    results = []
    
    # Simple keyword matcher
    for key, articles in MOCK_ARTICLES.items():
        if key in topic_clean or topic_clean in key:
            results.extend(articles)
            
    if not results:
        # General tech story fallback
        results = [
            {
                "title": f"Recent developments in {topic}",
                "url": f"https://tech-news.com/{topic}-advancements",
                "content": f"Industry experts report major technical breakthroughs in the field of {topic}, driving interest and capital investments from enterprise firms."
            },
            {
                "title": f"Open-source tools emerge for {topic}",
                "url": f"https://github.com/topics/{topic}",
                "content": f"A wave of open-source repository releases has accelerated development speed for projects implementing {topic} integrations."
            }
        ]
        
    return json.dumps(results, indent=2)


@mcp.tool()
def parse_article_content(url: str) -> str:
    """Parse and extract the full body text of a news article from a URL.

    Args:
        url: The URL of the news article to read.
    """
    # Scan mock database for URL match
    for key, articles in MOCK_ARTICLES.items():
        for article in articles:
            if article["url"] == url:
                return article["content"]
                
    # Generic fallback
    return (
        f"This is the simulated body content for the article at {url}. "
        "It details the latest technical updates, community discussions, and deployment strategies "
        "relevant to this technology sector."
    )


@mcp.tool()
def save_podcast_draft(filename: str, content: str) -> str:
    """Save a podcast script draft as a file on the local disk.

    Args:
        filename: Name of the file (e.g., 'script_draft.txt').
        content: The text content of the podcast script.
    """
    # Output to project directory
    safe_dir = "c:\\Users\\padhu\\CODING PROJECTS\\OneDrive\\Documents\\Attachments\\Desktop\\ADK-WORKSPACE\\podcast-script-curator"
    clean_filename = os.path.basename(filename)
    if not clean_filename.endswith(".txt") and not clean_filename.endswith(".md"):
        clean_filename += ".txt"
        
    dest_path = os.path.join(safe_dir, clean_filename)
    try:
        with open(dest_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully saved podcast draft to: {dest_path}"
    except Exception as e:
        return f"Error saving file: {str(e)}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
