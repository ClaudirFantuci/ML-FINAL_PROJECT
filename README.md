# ML-FINAL_PROJECT

Estimador acadêmico do **preço anunciado de casas em Londrina/PR**, com interface Django, mapa de anúncios de treino e previsão por vizinhos semelhantes (KNN). A base representa a oferta publicada nos portais consultados. Preços efetivos de escritura e imóveis fora desses portais ficam fora do escopo.

## Executar no Windows

Use Python 3.11 ou posterior. Na pasta do projeto:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py runserver
```

Abra <http://127.0.0.1:8000>. Sem modelo, a página informa como habilitar as estimativas. No Linux ou macOS use `.venv/bin/python`. O pacote Python de configuração do Django se chama `ml_final_project`.

## Preparar anúncios e treinar

Execute as etapas abaixo conforme os dados que já possui. Com o Parquet final compatível, comece diretamente em `train.py`. A partir de páginas locais, comece em `run_build.py`.

```powershell
.\.venv\Scripts\python.exe run_collect.py zap
.\.venv\Scripts\python.exe run_build.py
.\.venv\Scripts\python.exe train.py
```

A coleta aceita ZAP ou Viva Real, que compartilham parte do estoque. Faz consultas identificadas, com pausas, limites de tentativas e retomada das páginas salvas no dia. O acesso depende da disponibilidade e da permissão do portal. Em caso de recusa HTTP a coleta é interrompida. Use um acervo autorizado em `raw/<portal>/<data>/*.json`, com os campos `portal`, `collected_at` e `listings`, ou um dataset final compatível. Mudanças na estrutura das páginas podem exigir atualização do leitor.

- **Coleta e qualidade.** O relatório por portal e data registra volumes previstos e obtidos por faixa. A preparação grava contagens de cada etapa, datas, origens, frações de dados ausentes e alertas em `final/qualidade.json`.
- **Deduplicação.** Recoletas do mesmo anúncio conservam o registro mais recente e seu histórico. A fusão entre anúncios exige endereço completo, localização marcada como exata, configuração do imóvel e descrição coincidentes. A lista de pares removidos fica em `staged/auditoria_duplicatas.csv`. Para auditar manualmente, confira uma amostra desses pares nas páginas locais e também anúncios distintos do mesmo grupo que foram mantidos.
- **Privacidade.** As camadas bruta e intermediária e o cache de endereços são locais. O dataset final remove texto livre, rua, número e identificadores do anunciante. Conserva coordenadas, bairro e identificadores de anúncio para análise. Avalie esses campos antes de redistribuí-lo.

## Como interpretar a avaliação

1. O treino reserva um teste independente por grupo de imóvel. Quando há histórico suficiente, o teste usa grupos vistos pela primeira vez após o corte e o treino usa grupos cuja última observação antecede o corte. Grupos que cruzam o corte ficam fora dessa avaliação. Com uma única coleta, o relatório identifica a divisão por grupo. São necessários pelo menos 16 grupos para executar a avaliação.
2. Parte dos grupos restantes fica reservada para calibração. No restante, validação cruzada por blocos espaciais de 0,02 grau escolhe o número de vizinhos, a ponderação pela distância e o peso da zona. Quando só há um bloco, a validação usa grupos de imóveis. Em cada dobra, o escalonamento e o K-Means são ajustados apenas com o treino. O K-Means usa coordenadas convertidas em quilômetros e escolhe o número de regiões por silhouette. A grade inclui peso zero para medir o desempenho sem zona.
3. O teste compara KNN, mediana de preço, mediana de preço por m², Ridge e HistGradientBoosting nas mesmas casas, com MAE em reais, MAPE e R². O KNN atende à proposta acadêmica mesmo quando outro método tem menor erro. A contagem de comodidades usa exatamente as oito opções do formulário.
4. O intervalo conformal com alvo de 80% usa resíduos absolutos em log-preço em imóveis de calibração, com o maior resíduo por grupo. A largura média e a cobertura efetivamente observada são calculadas no teste independente. Mudanças de mercado, regiões com pouco histórico e amostras pequenas podem alterar a cobertura. As contagens em 1 e 2 km indicam densidade local de anúncios.
5. Cada treino publica uma pasta `models/treino-*/` com o modelo, os pontos e `meta.json`. O arquivo `models/CURRENT` indica a versão ativa e só muda após a gravação completa. O relatório inclui os parâmetros escolhidos, a grade avaliada, a comparação, estatísticas das entradas, versões de bibliotecas e identificadores do código e do arquivo de dados. Execute novamente o treinamento para atualizar modelos de versões anteriores.

## Interface e serviços

O formulário envia consultas para `/api/estimar/` com token CSRF. A API valida limites e relações entre os campos e limita consultas por IP. O endereço é conferido com os dados de município e estado retornados pelo Nominatim. O mapa Leaflet consome `/api/pontos/` e mostra até 1.500 anúncios de treino. As consultas de endereço, o fundo cartográfico e os arquivos do Leaflet usam serviços externos.

Por padrão, o Django aceita hosts locais e mantém o modo de depuração desligado. Para publicação, configure `DJANGO_ENV=production`, `DJANGO_SECRET_KEY` e `DJANGO_ALLOWED_HOSTS` com nomes explícitos e disponibilize HTTPS. A limitação de consultas e o controle de frequência do geocodificador são por processo. Para várias instâncias, centralize a quota e o agendamento das consultas externas.

## Verificar

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe -m unittest discover -v
```

A suíte usa anúncios sintéticos, diretórios temporários e geocodificação simulada. As métricas de desempenho imobiliário dependem de treino e teste com anúncios reais.
"# ML-FINAL_PROJECT" 
