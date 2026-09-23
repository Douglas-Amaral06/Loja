import os
import sqlite3

from pathlib import Path

from decimal import (
    Decimal,
    ROUND_HALF_UP,
)


# ============================================================
# DATABASE
# ============================================================

DEFAULT_DB_PATH = (
    Path(__file__).resolve().parent
    / "store.db"
)

DB_PATH = Path(
    os.getenv(
        "SQLITE_PATH",
        str(DEFAULT_DB_PATH)
    )
)


# ============================================================
# SCHEMA PIX
# ============================================================

PIX_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS pix_payments (

    gateway_payment_id TEXT PRIMARY KEY,

    external_id TEXT UNIQUE,

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


    conn.row_factory = (
        sqlite3.Row
    )


    conn.execute(
        "PRAGMA foreign_keys = ON"
    )


    conn.execute(
        "PRAGMA journal_mode = WAL"
    )


    return conn


# ============================================================
# MIGRAÇÃO AUTOMÁTICA DO PIX ANTIGO
# ============================================================

def _migrar_tabela_pix_se_necessario(
    conn: sqlite3.Connection
):

    tabela = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table'
        AND name='pix_payments'
        """
    ).fetchone()


    if not tabela:

        conn.execute(
            PIX_TABLE_SQL
        )

        return


    colunas = {
        row["name"]

        for row in conn.execute(
            "PRAGMA table_info(pix_payments)"
        ).fetchall()
    }


    # Já está no schema novo.

    if (
        "gateway_payment_id"
        in colunas

        and "external_id"
        in colunas
    ):

        return


    # Se existir uma tabela antiga,
    # NÃO apagamos.
    #
    # Renomeamos como backup.

    sufixo = 1

    nome_backup = (
        "pix_payments_legacy"
    )


    while conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type='table'
        AND name=?
        """,

        (nome_backup,),
    ).fetchone():

        sufixo += 1

        nome_backup = (
            f"pix_payments_legacy_"
            f"{sufixo}"
        )


    conn.execute(
        f"""
        ALTER TABLE pix_payments
        RENAME TO {nome_backup}
        """
    )


    conn.execute(
        PIX_TABLE_SQL
    )


# ============================================================
# INIT
# ============================================================

def init_db():

    conn = conectar()


    try:

        # ====================================================
        # USERS
        # ====================================================

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (

                telegram_id INTEGER PRIMARY KEY,

                username TEXT,

                first_name TEXT,

                balance_cents INTEGER
                    NOT NULL
                    DEFAULT 0,

                created_at TEXT
                    NOT NULL
                    DEFAULT CURRENT_TIMESTAMP,

                updated_at TEXT
                    NOT NULL
                    DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


        # ====================================================
        # PIX
        # ====================================================

        _migrar_tabela_pix_se_necessario(
            conn
        )


        # ====================================================
        # EVENTOS
        # ====================================================

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS webhook_events (

                event_id TEXT PRIMARY KEY,

                payment_id TEXT,

                event_type TEXT,

                created_at TEXT
                    NOT NULL
                    DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


        # ====================================================
        # ÍNDICES
        # ====================================================

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_pix_external_id
            ON pix_payments(external_id)
            """
        )


        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_pix_telegram_id
            ON pix_payments(telegram_id)
            """
        )


        conn.commit()


    finally:

        conn.close()


# ============================================================
# REAL -> CENTAVOS
# ============================================================

def decimal_para_centavos(
    valor: Decimal
) -> int:

    valor = valor.quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP
    )


    return int(
        valor
        * Decimal("100")
    )


# ============================================================
# CENTAVOS -> REAL
# ============================================================

def formatar_centavos(
    centavos: int
) -> str:

    reais = (
        Decimal(centavos)
        / Decimal("100")
    )


    return (
        f"R$ {reais:.2f}"
        .replace(".", ",")
    )


# ============================================================
# USUÁRIO
# ============================================================

def registrar_usuario(
    telegram_id: int,

    username: str | None = None,

    first_name: str | None = None,
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

                username =
                    excluded.username,

                first_name =
                    excluded.first_name,

                updated_at =
                    CURRENT_TIMESTAMP
            """,

            (
                telegram_id,

                username,

                first_name,
            ),
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

            (telegram_id,),
        ).fetchone()


        if not row:
            return 0


        return int(
            row["balance_cents"]
        )


    finally:

        conn.close()


# ============================================================
# REGISTRAR PIX
# ============================================================

def registrar_pagamento_pix(

    gateway_payment_id: str,

    external_id: str,

    telegram_id: int,

    amount_cents: int,

    status: str,
):

    conn = conectar()


    try:

        conn.execute(
            """
            INSERT INTO pix_payments (

                gateway_payment_id,

                external_id,

                telegram_id,

                amount_cents,

                status
            )

            VALUES (?, ?, ?, ?, ?)

            ON CONFLICT(gateway_payment_id)

            DO UPDATE SET

                external_id =
                    excluded.external_id,

                status =
                    excluded.status
            """,

            (
                gateway_payment_id,

                external_id,

                telegram_id,

                amount_cents,

                status,
            ),
        )


        conn.commit()


    finally:

        conn.close()


# ============================================================
# BUSCAR PAGAMENTO
# ============================================================

def _buscar_pagamento(

    conn: sqlite3.Connection,

    payment_id: str | None,

    external_id: str | None,
):

    if payment_id:

        row = conn.execute(
            """
            SELECT *

            FROM pix_payments

            WHERE gateway_payment_id = ?
            """,

            (payment_id,),
        ).fetchone()


        if row:
            return row


    if external_id:

        return conn.execute(
            """
            SELECT *

            FROM pix_payments

            WHERE external_id = ?
            """,

            (external_id,),
        ).fetchone()


    return None


# ============================================================
# PROCESSAR WEBHOOK
# ============================================================

def processar_pagamento_webhook(

    payment_id: str | None,

    status: str,

    webhook_amount_cents:
        int | None = None,

    external_id:
        str | None = None,

    event_id:
        str | None = None,
):

    conn = conectar()


    try:

        # Trava escrita do SQLite.
        #
        # Evita duas confirmações
        # creditarem o saldo juntas.

        conn.execute(
            "BEGIN IMMEDIATE"
        )


        # ====================================================
        # EVENTO DUPLICADO
        # ====================================================

        if event_id:

            evento_existente = (
                conn.execute(
                    """
                    SELECT event_id

                    FROM webhook_events

                    WHERE event_id = ?
                    """,

                    (event_id,),
                ).fetchone()
            )


            if evento_existente:

                conn.rollback()

                return {
                    "action":
                        "duplicate_event"
                }


        # ====================================================
        # PAGAMENTO
        # ====================================================

        pagamento = (
            _buscar_pagamento(
                conn=conn,

                payment_id=
                    payment_id,

                external_id=
                    external_id,
            )
        )


        if not pagamento:

            conn.rollback()

            return {
                "action":
                    "payment_not_found"
            }


        gateway_payment_id = str(
            pagamento[
                "gateway_payment_id"
            ]
        )


        telegram_id = int(
            pagamento[
                "telegram_id"
            ]
        )


        amount_cents = int(
            pagamento[
                "amount_cents"
            ]
        )


        credited = int(
            pagamento[
                "credited"
            ]
        )


        # ====================================================
        # CONFERÊNCIA DO VALOR
        # ====================================================

        if (
            webhook_amount_cents
            is not None

            and webhook_amount_cents
            != amount_cents
        ):

            conn.rollback()

            return {
                "action":
                    "amount_mismatch",

                "expected":
                    amount_cents,

                "received":
                    webhook_amount_cents,
            }


        status_normalizado = (
            str(status).lower()
        )


        # ====================================================
        # ATUALIZAR STATUS
        # ====================================================

        conn.execute(
            """
            UPDATE pix_payments

            SET status = ?

            WHERE gateway_payment_id = ?
            """,

            (
                status_normalizado,

                gateway_payment_id,
            ),
        )


        # ====================================================
        # NÃO APROVADO
        # ====================================================

        if (
            status_normalizado
            != "approved"
        ):

            if event_id:

                conn.execute(
                    """
                    INSERT OR IGNORE
                    INTO webhook_events (

                        event_id,

                        payment_id,

                        event_type
                    )

                    VALUES (?, ?, ?)
                    """,

                    (
                        event_id,

                        gateway_payment_id,

                        status_normalizado,
                    ),
                )


            conn.commit()


            return {
                "action":
                    "status_updated",

                "status":
                    status_normalizado,
            }


        # ====================================================
        # JÁ CREDITADO
        # ====================================================

        if credited == 1:

            saldo = conn.execute(
                """
                SELECT balance_cents

                FROM users

                WHERE telegram_id = ?
                """,

                (telegram_id,),
            ).fetchone()


            if event_id:

                conn.execute(
                    """
                    INSERT OR IGNORE
                    INTO webhook_events (

                        event_id,

                        payment_id,

                        event_type
                    )

                    VALUES (?, ?, ?)
                    """,

                    (
                        event_id,

                        gateway_payment_id,

                        "payment.confirmed",
                    ),
                )


            conn.commit()


            return {
                "action":
                    "already_credited",

                "telegram_id":
                    telegram_id,

                "balance_cents":
                    int(
                        saldo[
                            "balance_cents"
                        ]
                    )
                    if saldo
                    else 0,
            }


        # ====================================================
        # GARANTIR USUÁRIO
        # ====================================================

        conn.execute(
            """
            INSERT OR IGNORE
            INTO users (
                telegram_id
            )

            VALUES (?)
            """,

            (telegram_id,),
        )


        # ====================================================
        # ADICIONAR SALDO
        # ====================================================

        conn.execute(
            """
            UPDATE users

            SET
                balance_cents =
                    balance_cents + ?,

                updated_at =
                    CURRENT_TIMESTAMP

            WHERE telegram_id = ?
            """,

            (
                amount_cents,

                telegram_id,
            ),
        )


        # ====================================================
        # MARCAR PIX COMO CREDITADO
        # ====================================================

        conn.execute(
            """
            UPDATE pix_payments

            SET

                credited = 1,

                status = 'approved',

                paid_at =
                    CURRENT_TIMESTAMP

            WHERE gateway_payment_id = ?
            """,

            (
                gateway_payment_id,
            ),
        )


        # ====================================================
        # EVENTO
        # ====================================================

        if event_id:

            conn.execute(
                """
                INSERT OR IGNORE
                INTO webhook_events (

                    event_id,

                    payment_id,

                    event_type
                )

                VALUES (?, ?, ?)
                """,

                (
                    event_id,

                    gateway_payment_id,

                    "payment.confirmed",
                ),
            )


        # ====================================================
        # NOVO SALDO
        # ====================================================

        saldo = conn.execute(
            """
            SELECT balance_cents

            FROM users

            WHERE telegram_id = ?
            """,

            (telegram_id,),
        ).fetchone()


        novo_saldo = int(
            saldo["balance_cents"]
        )


        conn.commit()


        return {
            "action":
                "credited",

            "telegram_id":
                telegram_id,

            "amount_cents":
                amount_cents,

            "balance_cents":
                novo_saldo,

            "payment_id":
                gateway_payment_id,
        }


    except Exception:

        conn.rollback()

        raise


    finally:

        conn.close()