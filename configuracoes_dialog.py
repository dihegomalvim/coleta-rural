# -*- coding: utf-8 -*-

import os

from qgis.PyQt import uic
from qgis.PyQt import QtWidgets

from qgis.PyQt.QtCore import Qt

from qgis.core import (
    QgsProject,
    QgsSettings
)

from qgis.PyQt.QtWidgets import (
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

        self.btnSalvarConfig.clicked.connect(
            self.salvar_configuracao
        )

        self.carregar_camadas()

    def carregar_camadas(self):

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

            self.lstCamadas.addItem(item)

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