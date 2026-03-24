import json
import urllib.request
import urllib.error
import os

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
    else:
        return handle_analyze(event)


def handle_analyze(event):
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

    return call_anthropic(api_key, payload)


def handle_extract(event):
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return cors_response(500, {"error": "ANTHROPIC_API_KEY not configured"})

    try:
        body = json.loads(event.get("body", "{}"))
    except json.JSONDecodeError:
        return cors_response(400, {"error": "Invalid JSON body"})

    pdf_base64 = body.get("pdf_base64", "")
    filename   = body.get("filename", "documento.pdf")

    if not pdf_base64:
        return cors_response(400, {"error": "pdf_base64 is required"})

    prompt_text = EXTRACTION_PROMPT.replace('"arquivo_original": ""', f'"arquivo_original": "{filename}"')

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

    result = call_anthropic(api_key, payload)
    if result["statusCode"] != 200:
        return result

    # Parse the Claude response to extract the JSON nota
    try:
        data = json.loads(result["body"])
        text = data["content"][0]["text"]
        clean = text.replace("```json", "").replace("```", "").strip()
        nota = json.loads(clean)
        nota["arquivo_original"] = filename
        nota["_source"] = "pdf"
        return cors_response(200, {"nota": nota})
    except Exception as e:
        return cors_response(502, {"error": f"Failed to parse extraction response: {str(e)}"})


def call_anthropic(api_key, payload):
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
        with urllib.request.urlopen(req, timeout=90) as response:
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
