import os
import html
import base64
import logging

from io import BytesIO

from decimal import (
    Decimal,
    InvalidOperation,
)

import qrcode

from dotenv import load_dotenv

from telegram import (
    Update,
    InputFile,
    CopyTextButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from telegram.constants import (
    ParseMode,
)

from telegram.ext import (
    ContextTypes,
)

from services.pix_service import (
    criar_pagamento_pix,
    C7Error,
)

from database.db import (
    init_db,
    registrar_usuario,
    obter_saldo,
    registrar_pagamento_pix,
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

# Impede o httpx de jogar URL do Telegram
# com token dentro do log.

logging.getLogger(
    "httpx"
).setLevel(
    logging.WARNING
)

logger = logging.getLogger(
    __name__
)


# ============================================================
# PIX
# ============================================================

PIX_MINIMO = Decimal(
    "10.00"
)


# ============================================================
# CALLBACKS
# ============================================================

CALLBACK_MENU = "menu"

CALLBACK_PERFIL = "perfil"

CALLBACK_SALDO = (
    "adicionar_saldo"
)

CALLBACK_PIX = (
    "pix_automatico"
)

CALLBACK_RECARGA_MANUAL = (
    "recarga_manual"
)

CALLBACK_VOLTAR = (
    "voltar_inicio"
)

CALLBACK_VOLTAR_SALDO = (
    "voltar_saldo"
)


# ============================================================
# TECLADO PRINCIPAL
# ============================================================

TECLADO_PRINCIPAL = (
    InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🛒 Menu",
                    callback_data=(
                        CALLBACK_MENU
                    ),
                ),

                InlineKeyboardButton(
                    "💎 Seu Perfil",
                    callback_data=(
                        CALLBACK_PERFIL
                    ),
                ),
            ],

            [
                InlineKeyboardButton(
                    "💰 Adiciona Saldo",
                    callback_data=(
                        CALLBACK_SALDO
                    ),
                )
            ],
        ]
    )
)


# ============================================================
# TECLADO SALDO
# ============================================================

TECLADO_ADICIONAR_SALDO = (
    InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "💠 Pix automático",

                    callback_data=(
                        CALLBACK_PIX
                    ),
                ),

                InlineKeyboardButton(
                    "💵 Recarga manual",

                    callback_data=(
                        CALLBACK_RECARGA_MANUAL
                    ),
                ),
            ],

            [
                InlineKeyboardButton(
                    "« volta",

                    callback_data=(
                        CALLBACK_VOLTAR
                    ),
                )
            ],
        ]
    )
)


# ============================================================
# VOLTAR
# ============================================================

TECLADO_VOLTAR = (
    InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "« volta",

                    callback_data=(
                        CALLBACK_VOLTAR
                    ),
                )
            ]
        ]
    )
)


TECLADO_VOLTAR_SALDO = (
    InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "« volta",

                    callback_data=(
                        CALLBACK_VOLTAR_SALDO
                    ),
                )
            ]
        ]
    )
)


# ============================================================
# TEXTO START
# ============================================================

def gerar_texto_inicio(
    user_name: str
):

    nome = html.escape(
        user_name
    )


    return (
        f"👋 Fala, <b>{nome}</b>! "
        "Seja muito bem-vindo(a).\n\n"

        "🎩 <b>CHAPELEIRO7STORE — "
        "A EXCELÊNCIA EM DIGITAL</b> 🚀\n\n"

        "⭐ Operando com alta performance no mercado\n"

        "🥇 Referência em automação e atendimento no Telegram\n"

        "🔒 Padrão de qualidade exclusivo direto da administração\n\n"

        "⚡ <b>DIFERENCIAIS DA CASA:</b>\n"

        "• Sistema de pagamentos instantâneo via PIX\n"

        "• Processamento automatizado 24/7\n\n"

        "📌 <b>DIRETRIZES E TERMOS:</b>\n"

        "⚠️ Saldo adicionado não é reembolsável\n"

        "⚠️ Segurança e proteção antifraude ativas\n"

        "⚠️ Tentativas de fraude resultam em BAN imediato\n"

        "⚠️ Garantia restrita a itens LIVE no ato\n"

        "⚠️ Pediu VBV ou dados divergentes? Sem troca\n"

        "⚠️ Janela de suporte/troca via bot: até 5 minutos\n\n"

        "⏱️ <b>SUPORTE E GARANTIA:</b>\n"

        "🛡️ Validação automatizada ativa\n"

        "📞 Atendimento exclusivamente pelos canais oficiais\n\n"

        "📢 Canal Oficial: @CHAPELEIRO7NEWS\n"

        "📢 Grupo: @CHAPELEIRO7STOREGROUP\n"

        "📞 Suporte: @CHAPELEIROSTORESUPORTE01\n\n"

        "💼 Atitude de profissional.\n"

        "🔥 <b>Bem-vindo ao topo. "
        "Seja Chapeleiro7Store.</b>"
    )


# ============================================================
# TEXTO ADICIONAR SALDO
# ============================================================

def gerar_texto_adicionar_saldo():

    return (
        "💰 <b><u>Adicione saldo na STORE</u></b>\n\n"

        "<i>"
        "Você pode adicionar saldo na store via PIX "
        "de forma automática ou por recarga manual "
        "comprando diretamente com um dos admins."
        "</i>"
    )


# ============================================================
# TEXTO /PIX
# ============================================================

def gerar_texto_instrucao_pix():

    return (
        "✨ <b>Adição de saldo via pix</b>\n\n"

        "<i>"
        "Tornou-se mais fácil! Agora os seus pagamentos "
        "serão processados de forma automática pelo bot. 😜"
        "</i>\n\n"

        "<b>Para criar uma transação pelo bot use:</b>\n"

        "<code>/pix valor</code>\n\n"

        "<b>Exemplo:</b> "
        "<code>/pix 20</code>\n\n"

        "💰 Valor mínimo: <b>R$ 10,00</b>\n\n"

        "<i>"
        "✅ O seu saldo estará disponível após "
        "a confirmação do pagamento."
        "</i>"
    )


# ============================================================
# CONVERTER VALOR
# ============================================================

def converter_valor_pix(
    texto: str
):

    texto = (
        texto
        .strip()
        .replace("R$", "")
        .replace(" ", "")
        .replace(",", ".")
    )


    try:

        valor = Decimal(
            texto
        )

    except InvalidOperation:

        return None


    if (
        not valor.is_finite()
        or valor <= 0
    ):

        return None


    if abs(
        valor.as_tuple().exponent
    ) > 2:

        return None


    return valor.quantize(
        Decimal("0.01")
    )


# ============================================================
# GERAR QR LOCAL
# ============================================================

def gerar_qrcode_local(
    codigo_pix: str
):

    qr = qrcode.QRCode(
        version=None,

        error_correction=(
            qrcode.constants
            .ERROR_CORRECT_M
        ),

        box_size=10,

        border=4,
    )


    qr.add_data(
        codigo_pix
    )


    qr.make(
        fit=True
    )


    imagem = qr.make_image()


    arquivo = BytesIO()


    imagem.save(
        arquivo,
        format="PNG"
    )


    arquivo.seek(0)

    arquivo.name = "pix.png"


    return arquivo


# ============================================================
# QR BASE64
# ============================================================

def decodificar_qr_base64(
    valor: str
):

    # A API pode devolver:
    #
    # data:image/png;base64,ABC...
    #
    # ou somente:
    #
    # ABC...

    if "," in valor:

        valor = valor.split(
            ",",
            1
        )[1]


    try:

        dados = base64.b64decode(
            valor,
            validate=True
        )

    except Exception:

        dados = base64.b64decode(
            valor
        )


    arquivo = BytesIO(
        dados
    )


    arquivo.seek(0)

    arquivo.name = "pix.png"


    return arquivo


# ============================================================
# /START
# ============================================================

async def start(
    update: Update,

    context:
        ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user


    registrar_usuario(
        telegram_id=user.id,

        username=user.username,

        first_name=user.first_name,
    )


    nome = (
        user.first_name
        or "CHAPELEIRO"
    )


    await update.message.reply_text(
        text=gerar_texto_inicio(
            nome
        ),

        parse_mode=
            ParseMode.HTML,

        reply_markup=
            TECLADO_PRINCIPAL,
    )


# ============================================================
# CALLBACK
# ============================================================

async def handle_callback(
    update: Update,

    context:
        ContextTypes.DEFAULT_TYPE
):

    query = (
        update.callback_query
    )


    await query.answer()


    user = query.from_user

    data = query.data


    registrar_usuario(
        telegram_id=user.id,

        username=user.username,

        first_name=user.first_name,
    )


    nome = (
        user.first_name
        or "CHAPELEIRO"
    )


    # ========================================================
    # ADICIONAR SALDO
    # ========================================================

    if data == CALLBACK_SALDO:

        await query.edit_message_text(
            text=
                gerar_texto_adicionar_saldo(),

            parse_mode=
                ParseMode.HTML,

            reply_markup=
                TECLADO_ADICIONAR_SALDO,
        )

        return


    # ========================================================
    # VOLTAR
    # ========================================================

    if data == CALLBACK_VOLTAR:

        await query.edit_message_text(
            text=
                gerar_texto_inicio(
                    nome
                ),

            parse_mode=
                ParseMode.HTML,

            reply_markup=
                TECLADO_PRINCIPAL,
        )

        return


    # ========================================================
    # MENU
    # ========================================================

    if data == CALLBACK_MENU:

        await query.edit_message_text(
            text=(
                "🛒 <b>Catálogo de Produtos</b>\n\n"

                "🚧 O catálogo será configurado "
                "em breve."
            ),

            parse_mode=
                ParseMode.HTML,

            reply_markup=
                TECLADO_VOLTAR,
        )

        return


    # ========================================================
    # PERFIL
    # ========================================================

    if data == CALLBACK_PERFIL:

        saldo = obter_saldo(
            user.id
        )


        await query.edit_message_text(
            text=(
                "💎 <b>Seu Perfil</b>\n\n"

                f"👤 Nome: "
                f"<b>{html.escape(nome)}</b>\n"

                f"🆔 ID: "
                f"<code>{user.id}</code>\n"

                f"💰 Saldo: "
                f"<b>{formatar_centavos(saldo)}</b>"
            ),

            parse_mode=
                ParseMode.HTML,

            reply_markup=
                TECLADO_VOLTAR,
        )

        return


    # ========================================================
    # PIX
    # ========================================================

    if data == CALLBACK_PIX:

        await query.edit_message_text(
            text=
                gerar_texto_instrucao_pix(),

            parse_mode=
                ParseMode.HTML,

            reply_markup=
                TECLADO_VOLTAR_SALDO,
        )

        return


    # ========================================================
    # RECARGA MANUAL
    # ========================================================

    if (
        data
        == CALLBACK_RECARGA_MANUAL
    ):

        await query.edit_message_text(
            text=(
                "💵 <b>Recarga Manual</b>\n\n"

                "Para realizar uma recarga manual, "
                "entre em contato com o suporte.\n\n"

                "📞 @CHAPELEIROSTORESUPORTE01"
            ),

            parse_mode=
                ParseMode.HTML,

            reply_markup=
                TECLADO_VOLTAR_SALDO,
        )

        return


    # ========================================================
    # VOLTAR SALDO
    # ========================================================

    if (
        data
        == CALLBACK_VOLTAR_SALDO
    ):

        await query.edit_message_text(
            text=
                gerar_texto_adicionar_saldo(),

            parse_mode=
                ParseMode.HTML,

            reply_markup=
                TECLADO_ADICIONAR_SALDO,
        )

        return


# ============================================================
# /PIX
# ============================================================

async def pix(
    update: Update,

    context:
        ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user


    registrar_usuario(
        telegram_id=user.id,

        username=user.username,

        first_name=user.first_name,
    )


    # ========================================================
    # APENAS /PIX
    # ========================================================

    if not context.args:

        await update.message.reply_text(
            text=
                gerar_texto_instrucao_pix(),

            parse_mode=
                ParseMode.HTML,
        )

        return


    # ========================================================
    # FORMATO
    # ========================================================

    if len(context.args) != 1:

        await update.message.reply_text(
            text=(
                "❌ <b>Formato inválido.</b>\n\n"

                "Use:\n"

                "<code>/pix valor</code>\n\n"

                "Exemplo:\n"

                "<code>/pix 20</code>"
            ),

            parse_mode=
                ParseMode.HTML,
        )

        return


    valor = converter_valor_pix(
        context.args[0]
    )


    # ========================================================
    # VALOR INVÁLIDO
    # ========================================================

    if valor is None:

        await update.message.reply_text(
            text=(
                "❌ <b>Valor inválido.</b>\n\n"

                "Exemplo correto:\n"

                "<code>/pix 20</code>"
            ),

            parse_mode=
                ParseMode.HTML,
        )

        return


    # ========================================================
    # MÍNIMO
    # ========================================================

    if valor < PIX_MINIMO:

        await update.message.reply_text(
            text=(
                "❌ <b>Valor abaixo do mínimo.</b>\n\n"

                "O valor mínimo para adicionar saldo "
                "via PIX é <b>R$ 10,00</b>.\n\n"

                "Exemplo:\n"

                "<code>/pix 10</code>"
            ),

            parse_mode=
                ParseMode.HTML,
        )

        return


    valor_formatado = (
        f"{valor:.2f}"
        .replace(".", ",")
    )


    # ========================================================
    # CARREGANDO
    # ========================================================

    mensagem_carregando = (
        await update.message.reply_text(
            text=(
                "⏳ <b>Gerando seu PIX...</b>\n\n"

                f"💰 Valor: "
                f"<b>R$ {valor_formatado}</b>"
            ),

            parse_mode=
                ParseMode.HTML,
        )
    )


    # ========================================================
    # CRIAR PIX C7
    # ========================================================

    try:

        pagamento = (
            await criar_pagamento_pix(
                valor=valor,

                telegram_id=
                    user.id,
            )
        )


    except C7Error as erro:

        logger.error(
            "Erro C7: %s",
            erro,
        )


        await (
            mensagem_carregando
            .edit_text(
                text=(
                    "❌ <b>Não foi possível gerar "
                    "o PIX.</b>\n\n"

                    "Tente novamente em alguns instantes."
                ),

                parse_mode=
                    ParseMode.HTML,
            )
        )

        return


    except Exception:

        logger.exception(
            "Erro inesperado no /pix."
        )


        await (
            mensagem_carregando
            .edit_text(
                text=(
                    "❌ <b>Erro interno ao gerar PIX.</b>"
                ),

                parse_mode=
                    ParseMode.HTML,
            )
        )

        return


    # ========================================================
    # SALVAR NO BANCO
    # ========================================================

    payment_id = pagamento[
        "id"
    ]


    external_id = pagamento[
        "externalId"
    ]


    status = pagamento[
        "status"
    ]


    registrar_pagamento_pix(

        gateway_payment_id=
            payment_id,

        external_id=
            external_id,

        telegram_id=
            user.id,

        amount_cents=
            decimal_para_centavos(
                valor
            ),

        status=
            status,
    )


    # ========================================================
    # DADOS PIX
    # ========================================================

    qr_copy_paste = (
        pagamento.get(
            "pixCopiaECola"
        )
    )


    qr_base64 = (
        pagamento.get(
            "qrCodeBase64"
        )
    )


    expires_at = (
        pagamento.get(
            "expiresAt"
        )
    )


    # ========================================================
    # REMOVER CARREGANDO
    # ========================================================

    try:

        await (
            mensagem_carregando
            .delete()
        )

    except Exception:

        pass


    # ========================================================
    # LEGENDA
    # ========================================================

    legenda = (
        "✅ <b>PIX criado com sucesso!</b>\n\n"

        f"💰 Valor: "
        f"<b>R$ {valor_formatado}</b>\n"

        "⏳ Status: "
        "<b>Aguardando pagamento</b>"
    )


    if expires_at:

        legenda += (
            "\n🕐 Expiração: "
            f"<code>"
            f"{html.escape(str(expires_at))}"
            f"</code>"
        )


    legenda += (
        "\n\n"
        "📱 Escaneie o QR Code "
        "ou utilize o PIX Copia e Cola abaixo."
    )


    # ========================================================
    # QR CODE
    # ========================================================

    foto_enviada = False


    try:

        # A API já retorna a imagem.

        if qr_base64:

            qr_arquivo = (
                decodificar_qr_base64(
                    qr_base64
                )
            )


            await (
                update.message
                .reply_photo(
                    photo=InputFile(
                        qr_arquivo,

                        filename="pix.png",
                    ),

                    caption=
                        legenda,

                    parse_mode=
                        ParseMode.HTML,
                )
            )


            foto_enviada = True


        # Fallback:
        # gera QR pelo PIX Copia e Cola.

        elif qr_copy_paste:

            qr_arquivo = (
                gerar_qrcode_local(
                    qr_copy_paste
                )
            )


            await (
                update.message
                .reply_photo(
                    photo=InputFile(
                        qr_arquivo,

                        filename="pix.png",
                    ),

                    caption=
                        legenda,

                    parse_mode=
                        ParseMode.HTML,
                )
            )


            foto_enviada = True


    except Exception:

        logger.exception(
            "Erro ao enviar QR Code "
            "no Telegram."
        )


    # Se a imagem falhar,
    # ainda mostra os dados.

    if not foto_enviada:

        await update.message.reply_text(
            text=legenda,

            parse_mode=
                ParseMode.HTML,
        )


    # ========================================================
    # PIX COPIA E COLA
    # ========================================================

    if qr_copy_paste:

        codigo_seguro = html.escape(
            qr_copy_paste
        )


        teclado_copiar = None


        # Telegram limita CopyTextButton.

        if len(qr_copy_paste) <= 256:

            teclado_copiar = (
                InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "📋 Copiar PIX",

                                copy_text=
                                    CopyTextButton(
                                        text=
                                            qr_copy_paste
                                    ),
                            )
                        ]
                    ]
                )
            )


        await update.message.reply_text(
            text=(
                "📋 <b>PIX Copia e Cola</b>\n\n"

                f"<code>{codigo_seguro}</code>\n\n"

                "Após o pagamento, aguarde "
                "a confirmação automática."
            ),

            parse_mode=
                ParseMode.HTML,

            reply_markup=
                teclado_copiar,
        )


# ============================================================
# ERROS
# ============================================================

async def error_handler(
    update: object,

    context:
        ContextTypes.DEFAULT_TYPE
):

    logger.error(
        "Erro Telegram:",

        exc_info=
            context.error,
    )


# ============================================================
# INIT DATABASE
# ============================================================

init_db()