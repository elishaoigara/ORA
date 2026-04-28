from tavily import TavilyClient
import os

client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

res = client.search("latest AI advancements 2026")

print(res)