import os
import logging

from dotenv import load_dotenv

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from telegram.constants import ParseMode

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)


# ============================================================
# VARIÁVEIS DE AMBIENTE
# ============================================================

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


# ============================================================
# LOGS
# ============================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# ============================================================
# CALLBACKS
# ============================================================

CALLBACK_MENU = "menu"
CALLBACK_PERFIL = "perfil"
CALLBACK_SALDO = "adicionar_saldo"

CALLBACK_PIX = "pix_automatico"
CALLBACK_RECARGA_MANUAL = "recarga_manual"

CALLBACK_VOLTAR = "voltar_inicio"
CALLBACK_VOLTAR_SALDO = "voltar_saldo"


# ============================================================
# TECLADO PRINCIPAL
# ============================================================

TECLADO_PRINCIPAL = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton(
                "🛒 Menu",
                callback_data=CALLBACK_MENU
            ),
            InlineKeyboardButton(
                "💎 Seu Perfil",
                callback_data=CALLBACK_PERFIL
            ),
        ],
        [
            InlineKeyboardButton(
                "💰 Adiciona Saldo",
                callback_data=CALLBACK_SALDO
            )
        ],
    ]
)


# ============================================================
# TECLADO ADICIONAR SALDO
# ============================================================

TECLADO_ADICIONAR_SALDO = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton(
                "💠 Pix automático",
                callback_data=CALLBACK_PIX
            ),
            InlineKeyboardButton(
                "💵 Recarga manual",
                callback_data=CALLBACK_RECARGA_MANUAL
            ),
        ],
        [
            InlineKeyboardButton(
                "« volta",
                callback_data=CALLBACK_VOLTAR
            )
        ],
    ]
)


# ============================================================
# TECLADO VOLTAR AO MENU PRINCIPAL
# ============================================================

TECLADO_VOLTAR = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton(
                "« volta",
                callback_data=CALLBACK_VOLTAR
            )
        ]
    ]
)


# ============================================================
# TECLADO VOLTAR PARA ADICIONAR SALDO
# ============================================================

TECLADO_VOLTAR_SALDO = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton(
                "« volta",
                callback_data=CALLBACK_VOLTAR_SALDO
            )
        ]
    ]
)


# ============================================================
# TEXTO PRINCIPAL
# ============================================================

def gerar_texto_inicio(user_name: str):

    return (
        f"👋 Fala, <b>{user_name}</b>! Seja muito bem-vindo(a).\n\n"

        "🎩 <b>CHAPELEIRO7STORE — A EXCELÊNCIA EM DIGITAL</b> 🚀\n\n"

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
        "🔥 <b>Bem-vindo ao topo. Seja Chapeleiro7Store.</b>"
    )


# ============================================================
# TEXTO ADICIONAR SALDO
# ============================================================

def gerar_texto_adicionar_saldo():

    return (
        "💰 <b><u>Adicione saldo na STORE</u></b>\n\n"

        "<i>"
        "Você pode adicionar saldo na store via pix de forma "
        "automática ou por recarga manual comprando diretamente "
        "com um dos admins."
        "</i>"
    )


# ============================================================
# /START
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user

    user_name = (
        user.first_name
        if user and user.first_name
        else "CHAPELEIRO"
    )

    await update.message.reply_text(
        text=gerar_texto_inicio(user_name),
        parse_mode=ParseMode.HTML,
        reply_markup=TECLADO_PRINCIPAL,
    )


# ============================================================
# CALLBACK DOS BOTÕES
# ============================================================

async def handle_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    # Remove o "loading" do botão
    await query.answer()

    data = query.data

    user = query.from_user

    user_name = (
        user.first_name
        if user and user.first_name
        else "CHAPELEIRO"
    )

    logger.info(
        "Usuário %s clicou em %s",
        user.id,
        data,
    )


    # ========================================================
    # ADICIONAR SALDO
    # ========================================================

    if data == CALLBACK_SALDO:

        await query.edit_message_text(
            text=gerar_texto_adicionar_saldo(),
            parse_mode=ParseMode.HTML,
            reply_markup=TECLADO_ADICIONAR_SALDO,
        )

        return


    # ========================================================
    # VOLTAR PARA O INÍCIO
    # ========================================================

    if data == CALLBACK_VOLTAR:

        await query.edit_message_text(
            text=gerar_texto_inicio(user_name),
            parse_mode=ParseMode.HTML,
            reply_markup=TECLADO_PRINCIPAL,
        )

        return


    # ========================================================
    # MENU
    # ========================================================

    if data == CALLBACK_MENU:

        texto = (
            "🛒 <b>Catálogo de Produtos</b>\n\n"

            "Selecione uma categoria ou produto disponível.\n\n"

            "🚧 O catálogo será configurado em breve."
        )

        await query.edit_message_text(
            text=texto,
            parse_mode=ParseMode.HTML,
            reply_markup=TECLADO_VOLTAR,
        )

        return


    # ========================================================
    # PERFIL
    # ========================================================

    if data == CALLBACK_PERFIL:

        # Depois vamos puxar isso diretamente do SQLite
        saldo = 0.00

        texto = (
            "💎 <b>Seu Perfil</b>\n\n"

            f"👤 Nome: <b>{user.first_name}</b>\n"
            f"🆔 ID: <code>{user.id}</code>\n"
            f"💰 Saldo: <b>R$ {saldo:.2f}</b>\n\n"

            "📦 Compras realizadas: <b>0</b>"
        )

        await query.edit_message_text(
            text=texto,
            parse_mode=ParseMode.HTML,
            reply_markup=TECLADO_VOLTAR,
        )

        return


    # ========================================================
    # PIX AUTOMÁTICO
    # ========================================================

    if data == CALLBACK_PIX:

        texto = (
            "💠 <b>PIX Automático</b>\n\n"

            "💰 Adicione saldo automaticamente através do PIX.\n\n"

            "Digite o valor desejado utilizando:\n\n"

            "<code>/pix 50</code>\n\n"

            "Exemplo acima:\n"
            "Adicionar <b>R$ 50,00</b> de saldo.\n\n"

            "⚡ Após a confirmação do pagamento, "
            "o saldo será adicionado automaticamente."
        )

        await query.edit_message_text(
            text=texto,
            parse_mode=ParseMode.HTML,
            reply_markup=TECLADO_VOLTAR_SALDO,
        )

        return


    # ========================================================
    # RECARGA MANUAL
    # ========================================================

    if data == CALLBACK_RECARGA_MANUAL:

        texto = (
            "💵 <b>Recarga Manual</b>\n\n"

            "Para adicionar saldo manualmente, entre em contato "
            "com um dos administradores.\n\n"

            "📞 <b>Suporte oficial:</b>\n"
            "@CHAPELEIROSTORESUPORTE01"
        )

        await query.edit_message_text(
            text=texto,
            parse_mode=ParseMode.HTML,
            reply_markup=TECLADO_VOLTAR_SALDO,
        )

        return


    # ========================================================
    # VOLTAR PARA ADICIONAR SALDO
    # ========================================================

    if data == CALLBACK_VOLTAR_SALDO:

        await query.edit_message_text(
            text=gerar_texto_adicionar_saldo(),
            parse_mode=ParseMode.HTML,
            reply_markup=TECLADO_ADICIONAR_SALDO,
        )

        return


# ============================================================
# /PIX
# ============================================================

async def pix(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    # ========================================================
    # NÃO INFORMOU VALOR
    # ========================================================

    if not context.args:

        await update.message.reply_text(
            text=(
                "💠 <b>Gerar PIX</b>\n\n"

                "Informe o valor que deseja adicionar.\n\n"

                "Exemplo:\n"
                "<code>/pix 50</code>"
            ),
            parse_mode=ParseMode.HTML,
        )

        return


    # ========================================================
    # NORMALIZAR VALOR
    # ========================================================

    valor_texto = context.args[0]

    valor_texto = valor_texto.replace(",", ".")


    # ========================================================
    # VALIDAR NÚMERO
    # ========================================================

    try:

        valor = float(valor_texto)

    except ValueError:

        await update.message.reply_text(
            text=(
                "❌ <b>Valor inválido.</b>\n\n"

                "Use apenas números.\n\n"

                "Exemplo:\n"
                "<code>/pix 50</code>"
            ),
            parse_mode=ParseMode.HTML,
        )

        return


    # ========================================================
    # VALIDAR VALOR
    # ========================================================

    if valor <= 0:

        await update.message.reply_text(
            text=(
                "❌ <b>Valor inválido.</b>\n\n"

                "O valor precisa ser maior que R$ 0,00."
            ),
            parse_mode=ParseMode.HTML,
        )

        return


    # ========================================================
    # FUTURA INTEGRAÇÃO COM O GATEWAY
    # ========================================================
    #
    # Aqui depois teremos algo como:
    #
    # pagamento = gateway.criar_pix(
    #     telegram_id=update.effective_user.id,
    #     valor=valor
    # )
    #
    # pix_copia_cola = pagamento["pix"]
    # qr_code = pagamento["qr_code"]
    # transaction_id = pagamento["id"]
    #
    # ========================================================


    await update.message.reply_text(
        text=(
            "💠 <b>Solicitação PIX</b>\n\n"

            f"💰 Valor: <b>R$ {valor:.2f}</b>\n\n"

            "🚧 Gateway de pagamentos ainda não conectado."
        ),
        parse_mode=ParseMode.HTML,
    )


# ============================================================
# ERROS
# ============================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE
):

    logger.error(
        "Erro durante execução:",
        exc_info=context.error,
    )


# ============================================================
# MAIN
# ============================================================

def main():

    # ========================================================
    # VALIDAR TOKEN
    # ========================================================

    if not TELEGRAM_BOT_TOKEN:

        raise RuntimeError(
            "\n"
            "ERRO: TELEGRAM_BOT_TOKEN não encontrado.\n\n"
            "Verifique seu arquivo .env.\n\n"
            "Exemplo:\n"
            "TELEGRAM_BOT_TOKEN=seu_token\n"
        )


    # ========================================================
    # CRIAR BOT
    # ========================================================

    app = (
        ApplicationBuilder()
        .token(TELEGRAM_BOT_TOKEN)
        .build()
    )


    # ========================================================
    # HANDLERS
    # ========================================================

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    app.add_handler(
        CommandHandler(
            "pix",
            pix
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            handle_callback
        )
    )

    app.add_error_handler(
        error_handler
    )


    # ========================================================
    # START
    # ========================================================

    print(
        "\n"
        "========================================\n"
        "🎩 CHAPELEIRO7STORE\n"
        "✅ Bot iniciado\n"
        "✅ Menu Inline carregado\n"
        "✅ Sistema de navegação carregado\n"
        "✅ Aguardando mensagens...\n"
        "========================================\n"
    )


    app.run_polling(
        drop_pending_updates=True
    )


# ============================================================
# EXECUÇÃO
# ============================================================

if __name__ == "__main__":
    main()