import os
import json
import hmac
import hashlib
import logging

from contextlib import asynccontextmanager

from dotenv import load_dotenv

from fastapi import (
    FastAPI,
    Request,
    HTTPException,
)

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
)

# ============================================================
# IMPORTAR FUNÇÕES DO BOT
# ============================================================

from bot import (
    start,
    pix,
    handle_callback,
    error_handler,
)


# ============================================================
# CARREGAR ENV
# ============================================================

load_dotenv()


# ============================================================
# TELEGRAM
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN"
)

TELEGRAM_WEBHOOK_URL = os.getenv(
    "TELEGRAM_WEBHOOK_URL"
)

TELEGRAM_WEBHOOK_SECRET = os.getenv(
    "TELEGRAM_WEBHOOK_SECRET"
)


# ============================================================
# DOMINIPAY
# ============================================================

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
# VALIDAR VARIÁVEIS IMPORTANTES
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


# ============================================================
# CRIAR APLICAÇÃO DO TELEGRAM
#
# updater(None) porque NÃO usaremos polling.
# O FastAPI receberá as mensagens.
# ============================================================

telegram_app = (
    Application
    .builder()
    .token(TELEGRAM_BOT_TOKEN)
    .updater(None)
    .build()
)


# ============================================================
# HANDLERS DO TELEGRAM
# ============================================================

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
# STARTUP / SHUTDOWN
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):

    # ========================================================
    # INICIALIZAR TELEGRAM
    # ========================================================

    logger.info(
        "Inicializando Telegram Bot..."
    )

    await telegram_app.initialize()


    # ========================================================
    # CONFIGURAR WEBHOOK DO TELEGRAM
    # ========================================================

    webhook_result = (
        await telegram_app.bot.set_webhook(
            url=TELEGRAM_WEBHOOK_URL,
            allowed_updates=Update.ALL_TYPES,
            secret_token=TELEGRAM_WEBHOOK_SECRET,
        )
    )


    logger.info(
        "Webhook Telegram configurado: %s",
        webhook_result,
    )

    logger.info(
        "Telegram Webhook URL: %s",
        TELEGRAM_WEBHOOK_URL,
    )


    # ========================================================
    # INICIAR PROCESSAMENTO DE UPDATES
    # ========================================================

    await telegram_app.start()


    logger.info(
        "🤖 Telegram Bot iniciado."
    )

    logger.info(
        "🌐 FastAPI iniciado."
    )

    logger.info(
        "💰 DominiPay Webhook preparado."
    )


    # ========================================================
    # SERVIDOR RODANDO
    # ========================================================

    yield


    # ========================================================
    # DESLIGAMENTO
    # ========================================================

    logger.info(
        "Encerrando Telegram Bot..."
    )

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
        "service": "CHAPELEIRO7STORE",
        "telegram": "/telegram/webhook",
        "dominipay": "/webhooks/dominipay",
    }


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health")
async def health():

    return {
        "status": "ok",
        "telegram": "online",
        "dominipay": "online",
    }


# ============================================================
# WEBHOOK DO TELEGRAM
# ============================================================

@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request
):

    # ========================================================
    # VALIDAR SEGREDO DO TELEGRAM
    # ========================================================

    secret_recebido = request.headers.get(
        "X-Telegram-Bot-Api-Secret-Token"
    )


    if not secret_recebido:

        logger.warning(
            "Webhook Telegram sem secret."
        )

        raise HTTPException(
            status_code=401,
            detail="Telegram secret ausente",
        )


    secret_valido = hmac.compare_digest(
        secret_recebido,
        TELEGRAM_WEBHOOK_SECRET,
    )


    if not secret_valido:

        logger.warning(
            "Webhook Telegram com secret inválido."
        )

        raise HTTPException(
            status_code=401,
            detail="Telegram secret inválido",
        )


    # ========================================================
    # PEGAR JSON DO TELEGRAM
    # ========================================================

    try:

        data = await request.json()

    except Exception:

        raise HTTPException(
            status_code=400,
            detail="JSON inválido",
        )


    # ========================================================
    # CONVERTER JSON PARA UPDATE DO TELEGRAM
    # ========================================================

    update = Update.de_json(
        data=data,
        bot=telegram_app.bot,
    )


    # ========================================================
    # COLOCAR NA FILA DO BOT
    # ========================================================

    await telegram_app.update_queue.put(
        update
    )


    return {
        "ok": True
    }


# ============================================================
# VALIDAR ASSINATURA DOMINIPAY
# ============================================================

def validar_assinatura_dominipay(
    raw_body: bytes,
    timestamp: str,
    signature: str,
) -> bool:

    if not DOMINIPAY_WEBHOOK_SECRET:

        logger.error(
            "DOMINIPAY_WEBHOOK_SECRET "
            "não configurado."
        )

        return False


    # ========================================================
    # FORMATO DA DOMINIPAY:
    #
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
# WEBHOOK DOMINIPAY
# ============================================================

@app.post("/webhooks/dominipay")
async def dominipay_webhook(
    request: Request
):

    # ========================================================
    # PEGAR BODY CRU
    # ========================================================

    raw_body = await request.body()


    # ========================================================
    # HEADERS DOMINIPAY
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


    # ========================================================
    # VALIDAR HEADERS
    # ========================================================

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
    # VALIDAR ASSINATURA
    # ========================================================

    assinatura_valida = (
        validar_assinatura_dominipay(
            raw_body=raw_body,
            timestamp=timestamp,
            signature=signature,
        )
    )


    if not assinatura_valida:

        logger.warning(
            "Webhook DominiPay "
            "com assinatura inválida."
        )

        raise HTTPException(
            status_code=401,
            detail="Assinatura inválida",
        )


    # ========================================================
    # AGORA SIM TRANSFORMAR EM JSON
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
    # DADOS DOMINIPAY
    # ========================================================

    evento = payload.get(
        "event"
    )

    payment_id = payload.get(
        "id"
    )

    status = payload.get(
        "status"
    )

    previous_status = payload.get(
        "previousStatus"
    )

    amount = payload.get(
        "amount"
    )

    observation = payload.get(
        "observation"
    )


    # ========================================================
    # LOG
    # ========================================================

    logger.info(
        "========================================"
    )

    logger.info(
        "💰 WEBHOOK DOMINIPAY"
    )

    logger.info(
        "Evento: %s",
        evento,
    )

    logger.info(
        "Pagamento: %s",
        payment_id,
    )

    logger.info(
        "Status: %s",
        status,
    )

    logger.info(
        "Anterior: %s",
        previous_status,
    )

    logger.info(
        "Valor: %s",
        amount,
    )

    logger.info(
        "Observation: %s",
        observation,
    )

    logger.info(
        "Event ID: %s",
        event_id,
    )

    logger.info(
        "========================================"
    )


    # ========================================================
    # PAGAMENTO CRIADO
    # ========================================================

    if evento == "payment.created":

        logger.info(
            "💰 Pagamento criado: %s",
            payment_id,
        )


    # ========================================================
    # STATUS ALTERADO
    # ========================================================

    elif evento == "payment.status_changed":

        logger.info(
            "Pagamento %s: %s → %s",
            payment_id,
            previous_status,
            status,
        )


        # ====================================================
        # PAGAMENTO APROVADO
        # ====================================================

        if status == "approved":

            logger.info(
                "✅ PAGAMENTO APROVADO!"
            )

            logger.info(
                "Pagamento: %s",
                payment_id,
            )

            logger.info(
                "Valor: R$ %s",
                amount,
            )


            # ================================================
            # PRÓXIMA ETAPA:
            #
            # buscar payment_id no SQLite
            # descobrir telegram_id
            # creditar saldo
            # avisar usuário
            # ================================================


    return {
        "received": True,
        "event": evento,
        "payment_id": payment_id,
    }