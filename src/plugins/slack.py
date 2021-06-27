import slack_sdk
import json

client_id = ''
app_id = ''
client_secret = ''

def config(config):
    print("Plugin config handler reached!")
    client_id = config['client_id']
    client_secret = config['client_secret']
    slack_bot_token = config['slack_bot_token']
    print(slack_bot_token)

def output(output, config):
    slack_bot_token = config['slack_bot_token']
    client = slack_sdk.WebClient(token=slack_bot_token)
    try:
        response = client.chat_postMessage(
                channel="#pce",
                text=output
            )
    except SlackApiError as e:
        assert e.response["error"]
