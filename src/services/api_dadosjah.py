import logging
import sys
import time
from pathlib import Path

import httpx

# Permite executar o modulo de qualquer pasta: coloca a raiz do projeto no sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.services import auth_dadosjah
from src.utils.settings import Settings

logger = logging.getLogger("api_dadosjah")

# Tamanho máximo do trecho de mensagem da API incluído no campo ``erro``.
_TAMANHO_MENSAGEM = 150


def _erro(mensagem):
    """Empacota um resultado de falha no formato padrão de retorno.

    Args:
        mensagem: Descrição curta do erro.

    Returns:
        dict ``{"ok": False, "dados": None, "erro": mensagem}``.
    """
    return {"ok": False, "dados": None, "erro": mensagem}


def _mensagem_erro(status_code, corpo):
    """Monta a mensagem de erro de uma resposta não-200.

    A API devolve ``{"message": ["..."]}`` em muitos casos (ex.: falha de
    certificado no lado da API); esse texto ajuda o diagnóstico.

    Args:
        status_code: Código HTTP da resposta.
        corpo: Corpo JSON já decodificado (dict) ou None.

    Returns:
        str no formato ``HTTP <código>: <trecho da mensagem>``.
    """
    mensagem = f"HTTP {status_code}"
    if isinstance(corpo, dict):
        detalhe = corpo.get("message")
        if isinstance(detalhe, list):
            detalhe = "; ".join(str(item) for item in detalhe)
        if detalhe:
            mensagem += f": {str(detalhe)[:_TAMANHO_MENSAGEM]}"
    return mensagem


def _executar_get(url, params, token, timeout_s):
    """Executa o GET autenticado, isolando falhas de rede/timeout.

    Args:
        url: URL completa do endpoint.
        params: Query params (``{"UF": ..., "tpAmb": ...}``).
        token: accessToken a enviar no header Authorization.
        timeout_s: Timeout em segundos.

    Returns:
        dict ``{"status_code", "corpo", "response_time", "erro"}``. Em falha
        de rede/timeout, ``status_code`` é None e ``erro`` traz a descrição.
    """
    # perf_counter é monotônico: mede o tempo de parede sem sofrer ajustes do
    # relógio do sistema.
    inicio = time.perf_counter()
    try:
        with httpx.Client(timeout=timeout_s) as client:
            resposta = client.get(
                url,
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )
        response_time = int((time.perf_counter() - inicio) * 1000)
        try:
            corpo = resposta.json()
        except ValueError:
            corpo = None
        return {
            "status_code": resposta.status_code,
            "corpo": corpo,
            "response_time": response_time,
            "erro": None,
        }
    except httpx.TimeoutException:
        return {
            "status_code": None,
            "corpo": None,
            "response_time": None,
            "erro": f"timeout após {timeout_s}s",
        }
    except httpx.HTTPError as exc:
        return {
            "status_code": None,
            "corpo": None,
            "response_time": None,
            "erro": f"erro de rede: {exc}",
        }


def _normalizar_resposta(dados):
    """Achata a resposta da API no formato consumido pelo coletor.

    A API DadosJah devolve os campos de status aninhados em ``data.status``
    (ex.: ``{"statusCode": 200, "data": {"status": {"cStat": "107", ...}}}``),
    mas o coletor lê as chaves na raiz do dicionário. Esta função extrai
    ``data.status`` para o nível raiz. Se a resposta já vier no formato antigo
    (chaves de status na raiz, ex.: ``cStat`` presente) ou em qualquer formato
    inesperado, o dicionário é devolvido como está — nunca levanta exceção.
    O ``response_time`` medido pelo cliente é acrescentado depois, em
    :func:`consultar_status`.

    Args:
        dados: Corpo JSON já decodificado da API (esperado: dict).

    Returns:
        dict achatado com os campos de ``data.status``, ou o próprio ``dados``
        quando já está na raiz/formato antigo. Retorna ``{}`` se ``dados`` não
        for um dicionário.
    """
    if not isinstance(dados, dict):
        return {}
    envelope = dados.get("data")
    if isinstance(envelope, dict):
        status = envelope.get("status")
        if isinstance(status, dict):
            return dict(status)
    return dados


def consultar_status(uf, endpoint, tp_amb, timeout_s):
    """Consulta o status de um serviço SEFAZ na API DadosJah (autenticado).

    Autentica via :func:`src.services.auth_dadosjah.obter_token`, envia o
    header ``Authorization: Bearer <token>`` e mede o tempo de resposta em
    milissegundos (devolvido em ``dados["response_time"]``). A resposta é
    achatada por :func:`_normalizar_resposta` (campos de ``data.status`` vão
    para a raiz), preservando também o ``responseTime`` informado pela API; o
    ``response_time`` do cliente tem precedência. Em HTTP 401/403, renova o
    token e tenta **uma** vez mais. Respostas não-200 incluem o trecho de
    ``message`` da API no campo ``erro``. Nunca loga o token.

    Args:
        uf: Sigla da UF (ex.: ``MG``).
        endpoint: Caminho relativo do modelo (ex.: ``/v1/nfe/service-status``).
        tp_amb: Ambiente (1 = produção, 2 = homologação).
        timeout_s: Timeout da requisição, em segundos.

    Returns:
        dict ``{"ok": bool, "dados": dict | None, "erro": str | None}``.
    """
    url = f"{Settings.API_BASE_URL}{endpoint}"
    params = {"UF": uf, "tpAmb": tp_amb}

    try:
        token = auth_dadosjah.obter_token()
    except Exception as exc:
        logger.warning("UF=%s endpoint=%s falha de autenticação: %s", uf, endpoint, exc)
        return _erro(f"falha de autenticação: {exc}")

    resultado = _executar_get(url, params, token, timeout_s)

    if resultado["erro"] is None and resultado["status_code"] in (401, 403):
        # Token possivelmente expirado/revogado: renova e tenta uma vez.
        logger.info("UF=%s endpoint=%s HTTP %s; renovando token.", uf, endpoint, resultado["status_code"])
        try:
            token = auth_dadosjah.obter_token(forcar=True)
        except Exception as exc:
            return _erro(f"falha de autenticação: {exc}")
        resultado = _executar_get(url, params, token, timeout_s)

    if resultado["erro"] is not None:
        logger.warning("UF=%s endpoint=%s %s", uf, endpoint, resultado["erro"])
        return _erro(resultado["erro"])

    if resultado["status_code"] != 200:
        erro = _mensagem_erro(resultado["status_code"], resultado["corpo"])
        logger.warning("UF=%s endpoint=%s %s", uf, endpoint, erro)
        return _erro(erro)

    dados = _normalizar_resposta(resultado["corpo"] or {})
    # response_time (cliente) é inserido após a normalização: como o campo da
    # API se chama responseTime, ambos coexistem e o valor do cliente tem
    # precedência na leitura feita pelo coletor.
    dados["response_time"] = resultado["response_time"]
    return {"ok": True, "dados": dados, "erro": None}


if __name__ == "__main__":
    from src.utils.logger import configurar_logger
    from src.utils.settings import carregar_env

    carregar_env()
    configurar_logger("api_dadosjah")
    print(consultar_status("MG", "/v1/nfe/service-status", 2, Settings.API_TIMEOUT_S))
