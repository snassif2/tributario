import json
import urllib.request
import urllib.error
import os


def lambda_handler(event, context):
    # Handle CORS preflight
    if event.get("requestContext", {}).get("http", {}).get("method") == "OPTIONS":
        return cors_response(200, {})

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return cors_response(500, {"error": "ANTHROPIC_API_KEY not configured"})

    try:
        body = json.loads(event.get("body", "{}"))
    except json.JSONDecodeError:
        return cors_response(400, {"error": "Invalid JSON body"})

    payload = {
        "model": body.get("model", "claude-sonnet-4-6"),
        "max_tokens": body.get("max_tokens", 2000),
        "messages": body.get("messages", []),
    }

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
        return cors_response(200, result)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        return cors_response(e.code, json.loads(error_body) if error_body else {"error": str(e)})
    except Exception as e:
        return cors_response(502, {"error": str(e)})


def cors_response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Content-Type": "application/json",
        },
        "body": json.dumps(body),
    }
