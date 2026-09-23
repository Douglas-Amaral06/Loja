import os
import json
import hmac
import time
import asyncio
import hashlib
import logging

from decimal import Decimal

from contextlib import (
    asynccontextmanager,
)

from dotenv import load_dotenv

from fastapi import (
    FastAPI,
    Request,
    HTTPException,
)

from telegram import Update

from telegram.constants import (
    ParseMode,
)

from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
)

from bot import (
    start,
    pix,
    handle_callback,
    error_handler,
)

from database.db import (
    init_db,
    processar_pagamento_webhook,
    decimal_para_centavos,
    formatar_centavos,
)


# ============================================================
# ENV
# ============================================================

load_dotenv()


TELEGRAM_BOT_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN"
)


TELEGRAM_WEBHOOK_URL = os.getenv(
    "TELEGRAM_WEBHOOK_URL"
)


TELEGRAM_WEBHOOK_SECRET = os.getenv(
    "TELEGRAM_WEBHOOK_SECRET"
)


C7_API_SECRET = os.getenv(
    "C7_API_SECRET"
)


# ============================================================
# LOGS
# ============================================================

logging.basicConfig(
    format=(
        "%(asctime)s - "
        "%(name)s - "
        "%(levelname)s - "
        "%(message)s"
    ),

    level=logging.INFO,
)


logging.getLogger(
    "httpx"
).setLevel(
    logging.WARNING
)


logger = logging.getLogger(
    __name__
)


# ============================================================
# VALIDAR ENV
# ============================================================

if not TELEGRAM_BOT_TOKEN:

    raise RuntimeError(
        "TELEGRAM_BOT_TOKEN "
        "não configurado."
    )


if not TELEGRAM_WEBHOOK_URL:

    raise RuntimeError(
        "TELEGRAM_WEBHOOK_URL "
        "não configurado."
    )


if not TELEGRAM_WEBHOOK_SECRET:

    raise RuntimeError(
        "TELEGRAM_WEBHOOK_SECRET "
        "não configurado."
    )


if not C7_API_SECRET:

    raise RuntimeError(
        "C7_API_SECRET "
        "não configurado."
    )


# ============================================================
# TELEGRAM APP
# ============================================================

telegram_app = (
    Application
    .builder()
    .token(
        TELEGRAM_BOT_TOKEN
    )
    .updater(None)
    .build()
)


telegram_app.add_handler(
    CommandHandler(
        "start",
        start,
    )
)


telegram_app.add_handler(
    CommandHandler(
        "pix",
        pix,
    )
)


telegram_app.add_handler(
    CallbackQueryHandler(
        handle_callback,
    )
)


telegram_app.add_error_handler(
    error_handler
)


# ============================================================
# START / STOP
# ============================================================

@asynccontextmanager
async def lifespan(
    app: FastAPI
):

    init_db()


    logger.info(
        "Inicializando Telegram..."
    )


    await (
        telegram_app
        .initialize()
    )


    resultado = (
        await telegram_app.bot
        .set_webhook(
            url=
                TELEGRAM_WEBHOOK_URL,

            allowed_updates=
                Update.ALL_TYPES,

            secret_token=
                TELEGRAM_WEBHOOK_SECRET,
        )
    )


    logger.info(
        "Telegram webhook: %s",
        resultado,
    )


    await telegram_app.start()


    logger.info(
        "🤖 Telegram online."
    )


    logger.info(
        "💰 C7 webhook online."
    )


    yield


    await telegram_app.stop()

    await telegram_app.shutdown()


# ============================================================
# FASTAPI
# ============================================================

app = FastAPI(
    title=
        "CHAPELEIRO7STORE API",

    version=
        "2.0.0",

    lifespan=
        lifespan,
)


# ============================================================
# HOME
# ============================================================

@app.get("/")
async def home():

    return {
        "status":
            "online",

        "service":
            "CHAPELEIRO7STORE",

        "telegram":
            "/telegram/webhook",

        "c7":
            "/webhooks/c7",
    }


# Render costuma testar HEAD /

@app.head("/")
async def home_head():

    return {}


# ============================================================
# HEALTH
# ============================================================

@app.get("/health")
async def health():

    return {
        "status":
            "ok",

        "telegram":
            "online",

        "c7":
            "online",
    }


# ============================================================
# TELEGRAM WEBHOOK
# ============================================================

@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request
):

    secret_recebido = (
        request.headers.get(
            "X-Telegram-Bot-Api-Secret-Token"
        )
    )


    if not secret_recebido:

        raise HTTPException(
            status_code=401,

            detail=
                "Telegram secret ausente",
        )


    if not hmac.compare_digest(
        secret_recebido,
        TELEGRAM_WEBHOOK_SECRET,
    ):

        raise HTTPException(
            status_code=401,

            detail=
                "Telegram secret inválido",
        )


    try:

        data = (
            await request.json()
        )

    except Exception:

        raise HTTPException(
            status_code=400,

            detail=
                "JSON inválido",
        )


    update = Update.de_json(
        data=data,

        bot=
            telegram_app.bot,
    )


    await (
        telegram_app
        .update_queue
        .put(update)
    )


    return {
        "ok":
            True
    }


# ============================================================
# ASSINATURA WEBHOOK C7
# ============================================================

def _assinatura_c7_esperada(
    timestamp: str,

    body_text: str
) -> str:

    # Documentação:
    #
    # HMAC-SHA256(
    #   api_secret,
    #   timestamp + "." + body
    # )

    signed_payload = (
        f"{timestamp}."
        f"{body_text}"
    )


    return hmac.new(
        C7_API_SECRET.encode(
            "utf-8"
        ),

        signed_payload.encode(
            "utf-8"
        ),

        hashlib.sha256,
    ).hexdigest()


def validar_assinatura_c7(

    raw_body: bytes,

    timestamp: str,

    signature: str,
) -> bool:

    # ========================================================
    # TIMESTAMP
    # ========================================================

    try:

        timestamp_int = int(
            timestamp
        )

    except (
        TypeError,
        ValueError,
    ):

        return False


    # Janela de 5 minutos.
    #
    # A API também utiliza essa regra
    # nas assinaturas de escrita.

    agora = int(
        time.time()
    )


    if abs(
        agora
        - timestamp_int
    ) > 300:

        logger.warning(
            "Webhook C7 com "
            "timestamp expirado."
        )

        return False


    # ========================================================
    # BODY CRU
    # ========================================================

    raw_text = (
        raw_body.decode(
            "utf-8"
        )
    )


    expected_raw = (
        _assinatura_c7_esperada(
            timestamp,
            raw_text,
        )
    )


    if hmac.compare_digest(
        expected_raw,
        signature,
    ):

        return True


    # ========================================================
    # FALLBACK JSON.stringify
    #
    # A documentação mostra:
    #
    # JSON.stringify(req.body)
    #
    # Então também tentamos a
    # representação JSON compacta.
    # ========================================================

    try:

        parsed = json.loads(
            raw_text
        )


        compact_text = (
            json.dumps(
                parsed,

                separators=(
                    ",",
                    ":"
                ),

                ensure_ascii=False,
            )
        )


    except Exception:

        return False


    expected_compact = (
        _assinatura_c7_esperada(
            timestamp,
            compact_text,
        )
    )


    return hmac.compare_digest(
        expected_compact,
        signature,
    )


# ============================================================
# WEBHOOK C7
# ============================================================

@app.post("/webhooks/c7")
async def c7_webhook(
    request: Request
):

    # ========================================================
    # BODY CRU
    # ========================================================

    raw_body = (
        await request.body()
    )


    # ========================================================
    # HEADERS
    # ========================================================

    signature = (
        request.headers.get(
            "X-C7-Signature"
        )
    )


    timestamp = (
        request.headers.get(
            "X-C7-Timestamp"
        )
    )


    event_header = (
        request.headers.get(
            "X-C7-Event"
        )
    )


    if not signature:

        raise HTTPException(
            status_code=400,

            detail=
                "X-C7-Signature ausente",
        )


    if not timestamp:

        raise HTTPException(
            status_code=400,

            detail=
                "X-C7-Timestamp ausente",
        )


    # ========================================================
    # VALIDAR HMAC
    # ========================================================

    if not validar_assinatura_c7(

        raw_body=
            raw_body,

        timestamp=
            timestamp,

        signature=
            signature,
    ):

        logger.warning(
            "Webhook C7 com "
            "assinatura inválida."
        )


        raise HTTPException(
            status_code=401,

            detail=
                "Assinatura C7 inválida",
        )


    # ========================================================
    # JSON
    # ========================================================

    try:

        payload = json.loads(
            raw_body.decode(
                "utf-8"
            )
        )


    except Exception:

        raise HTTPException(
            status_code=400,

            detail=
                "JSON inválido",
        )


    # ========================================================
    # EVENTO
    # ========================================================

    evento = (
        payload.get("event")
        or event_header
    )


    data = payload.get(
        "data"
    )


    if not isinstance(
        data,
        dict
    ):

        data = {}


    logger.info(
        "C7 webhook | "
        "event=%s | "
        "identifier=%s | "
        "correlation=%s | "
        "status=%s | "
        "amount=%s",

        evento,

        data.get(
            "identifier"
        ),

        data.get(
            "correlationID"
        ),

        data.get(
            "status"
        ),

        data.get(
            "amount"
        ),
    )


    # ========================================================
    # SOMENTE payment.confirmed
    # ========================================================

    if (
        evento
        != "payment.confirmed"
    ):

        return {
            "received":
                True,

            "ignored":
                True,
        }


    # ========================================================
    # DADOS
    # ========================================================

    payment_id = data.get(
        "identifier"
    )


    external_id = data.get(
        "correlationID"
    )


    status = str(
        data.get(
            "status",
            ""
        )
    ).lower()


    amount = data.get(
        "amount"
    )


    # ========================================================
    # CONFIRMAR STATUS
    # ========================================================

    if status != "approved":

        logger.warning(
            "payment.confirmed recebido "
            "com status inesperado: %s",
            status,
        )


        return {
            "received":
                True,

            "ignored":
                True,
        }


    if (
        not payment_id
        and not external_id
    ):

        raise HTTPException(
            status_code=400,

            detail=
                "Webhook sem identificador "
                "do pagamento",
        )


    # ========================================================
    # VALOR
    # ========================================================

    webhook_amount_cents = None


    if amount is not None:

        try:

            webhook_amount_cents = (
                decimal_para_centavos(
                    Decimal(
                        str(amount)
                    )
                )
            )


        except Exception:

            raise HTTPException(
                status_code=400,

                detail=
                    "Valor inválido no webhook",
            )


    # ========================================================
    # PROCESSAR PAGAMENTO
    # ========================================================

    resultado = (
        await asyncio.to_thread(

            processar_pagamento_webhook,

            payment_id,

            status,

            webhook_amount_cents,

            external_id,

            None,
        )
    )


    action = resultado.get(
        "action"
    )


    logger.info(
        "Resultado webhook C7 | "
        "payment=%s | "
        "action=%s",

        payment_id
        or external_id,

        action,
    )


    # ========================================================
    # PAGAMENTO AINDA NÃO SALVO
    # ========================================================

    if (
        action
        == "payment_not_found"
    ):

        # Não retornamos 2xx.
        #
        # Isso permite que o provedor
        # faça as próximas tentativas
        # de webhook.

        raise HTTPException(
            status_code=409,

            detail=
                "Pagamento ainda não "
                "encontrado localmente",
        )


    # ========================================================
    # VALOR DIFERENTE
    # ========================================================

    if (
        action
        == "amount_mismatch"
    ):

        logger.error(
            "Valor divergente | "
            "esperado=%s | "
            "recebido=%s",

            resultado.get(
                "expected"
            ),

            resultado.get(
                "received"
            ),
        )


        raise HTTPException(
            status_code=409,

            detail=
                "Valor do webhook divergente",
        )


    # ========================================================
    # CREDITADO
    # ========================================================

    if action == "credited":

        telegram_id = (
            resultado[
                "telegram_id"
            ]
        )


        amount_cents = (
            resultado[
                "amount_cents"
            ]
        )


        balance_cents = (
            resultado[
                "balance_cents"
            ]
        )


        # ====================================================
        # AVISAR USUÁRIO
        # ====================================================

        try:

            await (
                telegram_app.bot
                .send_message(
                    chat_id=
                        telegram_id,

                    text=(
                        "✅ <b>Pagamento confirmado!</b>\n\n"

                        f"💰 Valor recebido: "
                        f"<b>{formatar_centavos(amount_cents)}</b>\n"

                        f"💎 Saldo adicionado: "
                        f"<b>{formatar_centavos(amount_cents)}</b>\n\n"

                        f"💳 Seu saldo atual é: "
                        f"<b>{formatar_centavos(balance_cents)}</b>"
                    ),

                    parse_mode=
                        ParseMode.HTML,
                )
            )


        except Exception:

            logger.exception(
                "Pagamento foi creditado, "
                "mas não foi possível "
                "avisar o usuário."
            )


    # ========================================================
    # OK
    # ========================================================

    return {
        "received":
            True,

        "action":
            action,
    }