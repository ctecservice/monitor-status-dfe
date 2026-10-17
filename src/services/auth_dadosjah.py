import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

# Permite executar o modulo de qualquer pasta: coloca a raiz do projeto no sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.utils.settings import Settings

logger = logging.getLogger("auth_dadosjah")

# Margem para renovar o token antes de ele expirar de fato, evitando usá-lo no
# limite (uma requisição lenta poderia pegá-lo já vencido).
_MARGEM_SEGUNDOS = 600  # 10 minutos

# Cache em memória do token. O JWT vale ~7 dias; renovar a cada consulta seria
# desperdício e poluição de log, então guardamos o token e a expiração e só
# renovamos quando faltar menos que a margem (ou quando forçar=True).
_TOKEN_CACHE: dict = {"token": None, "expira_em": None}


def _parse_expiracao(expires_at):
    """Converte o campo ``expiresAt`` (ISO com offset) em datetime aware UTC.

    Args:
        expires_at: String ISO 8601 (ex.: ``2026-10-23T15:19:14-03:00``) ou None.

    Returns:
        datetime em UTC, ou None se não for possível interpretar.
    """
    if not expires_at:
        return None
    try:
        dt = datetime.fromisoformat(expires_at)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _token_ainda_valido():
    """Indica se o token em cache ainda é utilizável.

    Returns:
        True se houver token em cache e faltar mais que a margem para expirar.
    """
    token = _TOKEN_CACHE["token"]
    expira_em = _TOKEN_CACHE["expira_em"]
    if not token or expira_em is None:
        return False
    return (expira_em - datetime.now(timezone.utc)).total_seconds() > _MARGEM_SEGUNDOS


def obter_token(forcar=False):
    """Obtém (ou reutiliza do cache) um accessToken da API DadosJah.

    Faz ``POST {API_BASE_URL}/v1/auth/user/login`` com as credenciais de
    ``Settings.API_LOGIN_USUARIO`` / ``Settings.API_LOGIN_SENHA``. Nunca loga
    credenciais nem o token.

    Args:
        forcar: Quando True, ignora o cache e renova o token.

    Returns:
        str com o accessToken.

    Raises:
        RuntimeError: quando as credenciais não estão configuradas ou o login
            falha (mensagem sem dados sensíveis).
    """
    if not forcar and _token_ainda_valido():
        return _TOKEN_CACHE["token"]

    usuario = Settings.API_LOGIN_USUARIO
    senha = Settings.API_LOGIN_SENHA
    if not usuario or not senha:
        raise RuntimeError(
            "Credenciais da API ausentes (API_LOGIN_USUARIO/API_LOGIN_SENHA no .env)."
        )

    url = f"{Settings.API_BASE_URL}/v1/auth/user/login"
    try:
        with httpx.Client(timeout=Settings.API_TIMEOUT_S) as client:
            resposta = client.post(
                url, json={"email": usuario, "password": senha}
            )
    except httpx.TimeoutException:
        raise RuntimeError("timeout ao autenticar na API DadosJah")
    except httpx.HTTPError as exc:
        raise RuntimeError(f"erro de rede ao autenticar: {exc}")

    if resposta.status_code not in (200, 201):
        logger.warning("Login na API falhou: HTTP %s", resposta.status_code)
        raise RuntimeError(f"login rejeitado (HTTP {resposta.status_code})")

    corpo = resposta.json()
    dados = corpo.get("data") or {}
    token = dados.get("accessToken")
    if not token:
        raise RuntimeError("resposta de login sem accessToken")

    expira_em = _parse_expiracao(dados.get("expiresAt"))
    if expira_em is None:
        # Sem expiração legível, assume uma janela conservadora.
        expira_em = datetime.now(timezone.utc) + timedelta(days=6)

    _TOKEN_CACHE["token"] = token
    _TOKEN_CACHE["expira_em"] = expira_em
    logger.info("Token da API renovado (expira em %s).", expira_em.isoformat())
    return token


if __name__ == "__main__":
    from src.utils.logger import configurar_logger
    from src.utils.settings import carregar_env

    carregar_env()
    configurar_logger("auth_dadosjah")
    try:
        token = obter_token()
        print("Token obtido:", bool(token))
        print("Expira em:", _TOKEN_CACHE["expira_em"].isoformat())
    except Exception as exc:  # nunca imprime credenciais/token
        print("Falha ao obter token:", exc)
