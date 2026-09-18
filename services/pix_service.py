import os
import base64
import logging
from decimal import Decimal
from typing import Any

import httpx
from dotenv import load_dotenv


# ============================================================
# ENV
# ============================================================

load_dotenv()


DOMINIPAY_API_TOKEN = os.getenv("DOMINIPAY_API_TOKEN")
DOMINIPAY_API_URL = os.getenv("DOMINIPAY_API_URL")
DOMINIPAY_EMAIL = os.getenv("DOMINIPAY_EMAIL")
DOMINIPAY_WEBHOOK_URL = os.getenv("DOMINIPAY_WEBHOOK_URL")
DOMINIPAY_AMOUNT_MODE = os.getenv(
    "DOMINIPAY_AMOUNT_MODE",
    "reais"
).lower()


# ============================================================
# LOG
# ============================================================

logger = logging.getLogger(__name__)


# ============================================================
# EXCEPTION
# ============================================================

class DominipayError(Exception):
    """
    Erro relacionado à comunicação com a DominiPay.
    """

    pass


# ============================================================
# NORMALIZAÇÃO DE CHAVES
# ============================================================

def _normalizar_chave(chave: str) -> str:

    return (
        str(chave)
        .lower()
        .replace("_", "")
        .replace("-", "")
        .replace(" ", "")
    )


# ============================================================
# PERCORRER JSON RECURSIVAMENTE
# ============================================================

def _percorrer_json(data: Any):

    if isinstance(data, dict):

        for chave, valor in data.items():

            yield chave, valor

            if isinstance(valor, (dict, list)):
                yield from _percorrer_json(valor)

    elif isinstance(data, list):

        for item in data:

            if isinstance(item, (dict, list)):
                yield from _percorrer_json(item)


# ============================================================
# PROCURAR CAMPO POR POSSÍVEIS NOMES
# ============================================================

def _buscar_valor(
    data: Any,
    possiveis_chaves: set[str]
):

    chaves_normalizadas = {
        _normalizar_chave(chave)
        for chave in possiveis_chaves
    }

    for chave, valor in _percorrer_json(data):

        chave_normalizada = _normalizar_chave(chave)

        if chave_normalizada in chaves_normalizadas:

            if valor is not None:
                return valor

    return None


# ============================================================
# IDENTIFICAR PIX COPIA E COLA
# ============================================================

def _extrair_pix_copia_cola(data: Any):

    # Primeiro tentamos pelos nomes mais comuns de campos.

    valor = _buscar_valor(
        data,
        {
            "pixCopyPaste",
            "pix_copy_paste",
            "pixCopiaCola",
            "pix_copia_cola",
            "copyPaste",
            "copy_paste",
            "copyAndPaste",
            "brCode",
            "br_code",
            "emv",
            "payload",
            "pixCode",
            "pix_code",
            "qrCodeText",
            "qr_code_text",
        }
    )

    if isinstance(valor, str):

        valor = valor.strip()

        if valor:
            return valor


    # Caso a API coloque o PIX dentro de um campo genérico QR Code,
    # verificamos se parece ser um payload EMV PIX.

    possivel_qr = _buscar_valor(
        data,
        {
            "qrCode",
            "qr_code",
            "qrcode"
        }
    )

    if isinstance(possivel_qr, str):

        possivel_qr = possivel_qr.strip()

        # Payload PIX normalmente começa com 000201.
        if possivel_qr.startswith("000201"):
            return possivel_qr


    # Último fallback:
    # procura qualquer string dentro do JSON começando com 000201.

    for _, valor in _percorrer_json(data):

        if isinstance(valor, str):

            valor = valor.strip()

            if valor.startswith("000201"):
                return valor

    return None


# ============================================================
# EXTRAIR CHAVE PIX
# ============================================================

def _extrair_chave_pix(data: Any):

    valor = _buscar_valor(
        data,
        {
            "pixKey",
            "pix_key",
            "chavePix",
            "chave_pix",
            "randomKey",
            "random_key",
            "pixRandomKey",
            "pix_random_key",
            "key",
        }
    )

    if isinstance(valor, str) and valor.strip():
        return valor.strip()

    return None


# ============================================================
# EXTRAIR ID DA TRANSAÇÃO
# ============================================================

def _extrair_transaction_id(data: Any):

    valor = _buscar_valor(
        data,
        {
            "transactionId",
            "transaction_id",
            "paymentId",
            "payment_id",
            "externalId",
            "external_id",
            "id",
        }
    )

    if valor is None:
        return None

    return str(valor)


# ============================================================
# EXTRAIR STATUS
# ============================================================

def _extrair_status(data: Any):

    valor = _buscar_valor(
        data,
        {
            "status",
            "paymentStatus",
            "payment_status"
        }
    )

    if valor is None:
        return None

    return str(valor)


# ============================================================
# EXTRAIR POSSÍVEL QR CODE EM BASE64
# ============================================================

def _extrair_qr_base64(data: Any):

    valor = _buscar_valor(
        data,
        {
            "qrCodeBase64",
            "qr_code_base64",
            "qrcodeBase64",
            "imageBase64",
            "image_base64",
            "qrImage",
            "qr_image",
        }
    )

    if not isinstance(valor, str):
        return None

    valor = valor.strip()

    if valor.startswith("data:image"):

        try:
            _, base64_data = valor.split(",", 1)
            return base64.b64decode(base64_data)

        except Exception:
            return None

    try:

        decoded = base64.b64decode(
            valor,
            validate=True
        )

        # PNG
        if decoded.startswith(b"\x89PNG"):
            return decoded

        # JPEG
        if decoded.startswith(b"\xff\xd8"):
            return decoded

    except Exception:
        pass

    return None


# ============================================================
# EXTRAIR URL DE QR CODE
# ============================================================

def _extrair_qr_url(data: Any):

    valor = _buscar_valor(
        data,
        {
            "qrCodeUrl",
            "qr_code_url",
            "qrcodeUrl",
            "qrUrl",
            "qr_url",
        }
    )

    if isinstance(valor, str):

        valor = valor.strip()

        if valor.startswith("http://") or valor.startswith("https://"):
            return valor

    return None


# ============================================================
# VALIDAR CONFIGURAÇÃO
# ============================================================

def validar_configuracao():

    erros = []

    if not DOMINIPAY_API_TOKEN:
        erros.append("DOMINIPAY_API_TOKEN")

    if not DOMINIPAY_API_URL:
        erros.append("DOMINIPAY_API_URL")

    if not DOMINIPAY_EMAIL:
        erros.append("DOMINIPAY_EMAIL")

    if erros:

        raise DominipayError(
            "Variáveis da DominiPay não configuradas: "
            + ", ".join(erros)
        )


# ============================================================
# CONVERTER VALOR PARA FORMATO ESPERADO PELA API
# ============================================================

def _converter_amount(valor: Decimal):

    if DOMINIPAY_AMOUNT_MODE == "centavos":

        return int(
            valor * Decimal("100")
        )


    # Modo padrão: reais.

    # Se for número inteiro:
    # 20.00 -> 20
    if valor == valor.to_integral_value():

        return int(valor)


    # 20.50 -> 20.5
    return float(valor)


# ============================================================
# CRIAR PAGAMENTO
# ============================================================

async def criar_pagamento_pix(
    valor: Decimal,
    telegram_user_id: int,
    telegram_username: str | None = None
):

    validar_configuracao()


    # ========================================================
    # PAYLOAD
    # ========================================================

    payload = {
        "amount": _converter_amount(valor),

        "email": DOMINIPAY_EMAIL,

        "observation": (
            f"Telegram #{telegram_user_id}"
        ),
    }


    # Só envia webhookUrl se estiver configurado.
    if DOMINIPAY_WEBHOOK_URL:

        payload["webhookUrl"] = DOMINIPAY_WEBHOOK_URL


    # Adiciona username apenas na observação se existir.
    if telegram_username:

        payload["observation"] = (
            f"Telegram @{telegram_username} "
            f"(ID {telegram_user_id})"
        )


    # ========================================================
    # HEADERS
    # ========================================================

    headers = {
        "Authorization": (
            f"Bearer {DOMINIPAY_API_TOKEN}"
        ),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


    # ========================================================
    # REQUEST
    # ========================================================

    try:

        timeout = httpx.Timeout(
            connect=10.0,
            read=30.0,
            write=30.0,
            pool=10.0,
        )

        async with httpx.AsyncClient(
            timeout=timeout
        ) as client:

            response = await client.post(
                DOMINIPAY_API_URL,
                headers=headers,
                json=payload,
            )


    except httpx.TimeoutException as exc:

        logger.exception(
            "Timeout ao conectar na DominiPay."
        )

        raise DominipayError(
            "A DominiPay demorou demais para responder."
        ) from exc


    except httpx.RequestError as exc:

        logger.exception(
            "Erro de conexão com a DominiPay."
        )

        raise DominipayError(
            "Não foi possível conectar ao gateway de pagamento."
        ) from exc


    # ========================================================
    # STATUS HTTP
    # ========================================================

    if response.status_code < 200 or response.status_code >= 300:

        # Não exibimos token nem headers.

        try:
            erro_api = response.json()

        except Exception:
            erro_api = response.text[:500]

        logger.error(
            "DominiPay retornou HTTP %s: %s",
            response.status_code,
            erro_api,
        )

        raise DominipayError(
            f"DominiPay retornou erro HTTP "
            f"{response.status_code}."
        )


    # ========================================================
    # JSON
    # ========================================================

    try:

        data = response.json()

    except ValueError as exc:

        raise DominipayError(
            "A DominiPay retornou uma resposta inválida."
        ) from exc


    # ========================================================
    # NORMALIZA RETORNO
    # ========================================================

    resultado = {
        "raw": data,

        "transaction_id":
            _extrair_transaction_id(data),

        "status":
            _extrair_status(data),

        "pix_copy_paste":
            _extrair_pix_copia_cola(data),

        "pix_key":
            _extrair_chave_pix(data),

        "qr_base64":
            _extrair_qr_base64(data),

        "qr_url":
            _extrair_qr_url(data),
    }


    # ========================================================
    # VERIFICAR SE RECEBEMOS DADOS PIX
    # ========================================================

    if (
        not resultado["pix_copy_paste"]
        and not resultado["qr_base64"]
        and not resultado["qr_url"]
    ):

        # Não logamos o token, mas as chaves da resposta ajudam
        # a descobrir o schema real da DominiPay.

        if isinstance(data, dict):

            logger.error(
                "Pagamento criado, mas nenhum QR/PIX foi "
                "identificado. Campos retornados: %s",
                list(data.keys()),
            )

        raise DominipayError(
            "O pagamento foi criado, mas a resposta da "
            "DominiPay não trouxe um QR Code reconhecível."
        )


    return resultado