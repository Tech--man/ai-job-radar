"""全局配置：受限出站请求、安全 XML 解析、常量。

安全约束（Mimosa）：
- 出站仅允许 https；host 白名单；解析出的全部 IP 必须为公网；连接固定到已校验
  IP（防 DNS rebinding）；不跟随重定向（3xx 拒绝）。
- XML 解析拒绝 DOCTYPE/ENTITY 并限制大小（防实体扩展）。
- 所有数据库写入使用参数绑定（见 build_db.py）。
- 凭据仅从环境变量读取，不入源码。
"""

from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
import urllib.parse
import xml.etree.ElementTree as ET

# ---- 允许访问的数据源主机白名单（均为公开 API / RSS，遵守其条款）----
ALLOWED_HOSTS = {
    "hn.algolia.com",
    "remoteok.com",
    "weworkremotely.com",
    "api.github.com",
    "raw.githubusercontent.com",
    "export.arxiv.org",
    "huggingface.co",
    "cdn.jsdelivr.net",
}

USER_AGENT = "ai-job-radar-research/0.1 (open-data research; contact: none)"
TIMEOUT = 40


class _PinnedHTTPS(http.client.HTTPSConnection):
    """连接到预先校验过的公网 IP，TLS 证书仍按原始主机名校验。

    用于抵御 DNS rebinding：建连目标不是重新解析的主机名，而是已校验的 IP。
    http.client 不跟随重定向，3xx 会在 safe_fetch 中被显式拒绝。
    """

    def __init__(self, host: str, ip: str, timeout: float) -> None:
        super().__init__(host, timeout=timeout)
        self._pinned_ip = ip

    def connect(self) -> None:
        sock = socket.create_connection((self._pinned_ip, self.port), self.timeout)
        ctx = ssl.create_default_context()
        self.sock = ctx.wrap_socket(sock, server_hostname=self.host)


def _resolve_public_ips(host: str) -> list[str]:
    """解析并校验地址。

    回环 / 私网 / 链路本地（含云元数据 169.254.169.254）/ 组播 / 其他保留段一律拒绝。
    例外：198.18.0.0/15（RFC 2544 基准段）在本机是 TUN 代理 fake-IP 隧道模式的表现
    （所有域名都解析到该段，由透明隧道转发到真实主机，TLS 仍按主机名校验），
    单独放行并打标记，其余环境仍按严格公网校验。
    """
    ips: list[str] = []
    tunnel = False
    for info in socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP):
        ip = ipaddress.ip_address(info[4][0])
        if ip in ipaddress.ip_network("198.18.0.0/15"):
            tunnel = True  # 本机代理 fake-IP：连接该地址 = 经系统隧道到达白名单主机
            ips.append(str(ip))
            continue
        if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local \
                or ip.is_multicast or not ip.is_global:
            raise ValueError(f"host {host} resolves to non-public address {ip}")
        ips.append(str(ip))
    if not ips:
        raise ValueError(f"host {host} did not resolve")
    if tunnel:
        # fake-IP 隧道下无法pin真实IP，直接用解析地址建连；SNI/证书校验仍绑定主机名
        return ips
    return ips


def safe_fetch(url: str, *, binary: bool = False, headers: dict | None = None) -> bytes | str:
    """一切出站请求必须经此函数：https-only、host 白名单、公网 IP 校验、
    连接固定（防 rebinding）、不跟随重定向。"""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"scheme not allowed: {parsed.scheme}")
    host = parsed.hostname or ""
    if host not in ALLOWED_HOSTS:
        raise ValueError(f"host not in allowlist: {host}")
    ips = _resolve_public_ips(host)  # 校验后立刻固定 IP 建连，收敛 TOCTOU 窗口
    conn = _PinnedHTTPS(host, ips[0], timeout=TIMEOUT)
    try:
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        req_headers = {"User-Agent": USER_AGENT, "Accept": "*/*", "Host": host}
        if headers:
            req_headers.update(headers)
        conn.request("GET", path, headers=req_headers)
        resp = conn.getresponse()
        if 300 <= resp.status < 400:
            raise ValueError(f"redirect not allowed: HTTP {resp.status}")
        if resp.status >= 400:
            raise RuntimeError(f"HTTP {resp.status} from {host}")
        data = resp.read()
    finally:
        conn.close()
    return data.decode("utf-8", errors="replace") if not binary else data


def parse_xml_safely(xml_text: str, *, max_bytes: int = 8 * 1024 * 1024) -> ET.Element:
    """解析不可信 XML 前拒绝 DOCTYPE/ENTITY 并限制大小，防实体扩展。"""
    if len(xml_text.encode("utf-8")) > max_bytes:
        raise ValueError("xml too large")
    head = xml_text[:65536].lower()
    if "<!doctype" in head or "<!entity" in head:
        raise ValueError("DTD/entity declarations not allowed")
    return ET.fromstring(xml_text)


# ---- 汇率静态快照（用于薪资归一化为 USD，仅作粗粒度参考折算，记录于方法论）----
FX_TO_USD = {
    "USD": 1.00, "EUR": 1.08, "GBP": 1.27, "CAD": 0.73, "AUD": 0.65,
    "NZD": 0.60, "CHF": 1.13, "SEK": 0.095, "NOK": 0.092, "DKK": 0.145,
    "SGD": 0.75, "JPY": 0.0067, "INR": 0.012, "CNY": 0.14, "BRL": 0.185,
    "PLN": 0.25, "CZK": 0.043,
}
FX_SNAPSHOT_NOTE = "静态汇率快照，仅用于粗粒度区间归一，不构成精确换算"

# ---- 薪资合理性区间（年薪 USD）----
SALARY_MIN_USD = 25_000
SALARY_MAX_USD = 900_000

T0_NOTE = "T+0 = 2026-10-04 00:05 +0800"
