# -*- coding: utf-8 -*-

import os
import re

from pypdf import PdfReader

from qgis.PyQt import uic
from qgis.PyQt import QtWidgets
from qgis.PyQt import QtGui

from qgis.PyQt.QtWidgets import (
    QFileDialog,
    QMessageBox
)

from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsSettings
)

from .configuracoes_dialog import ConfiguracoesDialog


FORM_CLASS, _ = uic.loadUiType(
    os.path.join(
        os.path.dirname(__file__),
        'coleta_rural_dialog_base.ui'
    )
)


class ColetaRuralDialog(QtWidgets.QDialog, FORM_CLASS):

    def __init__(self, iface, parent=None):
        super().__init__(parent)

        self.iface = iface

        self.setupUi(self)

        self.arquivo_pdf = None
        self.texto_memorial = ""
        self.imovel = ""
        self.municipio = ""
        self.area = ""
        self.declarante = ""
        self.cpf = ""
        self.vertices = []
        self.preview_layer = None

        self.btnSalvar.setEnabled(False)

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

        self.carregar_camadas_permitidas()
        
        self.toolbar = self.iface.addToolBar(
            "Coleta Rural"
        )
        self.toolbar.setObjectName(
            "Coleta Rural"
        )


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

        if self.preview_layer:

            try:

                QgsProject.instance().removeMapLayer(
                    self.preview_layer.id()
                )

            except Exception:
                pass

        self.preview_layer = None

    def selecionar_pdf(self):

        self.limpar_preview()

        self.btnSalvar.setEnabled(False)

        self.lblImovel.setText("-")
        self.lblMunicipio.setText("-")
        self.lblDeclarante.setText("-")
        self.lblArea.setText("-")

        self.imovel = ""
        self.municipio = ""
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

            self.preencher_dados(texto)

        except Exception as erro:

            QMessageBox.critical(
                self,
                "Erro",
                f"Não foi possível ler o PDF.\n\n{erro}"
            )

    def preencher_dados(self, texto):

        try:

            imovel = re.search(
                r"Imóvel:\s*(.*?)\s*Município sede:",
                texto,
                re.DOTALL
            )

            municipio = re.search(
                r"Município sede:\s*(.*?)\s*Área total:",
                texto,
                re.DOTALL
            )

            area = re.search(
                r"Área total:\s*(.*?)\s*Declarante:",
                texto,
                re.DOTALL
            )

            declarante = re.search(
                r"Declarante:\s*(.*?)\s*CPF/CNPJ:",
                texto,
                re.DOTALL
            )
            
            cpf = re.search(
                r"CPF/CNPJ:\s*(.*?)\s*MUNICÍPIOS ABRANGIDOS",
                texto,
                re.DOTALL
            )
            self.imovel = (
                imovel.group(1).strip()
                if imovel else ""
            )

            self.municipio = (
                municipio.group(1).strip()
                if municipio else ""
            )

            self.area = (
                area.group(1).strip()
                if area else ""
            )

            self.declarante = (
                declarante.group(1).strip()
                if declarante else ""
            )

            self.lblImovel.setText(
                imovel.group(1).strip()
                if imovel else "-"
            )

            self.lblMunicipio.setText(
                municipio.group(1).strip()
                if municipio else "-"
            )

            self.lblArea.setText(
                area.group(1).strip()
                if area else "-"
            )

            self.lblDeclarante.setText(
                declarante.group(1).strip()
                if declarante else "-"
            )

            self.cpf = (
                cpf.group(1).strip()
                if cpf else ""
            )
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

            except Exception:
                pass

    def visualizar_imovel(self):

        if len(self.vertices) < 3:

            QMessageBox.warning(
                self,
                "Coleta Rural",
                "Nenhum vértice válido encontrado."
            )

            return

        try:
            self.preview_layer = None if self.preview_layer is None else self.preview_layer

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

            self.btnSalvar.setEnabled(True)

        except Exception as erro:

            QMessageBox.critical(
                self,
                "Erro",
                str(erro)
            )

    def abrir_configuracoes(self):

        dlg = ConfiguracoesDialog(self)

        if dlg.exec_():

            self.carregar_camadas_permitidas()

    def salvar_camada(self):

        if not self.vertices:

            QMessageBox.warning(
                self,
                "Coleta Rural",
                "Primeiro visualize o imóvel no mapa."
            )

            return

        nome_camada = self.cmbCamada.currentText()

        if not nome_camada:

            QMessageBox.warning(
                self,
                "Coleta Rural",
                "Selecione uma camada de destino."
            )

            return

        layers = QgsProject.instance().mapLayersByName(
            nome_camada
        )

        if not layers:

            QMessageBox.warning(
                self,
                "Coleta Rural",
                "Camada não encontrada."
            )

            return

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

            return

        try:

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
                feicao["CIR"] = ""

            if "Imóvel" in campos:
                feicao["Imóvel"] = self.imovel

            if "Matrícula" in campos:
                feicao["Matrícula"] = ""

            if "Município" in campos:
                feicao["Município"] = self.municipio

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

            self.limpar_preview()

            self.vertices = []

            self.lblImovel.setText("-")
            self.lblMunicipio.setText("-")
            self.lblDeclarante.setText("-")
            self.lblArea.setText("-")

            self.imovel = ""
            self.municipio = ""
            self.area = ""
            self.declarante = ""
            self.cpf = ""

            self.btnSalvar.setEnabled(False)

            QMessageBox.information(
                self,
                "Coleta Rural",
                "Imóvel importado com sucesso."
            )

        except Exception as erro:

            try:
                layer.rollBack()
            except Exception:
                pass

            QMessageBox.critical(
                self,
                "Erro",
                str(erro)
            )