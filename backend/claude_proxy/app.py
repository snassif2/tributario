import json
import urllib.request
import urllib.error
import os
import base64
import boto3
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

EXTRACTION_PROMPT = """Você é um especialista em documentos fiscais brasileiros.
Analise o PDF fornecido e extraia todos os campos de NF-e (modelo 55) ou NFS-e (padrão nacional).

Retorne APENAS um JSON válido com a estrutura abaixo. Use null para campos ausentes no documento.
NÃO inclua texto adicional, apenas o JSON.

{
  "tipo": "NFe",
  "cenario": "B",
  "chave_acesso": null,
  "emitente": {
    "cnpj": "",
    "nome": "",
    "crt": "3",
    "regime": "Lucro Presumido / Real",
    "uf": ""
  },
  "destinatario": {
    "cnpj_cpf": "",
    "tipo": "PJ",
    "contribuinte": true
  },
  "data_emissao": "YYYY-MM-DD",
  "ano_emissao": 2026,
  "natureza_operacao": "",
  "valor_total_nota": 0.00,
  "itens": [
    {
      "numero": 1,
      "codigo": "",
      "descricao": "",
      "ncm": null,
      "nbs": null,
      "cfop": null,
      "quantidade": 1.0,
      "valor_unitario": 0.00,
      "valor_total": 0.00,
      "desconto": 0.00,
      "tributos_declarados": {
        "icms":   { "valor": 0.00, "aliquota": 0.00, "cst": null },
        "pis":    { "valor": 0.00, "aliquota": 0.00 },
        "cofins": { "valor": 0.00, "aliquota": 0.00 },
        "ipi":    { "valor": 0.00, "aliquota": 0.00 },
        "iss":    { "valor": 0.00, "aliquota": 0.00 },
        "ibs":    { "valor": null, "aliquota": null },
        "cbs":    { "valor": null, "aliquota": null }
      },
      "cst_ibs_cbs": null,
      "cclasstrib": null
    }
  ],
  "erros_parse": [],
  "arquivo_original": ""
}

Preencha todos os campos que conseguir identificar no PDF.
Para NFS-e: tipo="NFSe", preencha iss com a alíquota e valor do ISS, use nbs em vez de ncm se disponível.
Para o campo cenario: use "A" se o PDF mostrar campos IBS/CBS preenchidos, "B" caso contrário."""


def lambda_handler(event, context):
    method = event.get("requestContext", {}).get("http", {}).get("method", "")

    if method == "OPTIONS":
        return cors_response(200, {})

    path = event.get("rawPath", "") or event.get("path", "")

    if path.endswith("/extract"):
        return handle_extract(event)
    elif path.endswith("/report"):
        return handle_report(event)
    else:
        return handle_analyze(event)


def handle_analyze(event):
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    openai_key    = os.environ.get("OPENAI_API_KEY", "")

    if not anthropic_key and not openai_key:
        return cors_response(500, {"error": "No API key configured"})

    try:
        body = json.loads(event.get("body", "{}"))
    except json.JSONDecodeError:
        return cors_response(400, {"error": "Invalid JSON body"})

    messages   = body.get("messages", [])
    max_tokens = body.get("max_tokens", 2000)

    if anthropic_key:
        payload = {
            "model": body.get("model", "claude-sonnet-4-6"),
            "max_tokens": max_tokens,
            "messages": messages,
        }
        result = call_anthropic(anthropic_key, payload)
        if result["statusCode"] == 200 or not openai_key or not _is_billing_error(result):
            return result

    # Fallback to OpenAI
    return call_openai_analyze(openai_key, messages, max_tokens)


def handle_extract(event):
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    openai_key    = os.environ.get("OPENAI_API_KEY", "")

    if not anthropic_key and not openai_key:
        return cors_response(500, {"error": "No API key configured"})

    try:
        body = json.loads(event.get("body", "{}"))
    except json.JSONDecodeError:
        return cors_response(400, {"error": "Invalid JSON body"})

    pdf_base64 = body.get("pdf_base64", "")
    filename   = body.get("filename", "documento.pdf")

    if not pdf_base64:
        return cors_response(400, {"error": "pdf_base64 is required"})

    prompt_text = EXTRACTION_PROMPT.replace('"arquivo_original": ""', f'"arquivo_original": "{filename}"')

    if anthropic_key:
        payload = {
            "model": "claude-sonnet-4-6",
            "max_tokens": 4000,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": pdf_base64,
                            },
                        },
                        {
                            "type": "text",
                            "text": prompt_text,
                        },
                    ],
                }
            ],
        }
        result = call_anthropic(anthropic_key, payload)
        if result["statusCode"] == 200:
            return _parse_extraction_result(result, filename, "pdf")
        if not openai_key or not _is_billing_error(result):
            return result

    # Fallback to OpenAI
    return extract_with_openai(openai_key, pdf_base64, filename, prompt_text)


# ── Report / Email ─────────────────────────────────────────────────────────────

def handle_report(event):
    sender = os.environ.get("SENDER_EMAIL", "")
    if not sender:
        return cors_response(500, {"error": "SENDER_EMAIL not configured"})

    try:
        body = json.loads(event.get("body", "{}"))
    except json.JSONDecodeError:
        return cors_response(400, {"error": "Invalid JSON body"})

    recipient  = body.get("email", "")
    pdf_base64 = body.get("pdf_base64", "")
    filename   = body.get("filename", "relatorio-tributario.pdf")

    if not recipient or not pdf_base64:
        return cors_response(400, {"error": "email and pdf_base64 are required"})

    # Build MIME message with PDF attachment
    msg = MIMEMultipart("mixed")
    msg["Subject"] = "Relatório de Análise Tributária — LC 214/2025"
    msg["From"]    = f"Validador Tributario <{sender}>"
    msg["To"]      = recipient

    html_body = MIMEText(
        "<p>Olá,</p>"
        "<p>Segue em anexo o relatório de análise tributária gerado pelo <strong>Validador Tributário NF-e/NFS-e</strong>.</p>"
        "<p>O relatório contém o detalhamento do impacto da Reforma Tributária (LC 214/2025) nos documentos fiscais processados.</p>"
        "<br/><p style='color:#6b7280;font-size:12px'>Este relatório não substitui assessoria tributária especializada.</p>",
        "html", "utf-8"
    )
    msg.attach(html_body)

    pdf_bytes  = base64.b64decode(pdf_base64)
    attachment = MIMEApplication(pdf_bytes, _subtype="pdf")
    attachment.add_header("Content-Disposition", "attachment", filename=filename)
    msg.attach(attachment)

    try:
        ses = boto3.client("ses", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        ses.send_raw_email(
            Source=sender,
            Destinations=[recipient],
            RawMessage={"Data": msg.as_string()},
        )
        return cors_response(200, {"message": "Relatório enviado com sucesso"})
    except Exception as e:
        return cors_response(502, {"error": f"SES error: {str(e)}"})


# ── Helpers ────────────────────────────────────────────────────────────────────

def _is_billing_error(result):
    """Return True if the failure is a credit/billing issue (worth retrying with another provider)."""
    try:
        body = json.loads(result["body"])
        err = body.get("error", {})
        msg = (err.get("message", "") if isinstance(err, dict) else str(err)).lower()
        return any(w in msg for w in ("credit", "billing", "balance", "quota", "insufficient"))
    except Exception:
        return False


def _parse_extraction_result(result, filename, source_tag):
    try:
        data = json.loads(result["body"])
        text = data["content"][0]["text"]
        clean = text.replace("```json", "").replace("```", "").strip()
        nota = json.loads(clean)
        nota["arquivo_original"] = filename
        nota["_source"] = source_tag
        return cors_response(200, {"nota": nota})
    except Exception as e:
        return cors_response(502, {"error": f"Failed to parse extraction response: {str(e)}"})


# ── Anthropic ──────────────────────────────────────────────────────────────────

def call_anthropic(api_key, payload):
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            result = json.loads(response.read().decode("utf-8"))
        return cors_response(200, result)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        return cors_response(e.code, json.loads(error_body) if error_body else {"error": str(e)})
    except Exception as e:
        return cors_response(502, {"error": str(e)})


# ── OpenAI ─────────────────────────────────────────────────────────────────────

def call_openai_analyze(api_key, messages, max_tokens):
    """Call OpenAI Chat Completions, converting Anthropic message format."""
    openai_messages = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, list):
            # Keep only text blocks; drop binary document blocks
            parts = [{"type": "text", "text": b["text"]} for b in content if b.get("type") == "text"]
            content = parts if parts else ""
        openai_messages.append({"role": msg["role"], "content": content})

    payload = {
        "model": "gpt-4o",
        "max_tokens": max_tokens,
        "messages": openai_messages,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        # Wrap in Anthropic-compatible envelope so the frontend works unchanged
        text = result["choices"][0]["message"]["content"]
        return cors_response(200, {"content": [{"type": "text", "text": text}]})
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        return cors_response(e.code, json.loads(error_body) if error_body else {"error": str(e)})
    except Exception as e:
        return cors_response(502, {"error": str(e)})


def extract_with_openai(api_key, pdf_base64, filename, prompt):
    """Upload PDF to OpenAI Files API, run extraction, then delete the file."""
    try:
        file_id = _upload_pdf_openai(api_key, pdf_base64)
    except Exception as e:
        return cors_response(502, {"error": f"OpenAI file upload failed: {str(e)}"})

    payload = {
        "model": "gpt-4o",
        "max_tokens": 4000,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "file", "file": {"file_id": file_id}},
                {"type": "text", "text": prompt},
            ],
        }],
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        # Best-effort cleanup
        try:
            urllib.request.urlopen(urllib.request.Request(
                f"https://api.openai.com/v1/files/{file_id}",
                headers={"Authorization": f"Bearer {api_key}"},
                method="DELETE",
            ), timeout=10)
        except Exception:
            pass

        text = result["choices"][0]["message"]["content"]
        clean = text.replace("```json", "").replace("```", "").strip()
        nota = json.loads(clean)
        nota["arquivo_original"] = filename
        nota["_source"] = "pdf_openai"
        return cors_response(200, {"nota": nota})

    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        return cors_response(e.code, json.loads(error_body) if error_body else {"error": str(e)})
    except Exception as e:
        return cors_response(502, {"error": f"OpenAI extraction failed: {str(e)}"})


def _upload_pdf_openai(api_key, pdf_base64):
    """Upload a base64-encoded PDF to OpenAI and return the file_id."""
    pdf_bytes = base64.b64decode(pdf_base64)
    boundary = b"PythonMultipartBoundary7MA4YWx"

    body = (
        b"--" + boundary + b"\r\n"
        b'Content-Disposition: form-data; name="purpose"\r\n\r\n'
        b"user_data\r\n"
        b"--" + boundary + b"\r\n"
        b'Content-Disposition: form-data; name="file"; filename="document.pdf"\r\n'
        b"Content-Type: application/pdf\r\n\r\n"
        + pdf_bytes
        + b"\r\n--" + boundary + b"--\r\n"
    )

    req = urllib.request.Request(
        "https://api.openai.com/v1/files",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary.decode()}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())["id"]


# ── CORS ───────────────────────────────────────────────────────────────────────

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
