"""Plugin metadata: descriptions, field labels, and configuration hints."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FieldMeta:
    label: str
    help: str = ""
    required: bool = False
    secret: bool = False
    placeholder: str = ""
    field_type: str = "text"  # text, number, password, url, email


@dataclass
class PluginMeta:
    name: str
    display_name: str
    icon: str
    description: str
    how_it_works: str
    fields: dict[str, FieldMeta] = field(default_factory=dict)


PLUGIN_METADATA: dict[str, PluginMeta] = {
    "PCEStdout": PluginMeta(
        name="PCEStdout",
        display_name="Console Output",
        icon="bi-terminal",
        description="Prints event notifications to the application log. Useful for debugging, "
                    "development, and quick validation that events are flowing correctly.",
        how_it_works="When an event matches a watcher, the event data is rendered through a "
                     "Jinja2 template and written to the application log (stdout). You can add "
                     "a prefix and suffix to each message for easy visual identification.",
        fields={
            "prepend": FieldMeta(
                label="Prefix",
                help="Text prepended to every log line (e.g. '[PCE] ').",
                placeholder="[PCE] ",
            ),
            "append": FieldMeta(
                label="Suffix",
                help="Text appended to every log line.",
            ),
        },
    ),
    "PCESlack": PluginMeta(
        name="PCESlack",
        display_name="Slack",
        icon="bi-slack",
        description="Sends event notifications to Slack channels using the Slack Block Kit "
                    "format. Supports per-watcher channel targeting and rich message formatting.",
        how_it_works="Create a Slack App at api.slack.com/apps with the chat:write scope. "
                     "Install the app to your workspace and copy the Bot User OAuth Token. "
                     "Events are rendered as Slack Block Kit JSON and posted via the "
                     "chat.postMessage API. Each watcher can specify a different channel "
                     "in its extra_data.",
        fields={
            "slack_bot_token": FieldMeta(
                label="Bot Token",
                help="Slack Bot User OAuth Token (starts with xoxb-).",
                required=True, secret=True,
                placeholder="xoxb-...",
            ),
            "template": FieldMeta(
                label="Default Template",
                help="Jinja2 template that produces Slack Block Kit JSON.",
                placeholder="default-slack.html",
            ),
            "app_id": FieldMeta(label="App ID", help="Slack App ID (for reference)."),
            "client_id": FieldMeta(label="Client ID", secret=True),
            "client_secret": FieldMeta(label="Client Secret", secret=True),
            "signing_secret": FieldMeta(label="Signing Secret", secret=True),
        },
    ),
    "PCEMail": PluginMeta(
        name="PCEMail",
        display_name="Email (SMTP)",
        icon="bi-envelope",
        description="Sends HTML email notifications via SMTP. Supports TLS and "
                    "authentication. Great for compliance alerts and audit trails.",
        how_it_works="Configure an SMTP server (e.g. AWS SES, Gmail, corporate relay). "
                     "Events are rendered through an HTML template and sent as the email body. "
                     "The 'From' address and default 'To' address are set here; watchers can "
                     "override the recipient via extra_data.email_to.",
        fields={
            "smtp_host": FieldMeta(
                label="SMTP Host",
                help="SMTP server hostname.",
                required=True,
                placeholder="smtp.example.com",
            ),
            "smtp_port": FieldMeta(
                label="SMTP Port",
                help="SMTP server port (587 for TLS, 465 for SSL).",
                required=True, field_type="number",
                placeholder="587",
            ),
            "smtp_user": FieldMeta(
                label="SMTP Username",
                help="Username for SMTP authentication.",
                required=True,
            ),
            "smtp_password": FieldMeta(
                label="SMTP Password",
                help="Password for SMTP authentication.",
                required=True, secret=True,
            ),
            "email_from": FieldMeta(
                label="From Address",
                help="Sender email address.",
                required=True, field_type="email",
                placeholder="alerts@example.com",
            ),
            "email_to": FieldMeta(
                label="Default To Address",
                help="Default recipient. Watchers can override via extra_data.",
                field_type="email",
                placeholder="team@example.com",
            ),
            "template": FieldMeta(
                label="Default Template",
                placeholder="email-full.html",
            ),
        },
    ),
    "PCESNS": PluginMeta(
        name="PCESNS",
        display_name="SMS (AWS SNS)",
        icon="bi-phone",
        description="Sends SMS text messages via Amazon SNS. Ideal for critical alerts "
                    "that need immediate attention outside of work hours.",
        how_it_works="Uses AWS SNS Publish API to send SMS to a phone number. Configure "
                     "AWS credentials with SNS publish permissions. Each watcher specifies "
                     "the target phone number in extra_data.phone_number (E.164 format, "
                     "e.g. +15551234567).",
        fields={
            "access_key": FieldMeta(
                label="AWS Access Key",
                help="AWS IAM access key ID with SNS permissions.",
                required=True, secret=True,
            ),
            "access_key_secret": FieldMeta(
                label="AWS Secret Key",
                help="AWS IAM secret access key.",
                required=True, secret=True,
            ),
            "aws_region_name": FieldMeta(
                label="AWS Region",
                help="AWS region for SNS (e.g. us-east-1, eu-central-1).",
                required=True,
                placeholder="us-east-1",
            ),
        },
    ),
    "PCESyslog": PluginMeta(
        name="PCESyslog",
        display_name="Syslog",
        icon="bi-journal-text",
        description="Forwards event notifications to a remote syslog server. Supports "
                    "both UDP and TCP with optional TLS encryption for secure transport.",
        how_it_works="Events are rendered through a template and sent as syslog messages "
                     "to the configured host and port. If a TLS certificate file is provided, "
                     "the connection is upgraded to TLS over TCP. Compatible with any syslog "
                     "collector (rsyslog, syslog-ng, Splunk, etc.).",
        fields={
            "syslog_host": FieldMeta(
                label="Syslog Host",
                help="Hostname or IP of the syslog server.",
                required=True,
                placeholder="syslog.example.com",
            ),
            "syslog_port": FieldMeta(
                label="Syslog Port",
                help="Port number (514 for UDP, 6514 for TLS).",
                required=True, field_type="number",
                placeholder="514",
            ),
            "syslog_cert_file": FieldMeta(
                label="TLS Certificate",
                help="Path to CA certificate file for TLS. Leave empty for plain UDP.",
            ),
            "template": FieldMeta(
                label="Default Template",
                placeholder="json-lines.html",
            ),
        },
    ),
    "PCEWebhook": PluginMeta(
        name="PCEWebhook",
        display_name="Webhook",
        icon="bi-link-45deg",
        description="Sends event data as an HTTP POST to any URL. The universal integration "
                    "point for connecting to systems that accept webhooks.",
        how_it_works="The event is rendered through a template (or sent as raw JSON) and "
                     "POSTed to the configured URL. If a bearer token is provided, it is "
                     "included as an Authorization header. Use this for custom integrations, "
                     "IFTTT, Zapier, n8n, or any HTTP-based automation.",
        fields={
            "url": FieldMeta(
                label="Webhook URL",
                help="The full URL to POST event data to.",
                required=True, field_type="url",
                placeholder="https://hooks.example.com/events",
            ),
            "bearer_token": FieldMeta(
                label="Bearer Token",
                help="Optional bearer token for the Authorization header.",
                secret=True,
            ),
            "data": FieldMeta(
                label="Static Payload",
                help="Optional static JSON payload to include with each request.",
            ),
        },
    ),
    "PCEJira": PluginMeta(
        name="PCEJira",
        display_name="Jira",
        icon="bi-kanban",
        description="Automatically creates Jira issues from PCE events. Turns security "
                    "events into trackable work items for your team.",
        how_it_works="Connects to Jira Cloud or Server via the REST API. When an event "
                     "matches, a new issue is created in the specified project with the "
                     "event summary as the title and the rendered template as the description. "
                     "Requires a Jira API token (Cloud) or password (Server).",
        fields={
            "jira_server": FieldMeta(
                label="Jira Server URL",
                help="Jira instance URL (e.g. https://mycompany.atlassian.net).",
                required=True, field_type="url",
                placeholder="https://mycompany.atlassian.net",
            ),
            "username": FieldMeta(
                label="Username / Email",
                help="Jira account email (Cloud) or username (Server).",
                required=True,
            ),
            "api_token": FieldMeta(
                label="API Token",
                help="Jira API token (Cloud) or password (Server).",
                required=True, secret=True,
            ),
            "project": FieldMeta(
                label="Project Key",
                help="Jira project key where issues will be created (e.g. SEC).",
                required=True,
                placeholder="SEC",
            ),
            "template": FieldMeta(
                label="Default Template",
                placeholder="default.html",
            ),
        },
    ),
    "PCETeams": PluginMeta(
        name="PCETeams",
        display_name="Microsoft Teams",
        icon="bi-microsoft-teams",
        description="Sends event notifications to Microsoft Teams channels via "
                    "incoming webhooks.",
        how_it_works="Create an Incoming Webhook connector in your Teams channel "
                     "(Channel Settings > Connectors > Incoming Webhook). Copy the webhook "
                     "URL and paste it here. Events are rendered through a template and "
                     "POSTed as a message card to the channel.",
        fields={
            "webhook": FieldMeta(
                label="Webhook URL",
                help="Teams Incoming Webhook URL.",
                required=True, field_type="url",
                placeholder="https://outlook.office.com/webhook/...",
            ),
            "template": FieldMeta(
                label="Default Template",
                placeholder="default-teams.tmpl",
            ),
        },
    ),
    "PCEServiceNow": PluginMeta(
        name="PCEServiceNow",
        display_name="ServiceNow",
        icon="bi-building",
        description="Creates incidents in ServiceNow from PCE events. Integrates security "
                    "events directly into your ITSM workflow.",
        how_it_works="Connects to the ServiceNow Table API to create incident records. "
                     "The event summary becomes the short description and the rendered "
                     "template becomes the incident description. Requires a ServiceNow "
                     "user with the itil role.",
        fields={
            "instance": FieldMeta(
                label="Instance Name",
                help="ServiceNow instance (e.g. mycompany.service-now.com).",
                required=True,
                placeholder="mycompany.service-now.com",
            ),
            "username": FieldMeta(
                label="Username",
                help="ServiceNow user with itil role.",
                required=True,
            ),
            "password": FieldMeta(
                label="Password",
                required=True, secret=True,
            ),
            "template": FieldMeta(
                label="Default Template",
                placeholder="default.html",
            ),
        },
    ),
    "PCEPagerDuty": PluginMeta(
        name="PCEPagerDuty",
        display_name="PagerDuty",
        icon="bi-bell",
        description="Creates PagerDuty incidents from PCE events. Triggers your on-call "
                    "rotation for critical security events.",
        how_it_works="Uses the PagerDuty Events API v2 to create incidents. Configure an "
                     "API key with write access, the 'from' email (must match a PagerDuty "
                     "user), and the target service and priority IDs. Find these IDs in "
                     "PagerDuty under Services and Incident Priorities.",
        fields={
            "api_key": FieldMeta(
                label="API Key",
                help="PagerDuty REST API key (General Access or read/write).",
                required=True, secret=True,
            ),
            "pd_from": FieldMeta(
                label="From Email",
                help="Email of a valid PagerDuty user (used as incident creator).",
                required=True, field_type="email",
                placeholder="oncall@example.com",
            ),
            "pd_service": FieldMeta(
                label="Service ID",
                help="PagerDuty service ID to create incidents on.",
                required=True,
                placeholder="PXXXXXX",
            ),
            "pd_priority": FieldMeta(
                label="Priority ID",
                help="PagerDuty priority reference ID (optional).",
                placeholder="PXXXXXX",
            ),
            "template": FieldMeta(
                label="Default Template",
                placeholder="alert.tmpl",
            ),
        },
    ),
    "PCEFile": PluginMeta(
        name="PCEFile",
        display_name="File Logger",
        icon="bi-file-earmark-text",
        description="Appends rendered event notifications to a local file. Simple, "
                    "reliable, and useful for audit logs or feeding into log management tools.",
        how_it_works="Each event is rendered through a template and appended as a line to "
                     "the specified log file. The file is opened in append mode for each "
                     "write, so it is safe to rotate externally. Use the default-json.html "
                     "template for structured JSON lines.",
        fields={
            "logfile": FieldMeta(
                label="Log File Path",
                help="Path to the output file (created if it doesn't exist).",
                required=True,
                placeholder="events.log",
            ),
            "template": FieldMeta(
                label="Default Template",
                help="Template for formatting each log line.",
                placeholder="json-lines.html",
            ),
        },
    ),
    "PCEOpsgenie": PluginMeta(
        name="PCEOpsgenie",
        display_name="Opsgenie",
        icon="bi-bell-fill",
        description="Creates Opsgenie alerts for on-call notification. Alternative to "
                    "PagerDuty, widely used in enterprise incident management.",
        how_it_works="Uses the Opsgenie REST API v2 to create alerts. Get an API key from "
                     "Settings > API key management in Opsgenie. Optionally assign alerts to "
                     "a specific team. Priority maps to Opsgenie P1-P5 levels.",
        fields={
            "api_key": FieldMeta(
                label="API Key",
                help="Opsgenie API key (from Settings > API key management).",
                required=True, secret=True,
            ),
            "team": FieldMeta(
                label="Team",
                help="Opsgenie team name to assign alerts to (optional).",
                placeholder="security-team",
            ),
            "priority": FieldMeta(
                label="Default Priority",
                help="Alert priority: P1 (critical) to P5 (informational).",
                placeholder="P3",
            ),
            "tags": FieldMeta(
                label="Tags",
                help="Comma-separated tags added to every alert.",
                placeholder="illumio,pce",
            ),
            "template": FieldMeta(label="Default Template", placeholder="alert.tmpl"),
        },
    ),
    "PCEGithubIssue": PluginMeta(
        name="PCEGithubIssue",
        display_name="GitHub Issues",
        icon="bi-github",
        description="Creates GitHub issues from PCE events. Turn security events into "
                    "trackable issues in your repository.",
        how_it_works="Uses the GitHub REST API to create issues. Generate a personal access "
                     "token with 'issues: write' scope at github.com/settings/tokens. "
                     "Specify the target repo in owner/repo format. Each watcher can "
                     "override the repo via extra_data.",
        fields={
            "token": FieldMeta(
                label="GitHub Token",
                help="Personal access token with issues:write scope.",
                required=True, secret=True,
            ),
            "repo": FieldMeta(
                label="Repository",
                help="Target repository in owner/repo format.",
                required=True,
                placeholder="myorg/security-events",
            ),
            "labels": FieldMeta(
                label="Labels",
                help="Comma-separated labels to add to created issues.",
                placeholder="pce-event,security",
            ),
            "template": FieldMeta(label="Default Template", placeholder="github-issue.tmpl"),
        },
    ),
    "PCELambda": PluginMeta(
        name="PCELambda",
        display_name="AWS Lambda",
        icon="bi-cloud-arrow-up",
        description="Invokes AWS Lambda functions with PCE event data. Trigger serverless "
                    "workflows, custom processing, or cross-cloud integrations.",
        how_it_works="Uses boto3 to invoke the specified Lambda function. The event data is "
                     "sent as the function payload as JSON. Invocation type 'Event' (default) "
                     "is asynchronous; 'RequestResponse' waits for the function to complete. "
                     "Uses AWS credentials from config or the default credential chain.",
        fields={
            "function_name": FieldMeta(
                label="Function Name",
                help="Lambda function name or ARN.",
                required=True,
                placeholder="my-pce-event-handler",
            ),
            "aws_region": FieldMeta(
                label="AWS Region",
                placeholder="us-east-1",
            ),
            "access_key": FieldMeta(
                label="AWS Access Key",
                help="Leave empty to use the default credential chain (IAM role, env vars).",
                secret=True,
            ),
            "access_key_secret": FieldMeta(
                label="AWS Secret Key",
                secret=True,
            ),
            "invocation_type": FieldMeta(
                label="Invocation Type",
                help="'Event' (async) or 'RequestResponse' (sync).",
                placeholder="Event",
            ),
        },
    ),
    "PCEMattermost": PluginMeta(
        name="PCEMattermost",
        display_name="Mattermost",
        icon="bi-chat-dots",
        description="Sends notifications to Mattermost channels via incoming webhook. "
                    "Self-hosted Slack alternative.",
        how_it_works="Create an Incoming Webhook in Mattermost (Integrations > Incoming "
                     "Webhooks). Copy the webhook URL. Events are rendered through a "
                     "template and posted as messages. Each watcher can override the "
                     "channel via extra_data.",
        fields={
            "webhook_url": FieldMeta(
                label="Webhook URL",
                help="Mattermost incoming webhook URL.",
                required=True, field_type="url",
                placeholder="https://mattermost.example.com/hooks/xxx",
            ),
            "channel": FieldMeta(
                label="Default Channel",
                help="Channel to post to (overridable per watcher via extra_data).",
                placeholder="security-alerts",
            ),
            "username": FieldMeta(
                label="Bot Username",
                help="Display name for the bot in Mattermost.",
                placeholder="Pretty Cool Events",
            ),
            "icon_url": FieldMeta(
                label="Bot Icon URL",
                help="Avatar URL for the bot (optional).",
                field_type="url",
            ),
            "template": FieldMeta(label="Default Template", placeholder="chat-markdown.html"),
        },
    ),
    "PCETelegram": PluginMeta(
        name="PCETelegram",
        display_name="Telegram",
        icon="bi-telegram",
        description="Sends notifications via Telegram Bot API. Create a bot with "
                    "@BotFather, get the token, and add it to a chat or group.",
        how_it_works="Create a bot via @BotFather on Telegram. Send /newbot, follow "
                     "the prompts, and copy the bot token. Add the bot to a group or "
                     "start a chat with it, then get the chat ID (send a message and "
                     "check https://api.telegram.org/bot<token>/getUpdates). Each "
                     "watcher can override the chat_id via extra_data.",
        fields={
            "bot_token": FieldMeta(
                label="Bot Token",
                help="Telegram bot token from @BotFather.",
                required=True, secret=True,
                placeholder="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
            ),
            "chat_id": FieldMeta(
                label="Default Chat ID",
                help="Target chat/group/channel ID. Use negative IDs for groups.",
                required=True,
                placeholder="-1001234567890",
            ),
            "parse_mode": FieldMeta(
                label="Parse Mode",
                help="Message format: HTML or Markdown.",
                placeholder="HTML",
            ),
            "template": FieldMeta(label="Default Template", placeholder="default.html"),
        },
    ),
    "PCELine": PluginMeta(
        name="PCELine",
        display_name="LINE",
        icon="bi-chat-left-text",
        description="Sends notifications via LINE Messaging API. Push messages to "
                    "users, groups, or rooms.",
        how_it_works="Create a LINE Messaging API channel at developers.line.biz. "
                     "Get the Channel Access Token from the channel settings. The 'to' "
                     "field is the user ID, group ID, or room ID to send messages to. "
                     "You can find user IDs from webhook events or the LINE admin console. "
                     "Each watcher can override the recipient via extra_data.to.",
        fields={
            "channel_access_token": FieldMeta(
                label="Channel Access Token",
                help="Long-lived channel access token from LINE Developers console.",
                required=True, secret=True,
            ),
            "to": FieldMeta(
                label="Default Recipient",
                help="User ID, group ID, or room ID to send messages to.",
                required=True,
                placeholder="U1234567890abcdef...",
            ),
            "template": FieldMeta(label="Default Template", placeholder="default.html"),
        },
    ),
}


def get_all_plugin_names() -> list[str]:
    """Return all known plugin names in display order."""
    return list(PLUGIN_METADATA.keys())
