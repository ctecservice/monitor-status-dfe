# Como executar

Passo a passo para rodar o Monitor Status DFe localmente do zero, no Windows e no Linux, com solução de problemas comuns.

## Pré-requisitos

- **Python 3.12** instalado e disponível no PATH.
- Acesso à internet (para consultar a API DadosJah).
- Credenciais de login da API DadosJah (`API_LOGIN_USUARIO` e `API_LOGIN_SENHA`).

Para verificar o Python:

```
python --version
```

No Windows, o comando pode ser `py -3.12 --version`.

---

## Windows

### 1. Criar o ambiente virtual e instalar dependências

Na pasta do projeto, execute:

```
criar-venv.bat
```

Isso cria a pasta `.venv` e instala as dependências do `requirements.txt`.

### 2. Preparar o `.env`

Copie o arquivo de exemplo e ajuste os valores:

```
copy .env.example .env
```

Abra o `.env` e preencha ao menos `API_LOGIN_USUARIO` e `API_LOGIN_SENHA`.

### 3. Abrir o terminal com o ambiente ativado

```
entrar-venv.bat
```

### 4. Primeiro boot

```
python src/scripts/configurar.py
```

O script gera a chave mestra, cria o banco e pede a senha do painel `/config`.

### 5. Iniciar o monitor

```
python src/app.py
```

Acesse `http://127.0.0.1:5000`.

---

## Linux

### 1. Criar o ambiente virtual e instalar dependências

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Preparar o `.env`

```bash
cp .env.example .env
```

Edite o `.env` e preencha `API_LOGIN_USUARIO` e `API_LOGIN_SENHA`.

### 3. Primeiro boot

```bash
python src/scripts/configurar.py
```

### 4. Iniciar o monitor

```bash
python src/app.py
```

Acesse `http://127.0.0.1:5000`.

---

## Verificação rápida

- Painel: `http://127.0.0.1:5000/`
- Saúde do monitor: `http://127.0.0.1:5000/health` (deve retornar `"scheduler": "ativo"`)
- Painel de configuração: `http://127.0.0.1:5000/config`

A primeira coleta roda assim que o monitor inicia; as seguintes seguem o intervalo configurado.

---

## Solução de problemas

### A porta 5000 já está em uso

Sintoma: ao iniciar, aparece um erro informando que o endereço já está em uso (`Address already in use`).

Causas comuns: outra instância do monitor em execução ou outro programa usando a porta 5000.

Verifique e encerre o processo que ocupa a porta. No Windows:

```
netstat -ano | findstr :5000
```

Anote o PID da última coluna e encerre com `taskkill /PID <numero> /F`.

No Linux:

```bash
ss -ltnp | grep :5000
```

Encerre com `kill <numero>`.

### O arquivo `.env` não existe

Sintoma: o monitor reclama de configuração ausente ou de credenciais da API.

Copie o exemplo e ajuste os valores: `copy .env.example .env` (Windows) ou `cp .env.example .env` (Linux). Sem `API_LOGIN_USUARIO` e `API_LOGIN_SENHA` corretos, a coleta não consegue autenticar.

### O login do painel `/config` não funciona

Sintoma: a senha não é aceita, ou o painel informa "Acesso indisponível".

Causa provável: o script de primeiro boot ainda não foi executado, então não há senha de administrador definida.

Solução: rode `python src/scripts/configurar.py` e defina a senha. Você pode rodar novamente a qualquer momento para redefini-la.

### "Muitas tentativas" ao entrar no painel

O painel limita o número de tentativas de login por IP em um curto intervalo. Aguarde cerca de um minuto e tente novamente.

### O painel mostra "sem dados" na maioria das células

"Sem dados" indica que o monitor não conseguiu obter resposta da fonte. Verifique:

- as credenciais da API no `.env`;
- a conectividade do servidor com a internet;
- o valor de `API_BASE_URL`;
- o nível de log (`LOG_NIVEL=DEBUG`) durante a investigação, para ver as mensagens de erro da coleta nos arquivos em `logs/`.

### Sessões caem a cada reinício

Sintoma: é preciso entrar de novo no `/config` após reiniciar.

Causa: a chave mestra (`MONITOR_MASTER_KEY`) ainda não está definida no `.env`, e o monitor usa uma chave de sessão temporária.

Solução: rode `python src/scripts/configurar.py` para gerar e gravar a chave mestra.

---

## Veja também

- [Configuração](configuracao.md)
- [Uso do painel](uso.md)
- [Hospedagem (deploy)](deploy.md)
