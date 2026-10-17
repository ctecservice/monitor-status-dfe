import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Permite executar o modulo de qualquer pasta: coloca a raiz do projeto no sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Raiz do projeto: src/utils/settings.py -> src -> raiz do projeto
RAIZ_PROJETO = Path(__file__).resolve().parents[2]
CAMINHO_ENV = RAIZ_PROJETO / ".env"

# Chaves lidas do .env como texto simples (o default declarado em Settings vale)
_CHAVES_TEXTO = [
    "API_BASE_URL",
    "API_LOGIN_USUARIO",
    "API_LOGIN_SENHA",
    "MONITOR_MASTER_KEY",
    "SESSION_COOKIE_SECURE",
    "TURNSTILE_SITE_KEY",
    "TURNSTILE_SECRET_KEY",
    "UFS",
    "TP_AMBS",
    "BANCO_CAMINHO",
    "LOG_NIVEL",
]


class Settings:
    """Configuracoes do projeto, lidas do .env. Nenhum segredo nos padroes."""

    # API DadosJah
    API_BASE_URL = "https://api-dfe.dadosjah.com.br"
    API_TIMEOUT_S = 20
    # Credenciais de login da API (valores reais ficam no .env; nunca em defaults)
    API_LOGIN_USUARIO = ""
    API_LOGIN_SENHA = ""

    # Seguranca: chave mestra para derivar a chave de criptografia dos segredos
    MONITOR_MASTER_KEY = ""
    # Cookie de sessao somente sob HTTPS (True em producao; vazio/False no dev)
    SESSION_COOKIE_SECURE = ""

    # Anti-bot das APIs publicas (Cloudflare Turnstile). Sem chaves = desligado.
    TURNSTILE_SITE_KEY = ""
    TURNSTILE_SECRET_KEY = ""

    # Coleta (padroes de UFS/ambientes; intervalo e retencoes ficam em config.json)
    UFS = "AC,AL,AP,AM,BA,CE,DF,ES,GO,MA,MT,MS,MG,PA,PB,PR,PE,PI,RJ,RN,RS,RO,RR,SC,SP,SE,TO"
    TP_AMBS = "1,2"

    # Banco de dados
    BANCO_CAMINHO = "data/statusdfe.db"

    # Logs
    LOG_NIVEL = "INFO"

    @classmethod
    def recarregar(cls):
        """Le as variaveis do .env e sincroniza os atributos da classe."""
        for chave in _CHAVES_TEXTO:
            setattr(cls, chave, os.getenv(chave, getattr(cls, chave)))
        cls.API_TIMEOUT_S = int(os.getenv("API_TIMEOUT_S", cls.API_TIMEOUT_S))

    @classmethod
    def lista_ufs(cls):
        """Retorna a lista de UFs configuradas.

        Returns:
            Lista de siglas de UF em maiusculas, sem espacos em branco.
        """
        return [uf.strip().upper() for uf in cls.UFS.split(",") if uf.strip()]

    @classmethod
    def lista_tp_ambs(cls):
        """Retorna a lista de ambientes (tpAmb) configurados.

        Returns:
            Lista de inteiros representando os ambientes
            (1 = producao, 2 = homologacao).
        """
        return [int(amb.strip()) for amb in cls.TP_AMBS.split(",") if amb.strip()]


def carregar_env(caminho_env=None):
    """Carrega as variaveis do .env (raiz do projeto) e sincroniza Settings.

    Args:
        caminho_env: Caminho opcional de um arquivo .env especifico.
            Padrao: .env na raiz do projeto.

    Returns:
        None.
    """
    caminho = Path(caminho_env) if caminho_env else CAMINHO_ENV
    if caminho.exists():
        load_dotenv(caminho, override=False)
    Settings.recarregar()


# Inicializa com os padroes para acesso seguro antes do carregamento do .env
Settings.recarregar()
