# Coleta Rural

## Versão 1.0.0

Plugin QGIS para importação automática de memoriais descritivos gerados pelo sistema Coleta Rural, com criação e gravação de polígonos diretamente em camadas vetoriais previamente configuradas.

---

## Desenvolvedor

**Dihêgo Augusto Gomes Malvim de Barros**  
Assistente Técnico da Governança de Terras  
INCRA Pernambuco

---

## Objetivo

O plugin Coleta Rural foi desenvolvido para agilizar o processo de importação de memoriais descritivos em formato PDF, eliminando a necessidade de digitação manual de coordenadas e atributos.

A ferramenta realiza a leitura do memorial, extrai os dados do imóvel e gera automaticamente a geometria correspondente no QGIS.

---

## Funcionalidades

### Importação de Memorial

- Seleção de memorial em PDF;
- Leitura automática do conteúdo do documento;
- Extração de informações do imóvel;
- Extração automática dos vértices geográficos.

### Informações Extraídas

- Imóvel;
- Município;
- Declarante;
- CPF/CNPJ;
- Área;
- Coordenadas dos vértices.

### Pré-visualização

- Geração automática do polígono;
- Visualização temporária no mapa;
- Zoom automático para a geometria;
- Destaque visual com transparência.

### Configuração de Camadas

- Seleção das camadas autorizadas;
- Armazenamento das configurações do usuário;
- Exibição apenas das camadas permitidas na interface principal.

### Salvamento

- Inserção automática da geometria na camada escolhida;
- Preenchimento dos atributos do imóvel;
- Commit automático das alterações;
- Limpeza da área de trabalho após a importação.

---

## Campos Compatíveis

O plugin foi projetado para trabalhar com camadas contendo os seguintes atributos:

| Campo |
|---------|
| CIR |
| Imóvel |
| Matrícula |
| Município |
| Declarante |
| CPF/CNPJ |
| OBS |
| Área |

Campos adicionais podem ser adicionados futuramente.

---

## Fluxo de Trabalho

### 1. Selecionar Memorial

Clique em:

```text
Selecionar PDF