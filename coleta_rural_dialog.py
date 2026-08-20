# -*- coding: utf-8 -*-

import json
import os
import re
import sys
import unicodedata
import urllib.request

try:
    # usa o pypdf já instalado no ambiente, se houver
    from pypdf import PdfReader
except ImportError:
    # senão, usa a cópia embutida no plugin (libs/pypdf), para que
    # ninguém precise instalar nada manualmente ao baixar o plugin
    _pasta_libs = os.path.join(os.path.dirname(__file__), "libs")

    if _pasta_libs not in sys.path:
        sys.path.insert(0, _pasta_libs)

    from pypdf import PdfReader

from qgis.PyQt import uic
from qgis.PyQt import QtWidgets
from qgis.PyQt import QtGui
from qgis.PyQt import QtCore

from qgis.PyQt.QtWidgets import (
    QFileDialog,
    QInputDialog,
    QMessageBox,
    QTableWidgetItem
)

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsPalLayerSettings,
    QgsProject,
    QgsProviderRegistry,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsSettings,
    QgsTextFormat,
    QgsWkbTypes
)

from qgis.gui import QgsVertexMarker

from .configuracoes_dialog import ConfiguracoesDialog
from . import coordenadas
from . import memorial_pdf
from . import municipios_pe


FORM_CLASS, _ = uic.loadUiType(
    os.path.join(
        os.path.dirname(__file__),
        'coleta_rural_dialog_base.ui'
    )
)

# Rótulos alternativos aceitos ao extrair dados de memoriais fora do padrão
# Coleta Rural (comparação sempre sem diferenciar maiúsculas/minúsculas).
# Também reaproveitados para reconhecer os campos de camadas públicas
# oficiais (SIGEF Brasil, CAR) na aba Gerar Memorial: NOME_AREA/CODIGO_IMO/
# REGISTRO_M são do SIGEF; NOM_MUNICI/COD_ESTADO são do CAR. Os campos
# MUNICIPIO_/UF_ID do SIGEF não entram aqui de propósito — são código
# numérico do IBGE, não texto direto, e precisam de resolução à parte
# (ver _resolver_municipio_uf_sigef).
ALIASES_IMOVEL = ("IMÓVEL", "NOME DO IMÓVEL", "NOME_AREA")
ALIASES_MUNICIPIO = (
    "MUNICÍPIO SEDE", "MUNICÍPIO", "MUNICÍPIO/UF", "LOCALIZAÇÃO", "NOM_MUNICI"
)
ALIASES_UF = ("UF", "ESTADO", "COD_ESTADO")
ALIASES_DECLARANTE = ("DECLARANTE", "PROPRIETÁRIO", "PROPRIETARIO")
ALIASES_CPF = ("CPF/CNPJ", "CPF", "CNPJ")
ALIASES_CIR = ("CIR", "CODIGO_IMO")
ALIASES_MATRICULA = ("MATRÍCULA", "MATRICULA", "REGISTRO_M")

# nomes de campos (maiúsculo) que identificam a origem oficial do
# polígono selecionado na aba Gerar Memorial, para citar a fonte no
# memorial gerado
_CAMPOS_SIGEF = {"CODIGO_IMO", "SITUACAO_I", "PARCELA_CO"}
_CAMPOS_CAR = {"COD_IMOVEL", "NUM_AREA", "NOM_MUNICI"}

# categorias reconhecidas no formato "rótulos todos juntos, valores bem
# mais abaixo" (ver _extrair_bloco_identificacao_manual) — "area" entra
# só para não desalinhar a contagem de posições com os outros rótulos;
# o valor da área do memorial manual sempre vem do cálculo geodésico
# em cima das coordenadas, nunca do texto
_CAMPOS_BLOCO_IDENTIFICACAO = (
    ("imovel", ALIASES_IMOVEL),
    ("municipio", ALIASES_MUNICIPIO),
    ("area", ("ÁREA TOTAL", "AREA")),
    ("declarante", ALIASES_DECLARANTE),
    ("cpf", ALIASES_CPF),
)


def _sem_acentos(texto):
    """Remove acentos para comparações tolerantes a OCR que às vezes
    apaga o acento de uma palavra (ex.: "Municipio" em vez de
    "Município") — mantém tudo mais igual, só troca letras acentuadas
    pela versão sem acento."""

    texto_normalizado = unicodedata.normalize("NFKD", texto)

    return "".join(
        caractere for caractere in texto_normalizado
        if not unicodedata.combining(caractere)
    )

PADRAO_CIR = re.compile(r"\b\d{3}\.\d{3}\.\d{3}\.\d{3}-\d\b")

# Máscaras de entrada — o Brasil (único país atendido pelo plugin) está
# sempre a Sul e a Oeste, então o sinal negativo já vem fixo na máscara
# da coordenada (geográfica ou UTM não tem sinal, mas a geográfica
# sempre tem), sem precisar digitar. A coordenada geográfica usa só 2
# dígitos de grau — nenhuma latitude/longitude do Brasil passa de 2
# dígitos (latitude até ~34°, longitude até ~74°) — enquanto o azimute
# usa 3 (é um ângulo de 0 a 360°, não uma coordenada) e usa menos casas
# decimais nos segundos, já que não precisa da mesma precisão da
# coordenada. O caractere de preenchimento vazio é "0" (em vez do "_"
# padrão), para o campo já nascer mostrando os zeros em vez de traços.
MASCARA_COORDENADA_GMS = "-00°00'00,0000\";0"
MASCARA_COORDENADA_DECIMAL = "-00,000000;0"
MASCARA_AZIMUTE_GMS = "000°00'00,00\";0"
MASCARA_UTM_ESTE = "000.000,000;0"
MASCARA_UTM_NORTE = "0.000.000,000;0"

# Longitude e latitude são fáceis de confundir (qual campo é qual, e a
# ordem certa) — em vez de mostrar "00°" genérico, o valor de exemplo
# usa os graus de Brasília (capital federal, referência que qualquer
# pessoa no Brasil reconhece), com minutos e segundos zerados mesmo
# (não é a coordenada exata, só um exemplo de magnitude). O texto do
# exemplo fica cinza até a pessoa digitar de verdade por cima (ver
# _preencher_campo_mascarado_com_exemplo/_conectar_cor_ao_editar).
EXEMPLO_LATITUDE_GMS = "-15°00'00,0000\""
EXEMPLO_LONGITUDE_GMS = "-47°00'00,0000\""
EXEMPLO_LATITUDE_DECIMAL = "-15,000000"
EXEMPLO_LONGITUDE_DECIMAL = "-47,000000"


def _preencher_campo_mascarado_com_exemplo(campo, valor_exemplo):
    """Preenche um campo com máscara com um valor de exemplo, sem
    marcar como editado de verdade pela pessoa (setText() não dispara
    textEdited, diferente de insert()) — e deixa o texto em cinza
    enquanto for só o exemplo."""

    campo.setText(valor_exemplo)
    campo.setStyleSheet("color: gray;")


def _conectar_cor_ao_editar(campo):
    """Faz o campo voltar à cor normal assim que a pessoa realmente
    digita algo nele (ver _preencher_campo_mascarado_com_exemplo) —
    conectar uma única vez por campo, na criação dele."""

    campo.textEdited.connect(lambda _texto, c=campo: c.setStyleSheet(""))


class _VisualizadorPlanta(QtWidgets.QGraphicsView):
    """Painel que mostra a imagem da planta/croqui anexada, num
    QGraphicsView — não é uma camada do projeto QGIS nem toca no canvas
    principal, então o zoom/posição do mapa do projeto nunca é afetado
    (o problema de a imagem "ficar gigantesca" no mapa vinha justamente
    de carregá-la como camada raster sem georreferenciamento, cuja
    extensão em pixels era interpretada como se fosse graus/metros no
    canvas principal).

    Emite sinais de clique em coordenadas de PIXEL da própria imagem
    (não do mapa) — usados pela ferramenta "Desenhar Polígono na
    Planta" para calibrar e marcar vértices sem nenhuma dependência de
    CRS/projeto."""

    clicado = QtCore.pyqtSignal(QtCore.QPointF)
    clicado_direito = QtCore.pyqtSignal()
    cancelado = QtCore.pyqtSignal()

    def __init__(self, parent=None):

        super().__init__(parent)

        self._cena = QtWidgets.QGraphicsScene(self)
        self.setScene(self._cena)
        self.setRenderHints(
            QtGui.QPainter.RenderHint.Antialiasing
            | QtGui.QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setDragMode(QtWidgets.QGraphicsView.DragMode.NoDrag)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.setTransformationAnchor(
            QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )

        self._item_pixmap = None
        self._marcadores = []
        self._marcadores_removiveis = []
        self._arrastando_pan = False
        self._pan_ultima_pos = None

    def carregar_imagem(self, caminho):
        """Carrega uma imagem (jpg/png/tif/bmp) no painel. Devolve True
        se conseguiu, False se o arquivo não pôde ser lido como
        imagem."""

        pixmap = QtGui.QPixmap(caminho)

        if pixmap.isNull():
            return False

        self.carregar_pixmap(pixmap)

        return True

    def carregar_pixmap(self, pixmap):

        self._cena.clear()
        self._marcadores = []
        self._marcadores_removiveis = []

        self._item_pixmap = self._cena.addPixmap(pixmap)
        self._cena.setSceneRect(self._item_pixmap.boundingRect())
        self.fitInView(self._item_pixmap, QtCore.Qt.AspectRatioMode.KeepAspectRatio)

    def ajustar_zoom_para_caber(self):
        """Ajusta o zoom para mostrar a imagem inteira, ocupando o
        painel todo — chamado explicitamente depois que o painel já
        está visível no tamanho final (o ajuste feito dentro de
        carregar_pixmap() acontece cedo demais, antes de a janela
        expandir e o painel ficar visível, então calcula o encaixe
        contra um tamanho de viewport ainda pequeno/não realizado).
        Não é chamado a cada redimensionamento — isso desfaria o zoom
        manual que a pessoa já tivesse feito."""

        if self._item_pixmap is not None:
            self.fitInView(self._item_pixmap, QtCore.Qt.AspectRatioMode.KeepAspectRatio)

    def adicionar_marcador(self, ponto, removivel=False, arrastavel=None):
        """Marca um ponto clicado na planta com um círculo vermelho —
        confirma visualmente que o clique foi registrado.

        Se arrastavel=True, o marcador pode ser arrastado (para
        corrigir a posição sem precisar cancelar e clicar de novo).
        Se omitido, segue o valor de removivel (os dois sempre andaram
        juntos até os marcadores de calibração passarem a ser
        arrastáveis também, sem serem excluíveis).

        Se removivel=True (etapa de marcar os vértices do polígono,
        não a calibração), o marcador também pode ser excluído com um
        clique direito nele (em vez de clicar direito na área vazia,
        que finaliza o desenho ou confirma a calibração)."""

        if arrastavel is None:
            arrastavel = removivel

        raio = 6

        item = self._cena.addEllipse(
            ponto.x() - raio, ponto.y() - raio, raio * 2, raio * 2,
            QtGui.QPen(QtGui.QColor(255, 0, 0), 2),
            QtGui.QBrush(QtGui.QColor(255, 0, 0, 120))
        )

        if arrastavel:
            item.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable)

        if removivel:
            self._marcadores_removiveis.append(item)

        self._marcadores.append(item)

        return item

    def posicao_marcador(self, item):
        """Posição atual (na cena) de um marcador específico — já
        refletindo qualquer arrasto manual feito depois do clique
        original."""

        return item.mapToScene(item.rect().center())

    def pontos_marcadores_removiveis(self):
        """Devolve a posição atual (na cena) de cada marcador
        removível, na ordem em que foram adicionados — já refletindo
        qualquer arrasto manual feito depois do clique original, e sem
        os que já foram excluídos."""

        return [self.posicao_marcador(item) for item in self._marcadores_removiveis]

    def limpar_imagem(self):
        """Remove a imagem carregada e todos os marcadores, voltando o
        painel ao estado inicial (sem imagem nenhuma) — usado pelo
        botão "Limpar Imagem" para desfazer o que "Anexar Imagem
        (Planta)" fez."""

        self._cena.clear()
        self._item_pixmap = None
        self._marcadores = []
        self._marcadores_removiveis = []

    def limpar_marcadores(self):

        for item in self._marcadores:
            self._cena.removeItem(item)

        self._marcadores = []
        self._marcadores_removiveis = []

    def mousePressEvent(self, evento):

        if self._item_pixmap is None:
            return

        if evento.button() == QtCore.Qt.MouseButton.MiddleButton:
            # pan com o botão do meio — não conflita com o esquerdo
            # (marca vértice) nem o direito (confirma/exclui/finaliza),
            # então funciona em qualquer modo, inclusive com o
            # formulário de azimute/distância aberto ao lado, para
            # dar uma olhada no resto da planta sem perder a calibração
            self._arrastando_pan = True
            self._pan_ultima_pos = evento.pos()
            self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
            return

        item_clicado = self.itemAt(evento.pos())
        eh_marcador_removivel = item_clicado in self._marcadores_removiveis
        eh_marcador_arrastavel = item_clicado is not None and bool(
            item_clicado.flags() & QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        )

        if evento.button() == QtCore.Qt.MouseButton.RightButton:

            if eh_marcador_removivel:
                self._marcadores_removiveis.remove(item_clicado)
                self._marcadores.remove(item_clicado)
                self._cena.removeItem(item_clicado)
            else:
                self.clicado_direito.emit()

        elif evento.button() == QtCore.Qt.MouseButton.LeftButton:

            if eh_marcador_arrastavel:
                # deixa o Qt cuidar do arrasto (ItemIsMovable) em vez
                # de tratar como um clique para marcar um vértice novo
                # — vale tanto para os marcadores de vértice quanto
                # para os dois de calibração, que também podem ser
                # ajustados antes de informar o azimute/distância
                super().mousePressEvent(evento)
            else:
                self.clicado.emit(self.mapToScene(evento.pos()))

    def mouseMoveEvent(self, evento):

        if self._arrastando_pan:

            delta = evento.pos() - self._pan_ultima_pos
            self._pan_ultima_pos = evento.pos()

            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x()
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y()
            )

            return

        super().mouseMoveEvent(evento)

    def mouseReleaseEvent(self, evento):

        if evento.button() == QtCore.Qt.MouseButton.MiddleButton and self._arrastando_pan:
            self._arrastando_pan = False
            self.unsetCursor()
            return

        super().mouseReleaseEvent(evento)

    def keyPressEvent(self, evento):

        if evento.key() == QtCore.Qt.Key.Key_Escape:
            self.cancelado.emit()
        else:
            super().keyPressEvent(evento)

    def wheelEvent(self, evento):

        if self._item_pixmap is None:
            return

        # alguns mouses/trackpads (rolagem "suave"/de precisão) mandam
        # o movimento só em pixelDelta(), com angleDelta() sempre zero
        # — sem esse fallback, a condição "> 0" nunca era verdadeira e
        # a roda só dava zoom pra fora, nunca pra dentro
        delta = evento.angleDelta().y()

        if delta == 0:
            delta = evento.pixelDelta().y()

        if delta == 0:
            return

        fator = 1.25 if delta > 0 else 0.8
        self.scale(fator, fator)


class _DialogoCalibracaoPlanta(QtWidgets.QDialog):
    """Formulário curto pedindo os dados reais (já conhecidos do texto
    do memorial) do trecho clicado na planta: coordenada real do
    primeiro clique, e azimute/distância reais desse trecho — usados
    para calibrar a conversão clique→coordenada real do resto do
    desenho (ver coordenadas.calibrar_transformacao_planta)."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Coleta Rural — Calibrar trecho conhecido")

        layout = QtWidgets.QFormLayout(self)

        linha_modo = QtWidgets.QHBoxLayout()
        self.rdoGeografica = QtWidgets.QRadioButton("Geográfica (GMS)")
        self.rdoGeografica.setChecked(True)
        self.rdoGeograficaDecimal = QtWidgets.QRadioButton("Geográfica (decimal)")
        self.rdoUtm = QtWidgets.QRadioButton("UTM")
        linha_modo.addWidget(self.rdoGeografica)
        linha_modo.addWidget(self.rdoGeograficaDecimal)
        linha_modo.addWidget(self.rdoUtm)
        layout.addRow("Tipo de coordenada do 1º clique:", linha_modo)

        self.lblCoord1 = QtWidgets.QLabel("Longitude:")
        self.txtCoord1 = QtWidgets.QLineEdit()
        layout.addRow(self.lblCoord1, self.txtCoord1)

        self.lblCoord2 = QtWidgets.QLabel("Latitude:")
        self.txtCoord2 = QtWidgets.QLineEdit()
        layout.addRow(self.lblCoord2, self.txtCoord2)

        self.lblFuso = QtWidgets.QLabel("Fuso:")
        self.cmbFuso = QtWidgets.QComboBox()
        self.cmbFuso.addItems([f"{n}S" for n in range(18, 26)])
        layout.addRow(self.lblFuso, self.cmbFuso)

        self.lblDatum = QtWidgets.QLabel("Datum:")
        self.cmbDatum = QtWidgets.QComboBox()
        self.cmbDatum.addItems(["SIRGAS2000", "SAD69", "WGS84"])
        layout.addRow(self.lblDatum, self.cmbDatum)

        self.txtAzimute = QtWidgets.QLineEdit()
        self.txtAzimute.setInputMask(MASCARA_AZIMUTE_GMS)
        self.txtAzimute.setStyleSheet("color: gray;")
        layout.addRow("Azimute real do trecho:", self.txtAzimute)

        _conectar_cor_ao_editar(self.txtCoord1)
        _conectar_cor_ao_editar(self.txtCoord2)
        _conectar_cor_ao_editar(self.txtAzimute)

        self.txtDistancia = QtWidgets.QLineEdit()
        self.txtDistancia.setPlaceholderText("Ex.: 41,42")
        layout.addRow("Distância real do trecho (m):", self.txtDistancia)

        botoes = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        layout.addRow(botoes)

        self.rdoGeografica.toggled.connect(self._atualizar_modo)
        self.rdoGeograficaDecimal.toggled.connect(self._atualizar_modo)
        self.rdoUtm.toggled.connect(self._atualizar_modo)
        self._atualizar_modo()

    def _atualizar_modo(self):

        utm = self.rdoUtm.isChecked()
        decimal = self.rdoGeograficaDecimal.isChecked()

        self.lblCoord1.setText("Este:" if utm else "Longitude:")
        self.lblCoord2.setText("Norte:" if utm else "Latitude:")

        # limpa antes de trocar a máscara — senão os dígitos que
        # sobraram do modo anterior são reaproveitados na posição da
        # máscara nova, em vez de a máscara nascer zerada
        self.txtCoord1.setInputMask("")
        self.txtCoord1.clear()
        self.txtCoord2.setInputMask("")
        self.txtCoord2.clear()

        if utm:

            self.txtCoord1.setInputMask(MASCARA_UTM_ESTE)
            self.txtCoord1.setStyleSheet("color: gray;")
            self.txtCoord2.setInputMask(MASCARA_UTM_NORTE)
            self.txtCoord2.setStyleSheet("color: gray;")

        elif decimal:

            self.txtCoord1.setInputMask(MASCARA_COORDENADA_DECIMAL)
            _preencher_campo_mascarado_com_exemplo(
                self.txtCoord1, EXEMPLO_LONGITUDE_DECIMAL
            )
            self.txtCoord2.setInputMask(MASCARA_COORDENADA_DECIMAL)
            _preencher_campo_mascarado_com_exemplo(
                self.txtCoord2, EXEMPLO_LATITUDE_DECIMAL
            )

        else:

            self.txtCoord1.setInputMask(MASCARA_COORDENADA_GMS)
            _preencher_campo_mascarado_com_exemplo(
                self.txtCoord1, EXEMPLO_LONGITUDE_GMS
            )
            self.txtCoord2.setInputMask(MASCARA_COORDENADA_GMS)
            _preencher_campo_mascarado_com_exemplo(
                self.txtCoord2, EXEMPLO_LATITUDE_GMS
            )

        # o fuso só se aplica à UTM, mas o datum é pedido nos três modos
        # — inclusive coordenadas geográficas precisam de datum
        # conhecido (documentos anteriores a 2005 costumam usar SAD69,
        # não SIRGAS2000)
        self.lblFuso.setVisible(utm)
        self.cmbFuso.setVisible(utm)


class _DialogoEscolherImagemPdf(QtWidgets.QDialog):
    """Quando um PDF anexado como planta/croqui tem mais de uma imagem
    embutida (comum: página 1 é o título, página 2 é o memorial
    descritivo, página 3 é a planta em si — cada página escaneada como
    uma imagem própria), mostra uma miniatura de cada uma para a pessoa
    escolher visualmente qual delas usar, em vez de adivinhar pela
    posição da página."""

    def __init__(self, imagens, parent=None):
        """imagens: lista de (índice da página, QPixmap)."""

        super().__init__(parent)

        self.setWindowTitle("Coleta Rural — Escolher imagem do PDF")
        self.indice_pagina_escolhido = None

        layout = QtWidgets.QVBoxLayout(self)

        layout.addWidget(QtWidgets.QLabel(
            "Este PDF tem mais de uma imagem. Clique na que representa "
            "a planta/croqui do imóvel:"
        ))

        grade = QtWidgets.QHBoxLayout()

        for indice_pagina, pixmap in imagens:

            botao = QtWidgets.QToolButton()
            botao.setIcon(QtGui.QIcon(pixmap))
            botao.setIconSize(QtCore.QSize(150, 150))
            botao.setText(f"Página {indice_pagina + 1}")
            botao.setToolButtonStyle(
                QtCore.Qt.ToolButtonStyle.ToolButtonTextUnderIcon
            )
            botao.clicked.connect(
                lambda _checked=False, i=indice_pagina: self._escolher(i)
            )

            grade.addWidget(botao)

        layout.addLayout(grade)

        botao_cancelar = QtWidgets.QPushButton("Cancelar")
        botao_cancelar.clicked.connect(self.reject)
        layout.addWidget(botao_cancelar)

    def _escolher(self, indice_pagina):

        self.indice_pagina_escolhido = indice_pagina
        self.accept()


class ColetaRuralDialog(QtWidgets.QDialog, FORM_CLASS):

    def __init__(self, iface, parent=None):
        super().__init__(parent)

        self.iface = iface

        self.setupUi(self)

        # Em todos os campos de texto editáveis, se ainda não houver nada
        # de verdade digitado, um clique deve sempre levar o cursor para o
        # começo do campo (ver eventFilter/_cursor_ao_inicio_se_vazio) —
        # sem isso, campos com máscara (ex.: CIR) ainda vazios deixam
        # clicar no meio dos espaços em branco da máscara.
        for campo in (
            self.txtCirColetaRural,
            self.txtMatriculaColetaRural,
            self.txtImovelManual,
            self.txtCirManual,
            self.txtMatriculaManual,
            self.txtMunicipioManual,
            self.txtUfManual,
            self.txtDeclaranteManual,
            self.txtCpfManual,
            self.txtAreaManual,
            self.txtZoomCoord1,
            self.txtZoomCoord2,
            self.txtImovelSelecao,
            self.txtProcessoSeiSelecao,
            self.txtCirSelecao,
            self.txtMatriculaSelecao,
            self.txtMunicipioSelecao,
            self.txtUfSelecao,
            self.txtDeclaranteSelecao,
            self.txtCpfSelecao,
            self.txtAreaSelecao,
        ):
            campo.installEventFilter(self)

        self.arquivo_pdf = None
        self.texto_memorial = ""
        self.imovel = ""
        self.municipio = ""
        self.uf = ""
        self.area = ""
        self.declarante = ""
        self.cpf = ""
        self.cir = ""
        self.matricula = ""
        self.vertices = []
        self.preview_layer = None
        self.preview_linhas_internas_selecao = None
        self.preview_labels_selecao = None
        self._geometrias_origem_selecao = []
        self._crs_origem_selecao = None
        self._labels_origem_selecao = []
        self._fonte_poligono_selecao = ""
        self.zoom_marker = None
        self._fuso_veio_do_texto = False
        self._datum_veio_do_texto = False
        self._ultimos_pares_utm = None
        self._ultimos_pares_geograficos = None

        self.btnSalvar.setEnabled(False)
        self.btnSalvarManual.setEnabled(False)

        self.btnSelecionarPdf.clicked.connect(
            self.selecionar_pdf
        )

        self.btnVisualizar.clicked.connect(
            self.visualizar_imovel
        )

        self.btnSalvar.clicked.connect(
            self.salvar_camada
        )

        self.btnConfiguracoes.clicked.connect(
            self.abrir_configuracoes
        )

        self.btnSelecionarPdfManual.clicked.connect(
            self.selecionar_pdf_manual
        )

        self.btnAnexarArquivoManual.clicked.connect(
            self.selecionar_arquivo_geometria_manual
        )

        self.btnAnexarImagemManual.clicked.connect(
            self.anexar_imagem_referencia
        )

        self.btnDesenharPoligonoPlanta.clicked.connect(
            self.iniciar_desenho_sobre_planta
        )

        # Painel de visualização da planta — widget próprio (não é
        # camada do projeto QGIS), posicionado à direita do restante da
        # janela e só revelado (com a janela expandida) quando uma
        # imagem é anexada, para deixar claro pra quem está usando qual
        # imagem foi selecionada.
        self._largura_padrao_janela = self.width()
        _largura_painel_planta = 600  # 50% maior que os 400px originais
        self._largura_com_painel_planta = (
            self.width() + 10 + _largura_painel_planta
        )

        self.painelPlanta = _VisualizadorPlanta(self)
        self.painelPlanta.setGeometry(
            self._largura_padrao_janela + 10, 54, _largura_painel_planta, 626
        )
        self.painelPlanta.setVisible(False)

        # botão para desfazer o "Anexar Imagem (Planta)" — some junto
        # com o painel (fecha o painel e volta a janela ao tamanho
        # padrão), então fica escondido/mostrado do mesmo jeito que o
        # painel, em vez de ocupar espaço fixo na aba mesmo sem imagem
        # nenhuma anexada
        self.btnLimparImagemPlanta = QtWidgets.QPushButton(
            "Limpar Imagem", self
        )
        self.btnLimparImagemPlanta.setGeometry(
            self._largura_padrao_janela + 10, 28, 130, 22
        )
        self.btnLimparImagemPlanta.setVisible(False)
        self.btnLimparImagemPlanta.clicked.connect(self.limpar_imagem_planta)

        self.painelPlanta.clicado.connect(self._ao_clicar_planta)
        self.painelPlanta.clicado_direito.connect(
            self._ao_clicar_direito_planta
        )
        self.painelPlanta.cancelado.connect(self._ao_cancelar_planta)

        self._modo_clique_planta = None
        self._marcadores_calibracao_planta = []
        self._dialogo_calibracao_planta = None
        self._calibracao_planta_atual = None
        self._converter_planta = None
        self._crs_utm_planta = None
        self._crs_geografico_planta = None
        self._vertices_desenhados_planta_utm = []

        self.btnExtrairManual.clicked.connect(
            self.processar_texto_manual
        )

        self.btnVisualizarManual.clicked.connect(
            self.visualizar_imovel_manual
        )

        self.btnSalvarManual.clicked.connect(
            self.salvar_camada_manual
        )

        self.btnVisualizarLocal.clicked.connect(
            self.zoom_para_coordenada
        )

        self.btnLimparManual.clicked.connect(
            self.limpar_manual
        )

        self.txtCpfManual.textEdited.connect(
            lambda texto: self._formatar_cpf_cnpj(self.txtCpfManual, texto)
        )

        self.txtCpfSelecao.textEdited.connect(
            lambda texto: self._formatar_cpf_cnpj(self.txtCpfSelecao, texto)
        )

        self.rdoZoomGeografica.toggled.connect(
            self.atualizar_modo_zoom
        )

        self.rdoZoomGeograficaDecimal.toggled.connect(
            self.atualizar_modo_zoom
        )

        self.rdoZoomUtm.toggled.connect(
            self.atualizar_modo_zoom
        )

        _conectar_cor_ao_editar(self.txtZoomCoord1)
        _conectar_cor_ao_editar(self.txtZoomCoord2)

        self.atualizar_modo_zoom()

        self.tabelaCoordenadasManual.horizontalHeader().setStretchLastSection(True)

        self.cmbFusoManual.currentIndexChanged.connect(
            self._recalcular_vertices_utm_atuais
        )

        self.cmbDatumManual.currentIndexChanged.connect(
            self._recalcular_vertices_utm_atuais
        )

        self.btnCarregarSelecao.clicked.connect(
            self.carregar_selecao_memorial
        )

        self.btnVisualizarSelecao.clicked.connect(
            self.visualizar_memorial_selecao
        )

        self.btnGerarMemorialSelecao.clicked.connect(
            self.gerar_memorial_selecao
        )

        self.btnLimparSelecao.clicked.connect(
            self.limpar_memorial_selecao
        )

        self.chkProcessoSeiSelecao.toggled.connect(
            self._alternar_processo_sei_selecao
        )

        self.tabelaCoordenadasSelecao.horizontalHeader().setStretchLastSection(True)

        self.tabWidget.currentChanged.connect(
            self._aba_alterada
        )

        self.carregar_camadas_permitidas()
        self.carregar_camadas_origem_selecao()

        self.toolbar = self.iface.addToolBar(
            "Coleta Rural"
        )
        self.toolbar.setObjectName(
            "Coleta Rural"
        )

    def eventFilter(self, objeto, evento):

        if (
            evento.type() == QtCore.QEvent.MouseButtonPress
            and isinstance(objeto, QtWidgets.QLineEdit)
        ):
            QtCore.QTimer.singleShot(
                0, lambda campo=objeto: self._cursor_ao_inicio_se_vazio(campo)
            )

        return super().eventFilter(objeto, evento)

    def _cursor_ao_inicio_se_vazio(self, campo):
        """Se o campo não tiver nenhum conteúdo real digitado (só os
        caracteres literais de uma máscara ainda vazia, como
        "___.___.___.___-_" do campo CIR), move o cursor para o começo do
        campo assim que a pessoa clica nele — sem isso, um clique no meio
        de um campo com máscara ainda vazio posiciona o cursor no meio dos
        espaços em branco da máscara, em vez de no começo, de onde a
        pessoa realmente vai começar a digitar. Se o campo já tiver algum
        conteúdo real, o clique se comporta normalmente (cursor fica onde
        a pessoa clicou)."""

        if not re.search(r"[0-9A-Za-zÀ-ÿ]", campo.text()):
            campo.setCursorPosition(0)

    def carregar_camadas_permitidas(self):

        self.cmbCamada.clear()

        settings = QgsSettings()

        camadas_permitidas = settings.value(
            "ColetaRural/camadas_permitidas",
            [],
            type=list
        )

        for nome in camadas_permitidas:

            layers = QgsProject.instance().mapLayersByName(
                nome
            )

            if layers:
                self.cmbCamada.addItem(nome)

    def limpar_preview(self):

        try:

            if self.preview_layer:

                QgsProject.instance().removeMapLayer(
                    self.preview_layer.id()
                )

        except Exception as erro:
            # inclui o caso em que a camada de preview já foi apagada
            # manualmente pelo usuário (objeto C++ deletado) — nesse caso
            # não há nada a fazer além de esquecer a referência antiga
            print(f"Erro ao remover preview: {erro}")

        self.preview_layer = None

    def limpar_zoom_marker(self):

        try:

            if self.zoom_marker:

                self.iface.mapCanvas().scene().removeItem(
                    self.zoom_marker
                )

        except Exception as erro:
            print(f"Erro ao remover marcador de zoom: {erro}")

        self.zoom_marker = None

    def closeEvent(self, event):

        self.limpar_zoom_marker()

        super().closeEvent(event)

    def selecionar_pdf(self):

        self.limpar_preview()

        self.btnSalvar.setEnabled(False)

        self.lblImovel.setText("-")
        self.lblMunicipio.setText("-")
        self.lblDeclarante.setText("-")
        self.lblArea.setText("-")

        self.imovel = ""
        self.municipio = ""
        self.uf = ""
        self.area = ""
        self.declarante = ""
        self.cpf = ""

        arquivo, _ = QFileDialog.getOpenFileName(
            self,
            "Selecionar Memorial",
            "",
            "Arquivos PDF (*.pdf)"
        )

        if not arquivo:
            return

        try:

            self.arquivo_pdf = arquivo

            reader = PdfReader(arquivo)

            texto = ""

            for pagina in reader.pages:

                conteudo = pagina.extract_text()

                if conteudo:
                    texto += conteudo + "\n"

            self.texto_memorial = texto

            if not texto.strip():

                QMessageBox.warning(
                    self,
                    "Coleta Rural",
                    "Não foi possível extrair texto deste PDF — ele "
                    "provavelmente é uma imagem/scan, sem texto "
                    "embutido (comum em memoriais antigos digitalizados). "
                    "Faça o OCR externamente e cole o texto na aba "
                    "\"Memorial Genérico\"."
                )

                return

            self.preencher_dados(texto)

        except Exception as erro:

            QMessageBox.critical(
                self,
                "Erro",
                f"Não foi possível ler o PDF.\n\n{erro}"
            )

    def _extrair_campo(self, texto, inicio, fim):

        padrao = rf"{re.escape(inicio)}\s*(.*?)\s*{re.escape(fim)}"

        resultado = re.search(
            padrao,
            texto,
            re.DOTALL
        )

        return resultado.group(1).strip() if resultado else ""

    def preencher_dados(self, texto):

        try:

            self.imovel = self._extrair_campo(
                texto, "Imóvel:", "Município sede:"
            )

            self.municipio = self._extrair_campo(
                texto, "Município sede:", "Área total:"
            )

            self.area = self._extrair_campo(
                texto, "Área total:", "Declarante:"
            )

            self.declarante = self._extrair_campo(
                texto, "Declarante:", "CPF/CNPJ:"
            )

            self.cpf = self._extrair_campo(
                texto, "CPF/CNPJ:", "MUNICÍPIOS ABRANGIDOS"
            )

            self.lblImovel.setText(self.imovel if self.imovel else "-")
            self.lblMunicipio.setText(self.municipio if self.municipio else "-")
            self.lblArea.setText(self.area if self.area else "-")
            self.lblDeclarante.setText(self.declarante if self.declarante else "-")

            print("CPF CAPTURADO:", self.cpf)

            self.extrair_vertices(texto)

        except Exception as erro:

            QMessageBox.warning(
                self,
                "Aviso",
                f"Erro ao processar memorial:\n\n{erro}"
            )

    def extrair_vertices(self, texto):

        self.vertices = []

        linhas = texto.splitlines()

        for linha in linhas:

            linha = linha.strip()

            if not linha.startswith("P"):
                continue

            if ";" not in linha:
                continue

            partes = linha.split(";")

            if len(partes) < 3:
                continue

            try:

                latitude = float(
                    partes[1].replace(",", ".")
                )

                longitude = float(
                    partes[2].replace(",", ".")
                )

                ponto = QgsPointXY(
                    longitude,
                    latitude
                )

                self.vertices.append(ponto)

            except Exception as erro:
                print(f"Erro ao processar vértice: {erro}")

    def _construir_preview(self):

        self.limpar_preview()

        self.preview_layer = QgsVectorLayer(
            "Polygon?crs=EPSG:4674",
            "Coleta Rural - Preview",
            "memory"
        )

        provider = self.preview_layer.dataProvider()

        pontos = list(self.vertices)

        if pontos[0] != pontos[-1]:
            pontos.append(pontos[0])

        geometria = QgsGeometry.fromPolygonXY(
            [pontos]
        )

        feicao = QgsFeature()

        feicao.setGeometry(
            geometria
        )

        provider.addFeature(
            feicao
        )

        self.preview_layer.updateExtents()

        QgsProject.instance().addMapLayer(
            self.preview_layer
        )

        symbol = self.preview_layer.renderer().symbol()

        symbol.setColor(
            QtGui.QColor(255, 0, 0, 30)
        )

        symbol.symbolLayer(0).setStrokeColor(
            QtGui.QColor(255, 0, 0)
        )

        symbol.symbolLayer(0).setStrokeWidth(
            0.8
        )

        self.preview_layer.triggerRepaint()

        canvas = self.iface.mapCanvas()

        canvas.setExtent(
            self.preview_layer.extent()
        )

        canvas.refresh()

    def visualizar_imovel(self):

        if len(self.vertices) < 3:

            QMessageBox.warning(
                self,
                "Coleta Rural",
                "Nenhum vértice válido encontrado."
            )

            return

        try:

            self._construir_preview()

            self.btnSalvar.setEnabled(True)

        except Exception as erro:

            QMessageBox.critical(
                self,
                "Erro",
                str(erro)
            )

    def abrir_configuracoes(self):

        dlg = ConfiguracoesDialog(self)

        if dlg.exec():

            self.carregar_camadas_permitidas()

    def _obter_camada_destino(self):

        nome_camada = self.cmbCamada.currentText()

        if not nome_camada:

            QMessageBox.warning(
                self,
                "Coleta Rural",
                "Selecione uma camada de destino."
            )

            return None

        layers = QgsProject.instance().mapLayersByName(
            nome_camada
        )

        if not layers:

            QMessageBox.warning(
                self,
                "Coleta Rural",
                "Camada não encontrada."
            )

            return None

        layer = layers[0]

        if layer.isEditable():

            QMessageBox.warning(
                self,
                "Coleta Rural",
                (
                    "A camada selecionada está em modo de edição.\n\n"
                    "Salve ou descarte as alterações antes de continuar."
                )
            )

            return None

        return layer

    def _salvar_feature(self, layer):

        layer.startEditing()

        pontos = list(self.vertices)

        if pontos[0] != pontos[-1]:
            pontos.append(pontos[0])

        geometria = QgsGeometry.fromPolygonXY(
            [pontos]
        )

        feicao = QgsFeature(
            layer.fields()
        )

        feicao.setGeometry(
            geometria
        )

        campos = layer.fields().names()

        if "CIR" in campos:
            feicao["CIR"] = self.cir

        if "Imóvel" in campos:
            feicao["Imóvel"] = self.imovel

        if "Matrícula" in campos:
            feicao["Matrícula"] = self.matricula

        if "Município" in campos:
            feicao["Município"] = self.municipio

        if "UF" in campos:
            feicao["UF"] = self.uf

        if "Declarante" in campos:
            feicao["Declarante"] = self.declarante

        if "CPF/CNPJ" in campos:
            feicao["CPF/CNPJ"] = self.cpf

        if "OBS" in campos:
            feicao["OBS"] = "Importado pelo Coleta Rural"

        if "Área" in campos:

            area_limpa = (
                self.area
                .replace("ha", "")
                .replace(" ", "")
                .replace(",", ".")
            )

            try:
                feicao["Área"] = float(area_limpa)
            except Exception:
                feicao["Área"] = 0.0

        layer.addFeature(feicao)

        if not layer.commitChanges():

            raise Exception(
                "Não foi possível salvar a feição."
            )

        layer.triggerRepaint()

    def salvar_camada(self):

        if not self.vertices:

            QMessageBox.warning(
                self,
                "Coleta Rural",
                "Primeiro visualize o imóvel no mapa."
            )

            return

        layer = self._obter_camada_destino()

        if layer is None:
            return

        # so aceita o CIR se a mascara estiver completamente preenchida
        # (xxx.xxx.xxx.xxx-x); incompleto ou vazio é tratado como em branco
        self.cir = (
            self.txtCirColetaRural.text().strip()
            if self.txtCirColetaRural.hasAcceptableInput()
            else ""
        )

        self.matricula = self.txtMatriculaColetaRural.text().strip()

        try:

            self._salvar_feature(layer)

            self.limpar_preview()

            self.vertices = []

            self.lblImovel.setText("-")
            self.lblMunicipio.setText("-")
            self.lblDeclarante.setText("-")
            self.lblArea.setText("-")
            self.txtCirColetaRural.clear()
            self.txtMatriculaColetaRural.clear()

            self.imovel = ""
            self.municipio = ""
            self.uf = ""
            self.area = ""
            self.declarante = ""
            self.cpf = ""
            self.cir = ""
            self.matricula = ""

            self.btnSalvar.setEnabled(False)

            QMessageBox.information(
                self,
                "Coleta Rural",
                "Imóvel importado com sucesso."
            )

        except Exception as erro:

            try:
                layer.rollBack()
            except Exception as erro_rollback:
                print(f"Erro ao executar rollback: {erro_rollback}")

            QMessageBox.critical(
                self,
                "Erro",
                str(erro)
            )

    # ------------------------------------------------------------------
    # Memorial Genérico (memoriais fora do padrão Coleta Rural)
    # ------------------------------------------------------------------

    def selecionar_pdf_manual(self):

        arquivo, _ = QFileDialog.getOpenFileName(
            self,
            "Selecionar Memorial",
            "",
            "Arquivos PDF (*.pdf)"
        )

        if not arquivo:
            return

        try:

            reader = PdfReader(arquivo)

            texto = ""

            for pagina in reader.pages:

                conteudo = pagina.extract_text()

                if conteudo:
                    texto += conteudo + "\n"

            self.txtColarTexto.setPlainText(texto)

        except Exception as erro:

            QMessageBox.critical(
                self,
                "Erro",
                f"Não foi possível ler o PDF.\n\n{erro}"
            )

    def _extrair_anel_de_geometria(self, geom):
        """Extrai o anel externo (lista de QgsPointXY) de uma geometria de
        polígono. Também aceita uma linha FECHADA (primeiro vértice igual
        ao último) como se fosse um polígono — comum em arquivos DXF, onde
        o contorno de um imóvel costuma vir como uma polilinha fechada
        (LWPOLYLINE), não como um polígono de verdade."""

        if geom is None or geom.isEmpty():
            return None

        tipo = geom.type()

        if tipo == QgsWkbTypes.GeometryType.PolygonGeometry:

            if geom.isMultipart():

                poligonos = geom.asMultiPolygon()

                if not poligonos or not poligonos[0]:
                    return None

                return poligonos[0][0]

            poligono = geom.asPolygon()

            return poligono[0] if poligono else None

        if tipo == QgsWkbTypes.GeometryType.LineGeometry:

            if geom.isMultipart():

                linhas = geom.asMultiPolyline()
                linha = linhas[0] if linhas else None

            else:
                linha = geom.asPolyline()

            if linha and len(linha) >= 3 and linha[0] == linha[-1]:
                return linha

        return None

    def _carregar_poligono_de_arquivo(self, caminho):
        """Procura o primeiro polígono (ou contorno fechado) válido no
        arquivo, considerando que o arquivo pode ter mais de uma
        sub-camada (ex.: pastas diferentes num KML, ou um DXF com várias
        camadas de desenho). Retorna (feicao, camada, anel) ou
        (None, None, None) se nada for encontrado."""

        detalhes = QgsProviderRegistry.instance().querySublayers(caminho)

        if detalhes:
            candidatos = [
                (info.uri(), info.name(), info.providerKey())
                for info in detalhes
            ]
        else:
            candidatos = [(caminho, "geometria", "ogr")]

        for uri, nome, provider_key in candidatos:

            camada = QgsVectorLayer(uri, nome, provider_key)

            if not camada.isValid():
                continue

            for feicao in camada.getFeatures():

                anel = self._extrair_anel_de_geometria(feicao.geometry())

                if anel:
                    return feicao, camada, anel

        return None, None, None

    def _extrair_imagens_pdf(self, caminho):
        """Extrai todas as imagens embutidas de um PDF — um scan de
        planta/croqui costuma vir num PDF de página inteira em imagem,
        sem texto extraível nenhum (o mesmo tipo de arquivo que a aba
        "Memorial Coleta Rural" já avisa não ter texto). Devolve uma
        lista de (índice da página, QPixmap), na ordem em que aparecem
        no arquivo."""

        leitor = PdfReader(caminho)
        imagens = []

        for indice_pagina, pagina in enumerate(leitor.pages):
            for imagem_pagina in pagina.images:

                pixmap = QtGui.QPixmap()

                if pixmap.loadFromData(imagem_pagina.data):
                    imagens.append((indice_pagina, pixmap))

        return imagens

    def anexar_imagem_referencia(self):
        """Carrega uma imagem (foto/scan da planta ou croqui, ou um PDF
        contendo uma) no painel de visualização à direita da janela
        (expandindo-a se preciso) — sem tocar no projeto QGIS nem no
        canvas principal, para que a imagem nunca "exploda" o zoom do
        mapa (o que acontecia quando ela era carregada como camada
        raster sem georreferenciamento: a extensão em pixels da imagem
        era interpretada como se fosse graus/metros no canvas).
        Expandir a janela em vez de criar uma janela separada deixa
        claro, lado a lado, qual imagem foi selecionada."""

        caminho, _ = QFileDialog.getOpenFileName(
            self,
            "Anexar imagem de referência (planta/croqui)",
            "",
            "Imagens e PDF (*.jpg *.jpeg *.png *.tif *.tiff *.bmp *.pdf)"
        )

        if not caminho:
            return

        if caminho.lower().endswith(".pdf"):

            try:
                imagens = self._extrair_imagens_pdf(caminho)
            except Exception as erro:

                QMessageBox.critical(
                    self,
                    "Coleta Rural",
                    f"Não foi possível ler esse PDF.\n\n{erro}"
                )

                return

            if not imagens:

                QMessageBox.critical(
                    self,
                    "Coleta Rural",
                    "Esse PDF não tem nenhuma imagem embutida."
                )

                return

            if len(imagens) == 1:
                pixmap_escolhido = imagens[0][1]
            else:

                dialogo = _DialogoEscolherImagemPdf(imagens, self)

                if dialogo.exec() != QtWidgets.QDialog.DialogCode.Accepted:
                    return

                pixmap_escolhido = next(
                    pixmap for indice, pixmap in imagens
                    if indice == dialogo.indice_pagina_escolhido
                )

            self.painelPlanta.carregar_pixmap(pixmap_escolhido)

        elif not self.painelPlanta.carregar_imagem(caminho):

            QMessageBox.critical(
                self,
                "Coleta Rural",
                "Não foi possível carregar essa imagem."
            )

            return

        self.resize(self._largura_com_painel_planta, self.height())
        self.painelPlanta.setVisible(True)
        self.btnLimparImagemPlanta.setVisible(True)

        # o encaixe feito dentro de carregar_pixmap() aconteceu com o
        # painel ainda no tamanho antigo (a janela só expandiu agora,
        # na linha acima) — reajusta depois que a fila de eventos
        # processar o redimensionamento/exibição, com o tamanho final
        # de verdade
        QtCore.QTimer.singleShot(
            0, self.painelPlanta.ajustar_zoom_para_caber
        )

        self.btnDesenharPoligonoPlanta.setEnabled(True)

        QMessageBox.information(
            self,
            "Coleta Rural",
            "Imagem carregada no painel à direita. Você pode usá-la só "
            "para consulta visual (role a roda do mouse sobre ela para "
            "dar zoom), ou clicar em \"Desenhar Polígono na Planta\" "
            "para marcar os vértices diretamente sobre o desenho, "
            "calibrando a partir de um trecho já conhecido do memorial."
        )

    def limpar_imagem_planta(self):
        """Desfaz o que "Anexar Imagem (Planta)" fez: remove a imagem
        e os marcadores, esconde o painel e o próprio botão "Limpar
        Imagem", e volta a janela ao tamanho padrão — sem o campo da
        planta sobrando vazio depois de removê-la. Cancela também
        qualquer calibração/desenho em andamento sobre ela, já que os
        marcadores clicados deixam de fazer sentido sem a imagem."""

        self._modo_clique_planta = None
        self._marcadores_calibracao_planta = []
        self._calibracao_planta_atual = None
        self._converter_planta = None
        self._vertices_desenhados_planta_utm = []

        if not self._ultimos_pares_utm and not self._ultimos_pares_geograficos:
            self.grpUtmManual.setVisible(False)

        self.painelPlanta.limpar_imagem()
        self.painelPlanta.setVisible(False)
        self.btnLimparImagemPlanta.setVisible(False)
        self.resize(self._largura_padrao_janela, self.height())

        self.btnDesenharPoligonoPlanta.setEnabled(False)

    def iniciar_desenho_sobre_planta(self):
        """Passo 1 do fluxo "Desenhar Polígono na Planta": pede o
        primeiro dos dois cliques que marcam um trecho já conhecido
        (com azimute e distância informados no memorial) desenhado na
        planta — usado para calibrar a conversão clique→coordenada real
        do resto do desenho (ver coordenadas.calibrar_transformacao_planta)."""

        self._marcadores_calibracao_planta = []
        self._calibracao_planta_atual = None
        self._ultimos_pares_utm = None
        self._ultimos_pares_geograficos = None
        self._converter_planta = None
        self._vertices_desenhados_planta_utm = []

        self.painelPlanta.limpar_marcadores()
        self.grpUtmManual.setVisible(False)

        QMessageBox.information(
            self,
            "Coleta Rural",
            "Clique no vértice inicial de um trecho já conhecido "
            "(com azimute e distância informados no memorial) "
            "desenhado na planta."
        )

        self._modo_clique_planta = "calibracao_1"

    def _ao_clicar_planta(self, ponto_cena):

        # em "calibracao_ajuste" um clique em área vazia não faz nada
        # — só arrastar os dois marcadores já colocados (tratado
        # direto no _VisualizadorPlanta) ou clicar com o botão direito
        # para confirmar e seguir para o formulário de azimute/distância
        if self._modo_clique_planta in (None, "calibracao_ajuste"):
            return

        ponto = QgsPointXY(ponto_cena.x(), ponto_cena.y())

        if self._modo_clique_planta in ("calibracao_1", "calibracao_2"):
            # arrastáveis, para dar tempo de ajustar a posição exata
            # antes de informar o azimute/distância reais — mas não
            # excluíveis, já que o desenho precisa exatamente desses
            # 2 pontos para calibrar a transformação
            marcador = self.painelPlanta.adicionar_marcador(
                ponto_cena, arrastavel=True
            )
            self._marcadores_calibracao_planta.append(marcador)
        else:  # "vertices"
            self.painelPlanta.adicionar_marcador(ponto_cena, removivel=True)

        if self._modo_clique_planta == "calibracao_1":
            self._clique_calibracao_1_planta(ponto)
        elif self._modo_clique_planta == "calibracao_2":
            self._clique_calibracao_2_planta(ponto)

    def _ao_clicar_direito_planta(self):

        if self._modo_clique_planta == "vertices":
            self._finalizar_desenho_planta()
        elif self._modo_clique_planta == "calibracao_ajuste":
            self._confirmar_calibracao_planta()

    def _ao_cancelar_planta(self):

        if self._modo_clique_planta is None:
            return

        self._modo_clique_planta = None
        self._marcadores_calibracao_planta = []
        self._calibracao_planta_atual = None
        self.painelPlanta.limpar_marcadores()

        if not self._ultimos_pares_utm and not self._ultimos_pares_geograficos:
            self.grpUtmManual.setVisible(False)

        QMessageBox.information(
            self,
            "Coleta Rural",
            "Desenho do polígono cancelado."
        )

    def _clique_calibracao_1_planta(self, ponto):

        QMessageBox.information(
            self,
            "Coleta Rural",
            "Agora clique no vértice final desse mesmo trecho."
        )

        self._modo_clique_planta = "calibracao_2"

    def _clique_calibracao_2_planta(self, ponto):

        QMessageBox.information(
            self,
            "Coleta Rural",
            "Se precisar, arraste os dois pontos marcados para ajustar "
            "a posição exata em que foram clicados. Quando estiver "
            "pronto, clique com o botão direito do mouse para informar "
            "o azimute e a distância reais desse trecho."
        )

        self._modo_clique_planta = "calibracao_ajuste"

    def _confirmar_calibracao_planta(self):

        self._modo_clique_planta = None

        pontos_calibracao = [
            QgsPointXY(pos.x(), pos.y())
            for pos in (
                self.painelPlanta.posicao_marcador(item)
                for item in self._marcadores_calibracao_planta
            )
        ]

        # não-modal (show(), em vez de exec_()) para a planta continuar
        # respondendo a zoom/pan enquanto o formulário fica aberto ao
        # lado — muitas plantas têm o próprio azimute e distância
        # anotados no desenho, e a pessoa precisa poder ler essa
        # informação na imagem sem a janela travar. Mantém uma
        # referência em self enquanto o formulário está aberto, para
        # o objeto Python não ser descartado antes do C++ (e o
        # callback de "finished" ainda encontrar o dialogo válido).
        dialogo = _DialogoCalibracaoPlanta(self)
        self._dialogo_calibracao_planta = dialogo

        dialogo.finished.connect(
            lambda resultado: self._ao_fechar_dialogo_calibracao_planta(
                dialogo, resultado, pontos_calibracao
            )
        )
        dialogo.show()

    def _ao_fechar_dialogo_calibracao_planta(
        self, dialogo, resultado, pontos_calibracao
    ):

        self._dialogo_calibracao_planta = None

        if resultado != QtWidgets.QDialog.DialogCode.Accepted:
            return

        try:

            # todos os campos têm máscara de entrada agora, com "0"
            # como caractere de preenchimento vazio — displayText() é o
            # que reflete essa máscara (text() "esconde" posições que
            # ainda estão no valor de preenchimento, mesmo quando a
            # pessoa realmente digitou um "0" ali, então não serve para
            # ler o valor).
            if dialogo.rdoUtm.isChecked():

                # máscara UTM usa "." como separador de milhar e ","
                # como decimal (padrão brasileiro)
                valor1 = float(
                    dialogo.txtCoord1.displayText()
                    .replace(".", "").replace(",", ".")
                )
                valor2 = float(
                    dialogo.txtCoord2.displayText()
                    .replace(".", "").replace(",", ".")
                )

            else:
                valor1 = coordenadas.valor_coordenada_para_decimal(
                    dialogo.txtCoord1.displayText()
                )
                valor2 = coordenadas.valor_coordenada_para_decimal(
                    dialogo.txtCoord2.displayText()
                )

            azimute = coordenadas.valor_coordenada_para_decimal(
                dialogo.txtAzimute.displayText()
            )
            distancia = float(
                dialogo.txtDistancia.text().strip().replace(",", ".")
            )

        except ValueError as erro:

            QMessageBox.critical(
                self,
                "Coleta Rural",
                f"Não foi possível interpretar os dados digitados.\n\n{erro}"
            )

            return

        utm = dialogo.rdoUtm.isChecked()
        datum = dialogo.cmbDatum.currentText()

        self._calibracao_planta_atual = {
            "valor1": valor1,
            "valor2": valor2,
            "azimute": azimute,
            "distancia": distancia,
            "utm": utm,
            "fuso": (
                int(dialogo.cmbFuso.currentText().rstrip("Ss"))
                if utm else None
            ),
        }
        self._ultimos_pares_utm = None
        self._ultimos_pares_geograficos = None

        # mantém o combo "Datum" (compartilhado com a extração de
        # texto) sincronizado com o que foi escolhido no formulário,
        # sem disparar o recálculo duas vezes — o próprio
        # _recalibrar_planta_com_datum abaixo já faz esse cálculo
        indice_datum = self.cmbDatumManual.findText(datum)

        if indice_datum >= 0:
            bloqueado = self.cmbDatumManual.blockSignals(True)
            self.cmbDatumManual.setCurrentIndex(indice_datum)
            self.cmbDatumManual.blockSignals(bloqueado)

        if not self._recalibrar_planta_com_datum(datum):
            self._calibracao_planta_atual = None
            return

        # o combo de datum fica visível (e não é mais escondido ao
        # finalizar o desenho) justamente para poder ser corrigido
        # DEPOIS de já ver o polígono desenhado sobre a imagem de
        # satélite — trocar o datum aqui recalcula o desenho inteiro
        # na hora, sem precisar clicar nos pontos de novo
        self.grpUtmManual.setVisible(True)
        self.grpUtmManual.setTitle(
            "Desenho da planta calibrado — confirme o datum"
        )
        self.lblFusoManual.setVisible(False)
        self.cmbFusoManual.setVisible(False)
        self.lblDatumManual.setVisible(True)
        self.cmbDatumManual.setVisible(True)

        QMessageBox.information(
            self,
            "Coleta Rural",
            "Calibração pronta. Agora clique em cada vértice do "
            "polígono na planta, em ordem. Quando terminar, clique com "
            "o botão direito do mouse (ou pressione Esc)."
        )

        self._modo_clique_planta = "vertices"

    def _resolver_ponto_inicial_planta(self, valor1, valor2, utm, fuso, datum):
        """Resolve a coordenada real (em UTM) do primeiro ponto de
        calibração e o CRS UTM de trabalho, a partir dos valores brutos
        digitados no formulário de calibração e do datum atualmente
        escolhido — separado do resto do cálculo para poder ser refeito
        só com um datum novo (ver _recalibrar_planta_com_datum), sem
        reabrir o formulário nem clicar nos pontos de novo.

        Devolve (ponto_inicial_utm, crs_utm) ou (None, None) se algo
        der errado (já mostra o erro nesse caso)."""

        if utm:

            try:
                crs_utm = coordenadas.montar_crs_utm(fuso, datum)
            except ValueError as erro:
                QMessageBox.critical(self, "Coleta Rural", str(erro))
                return None, None

            return QgsPointXY(valor1, valor2), crs_utm

        try:
            ponto_inicial_geo = coordenadas.transformar_pontos_geograficos(
                [QgsPointXY(valor1, valor2)], datum
            )[0]
        except ValueError as erro:
            QMessageBox.critical(self, "Coleta Rural", str(erro))
            return None, None

        fuso_auto = max(18, min(25, int((valor1 + 180) // 6) + 1))
        crs_utm = coordenadas.montar_crs_utm(fuso_auto, "SIRGAS2000")

        ponto_inicial_utm = coordenadas.transformar_pontos(
            [ponto_inicial_geo],
            QgsCoordinateReferenceSystem("EPSG:4674"),
            crs_utm
        )[0]

        return ponto_inicial_utm, crs_utm

    def _recalibrar_planta_com_datum(self, datum):
        """Reconstrói a calibração e reconverte todos os vértices já
        marcados na planta (calibração + vértices do polígono) usando
        o datum passado — chamado tanto ao confirmar a calibração pela
        primeira vez quanto sempre que o operador troca o datum depois
        (mesmo já com o polígono desenhado e visualizado no mapa), para
        corrigi-lo comparando com a imagem de satélite sem ter que
        clicar tudo de novo. Clicar em "Visualizar no Mapa" outra vez
        depois de trocar reflete a correção no croqui."""

        dados = self._calibracao_planta_atual

        if dados is None:
            return False

        self._crs_geografico_planta = QgsCoordinateReferenceSystem(
            "EPSG:4674"
        )

        ponto_inicial_utm, crs_utm = self._resolver_ponto_inicial_planta(
            dados["valor1"], dados["valor2"], dados["utm"], dados["fuso"],
            datum
        )

        if ponto_inicial_utm is None:
            return False

        self._crs_utm_planta = crs_utm

        pontos_calibracao = [
            QgsPointXY(pos.x(), pos.y())
            for pos in (
                self.painelPlanta.posicao_marcador(item)
                for item in self._marcadores_calibracao_planta
            )
        ]

        try:

            self._converter_planta = coordenadas.calibrar_transformacao_planta(
                pontos_calibracao[0],
                pontos_calibracao[1],
                dados["azimute"],
                dados["distancia"],
                (ponto_inicial_utm.x(), ponto_inicial_utm.y())
            )

        except ValueError as erro:

            QMessageBox.critical(self, "Coleta Rural", str(erro))

            return False

        # já sabemos a coordenada real dos dois pontos de calibração —
        # não precisa clicar neles de novo
        self._vertices_desenhados_planta_utm = [
            (ponto_inicial_utm.x(), ponto_inicial_utm.y()),
            self._converter_planta(pontos_calibracao[1])
        ]

        vertices_utm = list(self._vertices_desenhados_planta_utm[:2]) + [
            self._converter_planta(QgsPointXY(ponto.x(), ponto.y()))
            for ponto in self.painelPlanta.pontos_marcadores_removiveis()
        ]

        pontos_geograficos = coordenadas.transformar_pontos(
            [QgsPointXY(este, norte) for este, norte in vertices_utm],
            self._crs_utm_planta,
            self._crs_geografico_planta
        )

        self._finalizar_vertices(pontos_geograficos)

        return True

    def _finalizar_desenho_planta(self):

        self._modo_clique_planta = None

        # a lista final é recalculada a partir da posição ATUAL de cada
        # marcador removível (reflete qualquer arrasto feito depois do
        # clique original, e já não inclui os que foram excluídos) — os
        # dois pontos de calibração entram fixos, na frente
        vertices_utm = list(self._vertices_desenhados_planta_utm[:2]) + [
            self._converter_planta(QgsPointXY(ponto.x(), ponto.y()))
            for ponto in self.painelPlanta.pontos_marcadores_removiveis()
        ]

        if len(vertices_utm) < 3:

            QMessageBox.warning(
                self,
                "Coleta Rural",
                "É preciso marcar pelo menos 3 vértices para formar um "
                "polígono. O desenho foi cancelado."
            )

            return

        pontos_geograficos = coordenadas.transformar_pontos(
            [QgsPointXY(este, norte) for este, norte in vertices_utm],
            self._crs_utm_planta,
            self._crs_geografico_planta
        )

        # o combo "Datum" continua visível depois de finalizar (não é
        # mais escondido aqui) — assim dá pra corrigir o datum
        # comparando com a imagem de satélite depois de visualizar o
        # polígono no mapa, sem precisar refazer os cliques
        self._finalizar_vertices(pontos_geograficos)

    def selecionar_arquivo_geometria_manual(self):

        arquivo, _ = QFileDialog.getOpenFileName(
            self,
            "Anexar arquivo de geometria",
            "",
            "Arquivos de geometria (*.kml *.kmz *.geojson *.json *.shp *.dxf)"
            ";;KML (*.kml *.kmz)"
            ";;GeoJSON (*.geojson *.json)"
            ";;Shapefile (*.shp)"
            ";;DXF (*.dxf)"
        )

        if not arquivo:
            return

        try:
            feicao, camada, anel = self._carregar_poligono_de_arquivo(arquivo)
        except Exception as erro:

            QMessageBox.critical(
                self,
                "Coleta Rural",
                f"Não foi possível ler o arquivo.\n\n{erro}"
            )

            return

        if anel is None:

            QMessageBox.warning(
                self,
                "Coleta Rural",
                "Nenhum polígono (ou contorno fechado) foi encontrado no "
                "arquivo."
            )

            return

        pontos = [QgsPointXY(p) for p in anel]

        if len(pontos) > 1 and pontos[0] == pontos[-1]:
            pontos = pontos[:-1]

        if len(pontos) < 3:

            QMessageBox.warning(
                self,
                "Coleta Rural",
                "O contorno encontrado no arquivo tem menos de 3 vértices."
            )

            return

        self.vertices = []
        self.lblAvisoFormatoManual.setText("")
        self.tabelaCoordenadasManual.setRowCount(0)
        self.txtAreaManual.clear()
        self._ultimos_pares_utm = None
        self._ultimos_pares_geograficos = None
        self._calibracao_planta_atual = None

        crs_origem = camada.crs()

        try:

            if crs_origem.isValid():

                self.grpUtmManual.setVisible(False)

                vertices_4674 = coordenadas.transformar_pontos(
                    pontos,
                    crs_origem,
                    QgsCoordinateReferenceSystem(coordenadas.CRS_GEOGRAFICO)
                )

                self._finalizar_vertices(vertices_4674)

            else:

                # arquivo sem sistema de referência definido (comum em
                # DXF, que só guarda coordenadas cruas) — classifica pela
                # magnitude, igual já se faz para texto colado
                tipo = coordenadas.classificar_par(pontos[0].x(), pontos[0].y())

                if tipo == "utm":

                    self._fuso_veio_do_texto = False

                    self._tentar_vertices_utm(
                        [(p.x(), p.y()) for p in pontos],
                        "O arquivo não tem sistema de referência definido "
                        "(comum em DXF). Selecione o fuso e o datum das "
                        "coordenadas:"
                    )

                    if not self.vertices:
                        return

                else:

                    self.grpUtmManual.setVisible(False)
                    self._finalizar_vertices(list(pontos))

        except Exception as erro:

            self.vertices = []

            QMessageBox.critical(
                self,
                "Coleta Rural",
                f"Não foi possível interpretar as coordenadas do "
                f"arquivo.\n\n{erro}"
            )

            return

        if not self.txtImovelManual.text().strip():

            campos = feicao.fields().names()

            for campo_nome in ("Name", "name", "nome", "NOME", "Nome"):

                if campo_nome in campos:

                    valor = feicao[campo_nome]

                    if valor:
                        self.txtImovelManual.setText(str(valor))

                    break

        QMessageBox.information(
            self,
            "Coleta Rural",
            f"{len(self.vertices)} vértices lidos do arquivo."
        )

    def processar_texto_manual(self):

        texto = self.txtColarTexto.toPlainText()

        if not texto.strip():

            QMessageBox.warning(
                self,
                "Coleta Rural",
                "Cole o texto do memorial antes de extrair os dados."
            )

            return

        self._detectar_fuso_datum(texto)
        self.extrair_dados_manual(texto)
        self.extrair_vertices_manual(texto)

    def _formatar_cpf_cnpj(self, campo, texto):
        """Formata um campo de CPF/CNPJ automaticamente enquanto o
        operador digita: até 11 dígitos formata como CPF
        (XXX.XXX.XXX-XX); ao ultrapassar 11 dígitos, passa a formatar
        como CNPJ (XX.XXX.XXX/XXXX-XX), até o limite de 14 dígitos."""

        digitos = re.sub(r"\D", "", texto)[:14]

        if len(digitos) <= 11:

            formatado = digitos[:3]

            if len(digitos) > 3:
                formatado += f".{digitos[3:6]}"

            if len(digitos) > 6:
                formatado += f".{digitos[6:9]}"

            if len(digitos) > 9:
                formatado += f"-{digitos[9:11]}"

        else:

            formatado = digitos[:2]
            formatado += f".{digitos[2:5]}"

            if len(digitos) > 5:
                formatado += f".{digitos[5:8]}"

            if len(digitos) > 8:
                formatado += f"/{digitos[8:12]}"

            if len(digitos) > 12:
                formatado += f"-{digitos[12:14]}"

        campo.blockSignals(True)
        campo.setText(formatado)
        campo.setCursorPosition(len(formatado))
        campo.blockSignals(False)

    def _cpf_cnpj_completo(self, texto):
        """True se o texto tiver exatamente 11 dígitos (CPF) ou 14
        dígitos (CNPJ) — qualquer outra quantidade é tratada como
        incompleto (inclusive vazio)."""

        digitos = re.sub(r"\D", "", texto)

        return len(digitos) in (11, 14)

    def limpar_manual(self):

        self.limpar_preview()

        self.vertices = []
        self._ultimos_pares_utm = None
        self._ultimos_pares_geograficos = None
        self._calibracao_planta_atual = None
        self._fuso_veio_do_texto = False
        self._datum_veio_do_texto = False

        self.txtColarTexto.clear()
        self.txtImovelManual.clear()
        self.txtMunicipioManual.clear()
        self.txtUfManual.clear()
        self.txtDeclaranteManual.clear()
        self.txtCpfManual.clear()
        self.txtCirManual.clear()
        self.txtMatriculaManual.clear()
        self.txtAreaManual.clear()
        self.tabelaCoordenadasManual.setRowCount(0)
        self.lblAvisoFormatoManual.setText("")
        self.grpUtmManual.setVisible(False)
        self.lblFusoManual.setVisible(True)
        self.cmbFusoManual.setVisible(True)
        self.cmbFusoManual.setCurrentIndex(0)
        self.cmbDatumManual.setCurrentIndex(0)

        self.imovel = ""
        self.municipio = ""
        self.uf = ""
        self.area = ""
        self.declarante = ""
        self.cpf = ""
        self.cir = ""
        self.matricula = ""

        self.btnSalvarManual.setEnabled(False)

    def _detectar_fuso_datum(self, texto):

        self._fuso_veio_do_texto = False
        self._datum_veio_do_texto = False

        encontro_fuso = re.search(
            # tolera o que costuma aparecer entre "fuso" e o número por
            # causa de OCR: hífen/travessão, "nº"/"n°", dois-pontos etc.
            r"fuso[\s\-–—nº°o:.]*(\d{1,2})\s*(N|S)?",
            texto,
            re.IGNORECASE
        )

        if encontro_fuso:

            numero = encontro_fuso.group(1)
            hemisferio = (encontro_fuso.group(2) or "S").upper()

            indice = self.cmbFusoManual.findText(f"{numero}{hemisferio}")

            if indice >= 0:
                self.cmbFusoManual.setCurrentIndex(indice)
                self._fuso_veio_do_texto = True

        if re.search(r"SAD\s*[\-–—]?\s*69", texto, re.IGNORECASE):

            indice = self.cmbDatumManual.findText("SAD69")

            if indice >= 0:
                self.cmbDatumManual.setCurrentIndex(indice)
                self._datum_veio_do_texto = True

        elif re.search(r"SIRGAS\s*2000", texto, re.IGNORECASE):

            indice = self.cmbDatumManual.findText("SIRGAS2000")

            if indice >= 0:
                self.cmbDatumManual.setCurrentIndex(indice)
                self._datum_veio_do_texto = True

        elif re.search(r"WGS[\s\-–—]?84", texto, re.IGNORECASE):

            indice = self.cmbDatumManual.findText("WGS84")

            if indice >= 0:
                self.cmbDatumManual.setCurrentIndex(indice)
                self._datum_veio_do_texto = True

    def _perguntar_fuso_datum(self, mensagem=None):
        """Pergunta o fuso e o datum ao operador quando não é possível
        identificá-los automaticamente (texto colado sem essa informação,
        ou arquivo de geometria sem sistema de referência definido, como é
        comum em DXF), em vez de usar silenciosamente o que já estiver
        selecionado (que pode estar errado ou ter ficado de uma
        importação anterior)."""

        if mensagem is None:
            mensagem = (
                "O memorial não informou o fuso UTM no texto colado.\n"
                "Selecione o fuso correto:"
            )

        fusos = [
            self.cmbFusoManual.itemText(i)
            for i in range(self.cmbFusoManual.count())
        ]

        fuso, ok = QInputDialog.getItem(
            self,
            "Fuso UTM não identificado",
            mensagem,
            fusos,
            max(self.cmbFusoManual.currentIndex(), 0),
            False
        )

        if not ok:
            return False

        indice_fuso = self.cmbFusoManual.findText(fuso)

        if indice_fuso >= 0:
            self.cmbFusoManual.setCurrentIndex(indice_fuso)

        datuns = [
            self.cmbDatumManual.itemText(i)
            for i in range(self.cmbDatumManual.count())
        ]

        datum, ok = QInputDialog.getItem(
            self,
            "Datum",
            "Confirme o datum (padrão SIRGAS2000):",
            datuns,
            max(self.cmbDatumManual.currentIndex(), 0),
            False
        )

        if not ok:
            return False

        indice_datum = self.cmbDatumManual.findText(datum)

        if indice_datum >= 0:
            self.cmbDatumManual.setCurrentIndex(indice_datum)

        self._fuso_veio_do_texto = True

        return True

    def _extrair_campo_manual(self, texto, aliases):
        """Procura, linha por linha, uma que comece com um dos
        aliases (sem diferenciar maiúsculas/minúsculas nem acento —
        tolera OCR que apaga acento, ex.: "Municipio" por
        "Município"), e devolve o que vier depois do rótulo (e do
        ":", se houver) como o valor do campo.

        Uma linha em que só o rótulo aparece, sem nenhum valor depois
        (ex.: "Imóvel:" sozinho numa linha, comum quando os rótulos e
        os valores de um memorial vêm em blocos separados — ver
        _extrair_bloco_identificacao_manual) não conta como valor
        encontrado: sem essa checagem, o "valor" capturado acabava
        sendo só o próprio ":" (o grupo (.+) do regex antigo, exigindo
        pelo menos 1 caractere, "devolvia" o ":" opcional que tinha
        acabado de consumir para conseguir casar com alguma coisa)."""

        # do mais longo para o mais curto: numa linha como "Município
        # sede:", o alias "MUNICÍPIO SEDE" tem que ganhar de "MUNICÍPIO"
        # sozinho — senão, ao rejeitar "MUNICÍPIO SEDE" por não ter
        # valor nenhum depois, cair para o alias mais curto "MUNICÍPIO"
        # faria capturar "sede:" (o resto do próprio rótulo) como se
        # fosse o valor do campo
        aliases_normalizados = sorted(
            (_sem_acentos(alias).upper() for alias in aliases),
            key=len,
            reverse=True
        )

        for linha in texto.splitlines():

            linha = linha.strip()

            if not linha:
                continue

            linha_normalizada = _sem_acentos(linha).upper()

            def _bate_com_fronteira(alias_normalizado):
                # exige fronteira de palavra depois do alias, senão
                # "MUNICÍPIO" também "bateria" com "MUNICÍPIOS
                # ABRANGIDOS" (plural, rótulo de outra seção)
                if not linha_normalizada.startswith(alias_normalizado):
                    return False
                resto = linha_normalizada[len(alias_normalizado):]
                return not resto or not resto[0].isalnum()

            alias_correspondente = next(
                (
                    alias_normalizado
                    for alias_normalizado in aliases_normalizados
                    if _bate_com_fronteira(alias_normalizado)
                ),
                None
            )

            if alias_correspondente is None:
                continue

            # a extração de acentos preserva o comprimento da string
            # (cada letra acentuada vira 1 letra sem acento), então o
            # mesmo comprimento vale para cortar a linha original
            valor = linha[len(alias_correspondente):].strip()
            valor = valor.lstrip(":").strip()

            if not re.search(r"\w", valor, re.UNICODE):
                continue

            # trunca se houver outro rótulo "PALAVRA(S):" mais adiante
            # na mesma linha (comum em cabeçalhos com vários campos na
            # mesma linha, ex.: "Caruaru UF: PE")
            proximo_rotulo = re.search(
                r"\s+[A-ZÀ-Ý][A-ZÀ-Ý/ ]{1,30}:\s", valor
            )

            if proximo_rotulo:
                valor = valor[:proximo_rotulo.start()].strip()

            return valor

        return ""

    def _extrair_bloco_identificacao_manual(self, texto):
        """Reconhece o formato em que os rótulos de identificação
        aparecem todos juntos, sem nenhum valor na frente ("Imóvel:",
        "Município sede:", "Área total:", "Declarante:", "CPF/CNPJ:",
        cada um na sua linha), com os valores de verdade bem mais
        abaixo no texto, na mesma ordem dos rótulos, logo após o
        título "MEMORIAL DESCRITIVO" — layout comum quando o próprio
        PDF gerado pelo sistema Coleta Rural é uma imagem/scan (sem
        texto embutido) e precisa ser colado aqui depois de um OCR
        externo, que costuma achatar a tabela de identificação dessa
        forma.

        Devolve um dicionário só com as chaves que conseguiu casar
        ("imovel", "municipio", "declarante", "cpf") — {} se não
        reconhecer o padrão."""

        linhas = [linha.strip() for linha in texto.splitlines()]

        categorias_encontradas = []

        for linha in linhas:

            if not linha:

                if categorias_encontradas:
                    break

                continue

            linha_normalizada = _sem_acentos(linha).upper()
            categoria_da_linha = None

            for categoria, aliases in _CAMPOS_BLOCO_IDENTIFICACAO:

                for alias in aliases:

                    if re.fullmatch(
                        rf"{re.escape(_sem_acentos(alias).upper())}\s*:?\s*",
                        linha_normalizada
                    ):
                        categoria_da_linha = categoria
                        break

                if categoria_da_linha:
                    break

            if categoria_da_linha:
                categorias_encontradas.append(categoria_da_linha)
            elif categorias_encontradas:
                break

        # exige pelo menos 2 rótulos em sequência — um só poderia ser
        # coincidência com uma linha comum do texto
        if len(categorias_encontradas) < 2:
            return {}

        indice_titulo = None

        for i, linha in enumerate(linhas):

            if re.fullmatch(
                r"MEMORIAL\s+DESCRITIVO", _sem_acentos(linha).upper()
            ):
                indice_titulo = i
                break

        if indice_titulo is None:
            return {}

        valores = []

        for linha in linhas[indice_titulo + 1:]:

            if linha:
                valores.append(linha)

            if len(valores) == len(categorias_encontradas):
                break

        if len(valores) != len(categorias_encontradas):
            return {}

        return dict(zip(categorias_encontradas, valores))

    def _separar_municipio_uf(self, texto_municipio):

        if "-" not in texto_municipio:
            return texto_municipio, ""

        partes = [
            parte.strip()
            for parte in texto_municipio.split("-")
            if parte.strip()
        ]

        # ignora um sufixo "BR" (país), comum em textos tipo
        # "Belo Jardim - PE - BR"
        if partes and partes[-1].upper() == "BR":
            partes = partes[:-1]

        if len(partes) < 2:
            return texto_municipio, ""

        uf_candidata = partes[-1]

        # só assume UF se o último trecho for mesmo uma sigla de 2 letras;
        # evita quebrar nomes de município com hífen no meio (ex.:
        # "Lugar Carapatós, KM-84, Gravatá - PE")
        if re.fullmatch(r"[A-Za-zÀ-ÿ]{2}", uf_candidata):
            municipio = "-".join(partes[:-1]).strip()
            return municipio, uf_candidata.upper()

        return texto_municipio, ""

    def extrair_dados_manual(self, texto):

        try:

            self.txtImovelManual.setText(
                self._extrair_campo_manual(texto, ALIASES_IMOVEL)
            )

            municipio = self._extrair_campo_manual(texto, ALIASES_MUNICIPIO)
            uf = self._extrair_campo_manual(texto, ALIASES_UF)

            if not uf:
                municipio, uf = self._separar_municipio_uf(municipio)

            self.txtMunicipioManual.setText(municipio)
            self.txtUfManual.setText(uf)

            self.txtDeclaranteManual.setText(
                self._extrair_campo_manual(texto, ALIASES_DECLARANTE)
            )

            self._formatar_cpf_cnpj(
                self.txtCpfManual,
                self._extrair_campo_manual(texto, ALIASES_CPF)
            )

            cir_rotulado = self._extrair_campo_manual(texto, ALIASES_CIR)

            if cir_rotulado and PADRAO_CIR.fullmatch(cir_rotulado):

                cir = cir_rotulado

            else:

                encontro_cir = PADRAO_CIR.search(texto)
                cir = encontro_cir.group(0) if encontro_cir else ""

            self.txtCirManual.setText(cir)

            self.txtMatriculaManual.setText(
                self._extrair_campo_manual(texto, ALIASES_MATRICULA)
            )

            # se o Imóvel não foi encontrado pelo caminho normal, tenta
            # o formato "rótulos todos juntos, valores bem mais abaixo"
            # (comum quando o memorial vem de um PDF escaneado do
            # próprio Coleta Rural, colado aqui depois de OCR externo)
            # — nunca sobrescreve um campo que já tenha sido preenchido
            if not self.txtImovelManual.text().strip():

                bloco = self._extrair_bloco_identificacao_manual(texto)

                if bloco.get("imovel") and not self.txtImovelManual.text().strip():
                    self.txtImovelManual.setText(bloco["imovel"])

                if bloco.get("municipio") and not self.txtMunicipioManual.text().strip():

                    municipio_bloco, uf_bloco = self._separar_municipio_uf(
                        bloco["municipio"]
                    )
                    self.txtMunicipioManual.setText(municipio_bloco)

                    if uf_bloco and not self.txtUfManual.text().strip():
                        self.txtUfManual.setText(uf_bloco)

                if bloco.get("declarante") and not self.txtDeclaranteManual.text().strip():
                    self.txtDeclaranteManual.setText(bloco["declarante"])

                if bloco.get("cpf") and not self._cpf_cnpj_completo(self.txtCpfManual.text()):
                    self._formatar_cpf_cnpj(self.txtCpfManual, bloco["cpf"])

        except Exception as erro:

            QMessageBox.warning(
                self,
                "Aviso",
                f"Erro ao tentar extrair automaticamente os dados do imóvel:\n\n{erro}"
            )

    def _preencher_tabela_coordenadas(self, vertices, tabela=None):

        if tabela is None:
            tabela = self.tabelaCoordenadasManual

        tabela.setRowCount(len(vertices))

        for linha, ponto in enumerate(vertices):

            tabela.setItem(
                linha, 0, QTableWidgetItem(f"P{linha + 1}")
            )

            tabela.setItem(
                linha, 1, QTableWidgetItem(f"{ponto.x():.6f}")
            )

            tabela.setItem(
                linha, 2, QTableWidgetItem(f"{ponto.y():.6f}")
            )

    def _finalizar_vertices(self, vertices):

        self.vertices = vertices

        self._preencher_tabela_coordenadas(vertices)

        area_ha = coordenadas.calcular_area_hectares(vertices)

        self.txtAreaManual.setText(f"{area_ha:.4f}")

        vertice_suspeito = coordenadas.detectar_vertice_anomalo(vertices)

        if vertice_suspeito is not None:

            self.lblAvisoFormatoManual.setText(
                f"Aviso: o vértice {vertice_suspeito} parece muito mais "
                "distante dos vizinhos do que o resto do perímetro — "
                "confira se não há um dígito errado na coordenada dele "
                "antes de salvar."
            )

        if not self.txtMunicipioManual.text().strip():
            self._identificar_municipio_por_coordenada(vertices)

    def _identificar_municipio_por_coordenada(self, vertices):
        """Identifica o município/UF do imóvel a partir do centro das
        coordenadas já extraídas, consultando o serviço público de
        geocodificação reversa do OpenStreetMap (Nominatim) — a mesma
        ideia de identificação automática pela localização que o
        aplicativo oficial Coleta Rural já tem. Só entra em ação quando
        o campo Município ainda está vazio (o memorial não o informou
        no texto, ou o polígono veio só do desenho da planta).

        Precisa de internet — mesma exigência que o croqui com imagem
        de satélite e o link do Google Maps já fazem na aba "Gerar
        Memorial". Falha silenciosamente (sem popup de erro) se não
        conseguir: é um preenchimento auxiliar que economiza digitação
        quando funciona, não uma etapa obrigatória — se falhar, o campo
        continua vazio para preenchimento manual, exatamente como já
        acontecia antes dessa função existir."""

        if not vertices:
            return

        centro_x = sum(ponto.x() for ponto in vertices) / len(vertices)
        centro_y = sum(ponto.y() for ponto in vertices) / len(vertices)

        url = (
            "https://nominatim.openstreetmap.org/reverse"
            f"?format=json&lat={centro_y}&lon={centro_x}"
            "&zoom=10&addressdetails=1"
        )

        requisicao = urllib.request.Request(
            url,
            headers={"User-Agent": "ColetaRural-QGIS-Plugin/1.2.3"}
        )

        try:

            with urllib.request.urlopen(requisicao, timeout=5) as resposta:
                dados = json.loads(resposta.read().decode("utf-8"))

        except Exception:
            return

        endereco = dados.get("address", {})

        municipio = (
            endereco.get("municipality")
            or endereco.get("city")
            or endereco.get("town")
            or endereco.get("village")
            or endereco.get("county")
        )

        if municipio:
            self.txtMunicipioManual.setText(municipio)

        codigo_iso = endereco.get("ISO3166-2-lvl4", "")

        if "-" in codigo_iso and not self.txtUfManual.text().strip():
            self.txtUfManual.setText(codigo_iso.split("-")[-1])

    def _tentar_vertices_utm(self, pares_utm, mensagem_pergunta=None):

        self._ultimos_pares_geograficos = None
        self._calibracao_planta_atual = None

        self.grpUtmManual.setVisible(True)
        self.grpUtmManual.setTitle(
            "Coordenada UTM identificada — confirme o fuso"
        )
        self.lblFusoManual.setVisible(True)
        self.cmbFusoManual.setVisible(True)
        self.lblDatumManual.setVisible(True)
        self.cmbDatumManual.setVisible(True)

        if not self._fuso_veio_do_texto:

            if not self._perguntar_fuso_datum(mensagem_pergunta):
                self.vertices = []
                self._ultimos_pares_utm = None
                return

        self._ultimos_pares_utm = pares_utm

        if not self._recalcular_vertices_utm_atuais():
            return

    def _recalcular_vertices_utm_atuais(self):
        """Reconverte os últimos dados identificados (calibração da
        planta, pares UTM, ou pares geográficos — o que estiver ativo
        no momento, sempre só um dos três) usando o fuso/datum
        atualmente selecionados nos combos — chamado tanto pelo fluxo
        normal de extração/desenho quanto sempre que o operador troca
        o fuso ou o datum manualmente, para atualizar tabela/mapa/área
        na hora, sem precisar clicar em "Extrair Dados do Texto" (ou
        refazer os cliques na planta) de novo. É assim que o datum
        pode ser corrigido depois de já ver o polígono no mapa, em vez
        de ter que acertar de antemão numa pergunta antes de qualquer
        visualização."""

        datum = self.cmbDatumManual.currentText()

        if self._calibracao_planta_atual is not None:
            return self._recalibrar_planta_com_datum(datum)

        if self._ultimos_pares_geograficos:

            try:

                vertices = coordenadas.pontos_rotulados_para_vertices_4674(
                    self._ultimos_pares_geograficos
                )
                vertices = coordenadas.transformar_pontos_geograficos(
                    vertices, datum
                )

            except Exception as erro:

                self.vertices = []

                QMessageBox.critical(
                    self,
                    "Coleta Rural",
                    f"Não foi possível interpretar as coordenadas.\n\n{erro}"
                )

                return False

            self._finalizar_vertices(vertices)

            return True

        if not self._ultimos_pares_utm:
            return False

        try:

            fuso = int(self.cmbFusoManual.currentText().rstrip("Ss"))

            vertices = coordenadas.pontos_utm_para_vertices_4674(
                self._ultimos_pares_utm, fuso, datum
            )

        except Exception as erro:

            self.vertices = []

            QMessageBox.critical(
                self,
                "Coleta Rural",
                f"Não foi possível interpretar as coordenadas.\n\n{erro}"
            )

            return False

        self._finalizar_vertices(vertices)

        return True

    def _finalizar_vertices_geograficos(self, pares):
        """Converte pares (longitude, latitude) já identificados por um
        dos formatos geográficos (rotulado, estrutural por hemisfério,
        poligonal em prosa) para vértices em EPSG:4674 — ponto único
        usado pelos três formatos geográficos para não repetir essa
        lógica em cada um.

        Quando o memorial não informa o datum de origem no texto,
        assume SIRGAS2000 (padrão do combo) em vez de interromper com
        uma pergunta antes de qualquer visualização — o combo "Datum"
        fica visível e habilitado, e trocá-lo depois recalcula tabela/
        área/mapa na hora (_recalcular_vertices_utm_atuais), então o
        datum pode ser corrigido já olhando o polígono desenhado no
        mapa, em vez de ter que adivinhar de antemão."""

        self._ultimos_pares_utm = None
        self._ultimos_pares_geograficos = pares
        self._calibracao_planta_atual = None

        self.grpUtmManual.setVisible(True)
        self.grpUtmManual.setTitle(
            "Coordenada geográfica identificada — confirme o datum"
        )
        self.lblFusoManual.setVisible(False)
        self.cmbFusoManual.setVisible(False)
        self.lblDatumManual.setVisible(True)
        self.cmbDatumManual.setVisible(True)

        if not self._datum_veio_do_texto:
            self.lblAvisoFormatoManual.setText(
                "Datum não informado no memorial — assumindo SIRGAS2000. "
                "Documentos anteriores a 2005 costumam usar SAD69: "
                "confira a data do memorial e corrija o datum acima se "
                "for o caso (o mapa e a área são recalculados na hora)."
            )

        self._recalcular_vertices_utm_atuais()

    def extrair_vertices_manual(self, texto):

        self.vertices = []
        self.lblAvisoFormatoManual.setText("")
        self.tabelaCoordenadasManual.setRowCount(0)
        self.txtAreaManual.clear()
        self._ultimos_pares_utm = None
        self._ultimos_pares_geograficos = None
        self._calibracao_planta_atual = None

        # Converte coordenadas em graus-minutos-segundos escritas por
        # extenso ("8 GRAUS 37 MINUTOS 43,36 SEGUNDOS SUL") para a mesma
        # notação com símbolos (°/'/") usada por todos os extratores
        # abaixo — assim nenhum deles precisa de lógica própria para
        # reconhecer esse formato, comum em memoriais mais antigos.
        texto = coordenadas.normalizar_gms_por_extenso(texto)

        # Tenta primeiro os formatos com rótulo explícito por vértice
        # (Longitude/Latitude ou N/E) — são inequívocos, então vêm antes
        # da tabela em duas colunas, cuja heurística (procurar cabeçalhos
        # "Norte"/"Este" e ler os números depois deles) é mais frágil e
        # pode se confundir com lixo de OCR de gráficos/imagens no meio
        # do PDF antes de alcançar o texto corrido com os rótulos certos.
        pares_rotulados = coordenadas.extrair_pares_rotulados(texto)

        if len(pares_rotulados) >= 3:
            self._finalizar_vertices_geograficos(pares_rotulados)
            return

        # mesma ideia, mas sem rótulo "Longitude:/Latitude:" — coordenada
        # em graus-minutos-segundos reconhecida pela própria estrutura do
        # valor (°'") seguida de uma letra de hemisfério (S/N/E/O/W),
        # independente da frase ao redor. Comum em memoriais que também
        # descrevem azimute/distância entre vértices.
        pares_gms_hemisferio = coordenadas.extrair_pares_gms_com_hemisferio(texto)

        if len(pares_gms_hemisferio) >= 3:
            self._finalizar_vertices_geograficos(pares_gms_hemisferio)
            return

        # poligonal descrita em prosa corrida, a partir de um marco com
        # coordenada geográfica conhecida (ex.: "PARTINDO DO MARCO
        # M-13723-37, COM LATITUDE ... E LONGITUDE ..., COM AZIMUTE DE
        # ... E DISTANCIA DE ...M, [...] CHEGA AO PONTO ...; DESTE, ...")
        # — comum em memoriais mais antigos do INCRA. Já devolve
        # coordenada geográfica (longitude, latitude), diferente das
        # poligonais UTM abaixo.
        pares_poligonal_prosa = coordenadas.extrair_poligonal_azimute_prosa(texto)

        if len(pares_poligonal_prosa) >= 3:
            self._finalizar_vertices_geograficos(pares_poligonal_prosa)
            return

        diagnostico_prosa = coordenadas.diagnosticar_poligonal_azimute_prosa(texto)

        if diagnostico_prosa:

            QMessageBox.warning(self, "Coleta Rural", diagnostico_prosa)

            return

        pares_utm_rotulados = coordenadas.extrair_pares_utm_rotulados(texto)

        if len(pares_utm_rotulados) >= 3:
            self._tentar_vertices_utm(pares_utm_rotulados)
            return

        # memorial em formato de poligonal (vértice inicial com
        # coordenada UTM conhecida + tabela de azimute/distância entre
        # vértices) — já sabemos que são pares (este, norte) calculados
        # a partir da poligonal, não precisa da heurística de tabela
        pares_poligonal = coordenadas.extrair_poligonal_azimute_distancia(texto)

        if len(pares_poligonal) >= 3:
            self._tentar_vertices_utm(pares_poligonal)
            return

        # mesma ideia, mas descrita em prosa corrida em vez de tabela
        # (ex.: "Partindo do vértice V-28 de coordenadas E=... e N=...
        # com uma distância de ...m e azimute de ... encontramos o
        # vértice V-29, deste com distância de ...m e azimute de ...
        # encontramos o vértice V-30, [...]")
        pares_poligonal_prosa_utm = coordenadas.extrair_poligonal_azimute_prosa_utm(texto)

        if len(pares_poligonal_prosa_utm) >= 3:
            self._tentar_vertices_utm(pares_poligonal_prosa_utm)
            return

        # mesma ideia, mas com o segmento descrito por rumo (quadrante +
        # ângulo, ex.: "NE 45°30'20"") em vez de azimute em graus decimais
        pares_poligonal_rumo = coordenadas.extrair_poligonal_rumo_distancia(texto)

        if len(pares_poligonal_rumo) >= 3:
            self._tentar_vertices_utm(pares_poligonal_rumo)
            return

        try:
            pares_tabela = coordenadas.extrair_pares_tabela_colunas(texto)
        except ValueError as erro:
            QMessageBox.warning(self, "Coleta Rural", str(erro))
            return

        if len(pares_tabela) >= 3:
            self._tentar_vertices_utm(pares_tabela)
            return

        pares = coordenadas.extrair_pares_numericos_texto_livre(texto)

        if len(pares) < 3:

            QMessageBox.warning(
                self,
                "Coleta Rural",
                "Não foram encontradas coordenadas suficientes no texto (mínimo 3)."
            )

            return

        classificacoes = [coordenadas.classificar_par(a, b) for a, b in pares]

        if "utm" in classificacoes:
            tipo = "utm"
        elif "geografico" in classificacoes:
            tipo = "geografico"
        else:
            tipo = "indefinido"

        if tipo == "indefinido":

            QMessageBox.warning(
                self,
                "Coleta Rural",
                "Não foi possível identificar se as coordenadas do texto são "
                "geográficas ou UTM. Confira o texto colado."
            )

            return

        anomalos = [
            i for i, classificacao in enumerate(classificacoes, start=1)
            if classificacao not in (tipo, "indefinido")
        ]

        if anomalos:

            self.lblAvisoFormatoManual.setText(
                f"Aviso: as coordenadas do(s) vértice(s) {anomalos} parecem estar "
                "num formato diferente dos demais. Confira a tabela abaixo."
            )

        if tipo == "utm":
            self._tentar_vertices_utm(pares)
            return

        self.grpUtmManual.setVisible(False)

        try:

            vertices = coordenadas.pontos_geograficos_para_vertices_4674(pares)

        except Exception as erro:

            self.vertices = []

            QMessageBox.critical(
                self,
                "Coleta Rural",
                f"Não foi possível interpretar as coordenadas.\n\n{erro}"
            )

            return

        self._finalizar_vertices(vertices)

    def visualizar_imovel_manual(self):

        if len(self.vertices) < 3:

            QMessageBox.warning(
                self,
                "Coleta Rural",
                "Nenhum vértice válido encontrado. Extraia os dados do texto primeiro."
            )

            return

        try:

            self._construir_preview()

            self.btnSalvarManual.setEnabled(True)

        except Exception as erro:

            QMessageBox.critical(
                self,
                "Erro",
                str(erro)
            )

    def salvar_camada_manual(self):

        if not self.vertices:

            QMessageBox.warning(
                self,
                "Coleta Rural",
                "Primeiro visualize o imóvel no mapa."
            )

            return

        layer = self._obter_camada_destino()

        if layer is None:
            return

        self.imovel = self.txtImovelManual.text().strip()
        self.municipio = self.txtMunicipioManual.text().strip()
        self.uf = self.txtUfManual.text().strip()
        self.declarante = self.txtDeclaranteManual.text().strip()
        # so aceita o CPF/CNPJ se tiver 11 ou 14 digitos (completo);
        # incompleto ou vazio é tratado como em branco
        self.cpf = (
            self.txtCpfManual.text().strip()
            if self._cpf_cnpj_completo(self.txtCpfManual.text())
            else ""
        )
        self.area = self.txtAreaManual.text().strip()
        # so aceita o CIR se a mascara estiver completamente preenchida
        # (xxx.xxx.xxx.xxx-x); incompleto ou vazio é tratado como em branco
        self.cir = (
            self.txtCirManual.text().strip()
            if self.txtCirManual.hasAcceptableInput()
            else ""
        )

        self.matricula = self.txtMatriculaManual.text().strip()

        try:

            self._salvar_feature(layer)

            self.limpar_preview()

            self.vertices = []

            self.txtColarTexto.clear()
            self.txtImovelManual.clear()
            self.txtMunicipioManual.clear()
            self.txtUfManual.clear()
            self.txtDeclaranteManual.clear()
            self.txtCpfManual.clear()
            self.txtAreaManual.clear()
            self.txtCirManual.clear()
            self.txtMatriculaManual.clear()
            self.tabelaCoordenadasManual.setRowCount(0)
            self.lblAvisoFormatoManual.setText("")
            self.grpUtmManual.setVisible(False)
            self._ultimos_pares_utm = None

            self.imovel = ""
            self.municipio = ""
            self.uf = ""
            self.area = ""
            self.declarante = ""
            self.cpf = ""
            self.cir = ""
            self.matricula = ""

            self.btnSalvarManual.setEnabled(False)

            QMessageBox.information(
                self,
                "Coleta Rural",
                "Imóvel importado com sucesso."
            )

        except Exception as erro:

            try:
                layer.rollBack()
            except Exception as erro_rollback:
                print(f"Erro ao executar rollback: {erro_rollback}")

            QMessageBox.critical(
                self,
                "Erro",
                str(erro)
            )

    # ------------------------------------------------------------------
    # Zoom Rápido (visualização de uma coordenada, sem criar camada)
    # ------------------------------------------------------------------

    def atualizar_modo_zoom(self):

        utm = self.rdoZoomUtm.isChecked()
        gms = self.rdoZoomGeografica.isChecked()
        decimal = self.rdoZoomGeograficaDecimal.isChecked()

        self.grpUtmZoom.setVisible(utm)

        if utm:

            self.lblZoomCoord1.setText("Este")
            self.lblZoomCoord2.setText("Norte")

            # limpa antes de trocar a máscara — senão os dígitos que
            # sobraram do modo anterior são reaproveitados na posição
            # da máscara nova, em vez de a máscara nascer zerada
            self.txtZoomCoord1.setInputMask("")
            self.txtZoomCoord1.clear()
            self.txtZoomCoord1.setInputMask(MASCARA_UTM_ESTE)
            self.txtZoomCoord1.setStyleSheet("color: gray;")

            self.txtZoomCoord2.setInputMask("")
            self.txtZoomCoord2.clear()
            self.txtZoomCoord2.setInputMask(MASCARA_UTM_NORTE)
            self.txtZoomCoord2.setStyleSheet("color: gray;")

        elif gms:

            self.lblZoomCoord1.setText("Longitude")
            self.lblZoomCoord2.setText("Latitude")

            self.txtZoomCoord1.setInputMask(MASCARA_COORDENADA_GMS)
            _preencher_campo_mascarado_com_exemplo(
                self.txtZoomCoord1, EXEMPLO_LONGITUDE_GMS
            )
            self.txtZoomCoord2.setInputMask(MASCARA_COORDENADA_GMS)
            _preencher_campo_mascarado_com_exemplo(
                self.txtZoomCoord2, EXEMPLO_LATITUDE_GMS
            )

        elif decimal:

            self.lblZoomCoord1.setText("Longitude")
            self.lblZoomCoord2.setText("Latitude")

            self.txtZoomCoord1.setInputMask(MASCARA_COORDENADA_DECIMAL)
            _preencher_campo_mascarado_com_exemplo(
                self.txtZoomCoord1, EXEMPLO_LONGITUDE_DECIMAL
            )
            self.txtZoomCoord2.setInputMask(MASCARA_COORDENADA_DECIMAL)
            _preencher_campo_mascarado_com_exemplo(
                self.txtZoomCoord2, EXEMPLO_LATITUDE_DECIMAL
            )

    def zoom_para_coordenada(self):

        try:

            # todos os modos têm máscara agora — displayText() reflete
            # o que a máscara mostra (com "0" como preenchimento vazio);
            # text() esconderia até um "0" digitado de verdade
            if self.rdoZoomGeografica.isChecked():

                valor1 = coordenadas.valor_coordenada_para_decimal(
                    self.txtZoomCoord1.displayText()
                )
                valor2 = coordenadas.valor_coordenada_para_decimal(
                    self.txtZoomCoord2.displayText()
                )

            elif self.rdoZoomUtm.isChecked():

                # máscara UTM usa "." como separador de milhar e ","
                # como decimal (padrão brasileiro) — remove o milhar
                # antes de trocar a vírgula por ponto
                valor1 = float(
                    self.txtZoomCoord1.displayText()
                    .replace(".", "").replace(",", ".")
                )
                valor2 = float(
                    self.txtZoomCoord2.displayText()
                    .replace(".", "").replace(",", ".")
                )

            else:

                valor1 = float(
                    self.txtZoomCoord1.displayText().strip().replace(",", ".")
                )
                valor2 = float(
                    self.txtZoomCoord2.displayText().strip().replace(",", ".")
                )

        except ValueError:

            QMessageBox.warning(
                self,
                "Coleta Rural",
                "Digite números válidos nos dois campos de coordenada."
            )

            return

        try:

            if self.rdoZoomUtm.isChecked():

                fuso = int(self.cmbFusoZoom.currentText().rstrip("Ss"))
                datum = self.cmbDatumZoom.currentText()

                crs_origem = coordenadas.montar_crs_utm(fuso, datum)
                ponto = QgsPointXY(valor1, valor2)

            else:

                if abs(valor1) > 180 or abs(valor2) > 90:

                    QMessageBox.warning(
                        self,
                        "Coleta Rural",
                        "Longitude deve estar entre -180 e 180, e "
                        "Latitude entre -90 e 90."
                    )

                    return

                crs_origem = QgsCoordinateReferenceSystem("EPSG:4674")
                ponto = QgsPointXY(valor1, valor2)

            crs_destino = QgsProject.instance().crs()

            ponto_final = coordenadas.transformar_pontos(
                [ponto], crs_origem, crs_destino
            )[0]

            self._mostrar_marcador_zoom(ponto_final)

        except Exception as erro:

            QMessageBox.critical(
                self,
                "Coleta Rural",
                f"Não foi possível localizar a coordenada.\n\n{erro}"
            )

    def _mostrar_marcador_zoom(self, ponto):

        self.limpar_zoom_marker()

        canvas = self.iface.mapCanvas()

        self.zoom_marker = QgsVertexMarker(canvas)

        self.zoom_marker.setCenter(ponto)
        self.zoom_marker.setColor(QtGui.QColor(255, 0, 0))
        self.zoom_marker.setIconType(QgsVertexMarker.IconType.ICON_CROSS)
        self.zoom_marker.setIconSize(14)
        self.zoom_marker.setPenWidth(3)

        canvas.setCenter(ponto)
        canvas.zoomScale(2000)
        canvas.refresh()

    # ------------------------------------------------------------------
    # Gerar Memorial (memorial a partir de polígono(s) já
    # selecionado(s) numa camada do projeto, com verificação de
    # adjacência e mesclagem quando for mais de um)
    # ------------------------------------------------------------------

    def carregar_camadas_origem_selecao(self):

        atual = self.cmbCamadaOrigemSelecao.currentData()

        self.cmbCamadaOrigemSelecao.clear()

        for camada in QgsProject.instance().mapLayers().values():

            if (
                isinstance(camada, QgsVectorLayer)
                and QgsWkbTypes.geometryType(camada.wkbType())
                == QgsWkbTypes.GeometryType.PolygonGeometry
            ):
                self.cmbCamadaOrigemSelecao.addItem(camada.name(), camada.id())

        if atual is not None:

            indice = self.cmbCamadaOrigemSelecao.findData(atual)

            if indice >= 0:
                self.cmbCamadaOrigemSelecao.setCurrentIndex(indice)

    def _aba_alterada(self, indice):

        if self.tabWidget.widget(indice) is self.tabMemorialSelecao:
            self.carregar_camadas_origem_selecao()

    def _formatar_cir(self, texto):
        """Formata um valor bruto de CIR (13 dígitos, ex.: vindo do
        campo "codigo_imo" do SIGEF, sem pontuação) no padrão
        xxx.xxx.xxx.xxx-x esperado pela máscara do campo. Se não tiver
        exatamente 13 dígitos, devolve o texto original sem alteração
        — não é um CIR válido mesmo, então não adianta tentar formatar."""

        digitos = re.sub(r"\D", "", texto)

        if len(digitos) != 13:
            return texto

        return (
            f"{digitos[0:3]}.{digitos[3:6]}.{digitos[6:9]}."
            f"{digitos[9:12]}-{digitos[12]}"
        )

    def _valor_campo_por_alias(self, feicao, aliases):
        """Procura, entre os campos da feição, um cujo nome bata (sem
        diferenciar maiúsculas/minúsculas) com algum dos aliases, e
        devolve seu valor como texto. Devolve "" se não achar nenhum
        campo correspondente ou se o valor estiver vazio/nulo."""

        nomes_campos = feicao.fields().names()

        for alias in aliases:

            for nome in nomes_campos:

                if nome.strip().upper() == alias.upper():

                    valor = feicao[nome]

                    if valor not in (None, ""):
                        return str(valor).strip()

        return ""

    def _resolver_municipio_uf_sigef(self, feicao):
        """Resolve os campos numéricos "municipio_"/"uf_id" do SIGEF
        Brasil (código IBGE de município e de UF) para nome de
        município/sigla de UF legíveis, usando as tabelas de
        municipios_pe.py. Devolve (municipio, uf) — cada um "" se o
        campo não existir, não for numérico, ou o código não for
        reconhecido (ex.: município fora de Pernambuco)."""

        municipio = ""
        uf = ""

        for nome in feicao.fields().names():

            nome_upper = nome.strip().upper()

            if nome_upper == "MUNICIPIO_":

                try:
                    codigo = int(feicao[nome])
                except (TypeError, ValueError):
                    continue

                municipio = municipios_pe.MUNICIPIOS_PE_POR_CODIGO_IBGE.get(
                    codigo, ""
                )

            elif nome_upper == "UF_ID":

                try:
                    codigo = int(feicao[nome])
                except (TypeError, ValueError):
                    continue

                uf = municipios_pe.UF_POR_CODIGO_IBGE.get(codigo, "")

        return municipio, uf

    def _detectar_fonte_poligono(self, feicao):
        """Identifica se o polígono vem de uma camada com o esquema de
        campos do SIGEF Brasil ou do CAR (SICAR), para citar a fonte
        no memorial gerado — só pela presença dos nomes de campo
        característicos de cada base, não pelo conteúdo."""

        nomes_campos = {
            nome.strip().upper() for nome in feicao.fields().names()
        }

        if nomes_campos & _CAMPOS_SIGEF:
            return "Certificado pelo SIGEF"

        if nomes_campos & _CAMPOS_CAR:
            return "Declarado no CAR"

        return "Indicado pela equipe do INCRA"

    def _alternar_processo_sei_selecao(self, marcado):
        """Habilita o campo do número do processo SEI só quando a
        caixa de seleção está marcada — mantém desmarcada e vazia por
        padrão, para o cabeçalho do memorial continuar exatamente como
        já era quando não há processo SEI a informar. Limpa o campo ao
        desmarcar, para não deixar um valor parcial/antigo digitado
        que não deveria mais entrar no PDF."""

        self.txtProcessoSeiSelecao.setEnabled(marcado)

        if not marcado:
            self.txtProcessoSeiSelecao.clear()

    def carregar_selecao_memorial(self):

        id_camada = self.cmbCamadaOrigemSelecao.currentData()

        if not id_camada:

            QMessageBox.warning(
                self,
                "Coleta Rural",
                "Selecione uma camada de origem."
            )

            return

        camada = QgsProject.instance().mapLayer(id_camada)

        if camada is None:

            QMessageBox.warning(
                self,
                "Coleta Rural",
                "Camada de origem não encontrada."
            )

            return

        feicoes = list(camada.selectedFeatures())

        self.lblAvisoSelecao.setText("")

        if not feicoes:

            QMessageBox.warning(
                self,
                "Coleta Rural",
                "Selecione ao menos um polígono na camada de origem "
                "(no mapa ou na tabela de atributos) antes de carregar."
            )

            return

        geometrias = [feicao.geometry() for feicao in feicoes]

        if len(geometrias) > 1 and not coordenadas.poligonos_conectados(geometrias):

            mensagem = (
                "É necessário que os polígonos sejam adjacentes "
                "(compartilhem uma borda, não só um vértice) para "
                "gerar o memorial em conjunto."
            )

            self.lblAvisoSelecao.setText(mensagem)

            QMessageBox.warning(
                self,
                "Coleta Rural",
                mensagem
            )

            self.vertices = []
            self._geometrias_origem_selecao = []
            self._labels_origem_selecao = []
            self._fonte_poligono_selecao = ""
            self.tabelaCoordenadasSelecao.setRowCount(0)
            self.txtAreaSelecao.clear()
            self.btnVisualizarSelecao.setEnabled(False)
            self.btnGerarMemorialSelecao.setEnabled(False)

            return

        uniao = QgsGeometry.unaryUnion(geometrias)

        anel = self._extrair_anel_de_geometria(uniao)

        if not anel:

            QMessageBox.critical(
                self,
                "Coleta Rural",
                "Não foi possível calcular o contorno externo do "
                "polígono mesclado."
            )

            return

        crs_4674 = QgsCoordinateReferenceSystem(coordenadas.CRS_GEOGRAFICO)

        self.vertices = coordenadas.transformar_pontos(
            anel, camada.crs(), crs_4674
        )

        self._preencher_tabela_coordenadas(
            self.vertices, self.tabelaCoordenadasSelecao
        )

        area_ha = coordenadas.calcular_area_hectares(self.vertices)
        self.txtAreaSelecao.setText(f"{area_ha:.4f}")

        self._geometrias_origem_selecao = geometrias
        self._crs_origem_selecao = camada.crs()

        # rótulos do croqui (etiqueta no centro de cada polígono): tenta
        # a Matrícula e, só como identificador alternativo quando não
        # houver, usa o CIR — mas essa troca é só para ter *algum*
        # identificador visível no croqui, não deve ir parar no campo
        # Matrícula em si (senão o memorial mostraria o código do CIR
        # como se fosse uma matrícula de verdade)
        rotulos = []
        matriculas_reais = []

        for feicao in feicoes:

            matricula = self._valor_campo_por_alias(feicao, ALIASES_MATRICULA)

            if matricula and matricula not in matriculas_reais:
                matriculas_reais.append(matricula)

            rotulo = matricula or self._valor_campo_por_alias(feicao, ALIASES_CIR)

            rotulos.append(rotulo)

        self._labels_origem_selecao = rotulos

        if not self.txtMatriculaSelecao.text().strip():
            self.txtMatriculaSelecao.setText("; ".join(matriculas_reais))

        primeira = feicoes[0]

        if not self.txtImovelSelecao.text().strip():
            self.txtImovelSelecao.setText(
                self._valor_campo_por_alias(primeira, ALIASES_IMOVEL)
            )

        if not self.txtDeclaranteSelecao.text().strip():
            self.txtDeclaranteSelecao.setText(
                self._valor_campo_por_alias(primeira, ALIASES_DECLARANTE)
            )

        if not self.txtCpfSelecao.text().strip():
            self._formatar_cpf_cnpj(
                self.txtCpfSelecao,
                self._valor_campo_por_alias(primeira, ALIASES_CPF)
            )

        # campo com máscara: text() de um campo "vazio" ainda devolve os
        # separadores literais da máscara (ex.: "...-"), não "" — por
        # isso hasAcceptableInput() é o jeito certo de saber se já tem
        # um CIR completo digitado antes de preencher automaticamente
        if not self.txtCirSelecao.hasAcceptableInput():
            self.txtCirSelecao.setText(
                self._formatar_cir(
                    self._valor_campo_por_alias(primeira, ALIASES_CIR)
                )
            )

        municipio_sigef, uf_sigef = self._resolver_municipio_uf_sigef(primeira)

        if not self.txtMunicipioSelecao.text().strip():
            self.txtMunicipioSelecao.setText(
                self._valor_campo_por_alias(primeira, ALIASES_MUNICIPIO)
                or municipio_sigef
            )

        if not self.txtUfSelecao.text().strip():
            self.txtUfSelecao.setText(
                self._valor_campo_por_alias(primeira, ALIASES_UF) or uf_sigef
            )

        self._fonte_poligono_selecao = self._detectar_fonte_poligono(primeira)

        self.btnVisualizarSelecao.setEnabled(True)
        self.btnGerarMemorialSelecao.setEnabled(False)

    def _limpar_camadas_internas_selecao(self):

        for atributo in (
            "preview_linhas_internas_selecao", "preview_labels_selecao"
        ):

            camada = getattr(self, atributo, None)

            try:

                if camada:
                    QgsProject.instance().removeMapLayer(camada.id())

            except Exception as erro:
                # inclui o caso em que a camada já foi apagada manualmente
                # pelo usuário (objeto C++ deletado)
                print(f"Erro ao remover camada de preview ({atributo}): {erro}")

            setattr(self, atributo, None)

    def _construir_linhas_internas_selecao(self):

        if len(self._geometrias_origem_selecao) < 2:
            return

        camada_linhas = QgsVectorLayer(
            "LineString?crs=" + self._crs_origem_selecao.authid(),
            "Coleta Rural - Limites Internos",
            "memory"
        )

        provider = camada_linhas.dataProvider()

        for geometria in self._geometrias_origem_selecao:

            feicao = QgsFeature()
            feicao.setGeometry(
                geometria.convertToType(QgsWkbTypes.GeometryType.LineGeometry, False)
            )
            provider.addFeature(feicao)

        camada_linhas.updateExtents()

        simbolo = camada_linhas.renderer().symbol()
        camada_simbolo = simbolo.symbolLayer(0)
        camada_simbolo.setPenStyle(QtCore.Qt.PenStyle.DashLine)
        camada_simbolo.setColor(QtGui.QColor(80, 80, 80))
        camada_simbolo.setWidth(0.5)

        QgsProject.instance().addMapLayer(camada_linhas)

        camada_linhas.triggerRepaint()

        self.preview_linhas_internas_selecao = camada_linhas

    def _construir_labels_selecao(self):

        if len(self._geometrias_origem_selecao) < 2:
            return

        camada_labels = QgsVectorLayer(
            "Point?crs=" + self._crs_origem_selecao.authid()
            + "&field=rotulo:string(100)",
            "Coleta Rural - Matrículas",
            "memory"
        )

        provider = camada_labels.dataProvider()

        for geometria, rotulo in zip(
            self._geometrias_origem_selecao, self._labels_origem_selecao
        ):

            feicao = QgsFeature(camada_labels.fields())
            feicao.setGeometry(geometria.centroid())
            feicao.setAttribute("rotulo", rotulo)
            provider.addFeature(feicao)

        camada_labels.updateExtents()

        configuracao_rotulo = QgsPalLayerSettings()
        configuracao_rotulo.fieldName = "rotulo"
        configuracao_rotulo.placement = QgsPalLayerSettings.Placement.OverPoint

        formato_texto = QgsTextFormat()
        formato_texto.setSize(8)
        configuracao_rotulo.setFormat(formato_texto)

        camada_labels.setLabeling(
            QgsVectorLayerSimpleLabeling(configuracao_rotulo)
        )
        camada_labels.setLabelsEnabled(True)

        # sem marcador visível no ponto — só o rótulo de texto (o
        # marcador por baixo do texto ficava sobreposto à etiqueta)
        simbolo = camada_labels.renderer().symbol()
        simbolo.setOpacity(0)

        QgsProject.instance().addMapLayer(camada_labels)

        camada_labels.triggerRepaint()

        self.preview_labels_selecao = camada_labels

    def visualizar_memorial_selecao(self):

        if len(self.vertices) < 3:

            QMessageBox.warning(
                self,
                "Coleta Rural",
                "Primeiro carregue a seleção de polígono(s)."
            )

            return

        try:

            self._construir_preview()

            self._limpar_camadas_internas_selecao()
            self._construir_linhas_internas_selecao()
            self._construir_labels_selecao()

            self.btnGerarMemorialSelecao.setEnabled(True)

        except Exception as erro:

            QMessageBox.critical(
                self,
                "Erro",
                str(erro)
            )

    def _nome_arquivo_seguro(self, texto):
        """Converte um texto livre (nome do imóvel) num nome de arquivo
        válido no Windows/Linux/Mac, trocando espaços e caracteres não
        permitidos por "_"."""

        texto = texto.strip() or "imovel"
        texto = re.sub(r'[\\/:*?"<>|]', "_", texto)
        texto = re.sub(r"\s+", "_", texto)

        return texto

    def gerar_memorial_selecao(self):

        if not self.vertices:

            QMessageBox.warning(
                self,
                "Coleta Rural",
                "Primeiro visualize o memorial no mapa."
            )

            return

        nome_sugerido = (
            "memorial_informativo_"
            + self._nome_arquivo_seguro(self.txtImovelSelecao.text())
            + ".pdf"
        )

        caminho, _ = QFileDialog.getSaveFileName(
            self,
            "Gerar Memorial PDF",
            nome_sugerido,
            "PDF (*.pdf)"
        )

        if not caminho:
            return

        if not caminho.lower().endswith(".pdf"):
            caminho += ".pdf"

        dados = {
            "imovel": self.txtImovelSelecao.text().strip(),
            "municipio": self.txtMunicipioSelecao.text().strip(),
            "uf": self.txtUfSelecao.text().strip(),
            "area": self.txtAreaSelecao.text().strip(),
            "declarante": self.txtDeclaranteSelecao.text().strip(),
            "cpf": (
                self.txtCpfSelecao.text().strip()
                if self._cpf_cnpj_completo(self.txtCpfSelecao.text())
                else ""
            ),
            "cir": (
                self.txtCirSelecao.text().strip()
                if self.txtCirSelecao.hasAcceptableInput()
                else ""
            ),
            "matricula": self.txtMatriculaSelecao.text().strip(),
            "processo_sei": (
                self.txtProcessoSeiSelecao.text().strip()
                if self.chkProcessoSeiSelecao.isChecked()
                and self.txtProcessoSeiSelecao.hasAcceptableInput()
                else ""
            ),
            "fonte": self._fonte_poligono_selecao,
        }

        # o croqui mostra só o(s) polígono(s) do imóvel — nenhuma outra
        # camada do projeto entra aqui; o fundo (OpenStreetMap) é
        # acrescentado automaticamente pelo memorial_pdf
        camadas_mapa = [
            camada for camada in (
                self.preview_labels_selecao,
                self.preview_linhas_internas_selecao,
                self.preview_layer,
            )
            if camada
        ]

        # margem generosa ao redor do polígono — além de dar contexto
        # visual melhor, evita pedir tiles de satélite num zoom tão
        # próximo/fechado que a Esri não tenha cobertura ali (o
        # "Map data not available" aparecia com uma margem apertada
        # em propriedades pequenas)
        extensao_mapa = self.preview_layer.extent()
        extensao_mapa.scale(1.6)

        try:

            memorial_pdf.gerar_pdf_memorial(
                caminho,
                dados,
                self.vertices,
                camadas_mapa,
                extensao_mapa,
                QgsCoordinateReferenceSystem(coordenadas.CRS_GEOGRAFICO)
            )

            QMessageBox.information(
                self,
                "Coleta Rural",
                f"Memorial descritivo gerado com sucesso:\n\n{caminho}"
            )

        except Exception as erro:

            QMessageBox.critical(
                self,
                "Erro",
                f"Não foi possível gerar o PDF.\n\n{erro}"
            )

    def limpar_memorial_selecao(self):

        self.limpar_preview()
        self._limpar_camadas_internas_selecao()

        self.vertices = []
        self._geometrias_origem_selecao = []
        self._labels_origem_selecao = []
        self._fonte_poligono_selecao = ""

        self.tabelaCoordenadasSelecao.setRowCount(0)
        self.lblAvisoSelecao.setText("")
        self.txtImovelSelecao.clear()
        self.txtMunicipioSelecao.clear()
        self.txtUfSelecao.clear()
        self.txtDeclaranteSelecao.clear()
        self.txtCpfSelecao.clear()
        self.chkProcessoSeiSelecao.setChecked(False)
        self.txtProcessoSeiSelecao.clear()
        self.txtCirSelecao.clear()
        self.txtMatriculaSelecao.clear()
        self.txtAreaSelecao.clear()

        self.btnVisualizarSelecao.setEnabled(False)
        self.btnGerarMemorialSelecao.setEnabled(False)
