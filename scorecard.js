// FrontEnd/js/scorecard.js - Versão Final Compatível com o Script Python

// --- VARIÁVEIS GLOBAIS ---
let rawData = []; // Dados da chave "summary"
let aggregatedData = []; // Dados da chave "per_responsavel"
let dailyData = []; // Dados da chave "daily_data"
let periodInfo = {}; // Dados da chave "period_info"
let metasGerais = {}; // Dados da chave "metas_gerais"
let atingimentoMetas = {}; // Dados da chave "atingimento_metas_gerais"
let currentFilteredData = [];
let chartTemporalInstance = null;

// --- INICIALIZAÇÃO ---
loadallDataAndInitialize();

function toggleMenu() {
  const menu = document.getElementById("menuOptions");
  menu.style.display = (menu.style.display === "block") ? "none" : "block";
}

function loadallDataAndInitialize() {
    fetch('https://joaovidaamazonlog.github.io/atlas/data/dados_scorecard.json')
        .then(response => response.json())
        .then(data => {
            rawData = data.summary;
            aggregatedData = data.per_responsavel;
            dailyData = data.daily_data || [];
            periodInfo = data.period_info || {};
            metasGerais = data.metas_gerais || {};
            atingimentoMetas = data.atingimento_metas_gerais || {};

            if (periodInfo.start_date && periodInfo.end_date) {
                document.getElementById('periodInfo').textContent = `Período dos Dados: ${periodInfo.start_date} a ${periodInfo.end_date}`;
            } else {
                document.getElementById('periodInfo').textContent = "Período dos dados não especificado.";
            }

            populateFilters();
            applyDashboardFilters();
        })
        .catch(err => {
            alert('Erro ao carregar os dados iniciais: ' + err.message);
            console.error(err);
        });
}

// --- LÓGICA DE FILTROS ---
function populateFilters() {
    const owners = [...new Set(rawData.map(item => item.responsavel))].sort();
    const origins = [...new Set(rawData.map(item => item.origem))].sort();

    const ownerFilter = document.getElementById('ownerFilter');
    const originFilter = document.getElementById('originFilter');

    ownerFilter.innerHTML = '<option value="all">Todos</option>';
    originFilter.innerHTML = '<option value="all">Todos</option>';

    owners.forEach(o => ownerFilter.innerHTML += `<option value="${o}">${o}</option>`);
    origins.forEach(o => originFilter.innerHTML += `<option value="${o}">${o}</option>`);
}

function applyDashboardFilters() {
    const selectedOwner = document.getElementById('ownerFilter').value;
    const selectedOrigin = document.getElementById('originFilter').value;

    // Filtra os dados brutos
    currentFilteredData = rawData.filter(item => {
        const ownerMatch = selectedOwner === 'all' || item.responsavel === selectedOwner;
        const originMatch = selectedOrigin === 'all' || item.origem === selectedOrigin;
        return ownerMatch && originMatch;
    });

    // Filtra os dados agregados
    const filteredAggregatedData = aggregatedData.filter(item => {
        return selectedOwner === 'all' || item.responsavel === selectedOwner;
    });

    // Atualiza todos os componentes
    updateResumoGeral(filteredAggregatedData);
    updateCardsPessoas(filteredAggregatedData);
    updatePodiumOrigens();
    updateGraficoTemporal();
    updateTable(currentFilteredData);
}

// --- SEÇÃO 1: RESUMO GERAL ---
function updateResumoGeral(data) {
    updateKPIsGerais(data);
    updateMetasSemana();
    updateMelhorOrigem();
}

function updateKPIsGerais(data) {
    const container = document.getElementById('kpi-geral-container');
    
    if (data.length === 0) {
        container.innerHTML = '<div class="col-12"><p class="text-center">Sem dados para exibir.</p></div>';
        return;
    }

    const totalContatos = atingimentoMetas.contatos.atingido
    const totalCadastros = atingimentoMetas.cadastros.atingido
    const taxaCadastros = (totalCadastros / totalContatos) * 100
    const scoreGeral = (atingimentoMetas.scorecard_geral) * 100
    
    const kpis = [
        { title: 'Contatos Realizados', value: totalContatos, icon: 'fa-phone', color: '#3498db' },
        { title: 'Total de Cadastros', value: totalCadastros, icon: 'fa-address-card', color: '#2ecc71' },
        { title: 'Taxa de Cadastros', value: `${taxaCadastros.toFixed(2)}%`, icon: 'fa-percentage', color: '#e74c3c' },
        { title: 'Score Geral', value: `${scoreGeral.toFixed(0)}/100`, icon: 'fa-star', color: '#f39c12' }
    ];

    container.innerHTML = kpis.map(kpi => `
        <div class="col-md-3 mb-3">
            <div class="kpi-card" style="background: linear-gradient(135deg, ${kpi.color}, ${adjustColor(kpi.color, -20)});">
                <i class="fas ${kpi.icon} fa-2x mb-2"></i>
                <h3 class="font-weight-bold">${kpi.value}</h3>
                <p class="mb-0">${kpi.title}</p>
            </div>
        </div>
    `).join('');
}

function updateMetasSemana() {
    const container = document.getElementById('metas-container');
    
    // Usa os dados de atingimento de metas vindos do Python
    const metas = [
        { nome: 'Contatos', ...atingimentoMetas.contatos },
        { nome: 'Cadastros', ...atingimentoMetas.cadastros },
    ];

    container.innerHTML = metas.map(meta => {
        const percentual = meta.percentual || 0;
        const cor = percentual >= 100 ? 'success' : percentual >= 70 ? 'warning' : 'danger';
        
        return `
            <div class="meta-progress">
                <div class="d-flex justify-content-between">
                    <span><strong>${meta.nome}</strong></span>
                    <span>${meta.atingido || 0}/${meta.meta || 0} (${percentual.toFixed(1)}%)</span>
                </div>
                <div class="progress mt-1">
                    <div class="progress-bar bg-${cor}" style="width: ${Math.min(percentual, 100)}%"></div>
                </div>
            </div>
        `;
    }).join('');
}

function updateMelhorOrigem() {
    const container = document.getElementById('melhor-origem-container');
    
    // Agrupa por origem e calcula performance
    const origemStats = {};
    rawData.forEach(item => {
        if (!origemStats[item.origem]) {
            origemStats[item.origem] = { contatos: 0, cadastros: 0, conversoes: 0 };
        }
        origemStats[item.origem].contatos++;
        if (item.data_cadastro) origemStats[item.origem].cadastros++;
        if (item.data_conversao) origemStats[item.origem].conversoes++;
    });

    // Encontra a origem com melhor taxa de conversão
    let melhorOrigem = null;
    let melhorTaxa = 0;
    
    Object.keys(origemStats).forEach(origem => {
        const stats = origemStats[origem];
        const taxa = stats.contatos > 0 ? (stats.cadastros / stats.contatos) * 100 : 0;
        if (taxa > melhorTaxa) {
            melhorTaxa = taxa;
            melhorOrigem = { nome: origem, ...stats, taxa };
        }
    });

    if (melhorOrigem) {
        container.innerHTML = `
            <div class="card border-success">
                <div class="card-body text-center">
                    <h5 class="card-title text-success">${melhorOrigem.nome}</h5>
                    <p class="card-text">
                        <strong>Taxa de Cadastro: ${melhorOrigem.taxa.toFixed(1)}%</strong><br>
                        ${melhorOrigem.contatos} contatos → ${melhorOrigem.conversoes} cadastros
                    </p>
                </div>
            </div>
        `;
    } else {
        container.innerHTML = '<p class="text-muted">Dados insuficientes</p>';
    }
}

// --- SEÇÃO 2: CARDS POR PESSOA ---
function updateCardsPessoas(data) {
    const container = document.getElementById('cards-pessoas-container');
    
    if (data.length === 0) {
        container.innerHTML = '<div class="col-12"><p class="text-center">Sem dados para exibir.</p></div>';
        return;
    }

    container.innerHTML = data.map(pessoa => {
        const score = (pessoa.score_final || 0) * 100; // Usa o score_final calculado pelo Python
        const melhorOrigem = getMelhorOrigemPessoa(pessoa.responsavel);
        const cor = score >= 80 ? 'green' : score >= 60 ? 'gold' : 'red';
        
        return `
            <div class="wrap" role="region" aria-label="Cartão de performance">
                <article class="card">
                <!-- Nome -->
                <div class="name">${pessoa.responsavel}</div>

                <!-- Barra de progresso -->
                <div class="progress-row" aria-hidden="true">
                    <div class="progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${score}">
                    <div class="fill" style="width: ${score}%; background: ${cor};"></div>
                    </div>
                </div>

                <!-- Final score -->
                <div class="score-row">
                    <div class="label">Score</div>
                    <div class="value" aria-label="Final score value">${score.toFixed(0)}</div>
                </div>

                <!-- Métricas -->
                <div class="metrics" aria-label="Métricas">
                    <div class="metric"><div class="k">Contatos</div><div class="v">${pessoa.contatos}</div></div>
                    <div class="metric"><div class="k">Cadastros</div><div class="v">${pessoa.cadastros}</div></div>
                    <div class="metric"><div class="k">Conversões</div><div class="v">${pessoa.conversoes}</div></div>
                    <div class="metric"><div class="k">Melhor Origem</div><div class="v">${melhorOrigem}</div></div>
                </div>
                </article>
            </div>
        `;
    }).join('');
}

function getMelhorOrigemPessoa(responsavel) {
    const pessoaData = rawData.filter(item => item.responsavel === responsavel);
    const origemStats = {};
    
    pessoaData.forEach(item => {
        if (!origemStats[item.origem]) {
            origemStats[item.origem] = { contatos: 0, cadastros: 0 };
        }
        origemStats[item.origem].contatos++;
        if (item.data_cadastro) origemStats[item.origem].cadastros++;
    });

    let melhorOrigem = 'N/A';
    let melhorTaxa = 0;
    
    Object.keys(origemStats).forEach(origem => {
        const stats = origemStats[origem];
        const taxa = stats.contatos > 0 ? (stats.cadastros / stats.contatos) * 100 : 0;
        if (taxa > melhorTaxa) {
            melhorTaxa = taxa;
            melhorOrigem = origem;
        }
    });

    return melhorOrigem;
}

// --- SEÇÃO 3: PÓDIUM POR ORIGEM ---
function updatePodiumOrigens() {
    const container = document.getElementById('podium-container');
    const origens = [...new Set(rawData.map(item => item.origem))];
    
    container.innerHTML = origens.map(origem => {
        const top3 = getTop3PorOrigem(origem);
        
        return `
            <div class="col-md-4 mb-4">
                <div class="card">
                    <div class="card-header text-center">
                        <h5>${origem}</h5>
                    </div>
                    <div class="card-body">
                        <div class="podium-container">
                            ${top3.map((pessoa, index) => `
                                <div class="podium-item podium-${index === 0 ? '1st' : index === 1 ? '2nd' : '3rd'}">
                                    <div class="font-weight-bold">${pessoa.nome}</div>
                                    <small width: fit-content>${pessoa.taxa_cadastro}% de aproveitamento</small><br><small>${pessoa.cadastros} cadastros</small><br><small>${pessoa.contatos} contatos</small>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

function getTop3PorOrigem(origem) {
    const pessoasPorOrigem = {};
    
    rawData.filter(item => item.origem === origem).forEach(item => {
        if (!pessoasPorOrigem[item.responsavel]) {
            pessoasPorOrigem[item.responsavel] = { nome: item.responsavel, cadastros: 0, contatos: 0, taxa_cadastro: 0 };
        }
        if (item.data_cadastro) {
            pessoasPorOrigem[item.responsavel].cadastros++;
        }
        pessoasPorOrigem[item.responsavel].contatos++;

        pessoasPorOrigem[item.responsavel].taxa_cadastro = ((pessoasPorOrigem[item.responsavel].cadastros / pessoasPorOrigem[item.responsavel].contatos) * 100).toFixed(0)
    });

    return Object.values(pessoasPorOrigem)
        .sort((a, b) => b.taxa_cadastro - a.taxa_cadastro)
        .slice(0, 3);
}

// --- SEÇÃO 4: GRÁFICO TEMPORAL ---
function updateGraficoTemporal() {
    const ctx = document.getElementById('chartTemporal').getContext('2d');
    
    // Dados diários
    const datasOrdenadas = dailyData.map(item => item.data_contato);
    const contatosData = dailyData.map(item => item.contatos);
    const cadastrosData = dailyData.map(item => item.cadastros);
    
    // Média dos últimos 20 dias
    const ultimosContatos = contatosData.slice(-20);
    const ultimosCadastros = cadastrosData.slice(-20);
    const mediaContatos = ultimosContatos.length > 0 
        ? (ultimosContatos.reduce((a, b) => a + b, 0) / ultimosContatos.length) 
        : 0;
    const mediaCadastros = ultimosCadastros.length > 0 
        ? (ultimosCadastros.reduce((a, b) => a + b, 0) / ultimosCadastros.length) 
        : 0;

    const diasRestantes = getDiasRestantesMes();

    // --- Contatos acumulado + projeção ---
    const contatosCumulativo = [];
    contatosData.forEach((val, i) => {
        contatosCumulativo.push((contatosCumulativo[i - 1] || 0) + val);
    });
    let ultimoContato = contatosCumulativo.at(-1) || 0;
    for (let i = 0; i < diasRestantes; i++) {
        ultimoContato += mediaContatos;
        contatosCumulativo.push(ultimoContato);
    }

    // --- Cadastros acumulado + projeção ---
    const cadastrosCumulativo = [];
    cadastrosData.forEach((val, i) => {
        cadastrosCumulativo.push((cadastrosCumulativo[i - 1] || 0) + val);
    });
    let ultimoCadastro = cadastrosCumulativo.at(-1) || 0;
    for (let i = 0; i < diasRestantes; i++) {
        ultimoCadastro += mediaCadastros;
        cadastrosCumulativo.push(ultimoCadastro);
    }

    // Labels: datas reais + dias projetados
    const labels = [
        ...datasOrdenadas,
        ...Array.from({ length: diasRestantes }, (_, i) => `Proj+${i + 1}`)
    ];

    // Linha de meta de 580 contatos
    const metaContatosDiarios = 580;
    const metaContatosData = labels.map(() => metaContatosDiarios);
    const metaContatosCumulativo = metaContatosData.reduce((acc, val, i) => {
        acc.push((acc[i - 1] || 0) + val);
        return acc;
    }, []);

    // Linha de meta de 11 cadastros
    const metaCadastrosDiarios = 11;
    const metaCadastrosData = labels.map(() => metaCadastrosDiarios);
    const metaCadastrosCumulativo = metaCadastrosData.reduce((acc, val, i) => {
        acc.push((acc[i - 1] || 0) + val);
        return acc;
    }, []);

    if (chartTemporalInstance) chartTemporalInstance.destroy();

    chartTemporalInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [
                {
                    label: 'Contatos (Acumulado + Projeção)',
                    data: contatosCumulativo,
                    borderColor: '#3498db',
                    backgroundColor: 'rgba(52, 152, 219, 0.1)',
                    fill: false,
                    yAxisID: 'contatos',
                    pointStyle: 'circle',
                    pointRadius: 4,
                    pointHitRadius: 8,
                    pointHoverRadius: 6
                },
                {
                    label: 'Cadastros (Acumulado + Projeção)',
                    data: cadastrosCumulativo,
                    borderColor: '#2ecc71',
                    backgroundColor: 'rgba(46, 204, 113, 0.1)',
                    fill: false,
                    yAxisID: 'cadastros',
                    pointStyle: 'circle',
                    pointRadius: 4,
                    pointHitRadius: 8,
                    pointHoverRadius: 6
                },
                {
                    label: 'Meta de Contatos',
                    data: metaContatosCumulativo,
                    borderColor: '#e74c3c',
                    backgroundColor: 'rgba(231, 76, 60, 0.1)',
                    fill: false,
                    yAxisID: 'contatos',
                    pointStyle: 'circle',
                    pointRadius: 0,
                    pointHitRadius: 0,
                    pointHoverRadius: 0,
                    borderDash: [5, 5]
                },
                {
                    label: 'Meta de Cadastros',
                    data: metaCadastrosCumulativo,
                    borderColor: '#e74c3c',
                    backgroundColor: 'rgba(231, 76, 60, 0.1)',
                    fill: false,
                    yAxisID: 'cadastros',
                    pointStyle: 'circle',
                    pointRadius: 0,
                    pointHitRadius: 0,
                    pointHoverRadius: 0,
                    borderDash: [5, 5]
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                contatos: {
                    type: 'linear',
                    position: 'left',
                    grid: { display: false }
                },
                cadastros: {
                    type: 'linear',
                    position: 'right',
                    grid: { display: false }
                }
            },
            plugins: {
                legend: { position: 'top' },
                tooltip: {
                    mode: 'index',
                    intersect: false,
                    callbacks: {
                        label: function (context) {
                            let label = context.dataset.label || '';
                            if (label) label += ': ';
                            if (context.parsed.y !== null) label += context.parsed.y.toFixed(0);
                            return label;
                        }
                    }
                }
            }
        }
    });
}

function getDiasRestantesMes() {
    const hoje = new Date();
    const ultimoDiaMes = new Date(hoje.getFullYear(), hoje.getMonth() + 1, 0);
    return ultimoDiaMes.getDate() - hoje.getDate();
}

// --- TABELA DE DETALHES (Mantida) ---
function updateTable(data) {
    const tableHead = document.getElementById('scorecard-table-head');
    const tableBody = document.getElementById('scorecard-table-body');

    if (data.length === 0) {
        tableHead.innerHTML = '';
        tableBody.innerHTML = '<tr><td colspan="5" class="text-center">Nenhum dado para exibir.</td></tr>';
        return;
    }

    const headers = Object.keys(data[0]);
    tableHead.innerHTML = `<tr>${headers.map(h => `<th>${h.replace(/_/g, ' ').toUpperCase()}</th>`).join('')}</tr>`;

    tableBody.innerHTML = data.map(row => `
        <tr>
            ${headers.map(header => `<td>${row[header] ?? 'N/A'}</td>`).join('')}
        </tr>
    `).join('');
}

function handleTableSearch() {
    const filter = document.getElementById('tableSearch').value.toLowerCase();
    const rows = document.getElementById('scorecard-table-body').getElementsByTagName('tr');

    for (let i = 0; i < rows.length; i++) {
        rows[i].style.display = rows[i].textContent.toLowerCase().includes(filter) ? '' : 'none';
    }
}

// --- FUNÇÕES AUXILIARES ---
function adjustColor(color, amount) {
    return '#' + color.replace(/^#/, '').replace(/../g, color => ('0'+Math.min(255, Math.max(0, parseInt(color, 16) + amount)).toString(16)).substr(-2));
}