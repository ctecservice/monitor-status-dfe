import sys
from abc import ABC, abstractmethod
from pathlib import Path

# Permite executar o modulo de qualquer pasta: coloca a raiz do projeto no sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


class MotorBase(ABC):
    """Contrato de um motor de consulta de status de serviços SEFAZ.

    Este é o **ponto de extensão público** do projeto: cada API de consulta é
    implementada por uma subclasse concreta (um módulo em ``src/motores/``) e
    registrada em ``_MOTORES`` no ``__init__`` do pacote.

    Ciclo de vida esperado pelo coletor::

        motor = criar_motor(config.motor_ativo())
        token = motor.autenticar()          # login no início do ciclo
        try:
            motor.consultar_status(...)     # todas as consultas usam o mesmo token
        finally:
            motor.encerrar(token)           # logout no final do ciclo

    Para adicionar uma nova API:

    1. Crie ``src/motores/<api>.py`` com uma subclasse de :class:`MotorBase`;
    2. Implemente :meth:`nome`, :meth:`autenticar`, :meth:`consultar_status` e
       :meth:`encerrar` sem manter credenciais em atributos persistentes;
    3. Registre a classe em ``_MOTORES`` no arquivo ``src/motores/__init__.py``.

    O motor deve ser "sem estado" entre ciclos: a credencial vive apenas
    durante o ciclo e é descartada em :meth:`encerrar`.
    """

    @property
    @abstractmethod
    def nome(self) -> str:
        """Nome curto do motor, usado como valor de ``motor_ativo``.

        Returns:
            str com o identificador do motor (ex.: ``"dadosjah"``).
        """

    @abstractmethod
    def autenticar(self) -> str:
        """Obtém a credencial de acesso (token) para o ciclo de coleta.

        Returns:
            str com o token a ser enviado nas consultas do ciclo.

        Raises:
            RuntimeError: quando as credenciais não estão configuradas ou o
                login falha. A mensagem nunca deve conter dados sensíveis.
        """

    @abstractmethod
    def consultar_status(self, uf, endpoint, tp_amb, timeout_s, token) -> dict:
        """Consulta o status de um serviço em uma UF.

        Args:
            uf: Sigla da UF (ex.: ``MG``).
            endpoint: Caminho relativo do endpoint de status.
            tp_amb: Ambiente (1 = produção, 2 = homologação).
            timeout_s: Timeout da requisição, em segundos.
            token: Credencial obtida em :meth:`autenticar` (mesma do ciclo).

        Returns:
            dict ``{"ok": bool, "dados": dict | None, "erro": str | None}``.
            Falhas de negócio/rede não levantam exceção: voltam em ``erro``.
        """

    @abstractmethod
    def encerrar(self, token) -> None:
        """Encerra a sessão/revoga a credencial no final do ciclo.

        Deve ser tolerante a falhas (apenas log de aviso) e **sempre** limpar
        qualquer credencial mantida em memória pelo motor.

        Args:
            token: Credencial devolvida por :meth:`autenticar`.

        Returns:
            None.
        """
