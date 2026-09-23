import os
import json
import hmac
import time
import uuid
import hashlib
import logging
from decimal import Decimal

import httpx
from dotenv import load_dotenv


load_dotenv()

C7_API_KEY = os.getenv("C7_API_KEY")
C7_API_SECRET = os.getenv("C7_API_SECRET")
C7_API_URL = os.getenv(
    "C7_API_URL",
    "https://api.carteirado7.com/v2"
)
C7_WEBHOOK_URL = os.getenv("C7_WEBHOOK_URL")

logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)


class C7Error(Exception):
    pass


def _validar_configuracao():
    faltando = []

    if not C7_API_KEY:
        faltando.append("C7_API_KEY")

    if not C7_API_SECRET:
        faltando.append("C7_API_SECRET")

    if not C7_API_URL:
        faltando.append("C7_API_URL")

    if not C7_WEBHOOK_URL:
        faltando.append("C7_WEBHOOK_URL")

    if faltando:
        raise C7Error(
            "Variáveis não configuradas: "
            + ", ".join(faltando)
        )


def _url_criar_pagamento() -> str:
    base = C7_API_URL.rstrip("/")

    if base.endswith("/payment/create"):
        return base

    return f"{base}/payment/create"


def _url_status_pagamento(
    payment_id: str
) -> str:

    base = C7_API_URL.rstrip("/")

    return (
        f"{base}/payment/"
        f"{payment_id}/status"
    )


def _serializar_body(
    payload: dict
) -> str:

    # IMPORTANTE:
    # vamos assinar exatamente o mesmo
    # JSON que será enviado para a API.

    return json.dumps(
        payload,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _criar_headers_escrita(
    body: str
) -> dict:

    timestamp = str(
        int(time.time())
    )

    nonce = str(
        uuid.uuid4()
    )

    signed_payload = (
        f"{timestamp}."
        f"{nonce}."
        f"{body}"
    )

    signature = hmac.new(
        C7_API_SECRET.encode("utf-8"),
        signed_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return {
        "Authorization":
            f"Bearer {C7_API_KEY}",

        "Content-Type":
            "application/json",

        "Accept":
            "application/json",

        "X-C7-Timestamp":
            timestamp,

        "X-C7-Nonce":
            nonce,

        "X-C7-Signature":
            signature,
    }


def _extrair_erro(
    response: httpx.Response
) -> str:

    try:
        data = response.json()

    except Exception:
        return response.text[:1000]


    if isinstance(data, dict):

        error = data.get("error")

        if isinstance(error, dict):

            code = error.get("code")
            message = error.get("message")
            request_id = error.get(
                "request_id"
            )

            partes = [
                item
                for item in (
                    code,
                    message,
                    request_id,
                )
                if item
            ]

            if partes:

                return " | ".join(
                    str(item)
                    for item in partes
                )


        message = data.get("message")

        if message:
            return str(message)


    return str(data)[:1000]


async def criar_pagamento_pix(
    valor: Decimal,
    telegram_id: int,
) -> dict:

    _validar_configuracao()


    # Identificador nosso.
    #
    # Depois o webhook devolve isso
    # em correlationID.

    external_id = (
        f"tg_{telegram_id}_"
        f"{uuid.uuid4().hex}"
    )


    # A documentação desta API trabalha
    # o amount em reais.
    #
    # /pix 10
    # ->
    # "amount": 10.00

    payload = {
        "amount": float(valor),

        "callbackUrl":
            C7_WEBHOOK_URL,

        "externalId":
            external_id,
    }


    # Não enviamos acquirer_code.
    #
    # A própria API selecionará
    # automaticamente a adquirente.


    body = _serializar_body(
        payload
    )


    headers = (
        _criar_headers_escrita(
            body
        )
    )


    url = _url_criar_pagamento()


    logger.info(
        "Criando PIX C7 | "
        "telegram=%s | "
        "valor=%s | "
        "external_id=%s",
        telegram_id,
        valor,
        external_id,
    )


    try:

        async with httpx.AsyncClient(
            timeout=30.0
        ) as client:

            response = await client.post(
                url,
                headers=headers,

                # IMPORTANTE:
                # enviamos exatamente o
                # body que assinamos.

                content=body.encode(
                    "utf-8"
                ),
            )


    except httpx.TimeoutException as exc:

        raise C7Error(
            "Timeout ao conectar "
            "com a API C7."
        ) from exc


    except httpx.RequestError as exc:

        raise C7Error(
            "Erro de conexão "
            "com a API C7."
        ) from exc


    if (
        response.status_code != 201
        and not response.is_success
    ):

        detalhe = _extrair_erro(
            response
        )

        logger.error(
            "C7 HTTP %s | %s",
            response.status_code,
            detalhe,
        )

        raise C7Error(
            f"C7 retornou HTTP "
            f"{response.status_code}: "
            f"{detalhe}"
        )


    try:

        data = response.json()

    except ValueError as exc:

        raise C7Error(
            "A API C7 retornou "
            "uma resposta JSON inválida."
        ) from exc


    if (
        not isinstance(data, dict)
        or data.get("ok") is not True
    ):

        logger.error(
            "Resposta inesperada "
            "da C7: %s",
            data,
        )

        raise C7Error(
            "A API C7 não confirmou "
            "a criação do pagamento."
        )


    payment = data.get(
        "payment"
    )


    if not isinstance(
        payment,
        dict
    ):

        raise C7Error(
            "A API C7 não retornou "
            "o objeto payment."
        )


    payment_id = payment.get(
        "id"
    )

    payment_external_id = (
        payment.get("externalId")
        or external_id
    )

    status = payment.get(
        "status",
        "pending"
    )

    pix_copia_e_cola = (
        payment.get(
            "pixCopiaECola"
        )
    )

    qr_code_base64 = (
        payment.get(
            "qrCodeBase64"
        )
    )

    expires_at = payment.get(
        "expiresAt"
    )


    if not payment_id:

        raise C7Error(
            "A API C7 não retornou "
            "o ID do pagamento."
        )


    if (
        not pix_copia_e_cola
        and not qr_code_base64
    ):

        raise C7Error(
            "A API C7 não retornou "
            "QR Code nem PIX Copia e Cola."
        )


    return {
        "id":
            str(payment_id),

        "externalId":
            str(payment_external_id),

        "amount":
            payment.get("amount"),

        "status":
            str(status).lower(),

        "pixCopiaECola":
            pix_copia_e_cola,

        "qrCodeBase64":
            qr_code_base64,

        "expiresAt":
            expires_at,

        "raw":
            data,
    }


async def consultar_status_pagamento(
    payment_id: str
) -> dict:

    _validar_configuracao()


    url = (
        _url_status_pagamento(
            payment_id
        )
    )


    # Consulta de status exige
    # somente a API Key.

    headers = {
        "Authorization":
            f"Bearer {C7_API_KEY}",

        "Accept":
            "application/json",
    }


    try:

        async with httpx.AsyncClient(
            timeout=30.0
        ) as client:

            response = await client.get(
                url,
                headers=headers,
            )


    except httpx.TimeoutException as exc:

        raise C7Error(
            "Timeout ao consultar "
            "pagamento na API C7."
        ) from exc


    except httpx.RequestError as exc:

        raise C7Error(
            "Erro de conexão ao "
            "consultar a API C7."
        ) from exc


    if not response.is_success:

        detalhe = _extrair_erro(
            response
        )

        raise C7Error(
            f"C7 retornou HTTP "
            f"{response.status_code}: "
            f"{detalhe}"
        )


    try:

        return response.json()

    except ValueError as exc:

        raise C7Error(
            "Resposta inválida ao "
            "consultar pagamento."
        ) from exc