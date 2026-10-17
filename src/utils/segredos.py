import base64
import json
import logging
import os
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# Permite executar o modulo de qualquer pasta: coloca a raiz do projeto no sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.utils.db import conexao
from src.utils.settings import Settings

logger = logging.getLogger("segredos")

# Parâmetros de derivação. 600.000 iterações de PBKDF2-HMAC-SHA256 seguem a
# recomendação do OWASP Password Storage Cheat Sheet (600k para PBKDF2-SHA256),
# tornando a força bruta cara sem inviabilizar o boot. O salt de 16 bytes é
# aleatório por segredo, impedindo rainbow tables e garantindo que o mesmo valor
# cifrado duas vezes gere saídas diferentes.
_ITERACOES = 600_000
_SALT_BYTES = 16


def _master_key():
    """Devolve a master key do .env ou falha com erro claro (sem expor valor).

    Returns:
        str com a master key.

    Raises:
        RuntimeError: quando a master key não está configurada no .env.
    """
    master_key = Settings.MONITOR_MASTER_KEY
    if not master_key:
        raise RuntimeError(
            "MONITOR_MASTER_KEY ausente no .env; rode src/scripts/configurar.py "
            "para gerar a chave mestra."
        )
    return master_key


def _derivar_chave_fernet(master_key, salt):
    """Deriva uma chave Fernet a partir da master key e de um salt.

    Usa PBKDF2-HMAC-SHA256 com 600.000 iterações e produz 32 bytes (o tamanho
    de chave usado pelo AES-128-CBC do Fernet), codificados em base64 urlsafe —
    que é exatamente o formato que a classe ``Fernet`` espera.

    Args:
        master_key: Chave mestra em texto (str).
        salt: Salt binário (bytes) de 16 bytes.

    Returns:
        Fernet já inicializada com a chave derivada.
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=_ITERACOES,
    )
    chave = base64.urlsafe_b64encode(kdf.derive(master_key.encode("utf-8")))
    return Fernet(chave)


def cifrar(master_key, valor):
    """Cifra um valor em texto com Fernet.

    O Fernet usa AES-128-CBC para confidencialidade e HMAC-SHA256 para
    autenticação no esquema encrypt-then-MAC (a mensagem é cifrada e depois
    autenticada), garantindo integridade além do sigilo.

    Args:
        master_key: Chave mestra em texto.
        valor: Texto a cifrar.

    Returns:
        dict ``{"salt": "<base64>", "token": "<base64>"}``.
    """
    salt = os.urandom(_SALT_BYTES)
    token = _derivar_chave_fernet(master_key, salt).encrypt(valor.encode("utf-8"))
    return {
        "salt": base64.b64encode(salt).decode("ascii"),
        "token": token.decode("ascii"),
    }


def decifrar(master_key, payload):
    """Decifra um payload produzido por :func:`cifrar`.

    Args:
        master_key: Chave mestra em texto.
        payload: dict ``{salt, token}`` ou a mesma estrutura como JSON (str).

    Returns:
        str com o valor original.
    """
    if isinstance(payload, str):
        payload = json.loads(payload)
    salt = base64.b64decode(payload["salt"])
    token = payload["token"].encode("ascii")
    return _derivar_chave_fernet(master_key, salt).decrypt(token).decode("utf-8")


def gravar_segredo(chave, valor):
    """Cifra e grava (insert ou update) um segredo na tabela ``segredos``.

    O payload é armazenado como JSON ``{salt, token}`` e a master key é lida de
    ``Settings.MONITOR_MASTER_KEY``. Nada é escrito em log.

    Args:
        chave: Identificador do segredo (ex.: ``api_token``).
        valor: Segredo em texto claro (nunca logado).

    Returns:
        None.
    """
    payload = json.dumps(cifrar(_master_key(), valor))
    agora = datetime.now(timezone.utc).isoformat()
    with conexao() as conn:
        conn.execute(
            "INSERT INTO segredos (chave, payload, atualizado_em) VALUES (?, ?, ?) "
            "ON CONFLICT(chave) DO UPDATE SET payload = excluded.payload, "
            "atualizado_em = excluded.atualizado_em",
            (chave, payload, agora),
        )
    logger.info("Segredo '%s' gravado.", chave)


def buscar_segredo(chave):
    """Lê e decifra um segredo da tabela ``segredos``.

    Args:
        chave: Identificador do segredo.

    Returns:
        Segredo em texto claro, ou None se a chave não existir.
    """
    with conexao() as conn:
        row = conn.execute(
            "SELECT payload FROM segredos WHERE chave = ?", (chave,)
        ).fetchone()
    if not row:
        return None
    return decifrar(_master_key(), row["payload"])


if __name__ == "__main__":
    from src.utils.settings import carregar_env

    carregar_env()
    # Round-trip com uma master key temporária (não grava no banco).
    chave_teste = secrets.token_urlsafe(32)
    original = "segredo-de-teste-áçãõ"
    recuperado = decifrar(chave_teste, cifrar(chave_teste, original))
    print("round-trip cifrar/decifrar:", recuperado == original)
