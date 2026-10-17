import logging
import sys
import time
import uuid
from pathlib import Path

import httpx

# Permite executar o modulo de qualquer pasta: coloca a raiz do projeto no sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.utils.settings import Settings

logger = logging.getLogger("turnstile")

# Endpoint de validação server-side do Cloudflare Turnstile.
_URL_SITEVERIFY = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
_TIMEOUT_S = 10
# Backoff entre a primeira tentativa e o retry de falha interna da Cloudflare.
_BACKOFF_S = 0.5


def turnstile_habilitado():
    """Indica se a proteção anti-bot está configurada.

    Returns:
        True se site key e secret key estiverem definidas; False caso
        contrário (sem chaves = proteção desligada, útil no desenvolvimento).
    """
    return bool(Settings.TURNSTILE_SITE_KEY and Settings.TURNSTILE_SECRET_KEY)


def _enviar_validacao(token, ip, idempotency_key):
    """Executa o POST de validação no siteverify (uma tentativa).

    Args:
        token: Token gerado pelo widget no cliente.
        ip: IP do cliente (opcional; enviado como ``remoteip``).
        idempotency_key: UUID que identifica a validação, reenviado idêntico em
            retry do MESMO token para evitar o erro ``timeout-or-duplicate``.

    Returns:
        dict com a resposta JSON do siteverify (``success`` e ``error-codes``).
    """
    payload = {
        "secret": Settings.TURNSTILE_SECRET_KEY,
        "response": token,
        "idempotency_key": idempotency_key,
    }
    if ip:
        payload["remoteip"] = ip
    with httpx.Client(timeout=_TIMEOUT_S) as client:
        resposta = client.post(_URL_SITEVERIFY, json=payload)
        resposta.raise_for_status()
        return resposta.json()


def verificar_token(token, ip=None):
    """Valida um token do Cloudflare Turnstile no servidor.

    Quando a proteção está desligada (sem chaves), libera sempre. Com a
    proteção ligada, token ausente/vazio reprova. Em retry, apenas o erro
    ``internal-error`` dispara uma segunda tentativa (backoff 0,5 s),
    reenviando o mesmo ``idempotency_key``. Falhas de rede/HTTP são logadas
    como warning (sem segredos) e reprovam.

    Args:
        token: Token recebido do cliente.
        ip: IP do cliente (opcional; enviado como ``remoteip``).

    Returns:
        True quando a validação é bem-sucedida (ou quando a proteção está
        desligada); False caso contrário.
    """
    if not turnstile_habilitado():
        return True
    if not token:
        return False

    # O mesmo idempotency_key acompanha todas as tentativas deste token.
    idempotency_key = str(uuid.uuid4())
    for tentativa in range(2):
        try:
            corpo = _enviar_validacao(token, ip, idempotency_key)
        except httpx.HTTPError as exc:
            logger.warning("Falha de rede ao validar o Turnstile: %s", exc)
            return False

        if corpo.get("success") is True:
            return True

        erros = corpo.get("error-codes") or []
        logger.info("Turnstile rejeitou o token: %s", erros)
        if "internal-error" in erros and tentativa == 0:
            time.sleep(_BACKOFF_S)
            continue
        return False
    return False


if __name__ == "__main__":
    from src.utils.settings import carregar_env

    carregar_env()
    print("habilitado:", turnstile_habilitado())
