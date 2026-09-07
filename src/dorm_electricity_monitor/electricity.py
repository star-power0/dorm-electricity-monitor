from __future__ import annotations

from dataclasses import dataclass
import time
import requests
import urllib3.util.connection

# The API host also resolves to an IPv6 address whose path is unreliable here,
# so pin requests to IPv4 to remove one source of connection stalls.
urllib3.util.connection.HAS_IPV6 = False

from .config import API_URL, AppConfig, MeterConfig

# Upstream response time swings between ~2s and 30s+, so keep the connect
# timeout tight but give the read phase room, and retry once on network errors.
CONNECT_TIMEOUT_SECONDS = 8
READ_TIMEOUT_SECONDS = 25
MAX_ATTEMPTS = 2
RETRY_DELAY_SECONDS = 1.5


@dataclass(frozen=True)
class MeterReading:
    name: str
    type: int
    room_label: str
    building_label: str
    balance: float
    energy: float
    collected_at: str


class ElectricityClient:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 "
                "MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI MiniProgramEnv/Windows "
                "WindowsWechat/WMPF WindowsWechat(0x63090a13) UnifiedPCWindowsWechat(0xf2541b18) XWEB/20005",
                "xweb_xhr": "1",
                "Content-Type": "application/json",
                "Accept": "*/*",
                "Sec-Fetch-Site": "cross-site",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Dest": "empty",
                "Referer": "https://servicewechat.com/wx0beafaec1332d39d/23/page-frame.html",
                "Accept-Language": "zh-CN,zh;q=0.9",
            }
        )

    def get_meter(self, meter: MeterConfig) -> MeterReading:
        attempts_left = MAX_ATTEMPTS
        while True:
            attempts_left -= 1
            try:
                return self._fetch_meter(meter)
            except requests.RequestException:
                if attempts_left <= 0:
                    raise
                time.sleep(RETRY_DELAY_SECONDS)

    def _fetch_meter(self, meter: MeterConfig) -> MeterReading:
        response = self.session.get(
            API_URL,
            params={"openId": self.config.open_id, "type": meter.type},
            timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
        )
        response.raise_for_status()
        payload = response.json()
        if str(payload.get("statusCode")) != "200":
            raise RuntimeError(f"接口返回异常：{payload}")
        data = payload.get("resultObject") or {}
        return MeterReading(
            name=meter.name,
            type=meter.type,
            room_label=clean_room_label(str(data.get("room", "")), meter.name),
            building_label=clean_building_label(str(data.get("loudong", "")), meter.name),
            balance=float(data.get("leftMoney", 0)),
            energy=float(data.get("leftEle", 0)),
            collected_at=str(data.get("monTime", "")),
        )

    def get_all(self) -> list[MeterReading]:
        return [self.get_meter(meter) for meter in self.config.enabled_meters]


def clean_room_label(raw: str, meter_name: str) -> str:
    text = raw.replace("#", "号楼 ").strip()
    if text.endswith("空"):
        text = text[:-1]
    if text.endswith("照"):
        text = text[:-1]
    text = text.strip()
    if "号楼" in text and "室" not in text:
        text = f"{text} 室"
    return f"{text} · {meter_name}" if text else meter_name


def clean_building_label(raw: str, meter_name: str) -> str:
    text = raw.replace("#", "号楼 ").strip()
    return text or meter_name
