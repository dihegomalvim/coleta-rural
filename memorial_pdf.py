# -*- coding: utf-8 -*-

"""Monta e exporta o PDF do memorial descritivo (aba "Gerar Memorial"),
inspirado na estrutura de seções do app oficial Coleta Rural
(cabeçalho com logo, caixa de identificação, croqui do imóvel, lista
de coordenadas geográficas e uma faixa de aviso legal — sem a seção
de municípios abrangidos, já que o plugin não tem competência para
afirmar isso). Só cuida da montagem visual e da exportação — toda a
lógica de geometria/CRS já vem pronta de quem chama."""

import os

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor, QFont

from qgis.core import (
    QgsFillSymbol,
    QgsGeometry,
    QgsLayout,
    QgsLayoutExporter,
    QgsLayoutItemLabel,
    QgsLayoutItemMap,
    QgsLayoutItemPicture,
    QgsLayoutItemShape,
    QgsLayoutMeasurement,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsProject,
    QgsRasterLayer,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsUnitTypes
)

_LARGURA_PAGINA = 210.0  # A4 retrato, em mm
_ALTURA_PAGINA = 297.0
_MARGEM = 10.0
_LARGURA_UTIL = _LARGURA_PAGINA - 2 * _MARGEM
_ALTURA_RODAPE = 14.0

# verde institucional do INCRA, usado nos frisos/faixas do documento
_VERDE_INCRA = QColor(46, 139, 65)

_PASTA_ASSETS = os.path.join(os.path.dirname(__file__), "assets")
_LOGO_INCRA = os.path.join(_PASTA_ASSETS, "incra_logo.png")

_SETA_NORTE_SVG = ":/images/north_arrows/layout_default_north_arrow.svg"

# crédito obrigatório pelos termos de uso do Esri World Imagery
_CREDITO_SATELITE = "Imagem: Esri, Maxar, Earthstar Geographics e comunidade GIS"

_TEXTO_AVISO_LEGAL = (
    "Este memorial descritivo possui caráter meramente informativo e foi "
    "construído com base nas interpretações das informações documentais "
    "disponibilizadas, auxiliadas pelas informações nos bancos de dados "
    "públicos geográficos a qual temos acesso, ou é um polígono já "
    "declarado em uma das bases públicas. A realidade em campo pode ser "
    "diferente."
)

_NOMES_AMIGAVEIS_CRS = {
    "EPSG:4674": "SIRGAS2000",
    "EPSG:4326": "WGS84",
    "EPSG:4618": "SAD69",
}

# coordenadas geográficas: até 4 colunas por página, para nunca invadir
# a faixa de rodapé — se não couber tudo, continua em página(s) extras
_NUM_COLUNAS_COORD = 4
_GAP_COLUNA_COORD = 4.0
_LARGURA_COLUNA_COORD = (
    _LARGURA_UTIL - (_NUM_COLUNAS_COORD - 1) * _GAP_COLUNA_COORD
) / _NUM_COLUNAS_COORD
# estimativa conservadora de altura por linha de texto 8pt — melhor
# paginar cedo demais do que arriscar estourar o rodapé
_ALTURA_LINHA_COORD = 5.0


def _mm(valor):
    return QgsLayoutMeasurement(valor, QgsUnitTypes.LayoutMillimeters)


def _posicionar(item, x, y, largura, altura, pagina=0):

    item.attemptMove(
        QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters),
        True,
        False,
        pagina
    )
    item.attemptResize(
        QgsLayoutSize(largura, altura, QgsUnitTypes.LayoutMillimeters)
    )


def _estilizar_retangulo(item, cor_preenchimento):

    simbolo = QgsFillSymbol.createSimple({
        "color": cor_preenchimento.name(),
        "outline_style": "no",
    })

    item.setSymbol(simbolo)


def _fonte_secao():

    fonte = QFont()
    fonte.setPointSize(10)
    fonte.setBold(True)

    return fonte


def _formato_com_buffer(tamanho_pt, negrito=False):
    """QgsTextFormat com um contorno branco ao redor do texto (preto),
    para continuar legível em cima da imagem de satélite, que tem
    trechos escuros/variados demais para um texto simples. Usado só no
    rótulo "N" da seta de norte, que fica sobre o croqui — as demais
    legendas (datum, crédito da imagem) agora ficam abaixo do croqui,
    sobre fundo branco, e não precisam do contorno."""

    fonte = QFont()
    fonte.setPointSize(tamanho_pt)
    fonte.setBold(negrito)

    formato = QgsTextFormat()
    formato.setFont(fonte)
    formato.setSize(tamanho_pt)
    formato.setSizeUnit(QgsUnitTypes.RenderPoints)
    formato.setColor(QColor(0, 0, 0))

    buffer_config = QgsTextBufferSettings()
    buffer_config.setEnabled(True)
    buffer_config.setColor(QColor(255, 255, 255))
    buffer_config.setSize(0.8)
    buffer_config.setSizeUnit(QgsUnitTypes.RenderMillimeters)
    formato.setBuffer(buffer_config)

    return formato


def _url_google_maps(vertices_4674):
    """Monta um link do Google Maps apontando para o centro do imóvel
    (centroide do contorno externo), para que qualquer pessoa consiga
    localizar rapidamente o imóvel no navegador, sem precisar de QGIS
    ou Google Earth. As coordenadas já vêm em EPSG:4674 (SIRGAS2000
    geográfico), numericamente compatível com o WGS84 usado pelo Google
    Maps — a diferença entre os dois data é da ordem de centímetros no
    Brasil, irrelevante para localizar o imóvel."""

    if len(vertices_4674) < 3:
        return None

    anel = list(vertices_4674)

    if anel[0] != anel[-1]:
        anel.append(anel[0])

    centro = QgsGeometry.fromPolygonXY([anel]).centroid().asPoint()

    return (
        "https://www.google.com/maps/search/?api=1&query="
        f"{centro.y():.6f},{centro.x():.6f}"
    )


def _nome_amigavel_crs(crs):

    authid = crs.authid()

    return _NOMES_AMIGAVEIS_CRS.get(authid, authid or crs.description())


def _camada_satelite():
    """Camada de imagem de satélite (Esri World Imagery, XYZ) para o
    croqui — sempre usada como fundo, para que o memorial mostre o
    contexto real do terreno mesmo que o projeto do usuário não tenha
    nenhuma camada de imagem carregada. Se não for possível carregar
    (ex.: sem internet no momento de gerar o PDF), o croqui segue sem
    fundo, só com o polígono — não interrompe a geração do memorial.

    zmax fica em 17 (não no máximo 19 que o serviço aceita) porque em
    áreas rurais o Esri World Imagery normalmente não tem cobertura em
    resolução tão alta — pedir zoom 19 nesses casos faz aparecer o
    "Map data not available" cinza da Esri em vez da imagem de
    verdade. Em zoom 17 a cobertura é bem mais confiável em qualquer
    lugar, ao custo de um pouco menos de nitidez onde há resolução
    maior disponível."""

    camada = QgsRasterLayer(
        "type=xyz&url=https://server.arcgisonline.com/ArcGIS/rest/services/"
        "World_Imagery/MapServer/tile/%7Bz%7D/%7By%7D/%7Bx%7D"
        "&zmax=17&zmin=0",
        "Esri World Imagery",
        "wms"
    )

    return camada if camada.isValid() else None


def _adicionar_titulo_secao(layout, texto, y, pagina=0):

    titulo = QgsLayoutItemLabel(layout)
    titulo.setText(texto)
    titulo.setFont(_fonte_secao())

    layout.addLayoutItem(titulo)
    _posicionar(titulo, _MARGEM, y, _LARGURA_UTIL, 6, pagina)

    return y + 7


def _adicionar_rodape(layout, pagina, y_rodape_local):
    """Adiciona a faixa verde de aviso legal no rodapé da página
    indicada — chamada uma vez por página usada no documento, para que
    o aviso apareça em todas elas."""

    friso_rodape = QgsLayoutItemShape(layout)
    friso_rodape.setShapeType(QgsLayoutItemShape.Rectangle)
    layout.addLayoutItem(friso_rodape)
    _posicionar(
        friso_rodape, 0, y_rodape_local, _LARGURA_PAGINA, _ALTURA_RODAPE, pagina
    )
    _estilizar_retangulo(friso_rodape, _VERDE_INCRA)

    texto_rodape = QgsLayoutItemLabel(layout)
    texto_rodape.setText(_TEXTO_AVISO_LEGAL)
    fonte_rodape = QFont()
    fonte_rodape.setPointSize(7)
    texto_rodape.setFont(fonte_rodape)
    texto_rodape.setFontColor(QColor(255, 255, 255))
    texto_rodape.setHAlign(Qt.AlignCenter)
    texto_rodape.setVAlign(Qt.AlignVCenter)
    layout.addLayoutItem(texto_rodape)
    _posicionar(
        texto_rodape,
        _MARGEM + 4,
        y_rodape_local + 1,
        _LARGURA_UTIL - 8,
        _ALTURA_RODAPE - 2,
        pagina
    )


def gerar_pdf_memorial(
    caminho_saida,
    dados,
    vertices_4674,
    layers_mapa,
    extensao_mapa,
    crs_mapa
):
    """Monta um QgsLayout no mesmo formato do app oficial Coleta Rural
    e exporta para PDF em caminho_saida.

    dados: dicionário com as chaves "imovel", "municipio", "uf", "area",
    "declarante", "cpf", "cir", "matricula", "processo_sei" (todas em
    texto, já formatadas — "cir"/"matricula"/"processo_sei" podem vir
    vazias, e nesse caso a linha correspondente não aparece no
    cabeçalho).
    vertices_4674: lista de QgsPointXY do contorno externo do imóvel
    (só o anel externo — limites internos não entram na lista).
    layers_mapa: lista de QgsMapLayer a desenhar no croqui, na ordem em
    que devem aparecer (do topo para baixo) — normalmente só o
    polígono mesclado (translúcido) e, quando houver mais de um
    polígono original, as linhas internas e os rótulos de matrícula.
    Uma camada de fundo de satélite (Esri World Imagery) é sempre
    acrescentada por baixo dessas, automaticamente, com o devido
    crédito da fonte exibido no croqui.
    extensao_mapa: QgsRectangle da área a enquadrar no croqui.
    crs_mapa: QgsCoordinateReferenceSystem em que extensao_mapa está
    definida (também usado como CRS do item de mapa do croqui)."""

    layout = QgsLayout(QgsProject.instance())
    layout.initializeDefaults()

    pagina = layout.pageCollection().page(0)
    pagina.setPageSize(
        QgsLayoutSize(_LARGURA_PAGINA, _ALTURA_PAGINA, QgsUnitTypes.LayoutMillimeters)
    )

    y = _MARGEM

    # --- Cabeçalho: logo do INCRA (fundo claro, pois a logo é verde) ---
    if os.path.exists(_LOGO_INCRA):

        logo = QgsLayoutItemPicture(layout)
        logo.setPicturePath(_LOGO_INCRA)
        layout.addLayoutItem(logo)
        _posicionar(logo, _MARGEM, y, 55, 16)

    titulo = QgsLayoutItemLabel(layout)
    titulo.setText("MEMORIAL DESCRITIVO")
    fonte_titulo = QFont()
    fonte_titulo.setPointSize(18)
    fonte_titulo.setBold(True)
    titulo.setFont(fonte_titulo)
    titulo.setHAlign(Qt.AlignRight)
    titulo.setVAlign(Qt.AlignVCenter)
    layout.addLayoutItem(titulo)
    _posicionar(titulo, _MARGEM + 55, y, _LARGURA_UTIL - 55, 16)

    y += 20

    friso_cabecalho = QgsLayoutItemShape(layout)
    friso_cabecalho.setShapeType(QgsLayoutItemShape.Rectangle)
    layout.addLayoutItem(friso_cabecalho)
    _posicionar(friso_cabecalho, 0, y, _LARGURA_PAGINA, 2)
    _estilizar_retangulo(friso_cabecalho, _VERDE_INCRA)

    y += 8

    # --- Caixa de identificação do imóvel ---
    linhas_info = []

    if dados.get("processo_sei"):
        linhas_info.append(("Processo SEI", dados["processo_sei"]))

    linhas_info += [
        ("Imóvel", dados.get("imovel") or "-"),
        (
            "Município sede",
            f"{dados['municipio']} - {dados['uf']}"
            if dados.get("municipio") and dados.get("uf")
            else dados.get("municipio") or "-"
        ),
        (
            "Área total",
            f"{dados['area']} ha" if dados.get("area") else "-"
        ),
        ("Declarante", dados.get("declarante") or "-"),
        ("CPF/CNPJ", dados.get("cpf") or "-"),
    ]

    if dados.get("cir"):
        linhas_info.append(("CIR", dados["cir"]))

    if dados.get("matricula"):
        linhas_info.append(("Matrícula", dados["matricula"]))

    linhas_info.append((
        "Fonte do polígono",
        dados.get("fonte") or "Indicado pela equipe do INCRA"
    ))

    url_maps = _url_google_maps(vertices_4674)

    if url_maps:
        linhas_info.append((
            "Localização",
            f'<a href="{url_maps}">Ver no Google Maps</a>'
        ))

    html_info = (
        "<table style='font-family:Arial; font-size:10pt; width:100%; "
        "border-collapse:collapse;'>"
    )

    for rotulo, valor in linhas_info:
        html_info += (
            "<tr><td style='width:35%; padding:2px 6px 2px 0;'>"
            f"<b>{rotulo}:</b></td>"
            f"<td style='padding:2px 0;'>{valor}</td></tr>"
        )

    html_info += "</table>"

    caixa_info = QgsLayoutItemLabel(layout)
    caixa_info.setMode(QgsLayoutItemLabel.ModeHtml)
    caixa_info.setText(html_info)
    caixa_info.setFrameEnabled(True)
    # afasta o texto das bordas do quadro (por padrão fica colado)
    caixa_info.setMarginX(4)
    caixa_info.setMarginY(3)
    layout.addLayoutItem(caixa_info)

    altura_info = 6 + len(linhas_info) * 6.0
    _posicionar(caixa_info, _MARGEM, y, _LARGURA_UTIL, altura_info)

    y += altura_info + 12

    # --- Croqui do imóvel: sempre com imagem de satélite de fundo,
    # mostrando só o(s) polígono(s) do imóvel (translúcido) por cima ---
    # (a seção "Municípios Abrangidos" foi retirada: o plugin não tem
    # competência para afirmar quais municípios um imóvel abrange — isso
    # é atribuição dos órgãos estaduais)
    y = _adicionar_titulo_secao(layout, "CROQUI DO IMÓVEL", y)

    altura_mapa = 110
    y_topo_mapa = y

    camadas_croqui = list(layers_mapa)
    camada_satelite = _camada_satelite()

    if camada_satelite:
        camadas_croqui.append(camada_satelite)

    mapa = QgsLayoutItemMap(layout)
    layout.addLayoutItem(mapa)
    _posicionar(mapa, _MARGEM, y, _LARGURA_UTIL, altura_mapa)
    mapa.setCrs(crs_mapa)
    mapa.zoomToExtent(extensao_mapa)
    mapa.setLayers(camadas_croqui)
    mapa.setFrameEnabled(True)

    rotulo_norte = QgsLayoutItemLabel(layout)
    rotulo_norte.setText("N")
    rotulo_norte.setHAlign(Qt.AlignCenter)
    rotulo_norte.setTextFormat(_formato_com_buffer(8, negrito=True))
    layout.addLayoutItem(rotulo_norte)
    _posicionar(rotulo_norte, _MARGEM + _LARGURA_UTIL - 15, y_topo_mapa + 2, 10, 5)

    seta_norte = QgsLayoutItemPicture(layout)
    seta_norte.setPicturePath(_SETA_NORTE_SVG)
    layout.addLayoutItem(seta_norte)
    _posicionar(seta_norte, _MARGEM + _LARGURA_UTIL - 14, y_topo_mapa + 7, 8, 10)

    y += altura_mapa + 3

    # legenda do datum e crédito da imagem de satélite ficam abaixo do
    # croqui (não mais sobre a imagem) — texto simples, sem precisar de
    # contorno branco, já que aqui é sempre sobre fundo branco da página
    fonte_legenda = QFont()
    fonte_legenda.setPointSize(7)

    legenda_crs = QgsLayoutItemLabel(layout)
    legenda_crs.setText(f"Datum: {_nome_amigavel_crs(crs_mapa)}")
    legenda_crs.setFont(fonte_legenda)
    legenda_crs.setHAlign(Qt.AlignLeft)
    layout.addLayoutItem(legenda_crs)
    _posicionar(legenda_crs, _MARGEM, y, 80, 5)

    if camada_satelite:

        legenda_credito = QgsLayoutItemLabel(layout)
        legenda_credito.setText(_CREDITO_SATELITE)
        legenda_credito.setFont(fonte_legenda)
        legenda_credito.setHAlign(Qt.AlignRight)
        layout.addLayoutItem(legenda_credito)
        _posicionar(
            legenda_credito,
            _MARGEM + _LARGURA_UTIL - 130,
            y,
            130,
            5
        )

    y += 9

    # --- Coordenadas geográficas (só o anel externo), em até 4 colunas
    # por página — continua em página(s) extras quando não couber tudo,
    # para nunca invadir a faixa de rodapé ---
    linhas_dados = [
        f"P{indice};{ponto.y():.6f};{ponto.x():.6f}"
        for indice, ponto in enumerate(vertices_4674, start=1)
    ] or ["(nenhuma coordenada)"]

    pagina_indice = 0
    primeiro_bloco = True

    while linhas_dados:

        if not primeiro_bloco:
            layout.pageCollection().extendByNewPage()
            pagina_indice += 1
            y = _MARGEM

        titulo_coord = (
            "COORDENADAS GEOGRÁFICAS" if primeiro_bloco
            else "COORDENADAS GEOGRÁFICAS (continuação)"
        )
        y = _adicionar_titulo_secao(layout, titulo_coord, y, pagina_indice)

        y_rodape_pagina = _ALTURA_PAGINA - _MARGEM - _ALTURA_RODAPE
        _adicionar_rodape(layout, pagina_indice, y_rodape_pagina)

        altura_disponivel = y_rodape_pagina - y - 4
        linhas_dados_por_coluna = max(
            1, int(altura_disponivel // _ALTURA_LINHA_COORD)
        )
        capacidade_pagina = linhas_dados_por_coluna * _NUM_COLUNAS_COORD

        bloco = linhas_dados[:capacidade_pagina]
        linhas_dados = linhas_dados[capacidade_pagina:]

        colunas_necessarias = min(
            _NUM_COLUNAS_COORD,
            -(-len(bloco) // linhas_dados_por_coluna)
        )
        linhas_por_coluna_real = -(-len(bloco) // colunas_necessarias)

        for coluna in range(colunas_necessarias):

            sub = bloco[
                coluna * linhas_por_coluna_real:
                (coluna + 1) * linhas_por_coluna_real
            ]

            if not sub:
                continue

            texto_coluna = "<br/>".join(sub)

            caixa_coord = QgsLayoutItemLabel(layout)
            caixa_coord.setMode(QgsLayoutItemLabel.ModeHtml)
            caixa_coord.setText(
                "<div style='font-family:Consolas,monospace; font-size:8pt;'>"
                + texto_coluna
                + "</div>"
            )
            layout.addLayoutItem(caixa_coord)

            x_coluna = _MARGEM + coluna * (_LARGURA_COLUNA_COORD + _GAP_COLUNA_COORD)
            _posicionar(
                caixa_coord,
                x_coluna,
                y,
                _LARGURA_COLUNA_COORD,
                linhas_dados_por_coluna * _ALTURA_LINHA_COORD,
                pagina_indice
            )

        primeiro_bloco = False

    exportador = QgsLayoutExporter(layout)
    configuracoes = QgsLayoutExporter.PdfExportSettings()

    resultado = exportador.exportToPdf(caminho_saida, configuracoes)

    if resultado != QgsLayoutExporter.Success:
        raise Exception(f"Falha ao exportar o PDF (código {resultado}).")
