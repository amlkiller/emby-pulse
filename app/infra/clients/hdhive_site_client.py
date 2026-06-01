import requests


class HdhiveSiteClient:
    def create_session(self, *, proxies=None):
        session = requests.Session()
        if proxies:
            session.proxies.update(proxies)
        return session

    @staticmethod
    def _requester(session=None):
        return session or requests

    def get_page(self, url: str, *, headers=None, cookies=None, proxies=None, timeout: float = 30, session=None):
        return self._requester(session).get(
            url,
            headers=headers,
            cookies=cookies,
            proxies=None if session else proxies,
            timeout=timeout,
        )

    def post_page(
        self,
        url: str,
        *,
        headers=None,
        cookies=None,
        data=None,
        json=None,
        proxies=None,
        timeout: float = 30,
        allow_redirects=True,
        session=None,
    ):
        return self._requester(session).post(
            url,
            headers=headers,
            cookies=cookies,
            data=data,
            json=json,
            proxies=None if session else proxies,
            timeout=timeout,
            allow_redirects=allow_redirects,
        )

    def get_login_page(self, base_url: str, *, headers=None, timeout: float = 30, session=None):
        return self.get_page(f"{base_url.rstrip('/')}/login", headers=headers, timeout=timeout, session=session)

    def post_login_action(self, base_url: str, *, headers=None, data=None, timeout: float = 30, session=None):
        return self.post_page(
            f"{base_url.rstrip('/')}/login",
            headers=headers,
            data=data,
            timeout=timeout,
            allow_redirects=False,
            session=session,
        )

    def post_legacy_login(self, url: str, *, headers=None, payload=None, timeout: float = 30, session=None):
        return self.post_page(url, headers=headers, json=payload, timeout=timeout, session=session)

    def get_user_info(self, base_url: str, *, headers=None, cookies=None, proxies=None, timeout: float = 30):
        return self.get_page(
            f"{base_url.rstrip('/')}/api/customer/user/info",
            headers=headers,
            cookies=cookies,
            proxies=proxies,
            timeout=timeout,
        )


hdhive_site_client = HdhiveSiteClient()
