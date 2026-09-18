import os
import sqlite3

from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP


# ============================================================
# CAMINHO DO BANCO
#
# Local:
# database/store.db
#
# Futuramente no Render com Persistent Disk:
# SQLITE_PATH=/var/data/store.db
# ============================================================

DEFAULT_DB_PATH = (
    Path(__file__).resolve().parent / "store.db"
)

DB_PATH = Path(
    os.getenv(
        "SQLITE_PATH",
        str(DEFAULT_DB_PATH)
    )
)


# ============================================================
# CONEXÃO
# ============================================================

def conectar():

    DB_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    conn = sqlite3.connect(
        DB_PATH,
        timeout=30
    )

    conn.row_factory = sqlite3.Row

    conn.execute(
        "PRAGMA foreign_keys = ON"
    )

    conn.execute(
        "PRAGMA journal_mode = WAL"
    )

    return conn


# ============================================================
# INICIALIZAR BANCO
# ============================================================

def init_db():

    conn = conectar()

    try:

        # ====================================================
        # USUÁRIOS
        # ====================================================

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,

                username TEXT,
                first_name TEXT,

                balance_cents INTEGER NOT NULL DEFAULT 0,

                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


        # ====================================================
        # PAGAMENTOS PIX
        # ====================================================

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pix_payments (
                dominipay_id TEXT PRIMARY KEY,

                telegram_id INTEGER NOT NULL,

                amount_cents INTEGER NOT NULL,

                status TEXT NOT NULL DEFAULT 'pending',

                credited INTEGER NOT NULL DEFAULT 0,

                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

                paid_at TEXT,

                FOREIGN KEY (telegram_id)
                    REFERENCES users(telegram_id)
            )
            """
        )


        # ====================================================
        # EVENTOS DE WEBHOOK
        #
        # Serve para impedir que o mesmo webhook seja
        # processado duas vezes.
        # ====================================================

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS webhook_events (
                event_id TEXT PRIMARY KEY,

                payment_id TEXT,
                event_type TEXT,

                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


        conn.commit()

    finally:

        conn.close()


# ============================================================
# CONVERTER REAIS -> CENTAVOS
# ============================================================

def decimal_para_centavos(
    valor: Decimal
) -> int:

    valor = valor.quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP
    )

    return int(
        valor * Decimal("100")
    )


# ============================================================
# FORMATAR CENTAVOS -> R$
# ============================================================

def formatar_centavos(
    centavos: int
) -> str:

    reais = (
        Decimal(centavos)
        / Decimal("100")
    )

    texto = f"{reais:.2f}"

    texto = texto.replace(
        ".",
        ","
    )

    return f"R$ {texto}"


# ============================================================
# CRIAR / ATUALIZAR USUÁRIO
# ============================================================

def registrar_usuario(
    telegram_id: int,
    username: str | None = None,
    first_name: str | None = None
):

    conn = conectar()

    try:

        conn.execute(
            """
            INSERT INTO users (
                telegram_id,
                username,
                first_name
            )
            VALUES (?, ?, ?)

            ON CONFLICT(telegram_id)
            DO UPDATE SET

                username = excluded.username,
                first_name = excluded.first_name,

                updated_at = CURRENT_TIMESTAMP
            """,
            (
                telegram_id,
                username,
                first_name,
            )
        )

        conn.commit()

    finally:

        conn.close()


# ============================================================
# SALDO
# ============================================================

def obter_saldo(
    telegram_id: int
) -> int:

    conn = conectar()

    try:

        row = conn.execute(
            """
            SELECT balance_cents
            FROM users
            WHERE telegram_id = ?
            """,
            (telegram_id,)
        ).fetchone()

        if not row:
            return 0

        return int(
            row["balance_cents"]
        )

    finally:

        conn.close()


# ============================================================
# SALVAR PAGAMENTO PIX CRIADO
# ============================================================

def registrar_pagamento_pix(
    dominipay_id: str,
    telegram_id: int,
    amount_cents: int,
    status: str
):

    conn = conectar()

    try:

        conn.execute(
            """
            INSERT INTO pix_payments (
                dominipay_id,
                telegram_id,
                amount_cents,
                status
            )
            VALUES (?, ?, ?, ?)

            ON CONFLICT(dominipay_id)
            DO UPDATE SET

                status = excluded.status
            """,
            (
                dominipay_id,
                telegram_id,
                amount_cents,
                status,
            )
        )

        conn.commit()

    finally:

        conn.close()


# ============================================================
# PROCESSAR WEBHOOK
# ============================================================

def processar_pagamento_webhook(
    payment_id: str,
    status: str,
    event_id: str | None,
    webhook_amount_cents: int | None = None,
):

    conn = conectar()

    try:

        # Trava escrita enquanto processamos o dinheiro.
        conn.execute(
            "BEGIN IMMEDIATE"
        )


        # ====================================================
        # EVENTO JÁ PROCESSADO?
        # ====================================================

        if event_id:

            evento_existente = conn.execute(
                """
                SELECT event_id
                FROM webhook_events
                WHERE event_id = ?
                """,
                (event_id,)
            ).fetchone()

            if evento_existente:

                conn.rollback()

                return {
                    "action": "duplicate_event"
                }


        # ====================================================
        # LOCALIZAR PAGAMENTO
        # ====================================================

        pagamento = conn.execute(
            """
            SELECT
                dominipay_id,
                telegram_id,
                amount_cents,
                status,
                credited

            FROM pix_payments

            WHERE dominipay_id = ?
            """,
            (payment_id,)
        ).fetchone()


        if not pagamento:

            conn.rollback()

            return {
                "action": "payment_not_found"
            }


        telegram_id = int(
            pagamento["telegram_id"]
        )

        amount_cents = int(
            pagamento["amount_cents"]
        )

        credited = int(
            pagamento["credited"]
        )


        # ====================================================
        # CONFERIR VALOR
        # ====================================================

        if (
            webhook_amount_cents is not None
            and webhook_amount_cents != amount_cents
        ):

            conn.rollback()

            return {
                "action": "amount_mismatch",
                "expected": amount_cents,
                "received": webhook_amount_cents,
            }


        # ====================================================
        # ATUALIZAR STATUS
        # ====================================================

        conn.execute(
            """
            UPDATE pix_payments

            SET status = ?

            WHERE dominipay_id = ?
            """,
            (
                status,
                payment_id,
            )
        )


        # ====================================================
        # NÃO FOI APROVADO
        # ====================================================

        if status.lower() != "approved":

            if event_id:

                conn.execute(
                    """
                    INSERT INTO webhook_events (
                        event_id,
                        payment_id,
                        event_type
                    )
                    VALUES (?, ?, ?)
                    """,
                    (
                        event_id,
                        payment_id,
                        status,
                    )
                )

            conn.commit()

            return {
                "action": "status_updated",
                "status": status,
            }


        # ====================================================
        # JÁ FOI CREDITADO?
        #
        # Isso impede:
        #
        # webhook 1 -> +10
        # webhook 2 -> +10
        # webhook 3 -> +10
        #
        # Macaco NÃO imprime dinheiro infinito.
        # ====================================================

        if credited == 1:

            if event_id:

                conn.execute(
                    """
                    INSERT INTO webhook_events (
                        event_id,
                        payment_id,
                        event_type
                    )
                    VALUES (?, ?, ?)
                    """,
                    (
                        event_id,
                        payment_id,
                        status,
                    )
                )

            conn.commit()

            saldo = conn.execute(
                """
                SELECT balance_cents

                FROM users

                WHERE telegram_id = ?
                """,
                (telegram_id,)
            ).fetchone()

            return {
                "action": "already_credited",
                "telegram_id": telegram_id,
                "balance_cents": (
                    int(saldo["balance_cents"])
                    if saldo
                    else 0
                ),
            }


        # ====================================================
        # GARANTIR USUÁRIO
        # ====================================================

        conn.execute(
            """
            INSERT OR IGNORE INTO users (
                telegram_id
            )
            VALUES (?)
            """,
            (telegram_id,)
        )


        # ====================================================
        # ADICIONAR SALDO
        # ====================================================

        conn.execute(
            """
            UPDATE users

            SET
                balance_cents = balance_cents + ?,
                updated_at = CURRENT_TIMESTAMP

            WHERE telegram_id = ?
            """,
            (
                amount_cents,
                telegram_id,
            )
        )


        # ====================================================
        # MARCAR PAGAMENTO COMO CREDITADO
        # ====================================================

        conn.execute(
            """
            UPDATE pix_payments

            SET
                credited = 1,
                status = 'approved',
                paid_at = CURRENT_TIMESTAMP

            WHERE dominipay_id = ?
            """,
            (payment_id,)
        )


        # ====================================================
        # SALVAR EVENTO
        # ====================================================

        if event_id:

            conn.execute(
                """
                INSERT INTO webhook_events (
                    event_id,
                    payment_id,
                    event_type
                )
                VALUES (?, ?, ?)
                """,
                (
                    event_id,
                    payment_id,
                    "payment.status_changed",
                )
            )


        # ====================================================
        # PEGAR NOVO SALDO
        # ====================================================

        saldo = conn.execute(
            """
            SELECT balance_cents

            FROM users

            WHERE telegram_id = ?
            """,
            (telegram_id,)
        ).fetchone()


        novo_saldo = int(
            saldo["balance_cents"]
        )


        conn.commit()


        return {
            "action": "credited",

            "telegram_id":
                telegram_id,

            "amount_cents":
                amount_cents,

            "balance_cents":
                novo_saldo,
        }


    except Exception:

        conn.rollback()

        raise


    finally:

        conn.close()