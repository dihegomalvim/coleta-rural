# Changelog

Todas as alterações relevantes deste projeto serão documentadas neste arquivo.

O formato segue o padrão de versionamento semântico (Semantic Versioning).

---

## [1.2.3] - 2026-08-19

### Adicionado

- Reconhecimento de memoriais descritivos em formato de poligonal (azimute e distância entre vértices, a partir de um vértice inicial com coordenada UTM conhecida) na aba "Memorial Genérico" — formato topográfico tradicional, comum em memoriais mais antigos, em vez de listar a coordenada de cada vértice diretamente. O plugin calcula a coordenada de cada vértice "andando" a partir do ponto inicial, segmento por segmento, na convenção padrão de azimute topográfico (medido no sentido horário a partir do Norte).
- Reconhecimento de memoriais descritivos em formato de poligonal por **rumo** (quadrante + ângulo, ex.: "NE 45°30'20"", em vez de azimute em graus decimais) na aba "Memorial Genérico" — outra notação tradicional muito usada em memoriais mais antigos. Aceita o quadrante antes ou depois do ângulo, com o ângulo em graus-minutos-segundos ou em graus decimais. O rumo é convertido para azimute pela conversão padrão de topografia (NE mantém o ângulo, SE/SO/NO refletem em torno dos eixos Norte-Sul e Leste-Oeste) e reaproveita o mesmo cálculo de poligonal já usado para azimute/distância.
- Reconhecimento de coordenadas em graus-minutos-segundos escritas por extenso ("8 GRAUS 37 MINUTOS 43,36 SEGUNDOS SUL", "35 GRAUS 53 MINUTOS 29,04 SEGUNDOS OESTE"), em vez dos símbolos °/'/" — comum em memoriais mais antigos (ex.: de levantamento aerofotogramétrico). O texto é convertido para a notação com símbolos antes de qualquer extração, então esse formato passa a funcionar em todos os reconhecimentos de coordenada já existentes (rotulado, estrutural por hemisfério, etc.), sem precisar de lógica própria — e sem confundir "sul"/"norte"/"leste"/"oeste" usados como direção cardinal comum em prosa (só converte quando a palavra aparece logo depois de um valor em graus-minutos-segundos).
- Reconhecimento de memoriais em formato de poligonal descrita em prosa corrida (em vez de tabela), comum em memoriais mais antigos do INCRA/convênios estaduais dos anos 1980 (ex.: "PARTINDO DO MARCO M-13723-37, COM LATITUDE 8°37'43,36" S E LONGITUDE 35°53'29,04" O, COM AZIMUTE DE 314°26'33" E DISTANCIA DE 41,42M, [...] CHEGA AO PONTO P-18209; DESTE, COM AZIMUTE DE [...]"). Diferente das poligonais já suportadas, o ponto de partida aqui é geográfico (latitude/longitude), não UTM — o plugin projeta esse ponto para uma zona UTM local só como etapa interna de cálculo, e devolve a poligonal já em coordenada geográfica. Quando o memorial original omite o azimute de algum trecho (algo comum em documentos antigos), o plugin não arrisca calcular uma poligonal incompleta — mostra um aviso específico indicando exatamente entre quais dois vértices falta o azimute, para conferência manual no documento original.
- Reconhecimento de mais uma variação de poligonal em prosa, dessa vez a partir de um vértice com coordenada UTM conhecida (E=/N=) e cada segmento descrito como "com distância de ...m e azimute de ..., encontramos o vértice ..." (distância antes do azimute, fechando com "encontramos", em vez de "com azimute de ... e distância de ...m, [...] chega ao ponto ..."). Reconhece também rótulos de vértice com espaçamento irregular ao redor do hífen (ex.: "V - 28", "V- 29"), comuns em memoriais digitados manualmente.
- Botão "Anexar Imagem (Planta)" na aba "Memorial Genérico": carrega uma foto ou scan da planta/croqui do imóvel (ou um PDF contendo uma) num painel de visualização próprio (600px de largura), que expande a janela do plugin para a direita — sem criar nenhuma camada no projeto QGIS nem mexer no canvas principal, para consulta visual lado a lado enquanto se confere ou completa manualmente um memorial. Aceita PDF diretamente: se o arquivo tiver mais de uma imagem embutida (comum quando o PDF tem várias páginas escaneadas — título, memorial descritivo, planta), mostra uma miniatura de cada uma para escolher visualmente qual usar. A primeira visualização já aparece ocupando o painel inteiro; a roda do mouse dá zoom livremente a partir daí (pra dentro e pra fora, com suporte a mouses/trackpads de rolagem de precisão), e o botão do meio do mouse (pressionar e arrastar) faz pan pela imagem sem alterar o zoom nem marcar nenhum ponto — essencial depois de dar zoom pra conferir uma anotação (muitas plantas trazem o próprio azimute/distância escritos no desenho) sem ter que voltar o zoom e perder a posição.
- Botão "Desenhar Polígono na Planta" (habilitado depois de anexar uma imagem): permite marcar os vértices do imóvel diretamente sobre o desenho da planta, sem depender de o texto do memorial estar completo. Funciona clicando primeiro nos dois pontos de um trecho já conhecido (com azimute e distância informados no memorial); antes de informar esses valores reais, os dois marcadores desse trecho podem ser arrastados para ajustar a posição exata do clique — só depois de clicar com o botão direito para confirmar é que abre o formulário curto, com três opções de coordenada (Geográfica GMS, Geográfica decimal ou UTM), usando a posição final (já ajustada, se for o caso) de cada marcador. Esse formulário não trava mais a imagem da planta atrás dele (deixou de ser uma janela modal): dá pra continuar dando zoom e pan na planta para ler uma anotação enquanto o preenche, em vez de ter que fechar o formulário, olhar a planta e reabri-lo. O plugin calcula sozinho a rotação e a escala do desenho a partir desse único trecho (não precisa medir a seta do norte manualmente) e converte cada clique seguinte na planta para a coordenada real correspondente. Cada clique deixa um marcador visível; os marcadores dos vértices (etapa seguinte à calibração) também podem ser arrastados para corrigir a posição sem cancelar o desenho, e excluídos com um clique direito em cima deles (os dois marcadores de calibração, mesmo arrastáveis, não são excluíveis — o desenho depende deles) — clique direito numa área vazia da planta finaliza o desenho normalmente (Esc cancela a qualquer momento). A lista final de coordenadas reflete a posição atual de cada marcador no momento de finalizar, já contando qualquer arrasto feito antes disso.
- Suporte a datum diferente de SIRGAS2000 em coordenadas geográficas (Longitude/Latitude) — antes, qualquer coordenada geográfica extraída do texto (ou usada na calibração de "Desenhar Polígono na Planta") era tratada como se já estivesse em SIRGAS2000/EPSG:4674, sem nenhuma pergunta. Memoriais anteriores a 2005 (quando o Brasil adotou SIRGAS2000 como referência oficial) costumam usar SAD69, e tratar essa coordenada como SIRGAS2000 sem transformar desloca o polígono na casa de dezenas de metros. Se o texto (ou o formulário de calibração da planta) mencionar/escolher o datum, aplica automaticamente; se não, assume SIRGAS2000 e já extrai/desenha o polígono, em vez de interromper com uma pergunta antes de qualquer visualização. Em ambos os casos, o combo "Datum" (aba "Memorial Genérico") fica visível ao lado da tabela de coordenadas — inclusive depois de terminar de desenhar sobre a planta, quando antes desaparecia — com um aviso lembrando de conferir a data do memorial, e pode ser corrigido a qualquer momento depois de ver o resultado no mapa: trocar o datum recalcula tabela/área/mapa (ou o desenho inteiro da planta, calibração e vértices) na hora, sem precisar extrair o texto de novo nem clicar nos pontos da planta de novo (mesmo comportamento que o fuso/datum de coordenada UTM já tinha). Útil, por exemplo, para comparar o mesmo desenho em SAD69 e SIRGAS2000 sobre a imagem de satélite e escolher visualmente qual bate certo, em vez de desenhar duas vezes.
- Máscara de entrada em todos os campos de coordenada e azimute (Zoom Rápido, nos três modos — Geográfica GMS, Geográfica decimal e UTM —, e no formulário de calibração do "Desenhar Polígono na Planta"). A coordenada sempre mostra o sinal negativo já fixo (o plugin atende só o Brasil, que está sempre a Sul e a Oeste) e usa só 2 dígitos de grau (nenhuma latitude/longitude do Brasil passa de 2 dígitos); o azimute usa 3 dígitos (é um ângulo de 0 a 360°, não uma coordenada) e menos casas decimais nos segundos, já que não precisa da mesma precisão da coordenada. Para longitude e latitude (fáceis de confundir — qual campo é qual, e a ordem certa), o valor de exemplo usa os graus de Brasília em vez de zeros genéricos (ex.: "-47°00'00,0000"" na longitude, "-15°00'00,0000"" na latitude — minutos e segundos zerados mesmo, só para dar a magnitude certa), mostrado em cinza até a pessoa digitar por cima; a partir daí o texto volta à cor normal.
- Identificação automática do Município (e da UF) a partir da localização do imóvel, na aba "Memorial Genérico" — a mesma ideia que o aplicativo oficial Coleta Rural já tem. Quando o memorial não informa o município no texto (ou o polígono vem só do desenho da planta), o plugin consulta o serviço público de geocodificação reversa do OpenStreetMap a partir do centro das coordenadas já extraídas e preenche os campos sozinho. Precisa de internet (mesma exigência já feita pelo croqui com satélite e pelo link do Google Maps, na aba "Gerar Memorial"); se não conseguir, falha em silêncio e os campos continuam vazios para preenchimento manual, como já acontecia antes.
- Caixa de seleção "Informar Número do Processo SEI" na aba "Gerar Memorial": desmarcada por padrão, deixando o memorial exatamente como já era (sem essa informação no cabeçalho). Ao marcar, habilita um campo com máscara no formato oficial do SEI (00000.000000/0000-00) — se preenchido, o número aparece como a primeira linha da caixa de identificação do PDF ("Processo SEI: ..."); ao desmarcar, o campo é limpo e a linha some do memorial de novo.
- Botão "Limpar Imagem", ao lado do painel da planta: some junto com o painel (só aparece depois de anexar uma imagem) e, ao clicar, remove a imagem e qualquer marcador/calibração em andamento, esconde o painel de volta e devolve a janela ao tamanho padrão — desfazendo por completo o que "Anexar Imagem (Planta)" fez, sem precisar fechar e reabrir o plugin para tirar a planta da tela.

### Corrigido

- Corrigido um bug sério na extração de dados da aba "Memorial Genérico": quando um rótulo aparecia sozinho numa linha, sem valor nenhum na frente (ex.: "Imóvel:" sem nada depois), o campo "Imóvel"/"Declarante"/etc. ficava preenchido com um ":" literal em vez do nome de verdade — o regex antigo, ao não achar nenhum valor, "devolvia" o próprio ":" que tinha acabado de consumir como se fosse o valor. Agora esse caso é corretamente tratado como "sem valor nesta linha".
- Reconhecimento automático de dados do imóvel agora tolera acento apagado pelo OCR (ex.: "Municipio" reconhecido como "Município").
- Corrigido um falso positivo em que "MUNICÍPIO" (singular) confundia com "MUNICÍPIOS ABRANGIDOS" (plural, de outra seção do memorial) por falta de checagem de fronteira de palavra.
- Nova detecção do formato "rótulos todos juntos, valores bem mais abaixo" (Imóvel/Município/Área/Declarante/CPF-CNPJ cada um sozinho numa linha, com os valores de verdade na mesma ordem, logo após o título "MEMORIAL DESCRITIVO") — comum quando o próprio PDF gerado pelo sistema Coleta Rural é uma imagem/scan sem texto embutido e precisa ser colado na aba "Memorial Genérico" depois de um OCR externo, que costuma achatar a tabela de identificação dessa forma.
- Aviso claro na aba "Memorial Coleta Rural" quando o PDF selecionado não tem texto extraível (comum em memoriais antigos digitalizados) — antes os campos simplesmente ficavam em branco sem nenhuma explicação; agora avisa que é preciso fazer OCR externamente e colar o texto na aba "Memorial Genérico".
- Corrigido um bug sério de reconhecimento de coordenadas na aba "Memorial Genérico": memoriais que descrevem cada vértice em prosa corrida, com a coordenada em graus-minutos-segundos seguida da letra do hemisfério (ex.: "de coordenadas -8°11'09,909" S e -35°46'12,804" W"), em vez de um rótulo explícito "Longitude:"/"Latitude:" — comum em memoriais SIGEF/INCRA que também trazem azimute e distância até o próximo vértice —, não eram reconhecidos por nenhum formato específico e caíam no reconhecimento genérico de texto livre, que confundia fragmentos do próprio valor em graus-minutos-segundos (os segundos de uma coordenada) com uma coordenada inteira. Isso produzia uma área e um polígono completamente errados, sem nenhum aviso ao usuário.
- Corrigido um bug sério na calibração do "Desenhar Polígono na Planta": o cálculo tratava o "y" do painel da planta como se aumentasse para cima (como um mapa de verdade), quando na verdade aumenta para baixo (convenção padrão de imagem/tela, já que o painel é um `QGraphicsScene` mostrando a planta escaneada). Isso acertava por acidente o próprio trecho usado na calibração, mas espelhava (Leste↔Oeste) todo o resto do polígono desenhado, girando o resultado numa orientação errada — por exemplo, um imóvel alongado de Norte a Sul na planta original aparecia "deitado" (alongado de Leste a Oeste) quando desenhado sobre o mapa/satélite.
- Corrigido todo o uso de enumerações do Qt/QGIS que o QGIS ainda aceitava na forma "curta" (ex.: `Qt.AlignCenter`, `QDialog.Accepted`, `QgsWkbTypes.PolygonGeometry`) para a forma totalmente qualificada exigida pelo Qt6 (ex.: `Qt.AlignmentFlag.AlignCenter`, `QDialog.DialogCode.Accepted`, `QgsWkbTypes.GeometryType.PolygonGeometry`), e trocado `.exec_()` por `.exec()` nos dois diálogos que ainda usavam o nome antigo — sem isso, o verificador automático do repositório de plugins do QGIS rejeitava a submissão por incompatibilidade com Qt6. Não muda nenhum comportamento visível: só deixa o plugin pronto para quando o QGIS migrar de Qt5 para Qt6.

### Melhorado

- O reconhecimento de coordenadas em graus-minutos-segundos sem rótulo explícito deixou de depender de uma frase fixa ("de coordenadas ... S e ... W") e passou a se basear só na estrutura do próprio valor (°'") seguida da letra do hemisfério (S/N/E/O/W), em qualquer posição, ordem ou pontuação ao redor — reconhece igualmente "...S e ...W", "...S, ...W", "...W, ...S" ou qualquer outra redação que um memorial venha a usar, sem precisar de mais um ajuste específico a cada novo modelo de documento. A letra do hemisfério é o que evita confundir a coordenada com um azimute (que também é escrito em graus-minutos-segundos, mas nunca é seguido de uma letra de hemisfério).
- Aba "Zoom Rápido" agora tem três opções de coordenada, em vez de duas: "Geográfica (GMS)" (graus-minutos-segundos), "Geográfica (decimal)" e "UTM (plana)". Os dois campos de coordenada mostram um exemplo do formato esperado como texto cinza (some assim que a pessoa começa a digitar).
- Em todos os campos de texto editáveis do plugin (todas as abas), clicar num campo que ainda não tem nada digitado agora sempre leva o cursor para o começo dele — antes, campos com máscara (como o CIR) ainda vazios deixavam clicar no meio dos espaços em branco da máscara, obrigando a pessoa a mover o cursor manualmente antes de começar a digitar. Campos que já têm conteúdo continuam funcionando normalmente (o clique posiciona o cursor onde a pessoa clicou).

---

## [1.2.0] - 2026-08-09

### Adicionado

- Nova aba "Gerar Memorial": gera o memorial descritivo (PDF, no mesmo layout do app oficial Coleta Rural, com a logo do INCRA) a partir de um ou mais polígonos já selecionados numa camada do projeto, em vez de depender de texto ou PDF importado. Se mais de um polígono estiver selecionado, só gera o memorial se forem adjacentes (compartilharem uma borda — dois polígonos que só se tocam num único vértice não contam); nesse caso, mescla num contorno externo único (só ele entra na lista de coordenadas), mas o croqui continua desenhando os limites internos originais (linha tracejada) com uma etiqueta no centro de cada polígono mostrando sua Matrícula (ou o CIR, quando não houver Matrícula). Se não forem adjacentes, nada é gerado — só um aviso pedindo que sejam adjacentes. A camada de origem dos polígonos é escolhida à parte, independente da "Camada de destino" do topo, e a aba só gera o PDF (não grava nenhuma feição em camada nenhuma). Os campos de identificação (Imóvel, CIR, Matrícula, Município/UF, Declarante, CPF/CNPJ) são pré-preenchidos, quando existirem, a partir dos atributos dos próprios polígonos selecionados — sempre editáveis antes de gerar o PDF.
- Reconhecimento automático dos campos de camadas públicas oficiais na aba Gerar Memorial: do **SIGEF Brasil** (`codigo_imo` → CIR, `registro_m` → Matrícula, `nome_area` → Imóvel, e os códigos IBGE `municipio_`/`uf_id` resolvidos para o nome do município e a sigla da UF, cobrindo os 185 municípios de Pernambuco); do **CAR/SICAR** (`NOM_MUNICI` → Município, `COD_ESTADO` → UF — o CAR não tem CIR/Matrícula/nome do imóvel, então esses ficam em branco mesmo, editáveis). O memorial gerado ganhou um campo "Fonte do polígono" na caixa de identificação, citando automaticamente se o polígono é "Certificado pelo SIGEF", "Declarado no CAR", ou (quando a camada de origem não bate com nenhum dos dois esquemas) "Indicado pela equipe do INCRA".
- Cabeçalho do memorial descritivo gerado ganhou um campo "Localização", com um link direto para o centro do imóvel no Google Maps (calculado a partir do centroide do contorno externo) — permite a qualquer pessoa localizar o imóvel rapidamente pelo navegador, sem precisar de QGIS ou Google Earth.
- Croqui do memorial gerado passa a usar sempre uma imagem de satélite (Esri World Imagery) de fundo (baixada na hora, precisa de internet), mostrando só o(s) polígono(s) do imóvel por cima, de forma translúcida — não depende mais do que estiver visível no canvas do QGIS, evitando que outras camadas do projeto apareçam no croqui por engano. Se não houver internet no momento de gerar o PDF, o croqui simplesmente fica sem imagem de fundo, sem travar a geração.
- Corrigido o croqui aparecendo com o aviso cinza "Map data not available" da Esri em vez da imagem de satélite, em propriedades pequenas — o memorial pedia a imagem num zoom (19) mais fechado do que a cobertura disponível em muitas áreas rurais permite. Reduzido para zoom 17 (cobertura bem mais confiável) e aumentada a margem ao redor do polígono no croqui, para não ficar tão perto do limite.
- Legenda do datum ("Datum: SIRGAS2000") e crédito da imagem de satélite ("Esri, Maxar, Earthstar Geographics e comunidade GIS", exigido pelos termos de uso do provedor) movidos para logo abaixo do croqui, em vez de sobrepostos à imagem — ficam sempre sobre fundo branco, sem risco de se perderem em cima de um trecho escuro da imagem.
- Rótulo "N" da seta de norte (que continua sobre a imagem) ganhou um contorno branco mais forte ao redor do texto, para continuar bem legível em qualquer trecho da imagem de satélite.
- Corrigido "Município sede: - - PE" no cabeçalho quando só a UF estava preenchida (sem o nome do município) — agora mostra só "-".
- Lista de coordenadas geográficas do memorial gerado passa a ser organizada em até 4 colunas por página, calculadas para nunca invadir a faixa verde do rodapé — antes, memoriais com muitos vértices tinham as coordenadas cortadas/sobrepostas pelo rodapé. Quando não cabem todas numa página, o memorial continua automaticamente em página(s) extras ("COORDENADAS GEOGRÁFICAS (continuação)"), cada uma com sua própria faixa de rodapé.
- Seta de norte do croqui substituída por um ícone vetorial (o mesmo usado nativamente pelo QGIS), em vez do texto "N ↑" simples.
- Canto do croqui agora mostra "SIRGAS2000" em vez de "EPSG:4674", mais reconhecível para quem não trabalha com SIG.
- Texto de aviso legal do rodapé do memorial atualizado para deixar claro que o documento foi construído a partir de interpretação de informações documentais e de bancos de dados públicos geográficos (ou que é um polígono já declarado em uma das bases públicas), e que a realidade em campo pode ser diferente.
- Título "MEMORIAL DESCRITIVO" do cabeçalho com fonte maior, e a caixa de identificação do imóvel com mais espaçamento entre as linhas, aproveitando o espaço que sobrou depois de retirar a seção de municípios abrangidos.
- Removida a seção "MUNICÍPIOS ABRANGIDOS" do memorial gerado — o plugin não tem competência para afirmar quais municípios um imóvel abrange (essa informação é dos órgãos estaduais).
- Removido o cabeçalho "P;Y;X" repetido em cada coluna da lista de coordenadas geográficas — informação redundante, já que o próprio plugin identifica os campos automaticamente.
- Nome do arquivo PDF do memorial agora é sugerido automaticamente como `memorial_informativo_<nome do imóvel>.pdf` ao gerar (ainda pode ser alterado na hora de salvar).
- Texto da caixa de identificação do imóvel deixou de ficar colado nas bordas do quadro — agora tem uma margem interna de respiro em todos os lados.
- Aba "Memorial Manual" renomeada para "Memorial Genérico" (mais claro que ela serve para qualquer memorial fora do padrão Coleta Rural, não só entrada manual de texto).
- Janela do plugin ajustada para 445px de largura — o suficiente para caber os nomes das 4 abas sem cortar nenhum título (a tira de abas precisa de pelo menos 421px), sem sobrar uma faixa grande de espaço em branco do lado direito como acontecia com a largura anterior (500px), já que o conteúdo das abas em si usa no máximo ~380px.
- Campos "CIR" (com máscara) e "Matrícula" (texto livre) também na aba "Memorial Coleta Rural" (a primeira aba), para preencher antes de salvar — evita precisar editar a camada depois só para completar esses dois campos.
- Suporte ao datum WGS84 (além de SIRGAS2000 e SAD69) para coordenadas UTM — reconhecido automaticamente no texto do memorial ou disponível para seleção manual, zonas 18S a 25S.
- Aviso automático quando um vértice fica muito mais distante dos vizinhos do que o resto do perímetro — sinal comum de um dígito perdido ou trocado numa das coordenadas do memorial de origem. Não bloqueia o salvamento (algumas propriedades genuinamente têm um lado bem mais comprido), só chama atenção para conferir antes de salvar.
- Botão "Anexar KML/GeoJSON/SHP/DXF" na aba Memorial Manual: lê o polígono do imóvel diretamente de um arquivo de geometria, em vez de depender de texto. KML e GeoJSON são reconhecidos automaticamente em WGS84 (sem perguntar nada); Shapefile usa o sistema de referência do próprio arquivo (`.prj`); DXF (que normalmente não guarda sistema de referência nenhum) pede o fuso e o datum, como já acontece com coordenadas UTM digitadas ou coladas. Também procura o nome do imóvel no arquivo (campo "Name"/"nome") para pré-preencher o campo Imóvel. Funciona mesmo quando o arquivo tem várias camadas/pastas internas (ex.: um KML do Google Earth com pontos e polígono em pastas separadas) — o plugin procura em todas até achar um polígono (ou uma linha fechada, comum em contornos de DXF).
- A biblioteca `pypdf` (leitura de PDF) passa a ser embutida dentro do próprio plugin (`libs/pypdf`). Quem baixar o plugin não precisa mais instalar nada manualmente pelo Console Python — o plugin usa a cópia do sistema se ela já existir, e só recorre à embutida como reserva.
- Nova aba "Memorial Manual" para importar memoriais descritivos que não vêm do sistema Coleta Rural: anexar o PDF (se tiver texto extraível) ou colar o texto já com OCR feito externamente (sem OCR embutido no plugin).
- Extração automática dos dados do imóvel (Imóvel, Município, Declarante, CPF/CNPJ) no Memorial Manual, reconhecendo rótulos alternativos (ex.: "PROPRIETÁRIO" para Declarante) e sem diferenciar maiúsculas/minúsculas, com campos editáveis para corrigir ou completar manualmente.
- Reconhecimento automático de coordenadas em texto corrido (copiado de PDF, com quebras de linha no meio dos números e outras medidas misturadas no texto), descartando números que não parecem coordenadas (medidas de distância, numeração de vértice).
- Correção automática da ordem (longitude/latitude) e do sinal negativo das coordenadas geográficas, independente de como o memorial as escreveu — sem exigir nenhuma escolha manual do operador.
- Tabela de conferência com as coordenadas já identificadas (Longitude, Latitude), exibida antes de visualizar ou salvar.
- Coordenada UTM identificada automaticamente pede apenas a confirmação do fuso e do datum (SIRGAS2000 padrão, ou SAD69), zonas 18S a 25S.
- Área do imóvel calculada automaticamente a partir do polígono das coordenadas declaradas (cálculo geodésico, em hectares), em vez de depender do valor/unidade informados no texto do memorial (que variam entre m² e ha conforme a fonte).
- Nova aba "Zoom Rápido": digite uma coordenada e clique em "Visualizar Localização" para centralizar e aproximar o mapa no local, com um marcador temporário — nenhuma camada é criada. Coordenada geográfica zoom direto; coordenada plana (UTM) exibe automaticamente os campos de fuso e datum.
- Tela principal reorganizada em abas (Memorial Coleta Rural / Memorial Manual / Zoom Rápido), com a camada de destino e o botão Configurações sempre visíveis no topo, independente da aba ativa.
- Reconhecimento de coordenadas geográficas em graus-minutos-segundos com rótulo explícito (ex.: `Longitude: -37°19'23,169", Latitude: -08°44'11,621"`), formato comum em memoriais de georreferenciamento SIGEF/INCRA — com prioridade sobre a heurística por magnitude, já que o rótulo elimina qualquer ambiguidade.
- Reconhecimento de coordenadas UTM com rótulo explícito N/E em qualquer ordem (ex.: `N=9.403.477,770 m. e E=1.470.385,437 m.`), formato usado em modelos oficiais de memorial topográfico (confirmado no modelo da Prefeitura de Goiânia).
- Detecção automática de qual valor é Este e qual é Norte num par UTM (pela magnitude — Norte é sempre um número bem maior no hemisfério sul brasileiro), já que memoriais diferentes escrevem em ordens diferentes.
- Nova coluna "UF" na camada padrão (`camada_padrao`) e no Memorial Manual, separada do Município — inclusive quando vêm juntos no texto original (ex.: "Belo Jardim - PE - BR" vira Município "Belo Jardim" e UF "PE") — já que o plugin atende o Brasil todo.
- Reconhecimento de coordenadas UTM listadas em duas colunas separadas (uma lista só de Norte, rótulo "N(Y)" ou "Norte", seguida de uma lista só de Este, rótulo "E(X)" ou "Este"), formato comum ao copiar uma tabela de coordenadas de uma planta via OCR — os valores são pareados por posição (1º Norte com 1º Este, e assim por diante). Se as duas listas tiverem quantidades diferentes, mostra um aviso específico em vez de tentar adivinhar o pareamento.
- Recuperação de coordenadas em tabela mesmo quando o OCR confunde a vírgula decimal com um ponto (formando um grupo de milhar incompleto) ou com um espaço, ou a apaga — o valor é reconstruído a partir dos dígitos da linha, assumindo 2 casas decimais (padrão de coordenadas UTM topográficas), sem depender de interpretar a pontuação.
- Detecção automática do fuso e do datum quando informados no texto do memorial (ex.: "SIRGAS 2000, projeção UTM, fuso 25S"), evitando usar por engano o fuso deixado de um memorial anterior.
- Quando o memorial não informa fuso nem datum no texto, o plugin agora pergunta explicitamente ao operador em vez de usar silenciosamente o que já estiver selecionado.
- Trocar o fuso ou o datum no combo da aba Memorial Manual agora recalcula a tabela/área/mapa na hora, sem precisar clicar em "Extrair Dados do Texto" de novo.
- Reconhecimento de cabeçalhos em formato de tabela sem dois-pontos entre rótulo e valor (ex.: "PROPRIETÁRIO GMG PATRIMONIAL LTDA.", "CNPJ 17.010.167/0001-36"), comum em memoriais topográficos de demarcação.
- Reconhecimento de "LOCALIZAÇÃO" como alternativa a "MUNICÍPIO" quando o memorial não tem um campo de município dedicado.
- Campos "CIR" (com máscara `xxx.xxx.xxx.xxx-x`) e "Matrícula" (texto livre, permitindo registrar a união de mais de uma matrícula) na aba Memorial Manual, com reconhecimento automático do CIR no texto colado quando presente.
- Botão "Limpar" na aba Memorial Manual, para reiniciar o formulário (texto, campos, tabela de coordenadas e fuso/datum) sem precisar salvar antes.
- Aba Zoom Rápido reformulada: campos separados e rotulados para Longitude/Latitude (ou Este/Norte, ao marcar "Coordenada UTM"), eliminando qualquer dúvida sobre a ordem de digitação. Ao marcar UTM, os campos de fuso e datum aparecem automaticamente.
- Botão "Configurações" renomeado para "Gerir Camadas".
- Campo "CPF/CNPJ" da aba Memorial Manual agora formata automaticamente enquanto o operador digita, alternando sozinho entre a máscara de CPF (`000.000.000-00`) e a de CNPJ (`00.000.000/0000-00`) assim que a quantidade de dígitos ultrapassa 11 — sem precisar escolher manualmente qual dos dois está sendo digitado.

### Corrigido

- Corrigido um caso em que salvar um imóvel numa camada de destino sem o campo "Área" causava falha e desfazia a importação em vez de simplesmente ignorar esse campo opcional, como já acontece com os demais campos.
- Corrigido o botão "Configurações" (camadas permitidas / criação da camada padrão), que ficava fora da área visível da janela em telas menores.
- Corrigido o reconhecimento de números com separador de milhar em ponto (padrão brasileiro, ex.: `9.403.477,770`), que antes eram fatiados incorretamente em pedaços menores, corrompendo as coordenadas.
- Corrigida a extração de campos do memorial manual (Imóvel, Município, Declarante, CPF/CNPJ) quando dois rótulos aparecem na mesma linha (ex.: "Município: Caruaru UF: Pernambuco" não capturava mais só "Caruaru").
- Corrigido um caso em que o polígono era georreferenciado no fuso UTM errado (deslocando o imóvel para muito longe do local real) quando o fuso informado no memorial não era detectado e o combo ficava com um valor desatualizado.
- Corrigida a separação de Município/UF para não quebrar nomes de local com hífen no meio (ex.: "Lugar Carapatós, KM-84, Gravatá - PE").
- Corrigido o reconhecimento de coordenadas rotuladas "N.../E..." quando o OCR gruda a palavra anterior no rótulo sem espaço (ex.: "coordenadasE:823,45..."), que antes fazia esses vértices serem perdidos silenciosamente.
- Reordenada a prioridade de reconhecimento de coordenadas no texto colado: formatos com rótulo explícito por vértice (Longitude/Latitude, N/E) agora são tentados antes da tabela em duas colunas, que é mais sensível a se confundir com lixo de OCR de gráficos/imagens presentes no PDF.
- Corrigido o reconhecimento do fuso/datum quando o OCR usa travessão (ex.: "fuso - 25", "WGS—84") em vez de hífen comum.
- Corrigido um erro ("wrapped C/C++ object ... has been deleted") que podia travar a visualização/o zoom quando a camada de pré-visualização ou o marcador do Zoom Rápido eram removidos manualmente (ex.: pelo painel de Camadas) entre um clique e outro.
- Corrigido o reconhecimento de coordenadas "Longitude:/Latitude:" quando o OCR deixa aspas soltas entre o valor e a vírgula/rótulo seguinte (ex.: `Longitude: -37.592643", Latitude: -8.927391"`), que antes fazia esses vértices serem perdidos silenciosamente.
- Corrigido um falso positivo no reconhecimento de tabela de coordenadas em duas colunas: a palavra "norte"/"este" usada como direção cardinal em frases comuns do memorial (ex.: "segue ao norte confrontando com...") não é mais confundida com o cabeçalho de uma tabela — só linhas curtas (até 40 caracteres) são consideradas cabeçalho.
- Corrigida a leitura de tabela de coordenadas em duas colunas quando os valores já vêm limpos e com muitas casas decimais separadas por vírgula (ex.: `9075203,806160292`, comum em tabelas exportadas de levantamento topográfico): antes, o reconstrutor de números (pensado para valores corrompidos pelo OCR) truncava esses valores assumindo sempre 2 casas decimais, corrompendo a coordenada inteira.
- Corrigido um caso em que colar uma tabela de coordenadas com as colunas Norte e Este lado a lado (em vez de duas listas separadas) — por exemplo, depois de reorganizar manualmente no LibreOffice Calc e colar com ";" entre os valores — travava a importação com um erro de "quantidade de coordenadas diferente entre as colunas" mesmo quando o formato genérico conseguiria reconhecer as coordenadas normalmente; agora esse formato lado a lado é identificado e repassado para o reconhecimento genérico em vez de travar.

---

## [1.1.0] - 2026-08-01

### Adicionado

- Botão "Incluir Camada Padrão" na tela de Configurações, para criação da camada padrão do Coleta Rural.
- Criação da camada padrão em formato Shapefile ou GeoPackage, à escolha do usuário.
- Seleção da pasta de destino da camada padrão, sugerindo automaticamente a pasta do projeto QGIS atual.
- Camada padrão criada já com os campos e o sistema de referência (SIRGAS 2000) utilizados pelo Coleta Rural.
- Camada padrão criada é adicionada automaticamente ao projeto e marcada na lista de camadas permitidas.
- Exibição em negrito das camadas marcadas na lista de Configurações.

### Corrigido

- Ordem dos campos da camada padrão ajustada (CPF/CNPJ reposicionado antes de OBS e Área), para manter compatibilidade com as camadas já utilizadas em produção.

---

## [1.0.1] - 2026-07-18

### Corrigido

- Removidos blocos try/except/pass identificados pelos verificadores de segurança do repositório oficial do QGIS.
- Melhor tratamento de exceções durante remoção de preview, processamento de vértices e rollback de alterações.


### Adicionado

- Criação do plugin Coleta Rural para QGIS.
- Interface gráfica para importação de memoriais em PDF.
- Seleção de arquivo PDF através de navegador de arquivos.
- Leitura automática de memoriais descritivos gerados pelo sistema Coleta Rural.
- Extração automática dos seguintes dados:
  - Imóvel;
  - Município;
  - Declarante;
  - CPF/CNPJ;
  - Área.
- Extração automática das coordenadas dos vértices do imóvel.
- Geração automática de geometria poligonal.
- Pré-visualização do imóvel no mapa.
- Zoom automático para o imóvel carregado.
- Configuração de transparência para a camada temporária de visualização.
- Criação da janela de Configurações.
- Seleção das camadas autorizadas para importação.
- Persistência das configurações utilizando QgsSettings.
- Atualização automática da lista de camadas permitidas.
- ComboBox dinâmico exibindo apenas as camadas autorizadas.

### Implementado

- Salvamento automático da geometria em camada vetorial selecionada.
- Criação automática de feições.
- Preenchimento automático dos atributos:
  - CIR;
  - Imóvel;
  - Matrícula;
  - Município;
  - Declarante;
  - CPF/CNPJ;
  - OBS;
  - Área.
- Commit automático após inserção da feição.
- Limpeza automática do formulário após o salvamento.
- Remoção automática da camada temporária de visualização após importação.

### Corrigido

- Correção da leitura de coordenadas do memorial.
- Correção da atualização da lista de camadas permitidas.
- Correção de problemas de identação dos métodos da classe.
- Correção da remoção de camadas temporárias já destruídas pelo QGIS.
- Correção da compatibilidade entre tipos de dados dos atributos e campos da camada.
- Conversão da área para tipo numérico compatível com campos Double.
- Ajustes para gravação correta do CPF/CNPJ.

### Melhorias

- Interface simplificada para o fluxo de importação.
- Barra de ferramentas exclusiva do plugin.
- Melhor tratamento de exceções.
- Organização do código-fonte.
- Melhor experiência de uso para analistas da Governança de Terras.

---

## Créditos

**Desenvolvedor**

Dihêgo Augusto Gomes Malvim de Barros  
Assistente Técnico da Governança de Terras  
INCRA Pernambuco

**Projeto**

Coleta Rural

**Versão atual**

1.2.3