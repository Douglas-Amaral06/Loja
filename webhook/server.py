import os
import json
import hmac
import hashlib
import logging

from dotenv import load_dotenv

from fastapi import (
    FastAPI,
    Request,
    HTTPException,
)


# ============================================================
# CARREGAR VARIÁVEIS
# ============================================================

load_dotenv()

DOMINIPAY_WEBHOOK_SECRET = os.getenv(
    "DOMINIPAY_WEBHOOK_SECRET"
)


# ============================================================
# LOGS
# ============================================================

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# ============================================================
# CRIAR FASTAPI
#
# ESTA LINHA É A QUE ESTAVA FALTANDO
# ============================================================

app = FastAPI(
    title="CHAPELEIRO7STORE API",
    version="1.0.0"
)


# ============================================================
# ROTA DE TESTE
# ============================================================

@app.get("/")
async def home():

    return {
        "status": "online",
        "service": "CHAPELEIRO7STORE",
        "webhook": "/webhooks/dominipay"
    }


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health")
async def health():

    return {
        "status": "ok"
    }


# ============================================================
# VALIDAR ASSINATURA DA DOMINIPAY
# ============================================================

def validar_assinatura(
    raw_body: bytes,
    timestamp: str,
    signature: str,
) -> bool:

    # Caso ainda não tenhamos configurado o secret
    if not DOMINIPAY_WEBHOOK_SECRET:

        logger.warning(
            "DOMINIPAY_WEBHOOK_SECRET não configurado."
        )

        return True


    # A documentação da DominiPay determina:
    #
    # signed_payload = "{timestamp}.{rawBody}"

    signed_payload = (
        timestamp.encode("utf-8")
        + b"."
        + raw_body
    )


    expected_signature = hmac.new(
        DOMINIPAY_WEBHOOK_SECRET.encode("utf-8"),
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
    # PEGAR BODY ORIGINAL
    #
    # IMPORTANTE:
    # precisamos validar assinatura ANTES do JSON.
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


    logger.info(
        "Webhook recebido | Event ID: %s",
        event_id
    )


    # ========================================================
    # VALIDAR ASSINATURA
    # ========================================================

    if DOMINIPAY_WEBHOOK_SECRET:

        if not signature:

            logger.warning(
                "Webhook recebido sem assinatura."
            )

            raise HTTPException(
                status_code=400,
                detail="X-Webhook-Signature ausente"
            )


        if not timestamp:

            logger.warning(
                "Webhook recebido sem timestamp."
            )

            raise HTTPException(
                status_code=400,
                detail="X-Webhook-Timestamp ausente"
            )


        assinatura_valida = validar_assinatura(
            raw_body=raw_body,
            timestamp=timestamp,
            signature=signature,
        )


        if not assinatura_valida:

            logger.warning(
                "Webhook com assinatura inválida."
            )

            raise HTTPException(
                status_code=401,
                detail="Assinatura inválida"
            )


    # ========================================================
    # TRANSFORMAR BODY EM JSON
    # ========================================================

    try:

        payload = json.loads(
            raw_body.decode("utf-8")
        )

    except Exception as erro:

        logger.error(
            "Erro ao converter webhook para JSON: %s",
            erro
        )

        raise HTTPException(
            status_code=400,
            detail="JSON inválido"
        )


    # ========================================================
    # PEGAR DADOS
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

    email = payload.get(
        "email"
    )

    observation = payload.get(
        "observation"
    )


    # ========================================================
    # MOSTRAR NO LOG
    # ========================================================

    logger.info(
        "========================================"
    )

    logger.info(
        "WEBHOOK DOMINIPAY"
    )

    logger.info(
        "Evento: %s",
        evento
    )

    logger.info(
        "Pagamento: %s",
        payment_id
    )

    logger.info(
        "Status: %s",
        status
    )

    logger.info(
        "Status anterior: %s",
        previous_status
    )

    logger.info(
        "Valor: %s",
        amount
    )

    logger.info(
        "Email: %s",
        email
    )

    logger.info(
        "Observação: %s",
        observation
    )

    logger.info(
        "Event ID: %s",
        event_id
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
            payment_id
        )


    # ========================================================
    # PAGAMENTO MUDOU DE STATUS
    # ========================================================

    elif evento == "payment.status_changed":

        logger.info(
            "Pagamento %s mudou de %s para %s",
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
                "ID: %s | Valor: R$ %s",
                payment_id,
                amount,
            )


            # ================================================
            # DEPOIS ENTRA AQUI:
            #
            # 1. procurar pagamento no SQLite
            # 2. descobrir Telegram ID
            # 3. verificar se já foi creditado
            # 4. adicionar saldo
            # 5. avisar usuário no Telegram
            # ================================================


    # ========================================================
    # RESPOSTA PARA DOMINIPAY
    # ========================================================

    return {
        "received": True,
        "event": evento,
        "payment_id": payment_id,
    }