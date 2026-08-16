# -*- coding: utf-8 -*-

import os
import re
import shutil

from qgis.PyQt import uic
from qgis.PyQt import QtWidgets

from qgis.PyQt.QtCore import Qt, QStandardPaths

from qgis.core import (
    QgsProject,
    QgsSettings,
    QgsVectorFileWriter,
    QgsVectorLayer
)

from qgis.PyQt.QtWidgets import (
    QFileDialog,
    QInputDialog,
    QListWidgetItem,
    QMessageBox
)

FORM_CLASS, _ = uic.loadUiType(
    os.path.join(
        os.path.dirname(__file__),
        'configuracoes_dialog.ui'
    )
)


class ConfiguracoesDialog(QtWidgets.QDialog, FORM_CLASS):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setupUi(self)

        self.btnAtualizar.clicked.connect(
            self.carregar_camadas
        )

        self.btnCamadaPadrao.clicked.connect(
            self.incluir_camada_padrao
        )

        self.btnSalvarConfig.clicked.connect(
            self.salvar_configuracao
        )

        self.lstCamadas.itemChanged.connect(
            self.atualizar_estilo_item
        )

        self.carregar_camadas()

    def atualizar_estilo_item(self, item):

        fonte = item.font()

        fonte.setBold(
            item.checkState() == Qt.Checked
        )

        item.setFont(fonte)

    def carregar_camadas(self):

        self.lstCamadas.blockSignals(True)

        self.lstCamadas.clear()

        settings = QgsSettings()

        camadas_salvas = settings.value(
            "ColetaRural/camadas_permitidas",
            [],
            type=list
        )

        for layer in QgsProject.instance().mapLayers().values():

            item = QListWidgetItem(
                layer.name()
            )

            item.setFlags(
                item.flags() | Qt.ItemIsUserCheckable
            )

            if layer.name() in camadas_salvas:

                item.setCheckState(
                    Qt.Checked
                )

            else:

                item.setCheckState(
                    Qt.Unchecked
                )

            self.atualizar_estilo_item(item)

            self.lstCamadas.addItem(item)

        self.lstCamadas.blockSignals(False)

    def obter_pasta_padrao(self):

        caminho_projeto = QgsProject.instance().fileName()

        if caminho_projeto:
            return os.path.dirname(caminho_projeto)

        pasta = os.path.join(
            QStandardPaths.writableLocation(
                QStandardPaths.DocumentsLocation
            ),
            "Coleta Rural"
        )

        os.makedirs(
            pasta,
            exist_ok=True
        )

        return pasta

    def criar_camada_shapefile(self, caminho_base_origem, caminho_destino, nome):

        caminho_base_destino = os.path.splitext(caminho_destino)[0]

        try:

            for extensao in (".shp", ".shx", ".dbf", ".prj", ".cpg", ".qmd"):

                origem = caminho_base_origem + extensao

                if os.path.exists(origem):

                    shutil.copyfile(
                        origem,
                        caminho_base_destino + extensao
                    )

        except Exception as erro:

            QMessageBox.critical(
                self,
                "Coleta Rural",
                f"Não foi possível criar o arquivo da camada padrão.\n\n{erro}"
            )

            return None

        camada = QgsVectorLayer(
            caminho_destino,
            nome,
            "ogr"
        )

        if not camada.isValid():

            QMessageBox.critical(
                self,
                "Coleta Rural",
                "Não foi possível carregar a camada padrão."
            )

            return None

        return camada

    def criar_camada_geopackage(self, caminho_base_origem, caminho_destino, nome):

        camada_origem = QgsVectorLayer(
            caminho_base_origem + ".shp",
            "camada_padrao",
            "ogr"
        )

        if not camada_origem.isValid():

            QMessageBox.critical(
                self,
                "Coleta Rural",
                "Não foi possível ler a camada padrão de origem."
            )

            return None

        opcoes = QgsVectorFileWriter.SaveVectorOptions()
        opcoes.driverName = "GPKG"
        opcoes.layerName = nome
        opcoes.fileEncoding = "UTF-8"

        resultado = QgsVectorFileWriter.writeAsVectorFormatV3(
            camada_origem,
            caminho_destino,
            QgsProject.instance().transformContext(),
            opcoes
        )

        erro = resultado[0]
        mensagem = resultado[1] if len(resultado) > 1 else ""

        if erro != QgsVectorFileWriter.NoError:

            QMessageBox.critical(
                self,
                "Coleta Rural",
                f"Não foi possível criar o GeoPackage.\n\n{mensagem}"
            )

            return None

        camada = QgsVectorLayer(
            f"{caminho_destino}|layername={nome}",
            nome,
            "ogr"
        )

        if not camada.isValid():

            QMessageBox.critical(
                self,
                "Coleta Rural",
                "Não foi possível carregar a camada padrão criada."
            )

            return None

        return camada

    def incluir_camada_padrao(self):

        nome, ok = QInputDialog.getText(
            self,
            "Camada Padrão",
            "Informe o nome da camada:"
        )

        if not ok:
            return

        nome = nome.strip()

        if not nome:

            QMessageBox.warning(
                self,
                "Coleta Rural",
                "Informe um nome válido para a camada."
            )

            return

        if QgsProject.instance().mapLayersByName(nome):

            QMessageBox.warning(
                self,
                "Coleta Rural",
                f"Já existe uma camada com o nome \"{nome}\" no projeto."
            )

            return

        formatos = {
            "Shapefile (.shp)": "shp",
            "GeoPackage (.gpkg)": "gpkg"
        }

        formato_escolhido, ok = QInputDialog.getItem(
            self,
            "Formato da Camada",
            "Selecione o formato do arquivo:",
            list(formatos.keys()),
            0,
            False
        )

        if not ok:
            return

        formato = formatos[formato_escolhido]

        caminho_base_origem = os.path.join(
            os.path.dirname(__file__),
            "camada_padrao"
        )

        if not os.path.exists(caminho_base_origem + ".shp"):

            QMessageBox.critical(
                self,
                "Coleta Rural",
                "Arquivo da camada padrão não encontrado no plugin."
            )

            return

        pasta_padrao = self.obter_pasta_padrao()

        pasta_destino = QFileDialog.getExistingDirectory(
            self,
            "Selecione a pasta onde a camada padrão será criada",
            pasta_padrao
        )

        if not pasta_destino:
            return

        nome_arquivo = re.sub(
            r'[\\/:*?"<>|]',
            "_",
            nome
        ).strip() or "camada_padrao"

        caminho_destino = os.path.join(
            pasta_destino,
            f"{nome_arquivo}.{formato}"
        )

        if os.path.exists(caminho_destino):

            QMessageBox.warning(
                self,
                "Coleta Rural",
                (
                    f"Já existe um arquivo \"{nome_arquivo}.{formato}\" em "
                    f"\"{pasta_destino}\".\n\nEscolha outro nome."
                )
            )

            return

        if formato == "shp":

            camada = self.criar_camada_shapefile(
                caminho_base_origem,
                caminho_destino,
                nome
            )

        else:

            camada = self.criar_camada_geopackage(
                caminho_base_origem,
                caminho_destino,
                nome
            )

        if camada is None:
            return

        QgsProject.instance().addMapLayer(
            camada
        )

        self.carregar_camadas()

        for i in range(self.lstCamadas.count()):

            item = self.lstCamadas.item(i)

            if item.text() == nome:

                item.setCheckState(
                    Qt.Checked
                )

                break

    def salvar_configuracao(self):

        camadas_selecionadas = []

        for i in range(self.lstCamadas.count()):

            item = self.lstCamadas.item(i)

            if item.checkState() == Qt.Checked:

                camadas_selecionadas.append(
                    item.text()
                )

        settings = QgsSettings()

        settings.setValue(
            "ColetaRural/camadas_permitidas",
            camadas_selecionadas
        )

        QMessageBox.information(
            self,
            "Coleta Rural",
            "Configurações salvas com sucesso."
        )

        self.accept()