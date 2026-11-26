# Coleta Rural

## Versão 1.2.5

Plugin QGIS para importação automática de memoriais descritivos (do sistema Coleta Rural ou de outras origens), com criação e gravação de polígonos diretamente em camadas vetoriais previamente configuradas — e geração de memoriais descritivos em PDF a partir de polígonos já selecionados no projeto.

---

## Desenvolvedor

**Dihêgo Augusto Gomes Malvim de Barros**
Assistente Técnico da Governança de Terras
INCRA Pernambuco

---

## Objetivo

O plugin Coleta Rural foi desenvolvido para agilizar o processo de importação de memoriais descritivos, eliminando a necessidade de digitação manual de coordenadas e atributos — e, quando o imóvel já está delimitado como polígono no projeto (ex.: uma parcela do SIGEF ou do CAR), para gerar o memorial descritivo em PDF diretamente a partir dele.

A tela principal é organizada em 4 abas, com a "Camada de destino" e o botão "Gerir Camadas" sempre visíveis no topo, independente da aba ativa.

---

## Funcionalidades

### Aba "Memorial Coleta Rural"

- Seleção do memorial em PDF gerado pelo sistema Coleta Rural — ou da Declaração de Posse Mansa e Pacífica gerada pelo app **Declara Rural**, lida da mesma forma (imóvel, município/UF, possuidor, CPF, área, CIR e os vértices da tabela de coordenadas geográficas);
- Leitura também do memorial descritivo (tabelas, texto corrido e remembramento) e da planta de levantamento georreferenciado do **Coleta Pro**;
- Leitura automática do conteúdo do documento;
- Extração de informações do imóvel e dos vértices geográficos;
- Campos "CIR" (com máscara) e "Matrícula" para preencher antes de salvar, evitando ter que editar a camada depois.

### Aba "Memorial Genérico" (memoriais fora do padrão Coleta Rural)

- Importação de memoriais descritivos de outras origens: anexando o PDF (se tiver texto extraível), anexando um arquivo de geometria (KML, KMZ, GeoJSON, Shapefile ou DXF), ou colando o texto já com OCR feito externamente;
- Extração automática dos dados do imóvel (inclusive rótulos alternativos, como "PROPRIETÁRIO" para Declarante), com campos editáveis para corrigir ou completar manualmente;
- Reconhecimento automático das coordenadas no texto corrido, mesmo com quebras de linha e outras medidas misturadas, corrigindo sozinho a ordem longitude/latitude e o sinal negativo;
- Reconhece também coordenadas em graus-minutos-segundos rotuladas ("Longitude: .../Latitude: ...") e coordenadas UTM rotuladas com N/E em qualquer ordem, formatos comuns em memoriais de georreferenciamento SIGEF/INCRA e modelos oficiais de memorial topográfico;
- Reconhece tabelas de coordenadas em duas colunas separadas (lista de Norte e lista de Este, comum ao copiar de uma planta via OCR), inclusive quando o OCR confunde a vírgula decimal com ponto ou espaço, e mesmo quando os valores já vêm limpos com muitas casas decimais;
- Reconhece memoriais em formato de poligonal (traverse): a partir de um vértice inicial com coordenada UTM conhecida, calcula a coordenada dos demais vértices "andando" segmento por segmento, seja por azimute em graus decimais ou por rumo quadrantal (ex.: "NE 45°30'20"");
- Reconhece coordenadas em graus-minutos-segundos escritas em prosa corrida, sem rótulo explícito ("de coordenadas -8°11'09,909" S e -35°46'12,804" W"), comum em memoriais SIGEF/INCRA que também descrevem azimute e distância entre vértices;
- Tabela de conferência com as coordenadas identificadas antes de visualizar ou salvar;
- Coordenada UTM identificada automaticamente pede apenas a confirmação do fuso e do datum (SIRGAS2000, SAD69 ou WGS84);
- Detecção automática do fuso e do datum quando informados no texto do memorial; se não informado, o plugin pergunta;
- Área do imóvel calculada automaticamente a partir das coordenadas declaradas (hectares), em vez do valor informado no texto do memorial;
- Campo CPF/CNPJ formata automaticamente enquanto se digita, alternando sozinho entre a máscara de CPF e CNPJ conforme a quantidade de dígitos;
- Aviso automático quando um vértice fica muito mais distante dos vizinhos do que o resto do perímetro — sinal comum de um dígito perdido ou trocado numa coordenada do memorial de origem (não bloqueia o salvamento, só chama atenção para conferir).

### Aba "Zoom Rápido"

- Campo para digitar uma coordenada e localizar rapidamente um ponto no mapa, sem criar nenhuma camada;
- Três opções de coordenada: Geográfica (graus-minutos-segundos), Geográfica (decimal) ou UTM (plana);
- Coordenada geográfica (GMS ou decimal): zoom imediato, sem perguntas;
- Coordenada UTM (plana): solicita automaticamente o fuso e o datum;
- Os campos mostram um exemplo do formato esperado como texto cinza, que some ao digitar.

### Aba "Gerar Memorial" (a partir de polígono(s) já selecionado(s))

- Gera o memorial descritivo em PDF, no mesmo layout do app oficial Coleta Rural (com a logo do INCRA), a partir de um ou mais polígonos já selecionados numa camada do projeto — sem depender de texto ou PDF importado;
- Se mais de um polígono estiver selecionado, só gera o memorial se forem adjacentes (compartilharem uma borda de verdade, não só um vértice); nesse caso mescla num contorno externo único (só ele entra na lista de coordenadas), mas o croqui continua desenhando os limites internos originais (linha tracejada), com uma etiqueta no centro de cada polígono (Matrícula, ou CIR quando não houver Matrícula); se não forem adjacentes, nada é gerado — só um aviso pedindo que sejam adjacentes;
- Reconhece automaticamente os campos de camadas públicas oficiais: **SIGEF Brasil** (código do imóvel, matrícula, nome da área, e os códigos IBGE de município/UF, resolvidos para nome/sigla) e **CAR/SICAR** (município, UF) — pré-preenchendo os campos correspondentes quando disponíveis, sempre editáveis;
- O memorial gerado cita automaticamente a fonte do polígono: "Certificado pelo SIGEF", "Declarado no CAR", ou "Indicado pela equipe do INCRA" quando a camada de origem não corresponde a nenhum dos dois esquemas;
- Croqui com imagem de satélite de fundo (Esri World Imagery, com o devido crédito da fonte), mostrando só o(s) polígono(s) do imóvel, de forma translúcida;
- Cabeçalho com link direto para o centro do imóvel no Google Maps;
- Lista de coordenadas organizada em até 4 colunas por página, continuando automaticamente em página(s) extras quando necessário, sem nunca invadir o rodapé;
- A camada de origem dos polígonos é escolhida à parte, independente da "Camada de destino" do topo — esta aba só gera o PDF, não grava nenhuma feição em camada nenhuma.

### Pré-visualização (abas de importação)

- Geração automática do polígono;
- Visualização temporária no mapa;
- Zoom automático para a geometria;
- Destaque visual com transparência.

### Configuração de Camadas

- Seleção das camadas autorizadas;
- Armazenamento das configurações do usuário;
- Exibição apenas das camadas permitidas na interface principal;
- Criação automática da camada padrão do Coleta Rural (Shapefile ou GeoPackage), já com os campos e o sistema de referência corretos, para quem ainda não possui uma camada configurada.

### Salvamento (abas de importação)

- Inserção automática da geometria na camada escolhida;
- Preenchimento dos atributos do imóvel;
- Commit automático das alterações;
- Limpeza da área de trabalho após a importação.

---

## Campos Compatíveis

O plugin foi projetado para trabalhar com camadas de destino contendo os seguintes atributos:

| Campo |
|---------|
| CIR |
| Imóvel |
| Matrícula |
| Município |
| UF |
| Declarante |
| CPF/CNPJ |
| OBS |
| Área |

Campos adicionais podem ser adicionados futuramente.

---

## Fluxo de Trabalho

1. Selecione a camada de destino no topo da janela (ou crie uma nova pela tela "Gerir Camadas");
2. Escolha a aba de acordo com a origem do memorial:
   - **Memorial Coleta Rural** — anexe o PDF gerado pelo sistema Coleta Rural;
   - **Memorial Genérico** — anexe um PDF, um arquivo de geometria, ou cole o texto do memorial e clique em "Extrair Dados do Texto"; revise os campos e as coordenadas identificadas;
   - **Zoom Rápido** — digite uma coordenada e clique em "Visualizar Localização" para conferir um ponto no mapa;
   - **Gerar Memorial** — selecione a camada de origem, selecione o(s) polígono(s) desejado(s) nela e clique em "Carregar Seleção"; revise os campos identificados automaticamente e clique em "Visualizar no Mapa" e depois "Gerar Memorial PDF";
3. Nas abas de importação, clique em "Visualizar no Mapa" para conferir a geometria e depois em "Salvar na Camada" para gravar a feição.
