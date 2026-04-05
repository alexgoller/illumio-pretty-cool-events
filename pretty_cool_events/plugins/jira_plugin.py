"""Jira output plugin."""

from __future__ import annotations

import logging
from typing import Any

from pretty_cool_events.plugins.base import OutputPlugin

logger = logging.getLogger(__name__)


class JiraPlugin(OutputPlugin):
    """Create Jira issues from rendered events."""

    name = "PCEJira"

    def configure(self, config: dict[str, Any]) -> None:
        self.jira_server = config.get("jira_server", "")
        self.username = config.get("username", "")
        self.api_token = config.get("api_token", "")
        self.project = config.get("project", "")
        self.template = config.get("template", "rule_set.create.jira.tmpl")
        self._configured = True

    def send(
        self,
        event: dict[str, Any],
        extra_data: dict[str, Any],
        template_globals: dict[str, Any],
    ) -> None:
        from jira import JIRA

        template_name = extra_data.get("template", self.template)

        try:
            rendered = self.render_template(template_name, event, template_globals)

            jira_client = JIRA(
                server=self.jira_server,
                basic_auth=(self.username, self.api_token),
            )

            issue = jira_client.create_issue(
                project=self.project,
                summary=extra_data.get("summary", "PCE Event"),
                description=rendered,
                issuetype={"name": extra_data.get("issue_type", "Task")},
            )
            logger.info("Created Jira issue: %s", issue.key)
        except Exception as e:
            logger.error("JiraPlugin failed to create issue: %s", e)
