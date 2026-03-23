# Instruções de Construção — Validador Tributário NF-e / NFS-e
## Sistema de Análise de Impacto da Reforma Tributária (LC 214/2025)

> **Tipo de entrega:** React Artifact com Claude API integrada  
> **Uso:** Upload de XMLs de NF-e e NFS-e → análise tributária completa  
> **Base legal:** LC nº 214/2025 · EC nº 132/2023 · NT 2025.002 v1.40  
> **Alíquotas de referência:** CBS 8,8% + IBS 17,7% = 26,5% (pleno em 2033)

---

## 1. VISÃO GERAL DO SISTEMA

Construir um **React Artifact** (arquivo `.jsx`) com Claude API integrada que:

1. Aceita upload de XMLs de NF-e (modelo 55) e NFS-e (padrão nacional) — individual ou múltiplos arquivos
2. Faz parse dos XMLs inteiramente no browser (sem backend)
3. Envia os dados extraídos para a Claude API para análise tributária
4. Exibe resultado completo: comparativo atual × novo regime, créditos, split payment e exportação

O sistema deve funcionar como **ferramenta de validação e testes iniciais** — não emite nota, não se comunica com SEFAZ. É uma ferramenta analítica standalone.

---

## 2. STACK E DEPENDÊNCIAS

```
Framework:    React (hooks: useState, useCallback, useRef, useEffect)
Styling:      Tailwind CSS (apenas classes utilitárias base)
XML Parsing:  DOMParser nativo do browser (sem lib externa)
PDF Export:   Nenhuma lib — gerar CSV simples para exportação
API:          Anthropic Claude API — fetch direto para https://api.anthropic.com/v1/messages
Modelo:       claude-sonnet-4-20250514
```

**Não usar** nenhuma biblioteca externa além das já disponíveis no ambiente React do Artifact.

---

## 3. LAYOUT E DESIGN

### Estética
- Tema: **profissional fiscal brasileiro** — sóbrio, técnico, confiável
- Fundo: cinza muito escuro `#0f1117` ou preto suave
- Superfícies: `#1a1d27` (cards), `#242736` (inputs)
- Accent primário: verde esmeralda `#00c896` (positivo, crédito)
- Accent secundário: âmbar `#f59e0b` (atenção)
- Accent terciário: vermelho `#ef4444` (erro, aumento de carga)
- Texto principal: `#e8eaf0`
- Texto secundário: `#8b90a4`
- Fonte: `'IBM Plex Mono', monospace` para valores numéricos e códigos fiscais; `'Inter', sans-serif` para texto
- Importar via Google Fonts: `https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Inter:wght@400;500;600&display=swap`

### Estrutura da tela (layout vertical, scroll)

```
┌─────────────────────────────────────┐
│  CABEÇALHO: título + badge "2026"   │
├─────────────────────────────────────┤
│  ZONA DE UPLOAD (drag & drop)       │
│  + lista de arquivos carregados     │
├─────────────────────────────────────┤
│  BOTÃO: Analisar XMLs               │
├─────────────────────────────────────┤
│  [RESULTADOS — aparecem após análise]│
│  ┌──────────────────────────────┐   │
│  │ RESUMO DO LOTE (se batch)    │   │
│  └──────────────────────────────┘   │
│  ┌──────────────────────────────┐   │
│  │ CARD POR NOTA (expansível)   │   │
│  │  > Cabeçalho da nota         │   │
│  │  > Tabela de itens           │   │
│  │  > Comparativo tributário    │   │
│  │  > Créditos apurados         │   │
│  │  > Split payment             │   │
│  └──────────────────────────────┘   │
│  BOTÃO: Exportar CSV / Exportar PDF │
└─────────────────────────────────────┘
```

---

## 4. MÓDULO 1 — PARSER XML (browser, puro JS)

### 4.1 Detecção de tipo de documento

O parser deve identificar automaticamente o tipo pelo elemento raiz ou namespace do XML:

```
NF-e  → tag raiz: <nfeProc> ou <NFe>, namespace: nfe.fazenda.gov.br/2009/01
NFS-e → tag raiz: <CompNfse> ou <NfseProc>, namespace: nfse.abrasf.org.br ou gov.br/nfse
```

Função a implementar:
```javascript
function detectTipoDocumento(xmlDoc) {
  // retorna: 'NFe' | 'NFSe' | 'desconhecido'
}
```

### 4.2 Campos a extrair — NF-e (modelo 55)

**Cabeçalho (grupo B — ide):**
| Campo XML | XPath | Descrição |
|---|---|---|
| `cNF` | `//ide/cNF` | Código numérico da NF |
| `natOp` | `//ide/natOp` | Natureza da operação |
| `dhEmi` | `//ide/dhEmi` | Data/hora de emissão |
| `tpNF` | `//ide/tpNF` | Tipo: 0=entrada, 1=saída |
| `idDest` | `//ide/idDest` | Destino: 1=interna, 2=interestadual |
| `cMunFG` | `//ide/cMunFG` | Município fato gerador |
| `finNFe` | `//ide/finNFe` | Finalidade: 1=normal, 3=ajuste |
| `indFinal` | `//ide/indFinal` | 1=consumidor final |

**Emitente (grupo C):**
| Campo XML | XPath | Descrição |
|---|---|---|
| `CNPJ` | `//emit/CNPJ` | CNPJ do emitente |
| `xNome` | `//emit/xNome` | Razão social |
| `CRT` | `//emit/CRT` | Regime: 1=Simples, 3=Normal |
| `UF` | `//emit/enderEmit/UF` | Estado |

**Destinatário (grupo E):**
| Campo XML | XPath | Descrição |
|---|---|---|
| `CNPJ` | `//dest/CNPJ` | CNPJ do destinatário (se PJ) |
| `CPF` | `//dest/CPF` | CPF do destinatário (se PF) |
| `indIEDest` | `//dest/indIEDest` | 1=contribuinte, 2=isento, 9=não contribuinte |

**Por item (grupo I — det, repetido N vezes):**
| Campo XML | XPath | Descrição |
|---|---|---|
| `nItem` | `//det/@nItem` | Número do item |
| `cProd` | `//det/prod/cProd` | Código do produto |
| `xProd` | `//det/prod/xProd` | Descrição do produto |
| `NCM` | `//det/prod/NCM` | Código NCM 8 dígitos |
| `CFOP` | `//det/prod/CFOP` | CFOP da operação |
| `uCom` | `//det/prod/uCom` | Unidade comercial |
| `qCom` | `//det/prod/qCom` | Quantidade |
| `vUnCom` | `//det/prod/vUnCom` | Valor unitário |
| `vProd` | `//det/prod/vProd` | Valor total do item |
| `vDesc` | `//det/prod/vDesc` | Desconto (opcional) |

**Tributos por item — sistema ATUAL (extrair se presentes):**
| Campo XML | XPath | Tributo |
|---|---|---|
| `vICMS` | `//det/imposto/ICMS//vICMS` | Valor ICMS |
| `pICMS` | `//det/imposto/ICMS//pICMS` | Alíquota ICMS |
| `CST` / `CSOSN` | `//det/imposto/ICMS//CST` ou `//CSOSN` | Situação ICMS |
| `vPIS` | `//det/imposto/PIS//vPIS` | Valor PIS |
| `pPIS` | `//det/imposto/PIS//pPIS` | Alíquota PIS |
| `vCOFINS` | `//det/imposto/COFINS//vCOFINS` | Valor COFINS |
| `pCOFINS` | `//det/imposto/COFINS//pCOFINS` | Alíquota COFINS |
| `vIPI` | `//det/imposto/IPI//vIPI` | Valor IPI (se houver) |
| `pIPI` | `//det/imposto/IPI//pIPI` | Alíquota IPI |

**Tributos por item — GRUPO UB (IBS/CBS — NT 2025.002, se presente):**
| Campo XML | Tag no XML | Descrição |
|---|---|---|
| `CST` | `//det/imposto/IBSCBS/CST` | CST-IBS/CBS (3 dígitos) |
| `cClassTrib` | `//det/imposto/IBSCBS/cClassTrib` | Classificação tributária (6 dígitos) |
| `vBC` | `//det/imposto/IBSCBS/gIBSCBS/vBC` | Base de cálculo |
| `pIBSUF` | `//det/imposto/IBSCBS/gIBSCBS/gIBSUF/pIBSUF` | Alíquota IBS estadual |
| `vIBSUF` | `//det/imposto/IBSCBS/gIBSCBS/gIBSUF/vIBSUF` | Valor IBS estadual |
| `pIBSMun` | `//det/imposto/IBSCBS/gIBSCBS/gIBSMun/pIBSMun` | Alíquota IBS municipal |
| `vIBSMun` | `//det/imposto/IBSCBS/gIBSCBS/gIBSMun/vIBSMun` | Valor IBS municipal |
| `pCBS` | `//det/imposto/IBSCBS/gIBSCBS/gCBS/pCBS` | Alíquota CBS |
| `vCBS` | `//det/imposto/IBSCBS/gIBSCBS/gCBS/vCBS` | Valor CBS |

**Totais da nota (grupo W):**
| Campo XML | Tag | Descrição |
|---|---|---|
| `vNF` | `//total/ICMSTot/vNF` | Valor total da nota |
| `vICMS` | `//total/ICMSTot/vICMS` | Total ICMS |
| `vPIS` | `//total/ICMSTot/vPIS` | Total PIS |
| `vCOFINS` | `//total/ICMSTot/vCOFINS` | Total COFINS |
| `vIBSTot` | `//total/IBSCBSTot/vIBSTot` | Total IBS (se grupo W03 presente) |
| `vCBSTot` | `//total/IBSCBSTot/vCBSTot` | Total CBS (se grupo W03 presente) |

**Chave de acesso:** extrair do atributo `Id` da tag `<infNFe Id="NFe...">` ou da tag `<chNFe>` dentro de `<protNFe>`.

### 4.3 Campos a extrair — NFS-e (padrão nacional)

```
CNPJ prestador:   //Prestador/IdentificacaoPrestador/CpfCnpj/Cnpj
xNome prestador:  //Prestador/NomeRazaoSocial
CNPJ tomador:     //Tomador/IdentificacaoTomador/CpfCnpj/Cnpj
competência:      //InfNfse/Competencia ou //DataEmissao
cód. tributação:  //Servico/CodigoTributacaoMunicipio
descrição:        //Servico/Discriminacao
NBS:              //Servico/CodigoNbs (se presente)
valor serviços:   //Servico/Valores/ValorServicos
ISS retido:       //Servico/Valores/IssRetido (1=sim, 2=não)
alíquota ISS:     //Servico/Valores/Aliquota
valor ISS:        //Servico/Valores/ValorIss
valor líquido:    //Servico/Valores/ValorLiquidoNfse
CST IBS/CBS:      //Servico/IBSCBS/CST (se presente)
cClassTrib:       //Servico/IBSCBS/cClassTrib (se presente)
pCBS:             //Servico/IBSCBS/gIBSCBS/gCBS/pCBS (se presente)
vCBS:             //Servico/IBSCBS/gIBSCBS/gCBS/vCBS (se presente)
```

### 4.4 Detecção de cenário XML

Após o parse, classificar cada documento em um dos dois cenários:

**Cenário A — Grupo UB presente:**
- XML já contém `<IBSCBS>` com CST, cClassTrib e valores calculados
- Ação: extrair valores declarados + comparar com recálculo do motor
- Gerar alerta se divergência > 0,01%

**Cenário B — Grupo UB ausente (XML pré-reforma ou não preenchido):**
- XML só contém ICMS/PIS/COFINS/ISS
- Ação: projetar IBS/CBS pelo NCM + regime + ano
- Exibir como "simulação — como seria em 2027+"

### 4.5 Estrutura de saída do parser

```javascript
{
  tipo: "NFe" | "NFSe",
  cenario: "A" | "B",
  chave_acesso: "35260312...",  // 44 dígitos ou null
  emitente: {
    cnpj: "12345678000195",
    nome: "Empresa XYZ",
    crt: "3",  // 1=Simples, 2=Simples Excesso, 3=Normal
    regime: "Lucro Presumido",  // derivado do CRT
    uf: "SP"
  },
  destinatario: {
    cnpj_cpf: "98765432000100",
    tipo: "PJ" | "PF",
    contribuinte: true | false  // derivado de indIEDest
  },
  data_emissao: "2026-03-15",
  ano_emissao: 2026,
  natureza_operacao: "Venda de mercadoria",
  valor_total_nota: 10000.00,
  itens: [
    {
      numero: 1,
      codigo: "PROD001",
      descricao: "Produto X",
      ncm: "84714900",
      nbs: null,  // preencher para NFSe
      cfop: "5102",
      quantidade: 10,
      valor_unitario: 1000.00,
      valor_total: 10000.00,
      desconto: 0,
      tributos_declarados: {
        icms: { valor: 1800.00, aliquota: 0.18, cst: "00" },
        pis:  { valor: 165.00,  aliquota: 0.0165 },
        cofins: { valor: 760.00, aliquota: 0.076 },
        ipi:  { valor: 0,       aliquota: 0 },
        iss:  { valor: 0,       aliquota: 0 },  // NFSe
        ibs:  { valor: null,    aliquota: null },  // null se cenário B
        cbs:  { valor: null,    aliquota: null }
      },
      cst_ibs_cbs: null,   // null se cenário B
      cclasstrib: null     // null se cenário B
    }
  ],
  erros_parse: [],  // lista de erros não fatais durante o parse
  arquivo_original: "nota001.xml"
}
```

---

## 5. MÓDULO 2 — MOTOR DE CÁLCULO TRIBUTÁRIO

### 5.1 Tabela de alíquotas de transição (embutida no código)

```javascript
const ALIQUOTAS_TRANSICAO = {
  2026: { cbs: 0.009,  ibs_uf: 0.001,  ibs_mun: 0.000, total: 0.010 },
  2027: { cbs: 0.088,  ibs_uf: 0.025,  ibs_mun: 0.025, total: 0.138 },
  2028: { cbs: 0.088,  ibs_uf: 0.025,  ibs_mun: 0.025, total: 0.138 },
  2029: { cbs: 0.088,  ibs_uf: 0.089,  ibs_mun: 0.088, total: 0.265 },
  2030: { cbs: 0.088,  ibs_uf: 0.089,  ibs_mun: 0.088, total: 0.265 },
  2031: { cbs: 0.088,  ibs_uf: 0.089,  ibs_mun: 0.088, total: 0.265 },
  2032: { cbs: 0.088,  ibs_uf: 0.089,  ibs_mun: 0.088, total: 0.265 },
  2033: { cbs: 0.088,  ibs_uf: 0.089,  ibs_mun: 0.088, total: 0.265 },
};
```

### 5.2 Fatores de redução por setor (embutidos)

```javascript
const REDUCOES_SETOR = {
  // NCMs / setores com redução de 60% (fator = 0.40 da alíquota plena)
  saude:       { fator: 0.40, exemplos_ncm: ["3001","3002","3003","3004","3005","3006"] },
  educacao:    { fator: 0.40, exemplos_ncm: [] },  // detectado pelo NBS/cClassTrib
  transporte:  { fator: 0.40, exemplos_ncm: [] },
  alimentos_basicos: { fator: 0.40, exemplos_ncm: ["1006","0713","0201","0202","0207","0401"] },

  // NCMs com redução de 30% (profissionais liberais — detectado via NBS)
  servicos_liberais: { fator: 0.70, exemplos_nbs: ["01040"] },  // Serv. jurídicos, eng, etc.

  // Alíquota zero — cesta básica nacional
  cesta_basica_zero: {
    fator: 0.00,
    ncms: ["1006","0713","0201","0202","0203","0207","0401","1905"]
    // arroz, feijão, carnes, leite, pão — verificar lista completa na LC 214/2025
  },

  // Imposto Seletivo (IS) — incide ALÉM do IBS+CBS
  imposto_seletivo: {
    ncms_cigarros:   { prefixo: "2402", aliquota_is: 0.20 },
    ncms_alcoolicas: { prefixo: "2203", aliquota_is: 0.10 },
    ncms_refrigerante: { prefixo: "2202", aliquota_is: 0.08 },
    ncms_mineracao:  { prefixo: "2601", aliquota_is: 0.04 },
  }
};
```

### 5.3 Lógica de cálculo por item

```javascript
function calcularItemNovo(item, regime_emitente, ano_emissao) {
  const aliq = ALIQUOTAS_TRANSICAO[ano_emissao] || ALIQUOTAS_TRANSICAO[2026];
  const base = item.valor_total - (item.desconto || 0);

  // 1. Determinar fator de redução pelo NCM
  const fator = detectarFatorReducao(item.ncm, item.nbs);

  // 2. Calcular CBS
  const cbs_bruta = base * aliq.cbs * fator;

  // 3. Calcular IBS
  const ibs_uf_bruta  = base * aliq.ibs_uf  * fator;
  const ibs_mun_bruta = base * aliq.ibs_mun * fator;
  const ibs_total     = ibs_uf_bruta + ibs_mun_bruta;

  // 4. Calcular Imposto Seletivo (se NCM enquadrado)
  const is = calcularIS(item.ncm, base);

  // 5. Calcular crédito gerado para o destinatário
  // Apenas se destinatário for contribuinte (PJ, não-Simples no padrão)
  const credito_cbs = cbs_bruta;  // crédito pleno (não cumulatividade)
  const credito_ibs = ibs_total;

  return {
    base_calculo: base,
    fator_reducao: fator,
    cbs: { aliquota: aliq.cbs * fator, valor: round2(cbs_bruta) },
    ibs_uf:  { aliquota: aliq.ibs_uf  * fator, valor: round2(ibs_uf_bruta) },
    ibs_mun: { aliquota: aliq.ibs_mun * fator, valor: round2(ibs_mun_bruta) },
    ibs_total: round2(ibs_total),
    is: round2(is),
    total_novo: round2(cbs_bruta + ibs_total + is),
    credito_cbs: round2(credito_cbs),
    credito_ibs: round2(credito_ibs),
    setor_identificado: detectarSetor(item.ncm, item.nbs)
  };
}
```

### 5.4 Cálculo de split payment por nota

```javascript
function calcularSplitPayment(total_ibs, total_cbs, valor_total_nota) {
  // Split payment: imposto retido na fonte no momento do pagamento
  const valor_retido = total_ibs + total_cbs;
  const percentual_retido = valor_total_nota > 0 ? valor_retido / valor_total_nota : 0;

  // Float perdido: hoje empresas pagam ~30-50 dias depois
  const float_dias_atual = 35;  // média 35 dias
  const custo_float_mensal = valor_retido;  // capital indisponível

  return {
    valor_retido: round2(valor_retido),
    valor_liquido_recebido: round2(valor_total_nota - valor_retido),
    percentual_retido: round2(percentual_retido * 100),
    float_perdido_dias: float_dias_atual,
    impacto_caixa_mensal: round2(custo_float_mensal),
    observacao: `R$ ${round2(valor_retido).toFixed(2)} serão retidos automaticamente no pagamento a partir de 2027`
  };
}
```

### 5.5 Comparativo de carga tributária

```javascript
function calcularComparativo(tributos_declarados, tributos_calculados, valor_nota) {
  const carga_atual = (
    (tributos_declarados.icms   || 0) +
    (tributos_declarados.pis    || 0) +
    (tributos_declarados.cofins || 0) +
    (tributos_declarados.ipi    || 0) +
    (tributos_declarados.iss    || 0)
  );

  const carga_nova = tributos_calculados.total_novo;

  const delta_abs = round2(carga_nova - carga_atual);
  const delta_pct = carga_atual > 0 ? round2((delta_abs / carga_atual) * 100) : null;

  return {
    carga_atual: round2(carga_atual),
    carga_nova:  round2(carga_nova),
    delta_abs,
    delta_pct,
    tendencia: delta_abs < 0 ? "reducao" : delta_abs > 0 ? "aumento" : "neutro",
    carga_atual_pct_nota: valor_nota > 0 ? round2((carga_atual / valor_nota) * 100) : 0,
    carga_nova_pct_nota:  valor_nota > 0 ? round2((carga_nova  / valor_nota) * 100) : 0,
  };
}
```

---

## 6. MÓDULO 3 — INTEGRAÇÃO COM CLAUDE API

### 6.1 Quando chamar a Claude API

A Claude API é chamada **uma vez por lote** (não por nota individual), recebendo o resumo de todas as notas parseadas. Ela realiza:

1. Interpretação de NCMs ambíguos ou não reconhecidos
2. Análise qualitativa do impacto por setor
3. Geração do parágrafo de recomendação estratégica
4. Alertas específicos por tipo de operação

### 6.2 Prompt para a Claude API

```javascript
function buildPrompt(lote_resumo) {
  return `Você é um especialista tributário brasileiro especializado na Reforma Tributária de 2026 (LC 214/2025).

Analise o seguinte lote de notas fiscais processadas e forneça uma análise tributária em JSON.

DADOS DO LOTE:
${JSON.stringify(lote_resumo, null, 2)}

INSTRUÇÕES:
1. Para cada nota, confirme ou corrija a classificação de setor (saúde, educação, serviços, comércio, indústria, etc.)
2. Identifique NCMs que possam ter tratamento especial (cesta básica, Imposto Seletivo, ZFM, etc.)
3. Gere um array de alertas por nota (máximo 3 alertas por nota)
4. Gere um resumo executivo do lote em português (máximo 150 palavras)
5. Gere recomendações estratégicas (máximo 3 recomendações)

RESPONDA APENAS EM JSON com esta estrutura exata:
{
  "analise_por_nota": [
    {
      "chave_acesso": "string",
      "setor_confirmado": "string",
      "tratamento_especial": "nenhum | cesta_basica | imposto_seletivo | saude | educacao | zmf | outro",
      "alertas": [
        { "tipo": "erro|atencao|info", "mensagem": "string" }
      ],
      "observacao_ncm": "string ou null"
    }
  ],
  "resumo_executivo": "string",
  "recomendacoes": [
    { "prioridade": "alta|media|baixa", "texto": "string" }
  ]
}`;
}
```

### 6.3 Chamada à API

```javascript
async function chamarClaudeAPI(lote_resumo) {
  const response = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: "claude-sonnet-4-20250514",
      max_tokens: 1000,
      messages: [{ role: "user", content: buildPrompt(lote_resumo) }]
    })
  });
  const data = await response.json();
  const text = data.content[0].text;
  // Limpar possíveis backticks antes de parsear
  const clean = text.replace(/```json|```/g, "").trim();
  return JSON.parse(clean);
}
```

---

## 7. MÓDULO 4 — COMPONENTES DE UI

### 7.1 Zona de Upload

- Área de drag & drop com borda tracejada, cor accent ao hover
- Aceitar: `accept=".xml"`, `multiple={true}`
- Mostrar lista de arquivos carregados com: nome, tamanho, status (aguardando / processado / erro)
- Botão "Remover" por arquivo
- Contador: "3 arquivos carregados"
- Ao arrastar arquivo sobre a área: mudar fundo e borda para accent verde

```jsx
// Componente DropZone
// Props: onFilesLoaded(files[])
// State interno: isDragging, filesLoaded[]
```

### 7.2 Card de Resultado por Nota

Cada nota processada vira um card expansível com:

**Header do card (sempre visível):**
- Ícone de tipo (NF-e / NFS-e) + Número/chave resumida
- Nome do emitente + CNPJ
- Data de emissão
- Badge de cenário: "A — IBS/CBS declarado" (verde) ou "B — Simulação" (âmbar)
- Badge de tendência: "↓ −12,3%" (verde) ou "↑ +8,1%" (vermelho)
- Botão expandir/colapsar

**Corpo expandido (4 abas ou seções com scroll):**

**Aba 1 — Itens**
Tabela com colunas:
`Nº | Descrição | NCM | Valor | ICMS | PIS/COFINS | IBS calc. | CBS calc. | IS | Δ%`

**Aba 2 — Comparativo**
Duas colunas lado a lado:
- Coluna esquerda: "Sistema Atual" — ICMS + PIS + COFINS + ISS + IPI
- Coluna direita: "Sistema Novo (ano X)" — IBS + CBS + IS
- Linha de total com delta em valor absoluto e percentual
- Mini gráfico de barras horizontais (CSS puro, sem lib)

**Aba 3 — Créditos**
- Tabela: por item → crédito CBS gerado + crédito IBS gerado
- Total de créditos aproveitáveis
- Observação: "Crédito válido apenas se destinatário for contribuinte do IBS/CBS"
- Alerta se destinatário for Simples Nacional (crédito limitado)

**Aba 4 — Split Payment**
- Valor total da nota
- Valor retido automaticamente (IBS + CBS)
- Valor líquido recebido pelo emitente
- Percentual retido
- Texto de alerta: "A partir de 2027, R$ X,XX serão retidos na fonte no momento do pagamento"
- Indicador visual: barra mostrando proporção retida × recebida

### 7.3 Resumo de Lote (aparece quando há 2+ notas)

Card no topo dos resultados com:
- Total de notas processadas / com erro
- Soma do valor total das notas
- Soma carga tributária atual × nova → delta total
- Total de créditos gerados pelo lote
- Total retido via split payment
- Análise Claude: resumo executivo + recomendações (com loading state)

### 7.4 Alertas por nota

Sistema de badges coloridos dentro de cada card:

```
🔴 ERRO CRÍTICO   — NCM inválido, schema falhou, valor inconsistente
🟡 ATENÇÃO        — IBS/CBS declarado diverge do calculado (>0,01%)
🟡 ATENÇÃO        — NCM com possível Imposto Seletivo não destacado
🟢 INFO           — Produto da cesta básica — alíquota zero aplicada
🟢 INFO           — Redução de 60% aplicada (saúde/educação)
🔵 SIMULAÇÃO      — Grupo UB ausente — valores projetados para 2027+
```

### 7.5 Exportação

**Exportar CSV:** gerar string CSV com todas as notas e itens, acionar download via `<a href="data:text/csv...">`.

Colunas do CSV:
```
chave_acesso | tipo_doc | emitente_cnpj | emitente_nome | regime | data_emissao | 
item_numero | item_descricao | ncm_nbs | valor_item | 
icms_atual | pis_atual | cofins_atual | iss_atual | total_atual |
cbs_novo | ibs_novo | is_novo | total_novo | 
delta_abs | delta_pct | credito_cbs | credito_ibs | split_payment_retido |
cenario | alertas
```

**Exportar PDF:** usar `window.print()` com CSS de impressão (`@media print`) aplicado à div de resultados. Ocultar zona de upload e botões na impressão.

---

## 8. ESTADOS DA APLICAÇÃO

```javascript
// Estado global (useState no componente raiz)
const [arquivos, setArquivos] = useState([]);          // File[] carregados
const [resultados, setResultados] = useState([]);      // resultado por nota
const [resumoLote, setResumoLote] = useState(null);    // resumo consolidado
const [analiseIA, setAnaliseIA] = useState(null);      // resposta Claude API
const [loading, setLoading] = useState(false);         // processando
const [loadingIA, setLoadingIA] = useState(false);     // aguardando Claude
const [erroGlobal, setErroGlobal] = useState(null);    // erro fatal
const [abaAtiva, setAbaAtiva] = useState({});          // {chave: "itens"...}
```

---

## 9. FLUXO DE PROCESSAMENTO (onClick "Analisar")

```
1. setLoading(true)
2. Para cada arquivo em paralelo (Promise.all):
   a. Ler conteúdo como texto (FileReader)
   b. Parsear com DOMParser
   c. Detectar tipo (NFe / NFSe)
   d. Extrair campos (parser)
   e. Calcular tributos novos (motor)
   f. Calcular comparativo
   g. Calcular split payment
   h. Classificar alertas determinísticos
3. setResultados(todosResultados)
4. Calcular resumoLote (somas e médias)
5. setLoading(false) — mostrar resultados
6. setLoadingIA(true)
7. Chamar Claude API com resumo do lote
8. setAnaliseIA(resposta)
9. setLoadingIA(false)
```

---

## 10. TRATAMENTO DE ERROS

| Situação | Comportamento |
|---|---|
| XML malformado | Marcar arquivo com erro, continuar lote, exibir mensagem |
| Schema inválido (não é NF-e nem NFS-e) | Idem acima |
| NCM não mapeado localmente | Calcular com alíquota padrão, marcar como "pendente revisão IA" |
| Claude API falha ou timeout | Exibir resultados determinísticos normalmente, mostrar "análise IA indisponível" |
| Arquivo maior que 5MB | Rejeitar na zona de upload com mensagem |
| Nenhum arquivo carregado | Desabilitar botão "Analisar" |

---

## 11. TEXTOS E LABELS DA INTERFACE

```
Título:          "Validador Tributário NF-e / NFS-e"
Subtítulo:       "Reforma Tributária 2026 — LC 214/2025"
Badge header:    "IBS · CBS · IS"
Drop zone:       "Arraste XMLs de NF-e ou NFS-e aqui"
Drop zone sub:   "ou clique para selecionar • múltiplos arquivos aceitos"
Botão analisar:  "Analisar XMLs"
Loading:         "Processando notas..."
Loading IA:      "Gerando análise tributária..."
Cenário A badge: "IBS/CBS Declarado"
Cenário B badge: "Projeção 2027+"
Aba 1:           "Itens"
Aba 2:           "Comparativo"
Aba 3:           "Créditos"
Aba 4:           "Split Payment"
Exportar:        "Exportar CSV"  |  "Imprimir / PDF"
Footer:          "Base: LC 214/2025 · NT 2025.002 v1.40 · Alíquotas de referência — não substitui assessoria tributária"
```

---

## 12. EXEMPLO DE XML MÍNIMO PARA TESTES

### NF-e mínima válida (cenário B — sem grupo UB)
```xml
<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe">
  <NFe>
    <infNFe Id="NFe35260312345678000195550010000001231234567890">
      <ide>
        <natOp>Venda de mercadoria</natOp>
        <dhEmi>2026-03-15T10:00:00-03:00</dhEmi>
        <tpNF>1</tpNF>
        <idDest>1</idDest>
        <finNFe>1</finNFe>
        <indFinal>0</indFinal>
      </ide>
      <emit>
        <CNPJ>12345678000195</CNPJ>
        <xNome>Empresa Teste Ltda</xNome>
        <CRT>3</CRT>
        <enderEmit><UF>SP</UF></enderEmit>
      </emit>
      <dest>
        <CNPJ>98765432000100</CNPJ>
        <indIEDest>1</indIEDest>
      </dest>
      <det nItem="1">
        <prod>
          <cProd>PROD001</cProd>
          <xProd>Computador Notebook</xProd>
          <NCM>84714900</NCM>
          <CFOP>5102</CFOP>
          <uCom>UN</uCom>
          <qCom>2</qCom>
          <vUnCom>5000.00</vUnCom>
          <vProd>10000.00</vProd>
        </prod>
        <imposto>
          <ICMS>
            <ICMS00>
              <orig>0</orig><CST>00</CST>
              <pICMS>18.00</pICMS><vICMS>1800.00</vICMS>
            </ICMS00>
          </ICMS>
          <PIS>
            <PISAliq>
              <CST>01</CST><vBC>10000.00</vBC>
              <pPIS>1.65</pPIS><vPIS>165.00</vPIS>
            </PISAliq>
          </PIS>
          <COFINS>
            <COFINSAliq>
              <CST>01</CST><vBC>10000.00</vBC>
              <pCOFINS>7.60</pCOFINS><vCOFINS>760.00</vCOFINS>
            </COFINSAliq>
          </COFINS>
        </imposto>
      </det>
      <total>
        <ICMSTot>
          <vICMS>1800.00</vICMS><vPIS>165.00</vPIS>
          <vCOFINS>760.00</vCOFINS><vNF>10000.00</vNF>
        </ICMSTot>
      </total>
    </infNFe>
  </NFe>
</nfeProc>
```

### NF-e com grupo UB (cenário A — IBS/CBS declarado)
Adicionar dentro de `<imposto>` de cada `<det>`, após COFINS:
```xml
<IBSCBS>
  <CST>000</CST>
  <cClassTrib>000001</cClassTrib>
  <gIBSCBS>
    <vBC>10000.00</vBC>
    <gIBSUF>
      <pIBSUF>0.10</pIBSUF>
      <vIBSUF>10.00</vIBSUF>
    </gIBSUF>
    <gIBSMun>
      <pIBSMun>0.00</pIBSMun>
      <vIBSMun>0.00</vIBSMun>
    </gIBSMun>
    <vIBS>10.00</vIBS>
    <gCBS>
      <pCBS>0.90</pCBS>
      <vCBS>90.00</vCBS>
    </gCBS>
  </gIBSCBS>
</IBSCBS>
```

---

## 13. RESTRIÇÕES E OBSERVAÇÕES IMPORTANTES

1. **Não há backend** — todo processamento ocorre no browser. Nenhuma NF-e é enviada para servidor.
2. **Não validar assinatura digital** — fora do escopo desta fase. Apenas parsear o XML.
3. **NCMs não mapeados** — usar alíquota padrão 26,5% plena e marcar como "classificação pendente". A Claude API pode sugerir a classificação correta.
4. **Simples Nacional** — CRT=1: calcular projeção do DAS ajustado (estimar +25% sobre alíquota DAS atual). Não é igual ao regime normal.
5. **2026 é ano de testes** — exibir sempre a projeção para 2027 também, não apenas 2026. Deixar claro na UI que em 2026 não há recolhimento efetivo.
6. **Valores arredondados** — usar `Math.round(value * 100) / 100` para 2 casas decimais.
7. **Disclaimer obrigatório** no rodapé: "Ferramenta de análise didática. Não substitui parecer tributário. Base: LC 214/2025."

---

## 14. CHECKLIST DE ENTREGA

- [ ] Upload de XML único e múltiplos arquivos
- [ ] Detecção automática NF-e vs NFS-e
- [ ] Parser Cenário A (grupo UB presente)
- [ ] Parser Cenário B (grupo UB ausente)
- [ ] Motor de cálculo com tabela 2026–2033
- [ ] Reduções setoriais (saúde, educação, cesta básica)
- [ ] Cálculo de créditos por item
- [ ] Cálculo de split payment
- [ ] Comparativo atual × novo regime
- [ ] Card expansível por nota com 4 abas
- [ ] Resumo consolidado do lote
- [ ] Integração Claude API (resumo executivo + alertas + recomendações)
- [ ] Loading states (processamento + IA)
- [ ] Sistema de alertas (erro / atenção / info)
- [ ] Exportação CSV
- [ ] Impressão / PDF via CSS print
- [ ] Tratamento de erros por arquivo (não quebra o lote)
- [ ] Responsivo (funciona em tablet)
- [ ] Disclaimer fiscal no rodapé
