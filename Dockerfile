# Monitor Status DFe - imagem de execucao
# Build: docker build -t monitor-status-dfe .
# Run:   docker run -d -p 5628:5628 -v $(pwd)/data:/app/data -v $(pwd)/logs:/app/logs monitor-status-dfe
#
# Antes do build, prepare config.json e .env no projeto (o COPY . . os inclui):
#   cp config.example.json config.json    # ajuste a secao "web" (porta, etc.)
#   cp .env.example .env                  # preencha as credenciais da API
#   python src/scripts/configurar.py      # gera a master key no .env

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5628

CMD ["python", "src/app.py"]
