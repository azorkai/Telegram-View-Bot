import aiohttp
import asyncio
from aiohttp_socks import ProxyConnector
from re import search


class TelegramBot:

    def __init__(self):
        self.proxies = []
        self.current_proxy_index = 0
        self.success_count = 0
        self.failed_count = 0
        self.settings = self.load_settings()
        self.user_agent = self.settings['user_agent']
        self.semaphore = asyncio.Semaphore(self.settings['semaphore_count'])
        self.load_proxies()

    def load_settings(self):
        """Load settings from settings.json file"""
        try:
            with open('settings.json', 'r') as f:
                import json
                return json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError("settings.json not found")

    def load_proxies(self):
        """Load proxies from proxy.txt file"""
        try:
            with open('proxy.txt', 'r') as f:
                self.proxies = [line.strip() for line in f.readlines()]
            if not self.proxies:
                raise ValueError("proxy.txt is empty")
        except FileNotFoundError:
            raise FileNotFoundError("proxy.txt not found")

    def get_next_proxy(self):
        """Get next proxy using round-robin"""
        proxy = self.proxies[self.current_proxy_index]
        self.current_proxy_index = (self.current_proxy_index + 1) % len(
            self.proxies)
        return proxy

    def format_proxy(self, proxy):
        """Format proxy string to URL format"""
        try:
            ip, port, username, password = proxy.split(":")
            return f"http://{username}:{password}@{ip}:{port}"
        except ValueError:
            raise ValueError(
                "Proxy must be in format: ip:port:username:password")

    async def fetch_token(self, session, url):
        """Fetch the view token by limiting the response size"""
        try:
            async with session.get(url,
                                   timeout=10,
                                   headers={"Range":
                                            "bytes=0-1024"}) as response:
                if response.status != 200:
                    return None

                html = await response.text()
                token_match = search(r'data-view="([^"]+)"', html)
                if token_match:
                    return token_match.group(1)

        except Exception as e:
            print(f"Error fetching token: {e}")
        return None

    async def add_view(self, channel: str, post_id: int):
        async with self.semaphore:
            try:
                proxy = self.get_next_proxy()
                formatted_proxy = self.format_proxy(proxy)
                connector = ProxyConnector.from_url(formatted_proxy)

                async with aiohttp.ClientSession(
                        connector=connector,
                        headers={'user-agent': self.user_agent}) as session:
                    url = f"https://t.me/{channel}/{post_id}?embed=1&mode=tme"

                    view_token = await self.fetch_token(session, url)
                    if not view_token:
                        self.failed_count += 1
                        return

                    post_url = f"https://t.me/v/?views={view_token}"

                    async with session.post(post_url,
                                            headers={
                                                "referer":
                                                url,
                                                "x-requested-with":
                                                "XMLHttpRequest"
                                            },
                                            timeout=10) as post_response:
                        if post_response.status == 200 and await post_response.text(
                        ) == "true":
                            self.success_count += 1
                        else:
                            self.failed_count += 1

            except Exception as e:
                print(f"Error: {e}")
                self.failed_count += 1

    async def process_link(self, link: str, views_per_post: int):
        try:
            parts = link.strip().split('/')
            channel = parts[-2]
            post_id = int(parts[-1])
            tasks = [
                self.add_view(channel, post_id) for _ in range(views_per_post)
            ]
            await asyncio.gather(*tasks)
        except Exception as e:
            print(f"Error processing link {link}: {e}")

    async def run(self, links_file: str, views_per_post: int):
        with open(links_file, 'r') as f:
            links = f.readlines()

        tasks = [self.process_link(link, views_per_post) for link in links]
        await asyncio.gather(*tasks)


async def main():
    bot = TelegramBot()
    print("Starting Telegram bot...")
    await bot.run("telegram_links.txt", bot.settings['views_per_post'])
    print(f"Successful views: {bot.success_count}")
    print(f"Failed views: {bot.failed_count}")


if __name__ == "__main__":
    asyncio.run(main())
