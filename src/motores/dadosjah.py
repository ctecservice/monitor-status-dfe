import logging
import sys
from pathlib import Path

import httpx

# Permite executar o modulo de qualquer pasta: coloca a raiz do projeto no sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.motores.base import MotorBase
from src.services import api_dadosjah, auth_dadosjah
from src.utils.settings import Settings

logger = logging.getLogger("motor_dadosjah")


class MotorDadosJah(MotorBase):
    """Motor da API DadosJah (``api-dfe.dadosjah.com.br``).

    A autenticação é renovada a cada ciclo de coleta (decisão de segurança):
    o login é feito no início do ciclo, o mesmo token é reaproveitado em todas
    as consultas e o logout é executado no final. A credencial é mantida em
    atributo privado apenas enquanto o ciclo está em andamento.
    """

    def __init__(self):
        # Referência temporária ao token do ciclo; zerada em encerrar().
        self._token = None
        # Cliente HTTP único do ciclo (reuso de conexão TCP/TLS); fechado em
        # encerrar(). None enquanto não há ciclo em andamento.
        self._client = None

    @property
    def nome(self):
        """Nome curto do motor.

        Returns:
            str: ``"dadosjah"``.
        """
        return "dadosjah"

    def autenticar(self):
        """Faz o login na API e devolve um token novo para o ciclo.

        A renovação é forçada (sem reaproveitar cache) para garantir memória
        limpa entre ciclos. Credenciais e token nunca são logados.

        Returns:
            str com o accessToken.

        Raises:
            RuntimeError: quando as credenciais não estão configuradas ou o
                login falha.
        """
        self._token = None
        token = auth_dadosjah.obter_token(forcar=True)
        self._token = token

        # Abre um único httpx.Client para todas as consultas do ciclo, evitando
        # o custo de abrir/fechar conexão a cada chamada. Se já houver um
        # cliente (relogin no meio do ciclo), fecha antes de criar o novo.
        if self._client is not None:
            try:
                self._client.close()
            except Exception as exc:  # fechamento nunca deve quebrar o ciclo
                logger.warning("Falha ao fechar cliente HTTP anterior: %s", exc)
        self._client = httpx.Client(timeout=Settings.API_TIMEOUT_S)
        return token

    def consultar_status(self, uf, endpoint, tp_amb, timeout_s, token):
        """Consulta o status de um serviço SEFAZ usando o token do ciclo.

        Em HTTP 401/403 (token expirado ou revogado) faz **um** relogin e
        repete a consulta com o novo token, que passa a ser o token corrente
        do motor. Nas consultas seguintes do ciclo, o token corrente tem
        precedência sobre o parâmetro (que serve de fallback), garantindo que
        um token renovado seja reaproveitado.

        Args:
            uf: Sigla da UF (ex.: ``MG``).
            endpoint: Caminho relativo do endpoint (ex.: ``/v1/nfe/service-status``).
            tp_amb: Ambiente (1 = produção, 2 = homologação).
            timeout_s: Timeout da requisição, em segundos.
            token: Token obtido em :meth:`autenticar`.

        Returns:
            dict ``{"ok": bool, "dados": dict | None, "erro": str | None}``.
        """
        token = self._token or token
        if not token:
            return {
                "ok": False,
                "dados": None,
                "erro": "token ausente; autenticação não realizada",
            }

        resultado = api_dadosjah.consultar_status(
            uf, endpoint, tp_amb, timeout_s, token, client=self._client
        )

        if resultado.get("status_code") in (401, 403):
            logger.info(
                "UF=%s endpoint=%s HTTP %s; refazendo login e repetindo a consulta.",
                uf,
                endpoint,
                resultado.get("status_code"),
            )
            try:
                token = self.autenticar()
            except Exception as exc:
                return {
                    "ok": False,
                    "dados": None,
                    "erro": f"falha de autenticação: {exc}",
                }
            # autenticar() recriou self._client; a nova consulta usa o novo.
            resultado = api_dadosjah.consultar_status(
                uf, endpoint, tp_amb, timeout_s, token, client=self._client
            )

        return {
            "ok": resultado["ok"],
            "dados": resultado["dados"],
            "erro": resultado["erro"],
        }

    def encerrar(self, token):
        """Faz o logout e descarta a credencial mantida em memória.

        O token efetivamente encerrado é o corrente do motor (pode ter sido
        renovado após um 401/403); o parâmetro ``token`` serve de fallback.
        Falhas de rede/HTTP não propagam: viram log de aviso.

        Args:
            token: Token devolvido por :meth:`autenticar`.

        Returns:
            None.
        """
        alvo = self._token or token
        try:
            if alvo:
                auth_dadosjah.encerrar_sessao(alvo)
        except Exception as exc:  # logout nunca deve quebrar o ciclo
            logger.warning("Falha ao encerrar sessão do motor dadosjah: %s", exc)
        finally:
            self._token = None
            # Fecha o cliente HTTP do ciclo após o logout; falha no fechamento
            # não propaga (apenas log de aviso).
            if self._client is not None:
                try:
                    self._client.close()
                except Exception as exc:
                    logger.warning("Falha ao fechar cliente HTTP: %s", exc)
                finally:
                    self._client = None


if __name__ == "__main__":
    from src.utils.logger import configurar_logger
    from src.utils.settings import carregar_env

    carregar_env()
    configurar_logger("motor_dadosjah")

    motor = MotorDadosJah()
    token_ciclo = None
    try:
        token_ciclo = motor.autenticar()
        print("Token obtido:", bool(token_ciclo))
        print(motor.consultar_status("MG", "/v1/nfe/service-status", 2, 20, token_ciclo))
    finally:
        motor.encerrar(token_ciclo)
        print("Token em memória após encerrar:", motor._token)
