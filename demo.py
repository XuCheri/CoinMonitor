import aiohttp
import asyncio

async def get_user_id():
    url = f"https://api.twitter.com/2/users/{705564530936418304}"
    headers = {
        "Authorization": f"Bearer AAAAAAAAAAAAAAAAAAAAAA%2BK2QEAAAAANPRnY%2B2%2FTBlzGWRoC4unwsgBYeQ%3DHIUFcsHtPInrYH15PWb9BNTShf0AdB9Ub5qiANoTVE8mcA2O2G"
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, proxy='http://127.0.0.1:7890') as resp:
            data = await resp.json()
            print(data)

# 替换为你的 Token 和用户名

asyncio.run(get_user_id())
