import sys
import time
from pathlib import Path

# Permite executar o modulo de qualquer pasta: coloca a raiz do projeto no sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


class RateLimiter:
    """Limitador de requisições em memória com janela deslizante.

    Mantém, por chave (ex.: IP do cliente), as marcas de tempo monotônicas das
    tentativas recentes e libera no máximo ``limite`` tentativas por
    ``janela_s`` segundos. O estado vive em memória do processo: é suficiente
    para uma única instância (1 worker). Em produção atrás de nginx com vários
    workers, ainda convém somar ``limit_req`` no proxy.

    Args:
        limite: Número máximo de tentativas permitidas na janela.
        janela_s: Tamanho da janela em segundos.
    """

    def __init__(self, limite, janela_s):
        self.limite = limite
        self.janela_s = janela_s
        self._tentativas = {}

    def consome(self, chave):
        """Registra uma tentativa da chave e informa se está dentro do limite.

        Descarta marcas fora da janela e chaves sem tentativas recentes, para
        que o dicionário não cresça indefinidamente.

        Args:
            chave: Identificador da origem (ex.: IP do cliente).

        Returns:
            True se a tentativa está dentro do limite; False se o excedeu.
        """
        agora = time.monotonic()
        limite_inferior = agora - self.janela_s

        # Expurgo: remove marcas antigas e apaga chaves que ficaram sem
        # tentativas na janela atual.
        for chave_antiga in list(self._tentativas):
            marcas = [m for m in self._tentativas[chave_antiga] if m >= limite_inferior]
            if marcas:
                self._tentativas[chave_antiga] = marcas
            else:
                del self._tentativas[chave_antiga]

        marcas = self._tentativas.setdefault(chave, [])
        if len(marcas) >= self.limite:
            return False
        marcas.append(agora)
        return True


if __name__ == "__main__":
    limiter = RateLimiter(2, 60)
    print("1a:", limiter.consome("ip-teste"))
    print("2a:", limiter.consome("ip-teste"))
    print("3a:", limiter.consome("ip-teste"))
