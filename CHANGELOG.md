# Changelog

Todas as alterações relevantes deste projeto serão documentadas neste arquivo.

O formato segue o padrão de versionamento semântico (Semantic Versioning).

---

## [1.0.0] - 2026-07-18

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

1.0.0