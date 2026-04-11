"""GitHub Issues output plugin."""

from __future__ import annotations

import logging
from typing import Any

from pretty_cool_events.plugins.base import OutputPlugin

logger = logging.getLogger(__name__)


class GithubIssuePlugin(OutputPlugin):
    """Create GitHub issues from PCE events."""

    name = "PCEGithubIssue"

    def configure(self, config: dict[str, Any]) -> None:
        self.token = config.get("token", "")
        self.repo = config.get("repo", "")  # owner/repo format
        self.labels = config.get("labels", "pce-event")
        self.template = config.get("template", "default.html")
        self._configured = True

    def send(
        self,
        event: dict[str, Any],
        extra_data: dict[str, Any],
        template_globals: dict[str, Any],
    ) -> None:
        import httpx

        template_name = extra_data.get("template", self.template)
        repo = extra_data.get("repo", self.repo)

        if not repo:
            logger.error("GithubIssuePlugin: no repo configured")
            return

        try:
            rendered = self.render_template(template_name, event, template_globals)
            event_type = event.get("event_type", "unknown")

            if not rendered.strip():
                logger.warning("GithubIssuePlugin: template '%s' rendered empty, skipping", template_name)
                return

            issue = {
                "title": f"PCE Event: {event_type}",
                "body": rendered,
                "labels": [lbl.strip() for lbl in self.labels.split(",") if lbl.strip()],
            }

            response = httpx.post(
                f"https://api.github.com/repos/{repo}/issues",
                json=issue,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            response.raise_for_status()
            issue_url = response.json().get("html_url", "")
            logger.info("Created GitHub issue for %s: %s", event_type, issue_url)
        except Exception as e:
            logger.error("GithubIssuePlugin failed: %s", e)
