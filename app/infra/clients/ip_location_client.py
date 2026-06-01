import requests


class IpLocationClient:
    @staticmethod
    def _headers() -> dict:
        return {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    def get_open_ipw_location(self, ip: str, *, timeout: float = 3):
        return requests.get(
            f"https://open.ipw.cn/api/ip/location?ip={ip}",
            headers=self._headers(),
            timeout=timeout,
        )

    def get_ip_zxinc_location(self, ip: str, *, timeout: float = 3):
        return requests.get(
            f"https://ip.zxinc.org/api.php?type=json&ip={ip}",
            headers=self._headers(),
            timeout=timeout,
        )

    def get_pconline_location(self, ip: str, *, timeout: float = 3):
        return requests.get(
            f"https://whois.pconline.com.cn/ipJson.jsp?ip={ip}&json=true",
            headers=self._headers(),
            timeout=timeout,
        )


ip_location_client = IpLocationClient()
