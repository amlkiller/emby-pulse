from dataclasses import dataclass
from typing import Callable, List, Optional


ServiceCallback = Callable[[], None]


@dataclass
class BootstrapService:
    name: str
    start: ServiceCallback
    stop: Optional[ServiceCallback] = None
    started: bool = False


class BootstrapServiceRegistry:
    """Process-local lifecycle registry for bootstrap-started services."""

    def __init__(self) -> None:
        self._services: List[BootstrapService] = []

    def register(self, name: str, start: ServiceCallback, stop: Optional[ServiceCallback] = None) -> None:
        self._services.append(BootstrapService(name=name, start=start, stop=stop))

    def start_all(self) -> None:
        for service in self._services:
            if service.started:
                continue
            service.start()
            service.started = True

    def stop_all(self) -> None:
        for service in reversed(self._services):
            if not service.started:
                continue
            try:
                if service.stop:
                    service.stop()
            finally:
                service.started = False

    def started_names(self) -> List[str]:
        return [service.name for service in self._services if service.started]

    def clear(self) -> None:
        self._services.clear()
