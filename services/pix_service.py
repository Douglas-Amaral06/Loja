import os
import logging

from decimal import Decimal

import httpx

from dotenv import load_dotenv


# ============================================================
# ENV
# ============================================================

load_dotenv()


DOMINIPAY_API_TOKEN = os.getenv(
    "DOMINIPAY_API_TOKEN"
)

DOMINIPAY_API_URL = os.getenv(
    "DOMINIPAY_API_URL"
)

DOMINIPAY_WEBHOOK_URL = os.getenv(
    "DOMINIPAY_WEBHOOK_URL"
)

# Só será usado caso esteja configurado.
DOMINIPAY_EMAIL = os.getenv(
    "DOMINIPAY_EMAIL"
)


# ============================================================
# LOG
# ============================================================

logger = logging.getLogger(__name__)


# ============================================================
# EXCEPTION
# ============================================================

class DominipayError(Exception):
    pass


# ============================================================
# URL FINAL
# ============================================================

def obter_url_pagamentos():

    if not DOMINIPAY_API_URL:

        raise DominipayError(
            "DOMINIPAY_API_URL não configurada."
        )


    url = DOMINIPAY_API_URL.rstrip("/")


    # Caso você já tenha colocado a URL completa.
    if url.endswith(
        "/api-public/payments"
    ):

        return url


    # Caso tenha colocado somente a Base URL.
    return (
        url
        + "/api-public/payments"
    )


# ============================================================
# PEGAR OBJETO DE PAGAMENTO
# ============================================================

def extrair_pagamento(
    response_json: dict
):

    # Algumas APIs retornam diretamente:
    #
    # {
    #   "id": "...",
    #   ...
    # }
    #
    # Outras:
    #
    # {
    #   "data": {
    #       "id": "..."
    #   }
    # }

    if isinstance(
        response_json.get("data"),
        dict
    ):

        return response_json["data"]


    if isinstance(
        response_json.get("payment"),
        dict
    ):

        return response_json["payment"]


    return response_json


# ============================================================
# CRIAR PAGAMENTO
# ============================================================

async def criar_pagamento_pix(
    valor: Decimal,
    telegram_id: int,
):

    if not DOMINIPAY_API_TOKEN:

        raise DominipayError(
            "DOMINIPAY_API_TOKEN não configurado."
        )


    if not DOMINIPAY_WEBHOOK_URL:

        raise DominipayError(
            "DOMINIPAY_WEBHOOK_URL não configurada."
        )


    url = obter_url_pagamentos()


    # ========================================================
    # PAYLOAD
    # ========================================================

    payload = {
        "amount": float(valor),

        "observation": (
            f"telegram_id={telegram_id}"
        ),

        "webhookUrl":
            DOMINIPAY_WEBHOOK_URL,
    }


    # ========================================================
    # EMAIL
    #
    # Só manda se estiver configurado.
    #
    # Se a API não exigir, perfeito.
    #
    # Se retornar erro dizendo que email é obrigatório,
    # depois colocamos DOMINIPAY_EMAIL.
    # ========================================================

    if DOMINIPAY_EMAIL:

        payload["email"] = (
            DOMINIPAY_EMAIL
        )


    # ========================================================
    # HEADERS
    # ========================================================

    headers = {
        "Authorization": (
            f"Bearer {DOMINIPAY_API_TOKEN}"
        ),

        "Content-Type":
            "application/json",

        "Accept":
            "application/json",
    }


    logger.info(
        "Criando PIX DominiPay | "
        "telegram=%s | valor=%s",
        telegram_id,
        valor,
    )


    # ========================================================
    # REQUEST
    # ========================================================

    try:

        async with httpx.AsyncClient(
            timeout=30.0
        ) as client:

            response = await client.post(
                url,
                headers=headers,
                json=payload,
            )


    except httpx.TimeoutException as exc:

        raise DominipayError(
            "Timeout ao conectar com a DominiPay."
        ) from exc


    except httpx.RequestError as exc:

        raise DominipayError(
            "Erro de conexão com a DominiPay."
        ) from exc


    # ========================================================
    # ERRO DA API
    # ========================================================

    if not response.is_success:

        try:

            detalhe = response.json()

        except Exception:

            detalhe = response.text[:1000]


        logger.error(
            "DominiPay HTTP %s | %s",
            response.status_code,
            detalhe,
        )


        raise DominipayError(
            f"DominiPay retornou HTTP "
            f"{response.status_code}."
        )


    # ========================================================
    # JSON
    # ========================================================

    try:

        response_json = (
            response.json()
        )

    except Exception as exc:

        raise DominipayError(
            "Resposta inválida da DominiPay."
        ) from exc


    pagamento = extrair_pagamento(
        response_json
    )


    # ========================================================
    # CAMPOS DA DOCUMENTAÇÃO
    # ========================================================

    payment_id = pagamento.get(
        "id"
    )

    status = pagamento.get(
        "status",
        "pending"
    )

    qr_copy_paste = pagamento.get(
        "qrCopyPaste"
    )

    qr_code_base64 = pagamento.get(
        "qrCodeBase64"
    )

    qr_code_url = pagamento.get(
        "qrCodeUrl"
    )


    if not payment_id:

        logger.error(
            "DominiPay não retornou ID. "
            "Campos: %s",
            list(pagamento.keys())
        )

        raise DominipayError(
            "Pagamento criado sem ID."
        )


    if not (
        qr_copy_paste
        or qr_code_base64
        or qr_code_url
    ):

        logger.error(
            "DominiPay não retornou QR. "
            "Campos: %s",
            list(pagamento.keys())
        )

        raise DominipayError(
            "DominiPay não retornou os dados do PIX."
        )


    return {
        "id": str(payment_id),

        "status": str(status),

        "qrCopyPaste":
            qr_copy_paste,

        "qrCodeBase64":
            qr_code_base64,

        "qrCodeUrl":
            qr_code_url,

        "raw":
            response_json,
    }