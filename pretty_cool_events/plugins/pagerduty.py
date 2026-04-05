"""PagerDuty output plugin."""

from __future__ import annotations

import logging
from typing import Any

from pretty_cool_events.plugins.base import OutputPlugin

logger = logging.getLogger(__name__)


class PagerDutyPlugin(OutputPlugin):
    """Create PagerDuty incidents from rendered events."""

    name = "PCEPagerDuty"

    def configure(self, config: dict[str, Any]) -> None:
        self.api_key = config.get("api_key", "")
        self.pd_from = config.get("pd_from", "")
        self.pd_priority = config.get("pd_priority", "")
        self.pd_service = config.get("pd_service", "")
        self.template = config.get("template", "default.html")
        self._configured = True

    def send(
        self,
        event: dict[str, Any],
        extra_data: dict[str, Any],
        template_globals: dict[str, Any],
    ) -> None:
        from pdpyras import APISession

        template_name = extra_data.get("template", self.template)

        try:
            rendered = self.render_template(template_name, event, template_globals)

            session = APISession(self.api_key, default_from=self.pd_from)

            payload = {
                "type": "incident",
                "title": extra_data.get("title", "PCE Event"),
                "service": {"id": self.pd_service, "type": "service_reference"},
                "body": {"type": "incident_body", "details": rendered},
            }

            if self.pd_priority:
                payload["priority"] = {
                    "id": self.pd_priority,
                    "type": "priority_reference",
                }

            incident = session.post("/incidents", json={"incident": payload})
            logger.info("Created PagerDuty incident: %s", incident.get("id", "unknown"))
        except Exception as e:
            logger.error("PagerDutyPlugin failed to create incident: %s", e)
