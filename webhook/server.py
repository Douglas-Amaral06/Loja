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

DOMINIPAY_WEBHOOK_SECRET = os.getenv(
    "DOMINIPAY_WEBHOOK_SECRET"
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

logger = logging.getLogger(__name__)


# ============================================================
# VALIDAR ENV
# ============================================================

if not TELEGRAM_BOT_TOKEN:

    raise RuntimeError(
        "TELEGRAM_BOT_TOKEN não configurado."
    )


if not TELEGRAM_WEBHOOK_URL:

    raise RuntimeError(
        "TELEGRAM_WEBHOOK_URL não configurado."
    )


if not TELEGRAM_WEBHOOK_SECRET:

    raise RuntimeError(
        "TELEGRAM_WEBHOOK_SECRET não configurado."
    )


if not DOMINIPAY_WEBHOOK_SECRET:

    raise RuntimeError(
        "DOMINIPAY_WEBHOOK_SECRET não configurado."
    )


# ============================================================
# TELEGRAM APP
# ============================================================

telegram_app = (
    Application
    .builder()
    .token(TELEGRAM_BOT_TOKEN)
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
# STARTUP
# ============================================================

@asynccontextmanager
async def lifespan(
    app: FastAPI
):

    init_db()


    logger.info(
        "Inicializando Telegram..."
    )


    await telegram_app.initialize()


    resultado = (
        await telegram_app.bot.set_webhook(
            url=TELEGRAM_WEBHOOK_URL,

            allowed_updates=(
                Update.ALL_TYPES
            ),

            secret_token=(
                TELEGRAM_WEBHOOK_SECRET
            ),
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
        "💰 DominiPay webhook online."
    )


    yield


    await telegram_app.stop()

    await telegram_app.shutdown()


# ============================================================
# FASTAPI
# ============================================================

app = FastAPI(
    title="CHAPELEIRO7STORE API",

    version="1.0.0",

    lifespan=lifespan,
)


# ============================================================
# HOME
# ============================================================

@app.get("/")
async def home():

    return {
        "status": "online",

        "service":
            "CHAPELEIRO7STORE",

        "telegram":
            "/telegram/webhook",

        "dominipay":
            "/webhooks/dominipay",
    }


# ============================================================
# HEALTH
# ============================================================

@app.get("/health")
async def health():

    return {
        "status": "ok"
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

            detail="Telegram secret ausente",
        )


    if not hmac.compare_digest(
        secret_recebido,
        TELEGRAM_WEBHOOK_SECRET,
    ):

        raise HTTPException(
            status_code=401,

            detail="Telegram secret inválido",
        )


    try:

        data = await request.json()

    except Exception:

        raise HTTPException(
            status_code=400,

            detail="JSON inválido",
        )


    update = Update.de_json(
        data=data,

        bot=telegram_app.bot,
    )


    await telegram_app.update_queue.put(
        update
    )


    return {
        "ok": True
    }


# ============================================================
# VALIDAR DOMINIPAY
# ============================================================

def validar_assinatura_dominipay(
    raw_body: bytes,
    timestamp: str,
    signature: str,
):

    try:

        timestamp_int = int(
            timestamp
        )

    except ValueError:

        return False


    # ========================================================
    # BLOQUEIA REPLAY ANTIGO
    #
    # Aceitamos no máximo 5 minutos de diferença.
    # ========================================================

    agora = int(
        time.time()
    )


    if abs(
        agora - timestamp_int
    ) > 300:

        logger.warning(
            "Webhook DominiPay expirado."
        )

        return False


    # ========================================================
    # timestamp.rawBody
    # ========================================================

    signed_payload = (
        timestamp.encode("utf-8")
        + b"."
        + raw_body
    )


    expected_signature = hmac.new(
        DOMINIPAY_WEBHOOK_SECRET.encode(
            "utf-8"
        ),

        signed_payload,

        hashlib.sha256,
    ).hexdigest()


    return hmac.compare_digest(
        expected_signature,
        signature,
    )


# ============================================================
# DOMINIPAY WEBHOOK
# ============================================================

@app.post("/webhooks/dominipay")
async def dominipay_webhook(
    request: Request
):

    # ========================================================
    # BODY CRU
    # ========================================================

    raw_body = await request.body()


    # ========================================================
    # HEADERS
    # ========================================================

    signature = request.headers.get(
        "X-Webhook-Signature"
    )

    timestamp = request.headers.get(
        "X-Webhook-Timestamp"
    )

    event_id = request.headers.get(
        "X-Webhook-Event-Id"
    )


    if not signature:

        raise HTTPException(
            status_code=400,

            detail=(
                "X-Webhook-Signature ausente"
            ),
        )


    if not timestamp:

        raise HTTPException(
            status_code=400,

            detail=(
                "X-Webhook-Timestamp ausente"
            ),
        )


    # ========================================================
    # ASSINATURA
    # ========================================================

    if not validar_assinatura_dominipay(
        raw_body=raw_body,

        timestamp=timestamp,

        signature=signature,
    ):

        raise HTTPException(
            status_code=401,

            detail=(
                "Assinatura inválida"
            ),
        )


    # ========================================================
    # JSON
    # ========================================================

    try:

        payload = json.loads(
            raw_body.decode("utf-8")
        )

    except Exception:

        raise HTTPException(
            status_code=400,

            detail="JSON inválido",
        )


    # ========================================================
    # CAMPOS
    # ========================================================

    evento = payload.get(
        "event"
    )

    payment_id = payload.get(
        "id"
    )

    status = str(
        payload.get(
            "status",
            ""
        )
    ).lower()

    previous_status = payload.get(
        "previousStatus"
    )

    amount = payload.get(
        "amount"
    )


    logger.info(
        "DominiPay | "
        "event=%s | "
        "id=%s | "
        "status=%s | "
        "previous=%s | "
        "amount=%s",
        evento,
        payment_id,
        status,
        previous_status,
        amount,
    )


    # ========================================================
    # PAGAMENTO CRIADO
    # ========================================================

    if evento == "payment.created":

        return {
            "received": True
        }


    # ========================================================
    # STATUS ALTERADO
    # ========================================================

    if evento != "payment.status_changed":

        return {
            "received": True
        }


    if not payment_id:

        raise HTTPException(
            status_code=400,

            detail="Pagamento sem ID",
        )


    # ========================================================
    # VALOR RECEBIDO
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

            logger.warning(
                "Valor inválido no webhook."
            )


    # ========================================================
    # PROCESSAR NO SQLITE
    #
    # Rodamos em outra thread para não bloquear FastAPI.
    # ========================================================

    resultado = await asyncio.to_thread(
        processar_pagamento_webhook,

        payment_id,

        status,

        event_id,

        webhook_amount_cents,
    )


    action = resultado.get(
        "action"
    )


    logger.info(
        "Resultado pagamento %s: %s",
        payment_id,
        action,
    )


    # ========================================================
    # CRÉDITO REALIZADO
    # ========================================================

    if action == "credited":

        telegram_id = resultado[
            "telegram_id"
        ]

        amount_cents = resultado[
            "amount_cents"
        ]

        balance_cents = resultado[
            "balance_cents"
        ]


        # ====================================================
        # AVISAR USUÁRIO
        # ====================================================

        try:

            await telegram_app.bot.send_message(
                chat_id=telegram_id,

                text=(
                    "✅ <b>Pagamento confirmado!</b>\n\n"

                    f"💰 Valor recebido: "
                    f"<b>{formatar_centavos(amount_cents)}</b>\n"

                    f"💎 Saldo adicionado: "
                    f"<b>{formatar_centavos(amount_cents)}</b>\n\n"

                    f"💳 Seu saldo atual é: "
                    f"<b>{formatar_centavos(balance_cents)}</b>"
                ),

                parse_mode=ParseMode.HTML,
            )


        except Exception:

            logger.exception(
                "Não foi possível avisar "
                "o usuário no Telegram."
            )


    # ========================================================
    # DIFERENÇA DE VALOR
    # ========================================================

    elif action == "amount_mismatch":

        logger.error(
            "VALOR DIVERGENTE! "
            "Pagamento=%s | "
            "esperado=%s | recebido=%s",
            payment_id,
            resultado.get("expected"),
            resultado.get("received"),
        )


    return {
        "received": True,

        "action": action,
    }