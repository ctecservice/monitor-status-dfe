import logging
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path

# Permite executar o modulo de qualquer pasta: coloca a raiz do projeto no sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.utils.settings import RAIZ_PROJETO, Settings, carregar_env

logger = logging.getLogger("db")

# DDL do banco: leituras (historico), modelos_dfe (extensivel por dados) e
# segredos (credenciais criptografadas em repouso). Configuracoes operacionais
# vivem em config.json, na raiz do projeto.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS leituras (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  uf            TEXT    NOT NULL,
  documento     TEXT    NOT NULL,
  tp_amb        INTEGER NOT NULL,
  coletado_em   TEXT    NOT NULL,
  dh_recebto    TEXT,
  cstat         TEXT,
  msg           TEXT,
  x_motivo      TEXT,
  t_med         INTEGER,
  response_time INTEGER,
  versao        TEXT,
  ver_aplic     TEXT,
  erro          TEXT
);
CREATE INDEX IF NOT EXISTS idx_leituras_lookup
  ON leituras (uf, documento, tp_amb, coletado_em);

CREATE TABLE IF NOT EXISTS modelos_dfe (
  codigo   TEXT PRIMARY KEY,
  nome     TEXT NOT NULL,
  endpoint TEXT NOT NULL,
  ativo    INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS segredos (
  chave         TEXT PRIMARY KEY,
  payload       TEXT NOT NULL,
  atualizado_em TEXT NOT NULL
);
"""


def caminho_banco():
    """Retorna o caminho absoluto do arquivo SQLite, garantindo a pasta data/.

    Returns:
        str com o caminho do banco. Caminhos relativos partem da raiz do projeto.
    """
    caminho = Path(Settings.BANCO_CAMINHO)
    if not caminho.is_absolute():
        caminho = RAIZ_PROJETO / caminho
    caminho.parent.mkdir(parents=True, exist_ok=True)
    return str(caminho)


@contextmanager
def conexao():
    """Abre uma conexão SQLite; COMMIT ao sair sem erro, ROLLBACK em exceção, sempre fecha.

    Yields:
        sqlite3.Connection com row_factory=Row e foreign_keys ligado.

    Uso:
        with conexao() as conn:
            conn.execute(...)
    """
    conn = sqlite3.connect(caminho_banco())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def criar_schema(conn):
    """Cria as tabelas, o índice de busca e ativa o modo WAL.

    Aplica o seed inicial do modelo NF-e com ``INSERT OR IGNORE`` (idempotente)
    e remove a tabela legada ``configuracoes`` — os valores operacionais agora
    vivem em ``config.json`` na raiz do projeto.

    Args:
        conn: Conexão sqlite3 aberta (ex.: obtida pela função conexao()).

    Returns:
        None.
    """
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA)

    # Migração de bancos legados: configurações saíram do banco para config.json.
    conn.execute("DROP TABLE IF EXISTS configuracoes")

    # Migração defensiva: CREATE TABLE IF NOT EXISTS não altera tabelas que já
    # existem, então bancos criados antes do M3 não ganham a coluna dh_recebto.
    # Verificamos o schema atual e só então aplicamos o ALTER TABLE.
    colunas = {row["name"] for row in conn.execute("PRAGMA table_info(leituras)")}
    if "dh_recebto" not in colunas:
        conn.execute("ALTER TABLE leituras ADD COLUMN dh_recebto TEXT")
        logger.info("Migração aplicada: coluna leituras.dh_recebto criada.")

    # Seed do modelo NF-e (documento inicial do MVP; novos DFes entram como dados).
    conn.execute(
        "INSERT OR IGNORE INTO modelos_dfe (codigo, nome, endpoint, ativo) "
        "VALUES (?, ?, ?, ?)",
        ("nfe", "NF-e", "/v1/nfe/service-status", 1),
    )

    logger.info(
        "Schema garantido (leituras, modelos_dfe, segredos + índice + WAL)."
    )


if __name__ == "__main__":
    carregar_env()
    with conexao() as conn:
        criar_schema(conn)
    print(f"Banco pronto em: {caminho_banco()}")
