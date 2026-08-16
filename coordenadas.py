# -*- coding: utf-8 -*-

import math
import re
import statistics

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsDistanceArea,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsWkbTypes
)


PADRAO_NUMERO = re.compile(
    r"-?\d{1,3}(?:\.\d{3}(?!\d))+(?:,\d+)?"  # 1.234.567,89 (milhar+decimal)
    r"|-?\d+,\d+"                            # 23,169 (decimal com vírgula)
    r"|-?\d+\.\d+"                           # 8.047123 (decimal com ponto)
    r"|-?\d+"                                # inteiro puro
)

CRS_GEOGRAFICO = "EPSG:4674"

# Zonas UTM que cobrem o território brasileiro (hemisfério sul).
# Códigos EPSG conferidos na base oficial de CRS do QGIS (proj.db),
# usando sempre a versão não depreciada de cada zona.
EPSG_UTM_SUL = {
    "SIRGAS2000": {
        18: 31978, 19: 31979, 20: 31980, 21: 31981,
        22: 31982, 23: 31983, 24: 31984, 25: 31985,
    },
    "SAD69": {
        18: 29188, 19: 29189, 20: 29190, 21: 29191,
        22: 29192, 23: 29193, 24: 29194, 25: 29195,
    },
    "WGS84": {
        18: 32718, 19: 32719, 20: 32720, 21: 32721,
        22: 32722, 23: 32723, 24: 32724, 25: 32725,
    },
}

# CRS geográfico (graus decimais) de cada datum suportado — mesmos três
# datuns já oferecidos para UTM (EPSG_UTM_SUL), agora também disponíveis
# para coordenadas geográficas (Longitude/Latitude) soltas no texto.
# Necessário porque memoriais anteriores a 2005 (quando o Brasil adotou
# SIRGAS2000 como referência oficial) costumam declarar a coordenada em
# SAD69 — tratar esse valor como se já fosse SIRGAS2000 sem transformar
# desloca o polígono na casa de dezenas de metros.
EPSG_GEOGRAFICO_POR_DATUM = {
    "SIRGAS2000": 4674,
    "SAD69": 4618,
    "WGS84": 4326,
}


def transformar_pontos_geograficos(pontos, datum_origem):
    """Transforma uma lista de QgsPointXY (longitude, latitude) do datum
    geográfico informado para EPSG:4674 (SIRGAS2000) — usado quando o
    memorial declara (ou o operador confirma) que as coordenadas
    geográficas extraídas estão num datum diferente do atual."""

    if datum_origem == "SIRGAS2000":
        return list(pontos)

    codigo = EPSG_GEOGRAFICO_POR_DATUM.get(datum_origem)

    if codigo is None:
        raise ValueError(f"Datum geográfico não suportado: {datum_origem}")

    crs_origem = QgsCoordinateReferenceSystem.fromEpsgId(codigo)
    crs_destino = QgsCoordinateReferenceSystem(CRS_GEOGRAFICO)

    return transformar_pontos(pontos, crs_origem, crs_destino)

def _texto_numero_para_float(texto_numero):
    """Converte um token numérico (já capturado por PADRAO_NUMERO) para
    float, tratando tanto o padrão brasileiro com separador de milhar em
    ponto (ex.: '9.403.477,770') quanto decimal simples com vírgula ou
    ponto (ex.: '23,169' ou '8.047123')."""

    texto_numero = texto_numero.strip()

    if "," in texto_numero:

        parte_inteira, parte_decimal = texto_numero.split(",", 1)
        parte_inteira = parte_inteira.replace(".", "")

        return float(f"{parte_inteira}.{parte_decimal}")

    return float(texto_numero)


def extrair_pares_numericos(texto):
    """Extrai um par de números de cada linha do texto, tolerando rótulos
    (P1, V-01...) e separadores variados (;, tab, espaço, vírgula), com
    milhar em ponto e/ou decimal em vírgula ou ponto. Usa os dois ÚLTIMOS
    números da linha, para ignorar rótulos numéricos no início. Retorna os
    pares na ordem em que aparecem no texto, sem interpretar o que cada
    valor representa."""

    pares = []

    for linha in texto.splitlines():

        linha = linha.strip()

        if not linha:
            continue

        numeros = PADRAO_NUMERO.findall(linha)

        if len(numeros) < 2:
            continue

        try:

            a = _texto_numero_para_float(numeros[-2])
            b = _texto_numero_para_float(numeros[-1])

        except ValueError:
            continue

        pares.append((a, b))

    return pares


def _eh_candidato_coordenada(token):
    """Decide se um token numérico bruto (texto, antes da conversão para
    float) é plausível como coordenada — descarta números que na prática
    costumam ser rótulo de vértice (P-01) ou medida de distância/área
    (79,29m), comuns misturados ao texto corrido de um memorial descritivo
    (PDF com texto corrido, às vezes até quebrando o próprio número no
    meio da linha). Reconhece separador de milhar em ponto."""

    if "," in token:
        parte_inteira, parte_decimal = token.split(",", 1)
        parte_inteira = parte_inteira.replace(".", "").lstrip("-")
    elif "." in token:
        parte_inteira, parte_decimal = token.split(".", 1)
        parte_inteira = parte_inteira.lstrip("-")
    else:
        parte_inteira, parte_decimal = token.lstrip("-"), ""

    decimais_suficientes = len(parte_decimal) >= 3
    parte_grande = len(parte_inteira) >= 5

    return decimais_suficientes or parte_grande


def extrair_pares_numericos_texto_livre(texto):
    """Como extrair_pares_numericos, mas mais rigorosa: descarta números que
    não parecem coordenadas (medidas de distância, numeração de vértice)
    antes de formar os pares. Pensada para texto corrido/copiado de PDF
    (Memorial Manual), onde números de todo tipo aparecem misturados."""

    pares = []

    for linha in texto.splitlines():

        linha = linha.strip()

        if not linha:
            continue

        numeros = [
            numero
            for numero in PADRAO_NUMERO.findall(linha)
            if _eh_candidato_coordenada(numero)
        ]

        if len(numeros) < 2:
            continue

        try:

            a = _texto_numero_para_float(numeros[-2])
            b = _texto_numero_para_float(numeros[-1])

        except ValueError:
            continue

        pares.append((a, b))

    return pares


# Valor em graus-minutos-segundos, ex.: -37°19'23,169" (tolera espaços e
# quebras de linha entre as partes, comuns em texto copiado de PDF).
_VALOR_GMS = (
    r"-?\s*\d{1,3}\s*°\s*\d{1,2}\s*['′]\s*\d{1,2}(?:[.,]\d+)?\s*[\"″]"
)

# Valor em graus-minutos-segundos escrito por extenso, com as palavras
# "GRAUS"/"MINUTOS"/"SEGUNDOS" em vez dos símbolos °/'/" — comum em
# memoriais antigos (ex.: aerofotogramétricos) de antes da digitação com
# esses símbolos ser padrão. Aceita "SEGUNDO" no singular (comum quando o
# valor é "01 segundo").
_PADRAO_GMS_POR_EXTENSO = re.compile(
    r"(\d{1,3})\s*graus\s*(\d{1,2})\s*minutos?\s*"
    r"(\d{1,2}(?:[.,]\d+)?)\s*segundos?",
    re.IGNORECASE
)

# Hemisfério escrito por extenso (Sul/Norte/Leste/Oeste) logo após um
# valor em graus-minutos-segundos — só troca a palavra nesse contexto
# (imediatamente após um valor GMS) para não confundir com outros usos
# comuns dessas mesmas palavras no memorial (direção cardinal em prosa,
# ex.: "confronta ao sul com...").
_HEMISFERIO_POR_EXTENSO = {"sul": "S", "norte": "N", "leste": "E", "oeste": "O"}

_PADRAO_GMS_HEMISFERIO_POR_EXTENSO = re.compile(
    rf"({_VALOR_GMS})\s*(sul|norte|leste|oeste)\b",
    re.IGNORECASE
)


def normalizar_gms_por_extenso(texto):
    """Converte coordenadas em graus-minutos-segundos escritas por
    extenso (ex.: "8 GRAUS 37 MINUTOS 43,36 SEGUNDOS SUL") para a mesma
    notação com símbolos usada pelo resto deste módulo (ex.:
    "8°37'43,36" S") — permite que qualquer extrator baseado em °/'/"
    (rotulado, estrutural por hemisfério, etc.) reconheça esse formato
    sem precisar de nenhuma lógica própria. Chamar antes de qualquer
    tentativa de extração de coordenadas."""

    texto = _PADRAO_GMS_POR_EXTENSO.sub(
        lambda encontro: (
            f"{encontro.group(1)}°{encontro.group(2)}'{encontro.group(3)}\""
        ),
        texto
    )

    texto = _PADRAO_GMS_HEMISFERIO_POR_EXTENSO.sub(
        lambda encontro: (
            f"{encontro.group(1)} "
            f"{_HEMISFERIO_POR_EXTENSO[encontro.group(2).lower()]}"
        ),
        texto
    )

    return texto

# Valor decimal simples (fallback quando o memorial usa graus decimais
# mesmo dentro do formato rotulado "Longitude: ...; Latitude: ...").
_VALOR_DECIMAL = r"-?\s*\d{1,3}(?:[.,]\d+)?"

_VALOR_COORDENADA = rf"(?:{_VALOR_GMS}|{_VALOR_DECIMAL})"

PADRAO_PAR_ROTULADO = re.compile(
    # entre o valor da longitude e o rótulo "Latitude" tolera aspas soltas
    # que sobram do OCR (quando o memorial usa graus-minutos-segundos em
    # algum lugar, o OCR às vezes deixa um "”"/'"' perdido mesmo em
    # valores decimais), além de vírgula/ponto-e-vírgula e espaços
    rf"Longitude\s*:\s*({_VALOR_COORDENADA})[\"'′″;,\s]*"
    rf"Latitude\s*:\s*({_VALOR_COORDENADA})",
    re.IGNORECASE
)


def valor_coordenada_para_decimal(texto_valor):
    """Converte um valor de coordenada em graus-minutos-segundos
    (ex.: -37°19'23,169") ou em graus decimais (ex.: -37,323) para graus
    decimais."""

    texto_valor = texto_valor.strip()

    gms = re.match(
        r"(-?)\s*(\d{1,3})\s*°\s*(\d{1,2})\s*['′]\s*(\d{1,2}(?:[.,]\d+)?)\s*[\"″]",
        texto_valor
    )

    if gms:

        sinal, graus, minutos, segundos = gms.groups()

        valor = (
            float(graus)
            + float(minutos) / 60
            + float(segundos.replace(",", ".")) / 3600
        )

        return -valor if sinal == "-" else valor

    decimal = re.match(r"-?\s*\d{1,3}(?:[.,]\d+)?", texto_valor)

    if decimal:
        return float(decimal.group(0).replace(" ", "").replace(",", "."))

    raise ValueError(f"Não foi possível interpretar a coordenada: {texto_valor!r}")


def extrair_pares_rotulados(texto):
    """Procura pares explicitamente rotulados 'Longitude: ...; Latitude: ...'
    no texto — formato comum em memoriais de georreferenciamento do
    SIGEF/INCRA, em graus-minutos-segundos ou decimais. Tolerante a quebras
    de linha no meio do valor (comum em texto copiado de PDF). Como a
    ordem já vem explícita no rótulo, não há necessidade de adivinhar pela
    magnitude — retorna diretamente pares (longitude, latitude) com o
    sinal já como escrito no memorial."""

    texto_achatado = re.sub(r"\s+", " ", texto)

    pares = []

    for encontro in PADRAO_PAR_ROTULADO.finditer(texto_achatado):

        try:

            longitude = valor_coordenada_para_decimal(encontro.group(1))
            latitude = valor_coordenada_para_decimal(encontro.group(2))

        except ValueError:
            continue

        pares.append((longitude, latitude))

    return pares


def pontos_rotulados_para_vertices_4674(pares):
    """Converte pares (longitude, latitude) já identificados via rótulos
    explícitos no texto (ver extrair_pares_rotulados) para uma lista de
    QgsPointXY em EPSG:4674 — não precisa de transformação, os valores já
    estão em graus decimais SIRGAS2000/WGS84."""

    return [QgsPointXY(longitude, latitude) for longitude, latitude in pares]


# Coordenada em graus-minutos-segundos identificada só pela própria
# estrutura do valor (°'") seguida de uma letra de hemisfério (S/N para
# latitude, W/O/E para longitude) — sem depender de nenhuma frase ou
# rótulo específico ao redor. É a letra de hemisfério que torna esse
# reconhecimento seguro: um azimute também é escrito em graus-minutos-
# segundos (ex.: "164°27'16""), mas nunca é seguido de uma letra de
# hemisfério — só uma coordenada geográfica de verdade tem essa letra
# logo depois do valor, então não há risco de confundir os dois.
#
# A letra de hemisfério é sempre exigida em maiúscula (sem
# re.IGNORECASE): memoriais reais sempre escrevem S/N/E/O/W maiúsculo, e
# tratar minúsculo aqui faria o conectivo "e" ("e distância", "e
# assim..."), muito comum logo depois de um azimute, ser confundido com a
# letra de hemisfério "E" (Este) — corrompendo o pareamento.
_PADRAO_GMS_COM_HEMISFERIO = re.compile(
    rf"({_VALOR_GMS})\s*([NSEOW])\b"
)


def extrair_pares_gms_com_hemisferio(texto):
    """Procura coordenadas em graus-minutos-segundos pela própria estrutura
    do valor (°'") seguida de uma letra de hemisfério (S/N/E/O/W) — em vez
    de depender de uma frase ou rótulo específico ao redor (ex.:
    "Longitude:", "de coordenadas ... S e ... W"). Reconhece qualquer
    redação que coloque a letra de hemisfério logo após o valor: "...
    -8°11'09,909" S e -35°46'12,804" W...", "...-8°11'09,909"S,
    -35°46'12,804"W...", ou qualquer outra pontuação/conector entre os
    dois valores — sem a letra de hemisfério, esse formato não seria
    reconhecido por nenhum extrator específico e cairia no reconhecimento
    genérico de texto livre, que pode confundir fragmentos do próprio
    valor (ex.: os segundos de uma coordenada) com uma coordenada inteira.

    A letra de hemisfério já diz sozinha qual eixo é qual (S/N ⇒
    latitude, W/O/E ⇒ longitude) e qual o sinal (S/W/O negativos, N/E
    positivos) — não depende da ordem em que o memorial escreveu
    latitude/longitude. Retorna pares (longitude, latitude), na mesma
    convenção das demais funções deste módulo."""

    texto_achatado = re.sub(r"\s+", " ", texto)

    valores = []

    for encontro in _PADRAO_GMS_COM_HEMISFERIO.finditer(texto_achatado):

        try:
            valor = abs(valor_coordenada_para_decimal(encontro.group(1)))
        except ValueError:
            continue

        hemisferio = encontro.group(2).upper()

        if hemisferio in ("S", "N"):
            eixo = "latitude"
        else:
            eixo = "longitude"

        sinal_positivo = hemisferio in ("N", "E")

        valores.append((eixo, valor if sinal_positivo else -valor))

    pares = []
    latitude_pendente = None
    longitude_pendente = None

    for eixo, valor in valores:

        if eixo == "latitude":
            latitude_pendente = valor
        else:
            longitude_pendente = valor

        if latitude_pendente is not None and longitude_pendente is not None:
            pares.append((longitude_pendente, latitude_pendente))
            latitude_pendente = None
            longitude_pendente = None

    return pares


# Par de coordenadas UTM rotuladas com N e E, em qualquer ordem — comum em
# memoriais topográficos (ex.: modelo oficial da Prefeitura de Goiânia:
# "N=9.403.477,770 m. e E=1.470.385,437 m."). Tolerante a "N"/"Norte" e
# "E"/"Este", com ou sem "=", ":" ou espaço, e a quebra de linha entre os
# dois valores (texto é achatado antes da busca).
PADRAO_PAR_UTM_ROTULADO = re.compile(
    # sem \b antes de N/E: o OCR de PDF às vezes gruda a palavra anterior
    # no rótulo sem espaço (ex.: "coordenadasE:823...") — nesse caso "E"
    # fica colado a uma letra (sem fronteira de palavra), então o \b
    # falharia. Quem garante que não é um falso positivo é a exigência de
    # um número com formatação válida logo em seguida.
    r"N(?:orte)?\s*[=:]?\s*(" + PADRAO_NUMERO.pattern + r")\s*"
    r"m?\.?\s*[,;]?\s*e?\s*"
    r"E(?:ste)?\s*[=:]?\s*(" + PADRAO_NUMERO.pattern + r")"
    r"|"
    r"E(?:ste)?\s*[=:]?\s*(" + PADRAO_NUMERO.pattern + r")\s*"
    r"m?\.?\s*[,;]?\s*e?\s*"
    r"N(?:orte)?\s*[=:]?\s*(" + PADRAO_NUMERO.pattern + r")",
    re.IGNORECASE
)


def extrair_pares_utm_rotulados(texto):
    """Procura pares de coordenadas UTM explicitamente rotuladas com N/Norte
    e E/Este, em qualquer ordem. Como já sabemos qual valor é Norte e qual
    é Este pela própria letra do rótulo (não pela magnitude), retorna
    diretamente pares (este, norte), tolerante a quebra de linha entre os
    dois valores (comum em texto copiado de PDF)."""

    texto_achatado = re.sub(r"\s+", " ", texto)

    pares = []

    for encontro in PADRAO_PAR_UTM_ROTULADO.finditer(texto_achatado):

        if encontro.group(1) is not None:
            norte_str, este_str = encontro.group(1), encontro.group(2)
        else:
            este_str, norte_str = encontro.group(3), encontro.group(4)

        try:

            norte = _texto_numero_para_float(norte_str)
            este = _texto_numero_para_float(este_str)

        except ValueError:
            continue

        pares.append((este, norte))

    return pares


_ROTULO_BLOCO_NORTE = re.compile(r"\bN\s*\(\s*Y\s*\)|\bNORTE\b", re.IGNORECASE)
_ROTULO_BLOCO_ESTE = re.compile(r"\bE\s*\(\s*X\s*\)|\bESTE\b", re.IGNORECASE)


# rótulo de vértice, ex.: "V01", "V-01", "V 01", "V - 01" — tolera
# qualquer combinação de espaços/hífen entre a letra e o número, comuns
# em memoriais digitados manualmente
_ROTULO_VERTICE_V = r"V\s*-?\s*\d+"

# memorial em formato de poligonal (traverse): um vértice inicial com
# coordenadas UTM conhecidas, seguido de uma tabela de segmentos
# azimute/distância entre vértices — formato topográfico tradicional,
# em vez de listar a coordenada de cada vértice diretamente
_PADRAO_INICIO_POLIGONAL = re.compile(
    r"v[eé]rtice\s+(" + _ROTULO_VERTICE_V + r")\D{0,60}?"
    r"E(?:ste)?\s*=\s*(" + PADRAO_NUMERO.pattern + r")\D{0,20}?"
    r"N(?:orte)?\s*=\s*(" + PADRAO_NUMERO.pattern + r")",
    re.IGNORECASE
)

# linha da tabela de segmentos, ex.: "V01–V02 53,4703 17,026 V02"
# (origem–destino, azimute em graus decimais, distância em metros,
# vértice de destino repetido) — tolera hífen/travessão entre os
# vértices do segmento, comuns em OCR
_PADRAO_SEGMENTO_AZIMUTE = re.compile(
    r"(V[\s\-]?\d+)\s*[\-–—]\s*(V[\s\-]?\d+)\s+"
    r"(" + PADRAO_NUMERO.pattern + r")\s+"
    r"(" + PADRAO_NUMERO.pattern + r")\s+"
    r"(V[\s\-]?\d+)",
    re.IGNORECASE
)


def _normalizar_vertice_poligonal(texto_vertice):
    numero = re.sub(r"\D", "", texto_vertice)
    return f"V{int(numero):02d}" if numero else texto_vertice.strip().upper()


def _percorrer_poligonal(vertice_inicial, e_inicial, n_inicial, segmentos):
    """Calcula a coordenada UTM de cada vértice "andando" a partir do
    vértice inicial, segmento por segmento (convenção de azimute
    topográfico: medido no sentido horário a partir do Norte — por isso
    a componente Leste usa seno e a componente Norte usa cosseno).
    segmentos é uma lista de (origem, destino, azimute_graus, distancia),
    já normalizada para azimute (0–360° a partir do Norte) independente
    de o memorial original descrever o rumo por azimute ou por rumo
    quadrantal. Devolve [] se a sequência de vértices dos segmentos não
    bater com o vértice de origem esperado (não arrisca calcular uma
    poligonal com uma sequência inconsistente)."""

    posicoes = {vertice_inicial: (e_inicial, n_inicial)}
    pares = [(e_inicial, n_inicial)]
    vertice_atual = vertice_inicial

    for origem, destino, azimute, distancia in segmentos:

        if origem != vertice_atual:
            return []

        e_atual, n_atual = posicoes[vertice_atual]
        azimute_rad = math.radians(azimute)

        e_novo = e_atual + distancia * math.sin(azimute_rad)
        n_novo = n_atual + distancia * math.cos(azimute_rad)

        if destino == vertice_inicial:
            # fecha a poligonal de volta ao vértice inicial — não
            # adiciona de novo, o polígono já está completo
            break

        posicoes[destino] = (e_novo, n_novo)
        pares.append((e_novo, n_novo))
        vertice_atual = destino

    return pares


def calibrar_transformacao_planta(
    clique_inicio, clique_fim, azimute_conhecido, distancia_conhecida,
    coordenada_real_inicio
):
    """Calibra uma transformação de similaridade (translação + rotação +
    escala, sem espelhamento) entre a posição de cliques num desenho
    (planta/croqui exibido num QGraphicsScene, cujo "y" aumenta para
    BAIXO — convenção padrão de imagem/tela, com origem no canto
    superior esquerdo — ao contrário de um mapa de verdade, onde "y"
    aumenta para cima/Norte) e coordenadas reais — a partir de um único
    trecho já conhecido (ex.: o primeiro segmento de uma poligonal,
    cujo azimute e distância já vêm do texto do memorial).

    Por isso o "y" de cada clique é invertido (multiplicado por -1)
    antes de calcular qualquer azimute: sem essa inversão, a
    transformação resultante mistura rotação com espelhamento
    Leste-Oeste — o que "por acaso" acerta o próprio trecho de
    calibração (colinear com o eixo invertido), mas desenha o restante
    do polígono como uma imagem espelhada da planta real, girado numa
    orientação errada (ex.: uma planta alongada de Norte a Sul aparece
    "deitada", alongada de Leste a Oeste, quando desenhada sobre o
    mapa).

    clique_inicio, clique_fim: QgsPointXY dos dois cliques no desenho,
    marcando o início e o fim desse trecho conhecido.
    azimute_conhecido: azimute real do trecho, em graus (0–360, sentido
    horário a partir do Norte — mesma convenção do resto do módulo).
    distancia_conhecida: distância real do trecho, em metros.
    coordenada_real_inicio: (x, y) coordenada real (num sistema plano,
    ex.: UTM) do ponto onde clique_inicio foi marcado.

    Devolve uma função conversora(ponto_clicado) -> (x_real, y_real) que
    aplica essa transformação a qualquer outro clique no mesmo desenho —
    usada para "desenhar" o restante do polígono clicando na planta."""

    dx_desenho = clique_fim.x() - clique_inicio.x()
    dy_desenho = clique_fim.y() - clique_inicio.y()
    distancia_desenho = math.hypot(dx_desenho, dy_desenho)

    if distancia_desenho == 0:
        raise ValueError(
            "Os dois cliques do trecho de calibração não podem ser no "
            "mesmo ponto."
        )

    escala = distancia_conhecida / distancia_desenho

    # -dy_desenho: converte o "y" da tela (aumenta para baixo) para um
    # "y" que aumenta para o Norte, como o resto do módulo assume
    azimute_desenho = math.degrees(math.atan2(dx_desenho, -dy_desenho)) % 360
    rotacao = (azimute_conhecido - azimute_desenho) % 360

    x_inicio_real, y_inicio_real = coordenada_real_inicio

    def converter(ponto_clicado):

        dx = ponto_clicado.x() - clique_inicio.x()
        dy = ponto_clicado.y() - clique_inicio.y()
        distancia_desde_inicio = math.hypot(dx, dy)

        if distancia_desde_inicio == 0:
            return (x_inicio_real, y_inicio_real)

        azimute_no_desenho = math.degrees(math.atan2(dx, -dy)) % 360
        azimute_real = (azimute_no_desenho + rotacao) % 360
        distancia_real = distancia_desde_inicio * escala

        azimute_rad = math.radians(azimute_real)

        return (
            x_inicio_real + distancia_real * math.sin(azimute_rad),
            y_inicio_real + distancia_real * math.cos(azimute_rad)
        )

    return converter


def extrair_poligonal_azimute_distancia(texto):
    """Reconhece um memorial descritivo em formato de poligonal
    (traverse): parte de um vértice inicial com coordenadas UTM
    conhecidas ("...vértice V-01, de coordenadas E = 761.226,038 m e
    N = 9.105.653,211 m...") e uma tabela de segmentos com azimute e
    distância até o próximo vértice ("V01–V02  53,4703  17,026  V02"),
    formato comum em memoriais topográficos tradicionais — em vez de
    listar a coordenada de cada vértice diretamente.

    Devolve uma lista de pares (este, norte), na mesma convenção das
    demais funções UTM deste módulo — [] se não reconhecer esse
    formato (ver _percorrer_poligonal para a lógica de cálculo)."""

    texto_achatado = re.sub(r"\s+", " ", texto)

    inicio = _PADRAO_INICIO_POLIGONAL.search(texto_achatado)

    if not inicio:
        return []

    try:
        e_inicial = _texto_numero_para_float(inicio.group(2))
        n_inicial = _texto_numero_para_float(inicio.group(3))
    except ValueError:
        return []

    vertice_inicial = _normalizar_vertice_poligonal(inicio.group(1))

    segmentos = []

    for encontro in _PADRAO_SEGMENTO_AZIMUTE.finditer(texto_achatado):

        try:
            azimute = _texto_numero_para_float(encontro.group(3))
            distancia = _texto_numero_para_float(encontro.group(4))
        except ValueError:
            continue

        segmentos.append((
            _normalizar_vertice_poligonal(encontro.group(1)),
            _normalizar_vertice_poligonal(encontro.group(2)),
            azimute,
            distancia
        ))

    # exige alguns segmentos — uma tabela de verdade, não uma menção
    # avulsa de "azimute"/"distância" em outro contexto do texto
    if len(segmentos) < 3:
        return []

    return _percorrer_poligonal(vertice_inicial, e_inicial, n_inicial, segmentos)


# poligonal descrita em prosa corrida a partir de um vértice inicial com
# coordenada UTM conhecida (diferente de extrair_poligonal_azimute_prosa,
# que parte de coordenada geográfica) — ex.: "Partindo do vértice V-28
# de coordenadas E= 284843,234 e N= 9149809,936 com uma distância de
# 556,02m e azimute de 50°50'53" encontramos o vértice V-29, deste com
# distância de 598,78m e azimute de 41°14'16" encontramos o vértice
# V-30, [...]". Nota a ordem (distância antes do azimute) e o verbo de
# fechamento ("encontramos o vértice"), diferentes da outra poligonal em
# prosa.
_PADRAO_SEGMENTO_AZIMUTE_PROSA_UTM = re.compile(
    r"dist[âa]ncia\s+de\s+(" + PADRAO_NUMERO.pattern + r")\s*m"
    r"\s+e\s+azimute\s+de\s+(" + _VALOR_GMS + r"|" + PADRAO_NUMERO.pattern + r")"
    r"\s+encontramos\s+o\s+v[ée]rtice\s+(" + _ROTULO_VERTICE_V + r")",
    re.IGNORECASE
)

_PADRAO_ENCONTRAMOS_TODOS = re.compile(
    r"encontramos\s+o\s+v[ée]rtice\s+(" + _ROTULO_VERTICE_V + r")",
    re.IGNORECASE
)


def extrair_poligonal_azimute_prosa_utm(texto):
    """Como extrair_poligonal_azimute_prosa, mas para memoriais que
    partem de um vértice com coordenada UTM conhecida (E=/N=) em vez de
    geográfica, e descrevem cada segmento como "com distância de ...m e
    azimute de ... encontramos o vértice ..." (distância antes do
    azimute, fechando com "encontramos", em vez de "com azimute de ... e
    distância de ...m, [...] chega ao ponto/marco ..."). Devolve pares
    (este, norte), na mesma convenção das demais poligonais UTM deste
    módulo — [] se não reconhecer esse formato ou se algum segmento não
    tiver azimute/distância reconhecíveis (não arrisca uma poligonal
    incompleta)."""

    texto_achatado = re.sub(r"\s+", " ", texto)

    inicio = _PADRAO_INICIO_POLIGONAL.search(texto_achatado)

    if not inicio:
        return []

    try:
        e_inicial = _texto_numero_para_float(inicio.group(2))
        n_inicial = _texto_numero_para_float(inicio.group(3))
    except ValueError:
        return []

    vertice_inicial = _normalizar_vertice_poligonal(inicio.group(1))

    destinos_esperados = [
        _normalizar_vertice_poligonal(rotulo)
        for rotulo in _PADRAO_ENCONTRAMOS_TODOS.findall(texto_achatado)
    ]

    if len(destinos_esperados) < 3:
        return []

    segmentos = []

    for encontro in _PADRAO_SEGMENTO_AZIMUTE_PROSA_UTM.finditer(texto_achatado):

        try:
            distancia = _texto_numero_para_float(encontro.group(1))
            azimute = _texto_azimute_para_graus(encontro.group(2))
        except ValueError:
            continue

        segmentos.append((
            azimute,
            distancia,
            _normalizar_vertice_poligonal(encontro.group(3))
        ))

    if [destino for _, _, destino in segmentos] != destinos_esperados:
        # algum segmento não teve azimute/distância reconhecidos — não
        # arrisca calcular uma poligonal com um trecho faltando
        return []

    segmentos_com_origem = []
    origem_atual = vertice_inicial

    for azimute, distancia, destino in segmentos:
        segmentos_com_origem.append((origem_atual, destino, azimute, distancia))
        origem_atual = destino

    if len(segmentos_com_origem) < 3:
        return []

    return _percorrer_poligonal(
        vertice_inicial, e_inicial, n_inicial, segmentos_com_origem
    )


# Ângulo de um rumo (rumo quadrantal, 0–90°), em graus-minutos-segundos
# completo, graus e minutos, ou graus decimais — mais tolerante que o
# valor de azimute porque memoriais mais antigos costumam registrar o
# rumo sem segundos, ou até só em graus decimais.
_VALOR_ANGULO_RUMO = (
    r"\d{1,2}\s*°\s*\d{1,2}\s*['′]\s*\d{1,2}(?:[.,]\d+)?\s*[\"″]"  # graus, min, seg
    r"|\d{1,2}\s*°\s*\d{1,2}(?:[.,]\d+)?\s*['′]?"                  # graus e minutos
    r"|\d{1,2}(?:[.,]\d+)?\s*°"                                    # graus decimais
)

# Quadrante do rumo — notação brasileira (NE/SE/SO/NO); SW/NW também são
# aceitos, caso o memorial tenha sido gerado por software em inglês.
_QUADRANTE_RUMO = r"N\s*E|S\s*E|S\s*O|N\s*O|S\s*W|N\s*W"

# linha da tabela de segmentos em rumo, ex.: "V01–V02 NE 45°30'20" 17,026
# V02" ou "V01–V02 45°30'20" NE 17,026 V02" — o rumo pode vir com o
# quadrante antes ou depois do ângulo, conforme o memorial
_PADRAO_SEGMENTO_RUMO = re.compile(
    r"(V[\s\-]?\d+)\s*[\-–—]\s*(V[\s\-]?\d+)\s+"
    r"(?:"
    r"(" + _QUADRANTE_RUMO + r")\s*(" + _VALOR_ANGULO_RUMO + r")"
    r"|"
    r"(" + _VALOR_ANGULO_RUMO + r")\s*(" + _QUADRANTE_RUMO + r")"
    r")\s+"
    r"(" + PADRAO_NUMERO.pattern + r")\s+"
    r"(V[\s\-]?\d+)",
    re.IGNORECASE
)


def _angulo_rumo_para_graus(texto_angulo):
    """Converte um ângulo de rumo (graus-minutos-segundos ou graus
    decimais, sempre positivo, 0–90°) para graus decimais."""

    texto_angulo = texto_angulo.strip()

    dms = re.match(
        r"(\d{1,2})\s*°\s*(\d{1,2})\s*['′]?\s*(\d{1,2}(?:[.,]\d+)?)?\s*[\"″]?",
        texto_angulo
    )

    if dms:

        graus, minutos, segundos = dms.groups()

        valor = float(graus) + float(minutos) / 60

        if segundos:
            valor += float(segundos.replace(",", ".")) / 3600

        return valor

    return _texto_numero_para_float(texto_angulo.rstrip("° ").strip())


def _rumo_para_azimute(quadrante, angulo_graus):
    """Converte um rumo quadrantal (quadrante + ângulo 0–90° a partir do
    eixo Norte-Sul) para azimute (0–360° a partir do Norte, sentido
    horário) — conversão padrão da topografia."""

    quadrante = re.sub(r"\s+", "", quadrante).upper()

    if quadrante == "NE":
        return angulo_graus % 360

    if quadrante == "SE":
        return (180 - angulo_graus) % 360

    if quadrante in ("SO", "SW"):
        return (180 + angulo_graus) % 360

    if quadrante in ("NO", "NW"):
        return (360 - angulo_graus) % 360

    raise ValueError(f"Quadrante de rumo não reconhecido: {quadrante!r}")


def extrair_poligonal_rumo_distancia(texto):
    """Como extrair_poligonal_azimute_distancia, mas para memoriais que
    descrevem cada segmento por rumo quadrantal (ex.: "NE 45°30'20"")
    em vez de azimute em graus decimais — mesmo formato de poligonal
    (traverse), a diferença é só a notação do ângulo de cada segmento.
    Reaproveita o mesmo vértice inicial (E=/N= conhecidos) e a mesma
    lógica de cálculo, convertendo cada rumo para azimute antes de
    "andar" a poligonal (ver _rumo_para_azimute)."""

    texto_achatado = re.sub(r"\s+", " ", texto)

    inicio = _PADRAO_INICIO_POLIGONAL.search(texto_achatado)

    if not inicio:
        return []

    try:
        e_inicial = _texto_numero_para_float(inicio.group(2))
        n_inicial = _texto_numero_para_float(inicio.group(3))
    except ValueError:
        return []

    vertice_inicial = _normalizar_vertice_poligonal(inicio.group(1))

    segmentos = []

    for encontro in _PADRAO_SEGMENTO_RUMO.finditer(texto_achatado):

        quadrante = encontro.group(3) or encontro.group(6)
        texto_angulo = encontro.group(4) or encontro.group(5)

        try:
            angulo = _angulo_rumo_para_graus(texto_angulo)
            azimute = _rumo_para_azimute(quadrante, angulo)
            distancia = _texto_numero_para_float(encontro.group(7))
        except ValueError:
            continue

        segmentos.append((
            _normalizar_vertice_poligonal(encontro.group(1)),
            _normalizar_vertice_poligonal(encontro.group(2)),
            azimute,
            distancia
        ))

    # exige alguns segmentos — uma tabela de verdade, não uma menção
    # avulsa de "rumo"/"distância" em outro contexto do texto
    if len(segmentos) < 3:
        return []

    return _percorrer_poligonal(vertice_inicial, e_inicial, n_inicial, segmentos)


# memorial em formato de poligonal descrita em prosa corrida (em vez de
# tabela), comum em memoriais antigos do INCRA/convênios estaduais (ex.:
# "PARTINDO DO MARCO M-13723-37, COM LATITUDE 8°37'43,36" S E LONGITUDE
# 35°53'29,04" O, COM AZIMUTE DE 314°26'33" E DISTANCIA DE 41,42M, [...]
# CHEGA AO PONTO P-18209; DESTE, COM AZIMUTE DE [...]"). O ponto inicial
# é geográfico (latitude/longitude), não UTM — diferente das poligonais
# em tabela já suportadas, que partem de um vértice com coordenada UTM
# conhecida.
_PADRAO_INICIO_POLIGONAL_PROSA = re.compile(
    r"PARTINDO\s+DO\s+(?:MARCO|PONTO|V[ÉE]RTICE)\s+([\w\-\/]+)",
    re.IGNORECASE
)

# cada segmento: "COM AZIMUTE DE <valor> E DISTANCIA DE <número>M, [texto
# livre até] CHEGA AO PONTO/MARCO <rótulo>" — o azimute pode estar em
# graus-minutos-segundos (símbolo, já convertido por
# normalizar_gms_por_extenso se o memorial usava "GRAUS/MINUTOS/
# SEGUNDOS") ou em graus decimais
_PADRAO_SEGMENTO_AZIMUTE_PROSA = re.compile(
    r"COM\s+AZIMUTE\s+DE\s+(" + _VALOR_GMS + r"|" + PADRAO_NUMERO.pattern + r")"
    r"\s*E\s+DISTANCIA\s+DE\s+(" + PADRAO_NUMERO.pattern + r")\s*M\s*,"
    r".*?CHEGA\s+AO\s+(?:PONTO\s+|MARCO\s+)?([\w\-\/]+)",
    re.IGNORECASE
)

# todo destino mencionado no texto, com ou sem azimute reconhecido —
# usado só para conferir que nenhum segmento foi pulado (ver comentário
# em extrair_poligonal_azimute_prosa)
_PADRAO_CHEGA_AO_TODOS = re.compile(
    r"CHEGA\s+AO\s+(?:PONTO\s+|MARCO\s+)?([\w\-\/]+)",
    re.IGNORECASE
)


def _texto_azimute_para_graus(texto_azimute):
    """Converte um valor de azimute em graus-minutos-segundos (símbolo)
    ou em graus decimais para graus decimais — mesma lógica de
    valor_coordenada_para_decimal, mas sem se preocupar com sinal
    negativo (azimute é sempre 0–360°)."""

    texto_azimute = texto_azimute.strip()

    if "°" in texto_azimute:
        return valor_coordenada_para_decimal(texto_azimute)

    return _texto_numero_para_float(texto_azimute)


def extrair_poligonal_azimute_prosa(texto):
    """Reconhece um memorial descritivo em formato de poligonal descrita
    em prosa corrida, comum em memoriais mais antigos (INCRA/convênios
    estaduais dos anos 1980): parte de um marco inicial com coordenada
    geográfica conhecida ("PARTINDO DO MARCO M-13723-37, COM LATITUDE
    8°37'43,36" S E LONGITUDE 35°53'29,04" O") e uma sequência de
    segmentos "COM AZIMUTE DE ... E DISTANCIA DE ...M, [...] CHEGA AO
    PONTO/MARCO ...", encadeados por "DESTE," até fechar de volta no
    marco inicial.

    Diferente das poligonais em tabela já suportadas (que partem de uma
    coordenada UTM conhecida), aqui o ponto inicial é geográfico — a
    poligonal é "andada" projetando esse ponto para uma zona UTM local
    (a escolha exata da zona não importa: é só um passo interno de
    cálculo, o resultado final volta para coordenada geográfica no fim),
    usando a mesma trigonometria de azimute das demais funções deste
    módulo, e devolve diretamente pares (longitude, latitude) — ao
    contrário das poligonais UTM, que devolvem (este, norte) para o
    chamador converter.

    Memoriais antigos às vezes omitem o azimute de algum segmento (só
    informam a distância) — quando isso acontece, não há como continuar
    "andando" a poligonal com segurança a partir dali, então essa função
    detecta o buraco (comparando quantos segmentos tinham azimute
    reconhecido contra quantos destinos "CHEGA AO ..." o texto menciona
    ao todo) e devolve [] em vez de arriscar uma poligonal incompleta ou
    incorreta."""

    texto_achatado = re.sub(r"\s+", " ", texto)

    inicio = _PADRAO_INICIO_POLIGONAL_PROSA.search(texto_achatado)

    if not inicio:
        return []

    vertice_inicial = inicio.group(1).strip().upper()

    pares_iniciais = extrair_pares_gms_com_hemisferio(texto_achatado)

    if not pares_iniciais:
        return []

    longitude_inicial, latitude_inicial = pares_iniciais[0]

    destinos_esperados = [
        rotulo.strip().upper()
        for rotulo in _PADRAO_CHEGA_AO_TODOS.findall(texto_achatado)
    ]

    if len(destinos_esperados) < 3 or destinos_esperados[-1] != vertice_inicial:
        # a poligonal precisa fechar de volta no marco inicial
        return []

    segmentos = []

    for encontro in _PADRAO_SEGMENTO_AZIMUTE_PROSA.finditer(texto_achatado):

        try:
            azimute = _texto_azimute_para_graus(encontro.group(1))
            distancia = _texto_numero_para_float(encontro.group(2))
        except ValueError:
            continue

        segmentos.append((azimute, distancia, encontro.group(3).strip().upper()))

    if [destino for _, _, destino in segmentos] != destinos_esperados:
        # algum segmento não teve o azimute reconhecido (ex.: omitido no
        # memorial original) — não arrisca calcular uma poligonal com um
        # trecho faltando
        return []

    segmentos_com_origem = []
    origem_atual = vertice_inicial

    for azimute, distancia, destino in segmentos:
        segmentos_com_origem.append((origem_atual, destino, azimute, distancia))
        origem_atual = destino

    # projeta o ponto inicial (geográfico) para uma zona UTM local só
    # para poder "andar" a poligonal com a trigonometria plana — a zona
    # é escolhida pela própria longitude do ponto, sem depender de o
    # memorial informar fuso/datum nenhum
    fuso = max(18, min(25, int((longitude_inicial + 180) // 6) + 1))

    crs_utm = montar_crs_utm(fuso, "SIRGAS2000")
    crs_geografico = QgsCoordinateReferenceSystem(CRS_GEOGRAFICO)

    ponto_utm_inicial = transformar_pontos(
        [QgsPointXY(longitude_inicial, latitude_inicial)],
        crs_geografico,
        crs_utm
    )[0]

    pares_utm = _percorrer_poligonal(
        vertice_inicial,
        ponto_utm_inicial.x(),
        ponto_utm_inicial.y(),
        segmentos_com_origem
    )

    if len(pares_utm) < 3:
        return []

    pontos_geograficos = transformar_pontos(
        [QgsPointXY(este, norte) for este, norte in pares_utm],
        crs_utm,
        crs_geografico
    )

    return [(ponto.x(), ponto.y()) for ponto in pontos_geograficos]


def diagnosticar_poligonal_azimute_prosa(texto):
    """Se o texto parecer ser uma poligonal em prosa (ver
    extrair_poligonal_azimute_prosa) mas a extração não conseguir
    completar por causa de um segmento sem azimute reconhecível
    (memoriais antigos às vezes omitem o azimute de algum trecho),
    devolve uma mensagem apontando exatamente qual segmento está
    incompleto — para orientar a conferência manual do memorial
    original. Devolve None se o texto nem começar a bater com esse
    formato (não é esse tipo de memorial) ou se a extração já tiver
    funcionado (nada para avisar)."""

    texto_achatado = re.sub(r"\s+", " ", texto)

    inicio = _PADRAO_INICIO_POLIGONAL_PROSA.search(texto_achatado)

    if not inicio:
        return None

    destinos_esperados = [
        rotulo.strip().upper()
        for rotulo in _PADRAO_CHEGA_AO_TODOS.findall(texto_achatado)
    ]

    if len(destinos_esperados) < 3:
        return None

    destinos_com_azimute = [
        encontro.group(3).strip().upper()
        for encontro in _PADRAO_SEGMENTO_AZIMUTE_PROSA.finditer(texto_achatado)
    ]

    if destinos_com_azimute == destinos_esperados:
        return None

    vertice_inicial = inicio.group(1).strip().upper()

    for indice, destino in enumerate(destinos_esperados):

        if indice < len(destinos_com_azimute) and destinos_com_azimute[indice] == destino:
            continue

        origem = destinos_esperados[indice - 1] if indice > 0 else vertice_inicial

        return (
            "O memorial parece estar no formato de poligonal em prosa "
            f'(azimute/distância), mas o trecho entre "{origem}" e '
            f'"{destino}" não tem um azimute reconhecível no texto — '
            "confira o memorial original e complete esse trecho "
            "manualmente antes de tentar novamente."
        )

    return None


_PADRAO_NUMERO_DECIMAL_VIRGULA = re.compile(r"-?\d+,\d+")

def _linha_para_numero_tabela(linha):
    """Recupera um número de uma linha que deveria conter só uma
    coordenada (uma por linha, como numa tabela de planta extraída por
    OCR), mesmo quando o OCR confundiu a vírgula decimal com um ponto
    (formando um 4º grupo de milhar com menos de 3 dígitos) ou com um
    espaço, ou a apagou. Em vez de tentar interpretar a pontuação,
    reconstrói o valor a partir dos dígitos da linha, assumindo sempre 2
    casas decimais (padrão de coordenadas UTM topográficas).

    Antes disso, porém, tenta reconhecer a linha como um número decimal
    com vírgula já bem formado (ex.: '9075203,806160292', comum em
    tabelas exportadas com muitas casas decimais) — sem essa checagem, a
    reconstrução por dígitos destruiria esses valores, já que ela sempre
    assume só 2 casas decimais."""

    resultado_limpo = _PADRAO_NUMERO_DECIMAL_VIRGULA.fullmatch(linha)

    if resultado_limpo:
        return _texto_numero_para_float(resultado_limpo.group(0))

    digitos = re.sub(r"[^\d]", "", linha)

    if len(digitos) < 3:
        return None

    try:
        return float(f"{digitos[:-2]}.{digitos[-2:]}")
    except ValueError:
        return None


def extrair_pares_tabela_colunas(texto):
    """Extrai coordenadas UTM de duas listas separadas — uma coluna de
    Norte (rótulo 'N(Y)' ou 'Norte') seguida de uma coluna de Este
    (rótulo 'E(X)' ou 'Este'), um valor por linha em cada — formato comum
    ao copiar por OCR uma tabela de coordenadas de uma planta. Pareia os
    valores por posição (o 1º Norte com o 1º Este, e assim por diante).

    Levanta ValueError se encontrar os rótulos mas as duas listas tiverem
    quantidades diferentes de valores (nesse caso não dá para parear com
    segurança). Retorna lista vazia se não encontrar nenhum dos rótulos,
    para que outros métodos de extração possam tentar."""

    bloco_atual = None
    valores_norte = []
    valores_este = []

    for linha in texto.splitlines():

        linha = linha.strip()

        if not linha:
            continue

        # só considera cabeçalho de tabela se a linha for curta — evita
        # confundir com prosa comum de memorial descritivo que usa as
        # mesmas palavras como direção cardinal (ex.: "segue ao norte
        # confrontando com...", "confrontando ao leste com..."), que não
        # tem nada a ver com uma tabela de coordenadas
        if len(linha) <= 40:

            tem_rotulo_norte = bool(_ROTULO_BLOCO_NORTE.search(linha))
            tem_rotulo_este = bool(_ROTULO_BLOCO_ESTE.search(linha))

            # os dois rótulos juntos na mesma linha (ex.: "Coord. N(Y);
            # Coord. E(X)") indicam uma tabela lado a lado, não o formato
            # de duas listas separadas que esta função trata — não entra
            # em nenhum bloco, para deixar a extração genérica de texto
            # livre cuidar desse formato
            if tem_rotulo_norte and not tem_rotulo_este:
                bloco_atual = "norte"
                continue

            if tem_rotulo_este and not tem_rotulo_norte:
                bloco_atual = "este"
                continue

        if bloco_atual is None:
            continue

        valor = _linha_para_numero_tabela(linha)

        if valor is None:
            continue

        if bloco_atual == "norte":
            valores_norte.append(valor)
        else:
            valores_este.append(valor)

    if not valores_norte and not valores_este:
        return []

    if len(valores_norte) != len(valores_este):
        raise ValueError(
            f"Encontrei {len(valores_norte)} valores na coluna Norte e "
            f"{len(valores_este)} na coluna Este — as duas listas "
            "precisam ter a mesma quantidade de coordenadas, uma por "
            "vértice, para eu poder parear corretamente."
        )

    return list(zip(valores_este, valores_norte))


def classificar_par(a, b):
    """Classifica um par de números como 'geografico', 'utm' ou 'indefinido'
    com base na magnitude dos valores, sem assumir qual é qual. Serve só
    para avisar o usuário de uma possível incompatibilidade — nunca para
    sobrescrever uma escolha explícita de formato."""

    maior = max(abs(a), abs(b))
    menor = min(abs(a), abs(b))

    geografico = maior <= 180 and menor <= 90

    utm = 1000 <= abs(a) <= 10000000 and 1000 <= abs(b) <= 10000000

    if geografico and not utm:
        return "geografico"

    if utm and not geografico:
        return "utm"

    return "indefinido"


def montar_crs_utm(fuso, datum="SIRGAS2000"):
    """Monta o CRS UTM (hemisfério sul) para o fuso/datum informados."""

    tabela = EPSG_UTM_SUL.get(datum)

    if tabela is None:
        raise ValueError(f"Datum não suportado: {datum}")

    codigo = tabela.get(fuso)

    if codigo is None:
        raise ValueError(
            f"Fuso {fuso} não suportado para o datum {datum}. "
            f"Fusos disponíveis: {sorted(tabela)}."
        )

    crs = QgsCoordinateReferenceSystem.fromEpsgId(codigo)

    if not crs.isValid():
        raise ValueError(f"CRS inválido para EPSG:{codigo}.")

    return crs


def transformar_pontos(pontos, crs_origem, crs_destino):
    """Transforma uma lista de QgsPointXY do crs_origem para o crs_destino."""

    if crs_origem == crs_destino:
        return list(pontos)

    transformador = QgsCoordinateTransform(
        crs_origem,
        crs_destino,
        QgsProject.instance().transformContext()
    )

    return [transformador.transform(ponto) for ponto in pontos]


def interpretar_par_geografico(a, b):
    """Decide automaticamente qual dos dois valores é longitude e qual é
    latitude, e corrige o sinal — sem depender da ordem em que o memorial
    descritivo escreveu as coordenadas.

    Critério (válido para o território brasileiro): a longitude tem
    magnitude maior que a latitude (Brasil vai de ~-73 a ~-34 de longitude
    e de ~-33 a ~+5 de latitude). O sinal negativo é sempre aplicado, já
    que o Brasil está a oeste de Greenwich e, salvo raríssimas exceções,
    ao sul do equador."""

    if abs(a) >= abs(b):
        longitude, latitude = a, b
    else:
        longitude, latitude = b, a

    return -abs(longitude), -abs(latitude)


def pontos_geograficos_para_vertices_4674(pares):
    """Converte pares brutos já classificados como geográficos para uma
    lista de QgsPointXY em EPSG:4674, com longitude/latitude e sinal
    corrigidos automaticamente (ver interpretar_par_geografico)."""

    pontos = []

    for a, b in pares:

        longitude, latitude = interpretar_par_geografico(a, b)

        pontos.append(QgsPointXY(longitude, latitude))

    return pontos


def interpretar_par_utm(a, b):
    """Decide automaticamente qual dos dois valores é Este (X) e qual é
    Norte (Y) — sem depender da ordem em que o memorial escreveu (muitos
    modelos oficiais, como o da Prefeitura de Goiânia, escrevem "N=... e
    E=...", Norte primeiro; outros escrevem Este primeiro).

    Critério (válido para o hemisfério sul brasileiro): a coordenada Norte
    em UTM é sempre um número bem maior (7 dígitos, ~1.000.000 a
    10.000.000, por causa da falsa origem no equador) do que a coordenada
    Este (6 dígitos, ~100.000 a 999.999)."""

    if abs(a) >= abs(b):
        norte, este = a, b
    else:
        norte, este = b, a

    return este, norte


def pontos_utm_para_vertices_4674(pares, fuso, datum="SIRGAS2000"):
    """Converte pares brutos UTM (Este/Norte, em qualquer ordem — ver
    interpretar_par_utm) para uma lista de QgsPointXY em EPSG:4674."""

    crs_origem = montar_crs_utm(fuso, datum)
    crs_destino = QgsCoordinateReferenceSystem(CRS_GEOGRAFICO)

    pontos = []

    for a, b in pares:

        este, norte = interpretar_par_utm(a, b)

        pontos.append(QgsPointXY(este, norte))

    return transformar_pontos(pontos, crs_origem, crs_destino)


def calcular_area_hectares(vertices_4674):
    """Calcula a área (em hectares) de um polígono definido por vértices em
    EPSG:4674, usando cálculo geodésico (elipsoide GRS80, do SIRGAS 2000)
    para maior precisão."""

    if len(vertices_4674) < 3:
        return 0.0

    pontos = list(vertices_4674)

    if pontos[0] != pontos[-1]:
        pontos.append(pontos[0])

    geometria = QgsGeometry.fromPolygonXY([pontos])

    calculadora = QgsDistanceArea()
    calculadora.setEllipsoid("GRS80")
    calculadora.setSourceCrs(
        QgsCoordinateReferenceSystem(CRS_GEOGRAFICO),
        QgsProject.instance().transformContext()
    )

    area_m2 = calculadora.measureArea(geometria)

    return area_m2 / 10000


def detectar_vertice_anomalo(vertices_4674, limiar=15):
    """Verifica se algum vértice está muito mais longe dos vizinhos do que
    o resto do perímetro — sinal comum de um dígito perdido ou trocado por
    erro de OCR/digitação em uma das coordenadas do memorial de origem
    (ex.: 'N 912724' em vez de 'N 9127240'), que pode jogar um único
    vértice para muito longe do imóvel sem que isso seja óbvio olhando só
    os números.

    Retorna o número do vértice suspeito (1-based) ou None se o perímetro
    parecer razoavelmente uniforme. É só um alerta (heurística por
    magnitude relativa) — imóveis com um lado genuinamente bem mais longo
    que os outros (ex.: formato em "L") também podem disparar o aviso,
    então não deve bloquear o salvamento, só chamar atenção para
    conferir."""

    if len(vertices_4674) < 4:
        return None

    distancias = []

    for i in range(len(vertices_4674)):

        anterior = vertices_4674[i - 1]
        atual = vertices_4674[i]

        distancias.append(
            math.hypot(atual.x() - anterior.x(), atual.y() - anterior.y())
        )

    mediana = statistics.median(distancias)

    if mediana == 0:
        return None

    for i, distancia in enumerate(distancias):

        if distancia > mediana * limiar:
            return i + 1  # vértice de destino do trecho anômalo


def poligonos_conectados(geometrias):
    """True se todas as geometrias formam um único grupo conectado por
    fronteira compartilhada — duas parcelas que só se tocam numa ponta
    (um único vértice em comum, sem dividir uma linha) não contam como
    adjacentes para fins de memorial descritivo, já que parcelas
    vizinhas de verdade compartilham uma linha de divisa, não uma
    ponta. Usa union-find sobre os pares cuja interseção de fronteiras
    tem comprimento maior que zero."""

    n = len(geometrias)

    if n <= 1:
        return True

    pais = list(range(n))

    def encontrar(indice):

        while pais[indice] != indice:
            pais[indice] = pais[pais[indice]]
            indice = pais[indice]

        return indice

    def unir(a, b):

        raiz_a = encontrar(a)
        raiz_b = encontrar(b)

        if raiz_a != raiz_b:
            pais[raiz_a] = raiz_b

    # QgsGeometry não tem um método boundary() direto nesta API — a
    # fronteira (contorno) do polígono é obtida convertendo a geometria
    # para linha, que segue todos os anéis (externo e furos)
    fronteiras = [
        geometria.convertToType(QgsWkbTypes.LineGeometry, False)
        for geometria in geometrias
    ]

    for i in range(n):

        for j in range(i + 1, n):

            fronteira_comum = fronteiras[i].intersection(fronteiras[j])

            if fronteira_comum and fronteira_comum.length() > 0:
                unir(i, j)

    raizes = {encontrar(i) for i in range(n)}

    return len(raizes) == 1

    return None
