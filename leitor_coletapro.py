# -*- coding: utf-8 -*-
"""Leitura dos documentos gerados pelo Coleta Pro (memorial descritivo em
tabelas, memorial em texto corrido, memorial de remembramento e planta de
levantamento georreferenciado), a partir do texto extraído do PDF (ou
colado pelo operador). Só texto -> dados; a conversão para geometria do
QGIS fica com quem chama."""

import re

_ROTULOS_TIPO_PLANTA = (
    "PLANTA DE LOTEAMENTO", "PLANTA DE USUCAPIÃO", "PLANTA DE RETIFICAÇÃO",
    "PLANTA DE REURB", "PLANTA DE IMÓVEL RURAL DE ESTRANGEIRO",
    "PLANTA — DEFINIDO PELO RI 1", "PLANTA — DEFINIDO PELO RI 2",
    "PLANTA DE REMEMBRAMENTO", "PLANTA DE DESMEMBRAMENTO",
)

_GMS = r"\d{1,3}\s*°\s*\d{1,2}\s*'\s*\d{1,2}(?:[.,]\d+)?\s*\"\s*"

# tabela do memorial: V1 código E N latitude longitude
_LINHA_MEMORIAL = re.compile(
    r"\bV(\d{1,4})\s+\S+\s+[\d.]+,\d{3}\s+[\d.]+,\d{3}\s+"
    r"(-\d{1,2},\d{4,})\s+(-\d{1,3},\d{4,})"
)

# tabela antiga / remembramento: V1 [código] E N fuso S (datum)
_LINHA_UTM = re.compile(
    r"\bV(\d{1,4})\s+(?:\S+\s+)??(\d{5,}(?:\.\d{3})*[.,]\d{1,3}|\d{1,3}(?:\.\d{3})+,\d+)\s+"
    r"(\d{6,}[.,]\d{1,3}|\d{1,3}(?:\.\d{3})+,\d+)\s+"
    r"(\d{2})\s*S\s*\(\s*(SIRGAS\s*2000|SAD\s*69|WGS\s*84)\s*\)"
)

# tabela da planta: V1 código longitude latitude (decimal ou GMS)
_LINHA_PLANTA_DECIMAL = re.compile(
    r"\bV(\d{1,4})\s+\S+\s+(-\d{1,3},\d{4,})\s*°\s*(-\d{1,2},\d{4,})\s*°"
)
_LINHA_PLANTA_GMS = re.compile(
    r"\bV(\d{1,4})\s+\S+\s+(" + _GMS + r")([WOE])\s*(" + _GMS + r")([SN])"
)


def eh_coletapro(texto):
    """True se o texto é de um documento gerado pelo Coleta Pro."""

    if not re.search(r"Coleta\s?Pro\b", texto):
        return False

    return bool(
        re.search(r"MEMORIAL\s+DESCRITIVO", texto)
        or re.search(r"descri[çc][ãa]o\s+deste\s+per[íi]metro", texto)
        # qualquer planta: as temáticas (sem tabela de vértices) precisam
        # ser reconhecidas para o operador receber o aviso certo
        or re.search(r"\bPLANTA\b", texto)
        or "Tabela de coordenadas" in texto
        or "TERMO DE" in texto
    )


def _numero(texto):
    """'190.521,571' ou '189303.916' -> float."""

    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")

    return float(texto)


def _gms(texto, hemisferio):
    graus, minutos, segundos = re.match(
        r"\s*(\d+)\s*°\s*(\d+)\s*'\s*([\d.,]+)", texto
    ).groups()

    valor = int(graus) + int(minutos) / 60 + _numero(segundos) / 3600

    return -valor if hemisferio in "SWO" else valor


def _separar_aneis(linhas):
    """Recebe [(numero_do_vertice, ponto)] na ordem do documento; a
    numeração voltando a V1 marca o começo de outra poligonal."""

    aneis = []
    anterior = None

    for numero, ponto in linhas:

        if anterior is None or numero <= anterior:
            aneis.append([])

        aneis[-1].append(ponto)
        anterior = numero

    return [a for a in aneis if len(a) >= 3]


def _poligonais_tabela_memorial(texto):
    """Só a tabela do memorial principal: as páginas finais repetem os
    vértices de cada parcela (e o termo de concordância), que não podem
    ser somados ao perímetro."""

    # em PDFs das primeiras versões o título saiu quebrado em várias
    # linhas; as linhas de vértice são específicas o bastante sem ele
    inicio = re.search(r"Tabela de Coordenadas", texto)

    resto = texto[inicio.end():] if inicio else texto

    fim = re.search(
        r"Tabela de Confronta|Planta \(croqui|Documento gerado|"
        r"TERMO DE CONCORD",
        resto
    )

    secao = resto[:fim.start()] if fim else resto

    linhas = [
        (int(m.group(1)), (_numero(m.group(3)), _numero(m.group(2))))
        for m in _LINHA_MEMORIAL.finditer(secao)
    ]

    if linhas:
        return [
            {"sistema": "geografico", "vertices": a}
            for a in _separar_aneis(linhas)
        ]

    linhas = []
    zonas = {}

    for m in _LINHA_UTM.finditer(secao):

        ponto = (_numero(m.group(2)), _numero(m.group(3)))
        zonas[ponto] = (int(m.group(4)), re.sub(r"\s", "", m.group(5)))
        linhas.append((int(m.group(1)), ponto))

    return [
        {
            "sistema": "utm",
            "vertices": a,
            "fuso": zonas[a[0]][0],
            "datum": zonas[a[0]][1],
        }
        for a in _separar_aneis(linhas)
    ]


def _poligonais_planta(texto):

    inicio = re.search(r"Tabela de coordenadas", texto)
    secao = texto[inicio.end():] if inicio else texto

    achados = [
        (m.start(), int(m.group(1)), (_numero(m.group(2)), _numero(m.group(3))))
        for m in _LINHA_PLANTA_DECIMAL.finditer(secao)
    ]

    achados += [
        (
            m.start(),
            int(m.group(1)),
            (_gms(m.group(2), m.group(3)), _gms(m.group(4), m.group(5))),
        )
        for m in _LINHA_PLANTA_GMS.finditer(secao)
    ]

    linhas = [(numero, ponto) for _, numero, ponto in sorted(achados)]

    return [
        {"sistema": "geografico", "vertices": a}
        for a in _separar_aneis(linhas)
    ]


def _poligonais_texto_corrido(texto):
    """Memorial em texto corrido (UTM, geográfica decimal ou GMS do
    SIGEF) — um parágrafo por poligonal."""

    # o cabeçalho "Coleta Pro" das páginas cai no meio das frases
    plano = " ".join(
        linha for linha in texto.splitlines()
        if linha.strip() not in ("Coleta Pro", "ColetaPro")
    )
    plano = re.sub(r"\s+", " ", plano)

    trechos = re.split(r"Inicia-se a descri[çc][ãa]o deste per[íi]metro", plano)

    marcador = r"v[ée]rtice [^,;]{1,40}?, de coordenadas "

    padrao_utm = re.compile(
        marcador + r"N ([\d.]+,\d+) ?m e E ([\d.]+,\d+) ?m"
    )
    padrao_decimal = re.compile(
        marcador + r"latitude ([\d]+,\d+) ?° ?([NS]) e longitude "
        r"([\d]+,\d+) ?° ?([EWO])"
    )
    padrao_gms = re.compile(
        marcador + r"latitude (" + _GMS + r")([NS]) e longitude "
        r"(" + _GMS + r")([EWO])"
    )

    poligonais = []

    for trecho in trechos[1:]:

        utm = [
            (_numero(m.group(2)), _numero(m.group(1)))
            for m in padrao_utm.finditer(trecho)
        ]

        if len(utm) >= 3:

            fuso = re.search(r"Fuso (\d{2}) Sul", trecho)

            poligonais.append({
                "sistema": "utm",
                "vertices": utm,
                "fuso": int(fuso.group(1)) if fuso else None,
                "datum": "SIRGAS2000",
            })

            continue

        geo = []

        for m in padrao_decimal.finditer(trecho):

            latitude = _numero(m.group(1)) * (-1 if m.group(2) == "S" else 1)
            longitude = _numero(m.group(3)) * (
                -1 if m.group(4) in "WO" else 1
            )
            geo.append((longitude, latitude))

        if not geo:

            geo = [
                (_gms(m.group(3), m.group(4)), _gms(m.group(1), m.group(2)))
                for m in padrao_gms.finditer(trecho)
            ]

        if len(geo) >= 3:
            poligonais.append({"sistema": "geografico", "vertices": geo})

    return poligonais


def extrair_poligonais(texto):
    """Lista de poligonais do documento. Cada uma é um dict com
    'sistema' ('geografico' ou 'utm') e 'vertices' ((longitude, latitude)
    ou (este, norte)); as UTM trazem também 'fuso' e 'datum'."""

    if re.search(r"descri[çc][ãa]o\s+deste\s+per[íi]metro", texto):
        return _poligonais_texto_corrido(texto)

    if re.search(r"V\s+C[óo]digo\s+Longitude\s+Latitude", texto):
        return _poligonais_planta(texto)

    return _poligonais_tabela_memorial(texto)


def _campo(texto, padrao):
    m = re.search(padrao, texto, re.MULTILINE)
    return m.group(1).strip() if m else ""


def _dados_planta(texto, dados):

    bloco = re.search(
        r"PLANTA DE LEVANTAMENTO\s*\n\s*GEORREFERENCIADO\s*\n(.*?)"
        r"\n([^\n]+)/([A-Z]{2})\s*\n",
        texto,
        re.DOTALL
    )

    if bloco:

        nome = [
            linha.strip() for linha in bloco.group(1).splitlines()
            if linha.strip() and linha.strip() not in _ROTULOS_TIPO_PLANTA
        ]

        dados["imovel"] = " ".join(nome)
        dados["municipio"] = bloco.group(2).strip()
        dados["uf"] = bloco.group(3)

    dados["matricula"] = _campo(texto, r"^Matr[íi]culas?:[ \t]*(\S[^\n]*)$")

    if not dados["matricula"]:

        # remembramento: "Matrículas:" e uma linha "número  área — perímetro"
        bloco_mat = re.search(
            r"^Matr[íi]culas:\s*\n((?:[^\n]*ha\s*—[^\n]*\n)+)",
            texto,
            re.MULTILINE
        )

        if bloco_mat:
            dados["matricula"] = " / ".join(
                linha.split()[0]
                for linha in bloco_mat.group(1).splitlines() if linha.strip()
            )

    dados["cir"] = _campo(
        texto, r"^CIR\b[^\n]*\n(?:CIB[^\n]*\n)?\s*(\d{3}\.\d{3}\.\d{3}\.\d{3}-\d)"
    ) or _campo(texto, r"\b(\d{3}\.\d{3}\.\d{3}\.\d{3}-\d)\b")

    assinatura = re.search(
        r"^Assinaturas\s*\n(.*?)\n\s*CPF(?:/CNPJ)?:\s*([\d./\-]+)[^\n]*\n"
        r"\s*([^\n]+)",
        texto,
        re.MULTILINE | re.DOTALL
    )

    # a 1ª assinatura é a do proprietário/declarante (a do RT vem depois)
    if assinatura and "Responsável" not in assinatura.group(3):
        dados["declarante"] = " ".join(assinatura.group(1).split())
        dados["cpf"] = assinatura.group(2)


def extrair_dados(texto):
    """Dados de identificação do documento do Coleta Pro: imovel,
    municipio, uf, declarante, cpf, cir, matricula e area (hectares, como
    texto com vírgula decimal)."""

    dados = dict.fromkeys(
        ("imovel", "municipio", "uf", "declarante", "cpf", "cir",
         "matricula", "area"),
        ""
    )

    area = _campo(texto, r"^[ÁA]rea(?: resultante)?:[ \t]*([\d.]+(?:,\d+)?)[ \t]*ha")

    if area:

        if "," not in area:
            area = area.replace(".", ",")

        dados["area"] = area

    if re.search(r"PLANTA\s+DE\s+LEVANTAMENTO", texto) and re.search(
        r"V\s+C[óo]digo\s+Longitude", texto
    ):
        _dados_planta(texto, dados)
        return dados

    # só o memorial principal: as parcelas anexadas repetem os rótulos
    principal = re.split(r"\n\s*Parcela \S+\s*\n(?:[^\n]*\n){0,2}?\s*1\. Identifica", texto)[0]

    dados["imovel"] = (
        _campo(principal, r"^Nome do im[óo]vel:[ \t]*(.+)$")
        or _campo(principal, r"^Im[óo]vel:[ \t]*(.+)$")
        or _campo(principal, r"^Nome:[ \t]*(.+)$"
                  if "DE REMEMBRAMENTO" in principal else r"(?!x)x")
    )

    local = _campo(principal, r"^Munic[íi]pio/UF:[ \t]*(.+)$")

    if "/" in local:
        municipio, uf = local.rsplit("/", 1)
        dados["municipio"], dados["uf"] = municipio.strip(), uf.strip()
    else:
        dados["municipio"] = local

    dados["cir"] = _campo(
        principal, r"^CIR:[ \t]*(\d{3}\.\d{3}\.\d{3}\.\d{3}-\d)"
    )

    dados["matricula"] = _campo(principal, r"^Matr[íi]culas?:[ \t]*(.+)$")

    if not dados["matricula"]:

        tabela = re.search(
            r"Matr[íi]culas do Im[óo]vel\s*\n[^\n]*CNM[^\n]*\n(.*?)\n\s*\d\. ",
            principal,
            re.DOTALL
        )

        if tabela:
            dados["matricula"] = " / ".join(
                re.findall(r"^(\d[\d.\-]*)[ \t]+\D", tabela.group(1), re.MULTILINE)
            )

    # texto corrido
    corrido = re.search(
        r"^Propriet[áa]rio/(?:Possuidor|Declarante):[ \t]*(.+?)\s*—\s*CPF[ \t]*"
        r"([\d./\-]*)",
        principal,
        re.MULTILINE
    )

    if corrido:
        dados["declarante"] = corrido.group(1).strip().strip("-")
        dados["cpf"] = corrido.group(2)
        return dados

    # tabela "Proprietários/Possuidores": o titular, não o declarante (que
    # pode ser só quem preencheu o cadastro)
    titular = re.search(
        r"Propriet[áa]rios/Possuidores\s*\nNome/Raz[ãa]o Social[^\n]*\n"
        r"(.+?)\s+(\d[\d./\-]{9,17})\s+[A-Z_]{5,}",
        principal,
        re.DOTALL
    )

    if titular:
        dados["declarante"] = " ".join(titular.group(1).split())
        dados["cpf"] = titular.group(2)
        return dados

    declarante = re.search(
        r"\d\. Declarante\s*\nNome:[ \t]*([^\n]+)\nCPF(?:/CNPJ)?:[ \t]*([\d./\-]+)",
        principal
    )

    if declarante:
        dados["declarante"] = declarante.group(1).strip()
        dados["cpf"] = declarante.group(2)

    return dados
