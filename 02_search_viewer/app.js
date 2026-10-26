/**
 * ArchiveViewer Core Engine - Modern Client-Side Architecture
 */

// Global App State
const state = {
    allRecords: [],
    filteredRecords: [],
    currentPage: 1,
    pageSize: 24,
    searchKeyword: '',
    selectedGenres: new Set(),
    selectedProviders: new Set(),
    selectedAttributes: new Set(),
    sortBy: 'title-asc',
    chartInstance: null
};

// DOM Elements Reference
const elements = {
    keywordInput: document.getElementById('input-keyword-search'),
    genreContainer: document.getElementById('container-genre-filters'),
    providerContainer: document.getElementById('container-provider-filters'),
    attributeContainer: document.getElementById('container-attribute-filters'),
    cardsGrid: document.getElementById('cards-grid'),
    paginationContainer: document.getElementById('container-pagination'),
    sortSelect: document.getElementById('select-sort'),
    btnReset: document.getElementById('btn-reset-filters'),
    btnThemeToggle: document.getElementById('btn-theme-toggle'),
    
    lblMatchCount: document.getElementById('lbl-match-count'),
    lblTotalCount: document.getElementById('lbl-total-count'),
    statMatchCount: document.getElementById('stat-match-count'),
    statTotalCount: document.getElementById('stat-total-count'),
    
    modal: document.getElementById('modal-detail'),
    modalClose: document.getElementById('btn-modal-close'),
    modalTag: document.getElementById('modal-item-tag'),
    modalTitle: document.getElementById('modal-item-title'),
    modalDesc: document.getElementById('modal-item-description'),
    modalImage: document.getElementById('modal-item-image'),
    modalImgPlaceholder: document.getElementById('modal-image-placeholder'),
    modalExternalLink: document.getElementById('link-external-source'),
    modalProvenance: document.getElementById('modal-item-provenance'),

    // Tabs & Views
    tabBtnSearch: document.getElementById('tab-btn-search'),
    tabBtnProvenance: document.getElementById('tab-btn-provenance'),
    viewSearch: document.getElementById('view-search'),
    viewProvenance: document.getElementById('view-provenance'),

    // Provenance View Elements
    provKeywords: document.getElementById('prov-keywords'),
    provTargetNdc: document.getElementById('prov-target-ndc'),
    provExcludeNdc: document.getElementById('prov-exclude-ndc'),
    provRegex: document.getElementById('prov-regex'),
    flowStatTotal: document.getElementById('flow-stat-total'),
    flowStatTypeDisc: document.getElementById('flow-stat-type-disc'),
    flowStatRuleDisc: document.getElementById('flow-stat-rule-disc'),
    flowStatLlmDisc: document.getElementById('flow-stat-llm-disc'),
    flowStatFinal: document.getElementById('flow-stat-final'),
    containerTopDropReasons: document.getElementById('container-top-drop-reasons')
};

// Initialize Application
document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    setupTabs();
    loadData();
    setupEventListeners();
});

// Theme Switcher Logic
function initTheme() {
    const savedTheme = localStorage.getItem('archive_theme') || 'dark';
    document.documentElement.setAttribute('data-theme', savedTheme);
    elements.btnThemeToggle.textContent = savedTheme === 'dark' ? '☀️' : '🌙';

    elements.btnThemeToggle.addEventListener('click', () => {
        const current = document.documentElement.getAttribute('data-theme');
        const next = current === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', next);
        localStorage.setItem('archive_theme', next);
        elements.btnThemeToggle.textContent = next === 'dark' ? '☀️' : '🌙';
        if (state.chartInstance) {
            updateChartTheme();
        }
    });
}

// Load JSON Data
async function loadData() {
    try {
        const response = await fetch('scores_data.json');
        if (!response.ok) {
            throw new Error(`Data load error: ${response.status}`);
        }
        state.allRecords = await response.json();
        state.filteredRecords = [...state.allRecords];
        
        elements.lblTotalCount.textContent = state.allRecords.length;
        elements.statTotalCount.textContent = state.allRecords.length.toLocaleString();
        
        buildFilterOptions();
        initChart();
        applyFilters();
    } catch (err) {
        console.warn('scores_data.json の直接読み込みに失敗しました。フォールバックテストデータを生成します。', err);
        generateFallbackData();
    }
}

// Fallback Demo Data Generation (If scores_data.json is missing initially)
function generateFallbackData() {
    const sampleGenres = ['雅楽', '能楽/謡曲', '三味線音楽', '琵琶楽', '尺八楽', '声明/仏教音楽'];
    const sampleProviders = ['国立国会図書館', '東京藝術大学', '国文学研究資料館', '早稲田大学'];
    
    state.allRecords = Array.from({ length: 60 }, (_, i) => ({
        id: `https://jpsearch.go.jp/item/sample-${i + 1}`,
        title: `古典楽譜・資料サンプル ${i + 1} (${sampleGenres[i % sampleGenres.length]})`,
        description: `これはサンプル表示用の楽譜資料メタデータです。音符、記譜法、伝来に関する詳細な記述が含まれています。`,
        genre: sampleGenres[i % sampleGenres.length],
        provider: sampleProviders[i % sampleProviders.length],
        instruments: ['箏', '三味線', '尺八'][i % 3] ? [['箏', '三味線', '尺八'][i % 3]] : [],
        url: `https://jpsearch.go.jp/item/sample-${i + 1}`
    }));
    
    state.filteredRecords = [...state.allRecords];
    elements.lblTotalCount.textContent = state.allRecords.length;
    elements.statTotalCount.textContent = state.allRecords.length.toLocaleString();
    
    buildFilterOptions();
    initChart();
    applyFilters();
}

// Build Filter Options (Genres, Providers, Attributes)
function buildFilterOptions() {
    const genres = new Set();
    const providers = new Set();
    const attributes = new Set();

    state.allRecords.forEach(r => {
        if (r.genre) genres.add(r.genre);
        if (r.provider) providers.add(r.provider);
        if (Array.isArray(r.instruments)) {
            r.instruments.forEach(inst => attributes.add(inst));
        }
    });

    renderCheckboxGroup(elements.genreContainer, genres, state.selectedGenres);
    renderCheckboxGroup(elements.providerContainer, providers, state.selectedProviders);
    renderCheckboxGroup(elements.attributeContainer, attributes, state.selectedAttributes);
}

function renderCheckboxGroup(container, itemSet, selectedSet) {
    container.innerHTML = '';
    const sorted = Array.from(itemSet).sort();
    
    sorted.forEach(item => {
        const label = document.createElement('label');
        label.className = 'checkbox-item';
        
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.value = item;
        checkbox.checked = selectedSet.has(item);
        
        checkbox.addEventListener('change', (e) => {
            if (e.target.checked) {
                selectedSet.add(item);
            } else {
                selectedSet.delete(item);
            }
            state.currentPage = 1;
            applyFilters();
        });
        
        label.appendChild(checkbox);
        label.appendChild(document.createTextNode(item));
        container.appendChild(label);
    });
}

// Filter Engine & Event Listeners
function setupEventListeners() {
    // Keyword Search Input (Debounced)
    let debounceTimer;
    elements.keywordInput.addEventListener('input', (e) => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
            state.searchKeyword = e.target.value.trim().toLowerCase();
            state.currentPage = 1;
            applyFilters();
        }, 200);
    });

    // Sort Select
    elements.sortSelect.addEventListener('change', (e) => {
        state.sortBy = e.target.value;
        applyFilters();
    });

    // Reset Button
    elements.btnReset.addEventListener('click', () => {
        state.searchKeyword = '';
        state.selectedGenres.clear();
        state.selectedProviders.clear();
        state.selectedAttributes.clear();
        elements.keywordInput.value = '';
        state.currentPage = 1;
        
        buildFilterOptions();
        applyFilters();
    });

    // Modal Close
    elements.modalClose.addEventListener('click', closeModal);
    elements.modal.addEventListener('click', (e) => {
        if (e.target === elements.modal) closeModal();
    });
}

// Apply Active Filters & Render
function applyFilters() {
    state.filteredRecords = state.allRecords.filter(item => {
        // Keyword Filter
        if (state.searchKeyword) {
            const title = (item.title || '').toLowerCase();
            const desc = (item.description || '').toLowerCase();
            if (!title.includes(state.searchKeyword) && !desc.includes(state.searchKeyword)) {
                return false;
            }
        }
        
        // Genre Filter
        if (state.selectedGenres.size > 0 && !state.selectedGenres.has(item.genre)) {
            return false;
        }

        // Provider Filter
        if (state.selectedProviders.size > 0 && !state.selectedProviders.has(item.provider)) {
            return false;
        }

        // Attribute Filter
        if (state.selectedAttributes.size > 0) {
            const insts = item.instruments || [];
            const hasAttribute = insts.some(inst => state.selectedAttributes.has(inst));
            if (!hasAttribute) return false;
        }

        return true;
    });

    // Sorting
    state.filteredRecords.sort((a, b) => {
        const titleA = a.title || '';
        const titleB = b.title || '';
        if (state.sortBy === 'title-asc') {
            return titleA.localeCompare(titleB, 'ja');
        } else {
            return titleB.localeCompare(titleA, 'ja');
        }
    });

    // Update Counts
    elements.lblMatchCount.textContent = state.filteredRecords.length;
    elements.statMatchCount.textContent = state.filteredRecords.length.toLocaleString();

    renderCards();
    renderPagination();
    updateChartData();
}

// Render Card Grid
function renderCards() {
    elements.cardsGrid.innerHTML = '';

    if (state.filteredRecords.length === 0) {
        if (state.allRecords.length === 0) {
            elements.cardsGrid.innerHTML = `
                <div style="grid-column: 1 / -1; text-align: center; padding: 4rem 1rem; color: var(--text-muted); background: var(--bg-card); border-radius: var(--radius-lg); border: 1px dashed var(--border);">
                    <div style="font-size: 2.5rem; margin-bottom: 1rem;">📦</div>
                    <h3 style="color: var(--text-main); font-size: 1.25rem;">公開用データセットが未エクスポートです</h3>
                    <p style="margin-top: 0.5rem; max-width: 500px; margin-left: auto; margin-right: auto; line-height: 1.6;">
                        現在、表示可能な精緻化済み楽譜メタデータが存在しません。<br>
                        <code>01_cleansing_studio</code> を起動し、Step 5 で <strong>「統合検索ポータル用データ出力」</strong> を実行するか、<br>
                        <code>python3 02_search_viewer/build_viewer_data.py</code> を実行してデータを生成してください。
                    </p>
                </div>
            `;
        } else {
            elements.cardsGrid.innerHTML = `
                <div style="grid-column: 1 / -1; text-align: center; padding: 4rem 1rem; color: var(--text-muted);">
                    <h3>該当する資料が見つかりませんでした</h3>
                    <p style="margin-top: 0.5rem;">検索キーワードやフィルタ条件を緩和してみてください。</p>
                </div>
            `;
        }
        return;
    }

    const start = (state.currentPage - 1) * state.pageSize;
    const end = start + state.pageSize;
    const pageItems = state.filteredRecords.slice(start, end);

    pageItems.forEach(item => {
        const card = document.createElement('div');
        card.className = 'item-card';
        
        let provBadgeHtml = '';
        if (item.provenance) {
            const stageLabel = getStageLabel(item.provenance.stage);
            provBadgeHtml = `
                <div class="provenance-badge" title="${escapeHtml(item.provenance.reason || '')}">
                    <span>🏷️ 採択: ${escapeHtml(stageLabel)}</span>
                </div>
            `;
        }

        card.innerHTML = `
            <div>
                <span class="card-tag">${escapeHtml(item.genre || '未分類')}</span>
                <h3 class="card-title">${escapeHtml(item.title || '無題')}</h3>
                <p class="card-description">${escapeHtml(item.description || '説明文なし')}</p>
                ${provBadgeHtml}
            </div>
            <div class="card-meta">
                <span>📍 ${escapeHtml(item.provider || '提供元情報なし')}</span>
                <span>詳細 ➔</span>
            </div>
        `;

        card.addEventListener('click', () => openModal(item));
        elements.cardsGrid.appendChild(card);
    });
}

// Render Pagination
function renderPagination() {
    elements.paginationContainer.innerHTML = '';
    const totalPages = Math.ceil(state.filteredRecords.length / state.pageSize);
    
    if (totalPages <= 1) return;

    for (let p = 1; p <= totalPages; p++) {
        if (totalPages > 7 && Math.abs(p - state.currentPage) > 2 && p !== 1 && p !== totalPages) {
            if (p === 2 || p === totalPages - 1) {
                const dots = document.createElement('span');
                dots.textContent = '...';
                dots.style.color = 'var(--text-muted)';
                dots.style.alignSelf = 'center';
                elements.paginationContainer.appendChild(dots);
            }
            continue;
        }

        const btn = document.createElement('button');
        btn.className = `page-btn ${p === state.currentPage ? 'active' : ''}`;
        btn.textContent = p;
        btn.addEventListener('click', () => {
            state.currentPage = p;
            renderCards();
            renderPagination();
            window.scrollTo({ top: 300, behavior: 'smooth' });
        });
        elements.paginationContainer.appendChild(btn);
    }
}

// Chart.js Dashboard Engine
function initChart() {
    const ctx = document.getElementById('categoryChart').getContext('2d');
    
    state.chartInstance = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: [],
            datasets: [{
                data: [],
                backgroundColor: [
                    '#6366f1', '#8b5cf6', '#ec4899', '#3b82f6', 
                    '#10b981', '#f59e0b', '#64748b'
                ],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'right',
                    labels: {
                        color: getComputedStyle(document.documentElement).getPropertyValue('--text-primary').trim(),
                        font: { family: 'Outfit', size: 11 }
                    }
                }
            },
            cutout: '70%'
        }
    });
}

function updateChartData() {
    if (!state.chartInstance) return;

    const genreCounts = {};
    state.filteredRecords.forEach(r => {
        const g = r.genre || 'その他/未分類';
        genreCounts[g] = (genreCounts[g] || 0) + 1;
    });

    const sorted = Object.entries(genreCounts).sort((a, b) => b[1] - a[1]);
    const top = sorted.slice(0, 6);
    const othersCount = sorted.slice(6).reduce((acc, curr) => acc + curr[1], 0);

    const labels = top.map(item => item[0]);
    const data = top.map(item => item[1]);

    if (othersCount > 0) {
        labels.push('その他');
        data.push(othersCount);
    }

    state.chartInstance.data.labels = labels;
    state.chartInstance.data.datasets[0].data = data;
    state.chartInstance.update();
}

function updateChartTheme() {
    const textColor = getComputedStyle(document.documentElement).getPropertyValue('--text-primary').trim();
    state.chartInstance.options.plugins.legend.labels.color = textColor;
    state.chartInstance.update();
}

// Modal Control
function openModal(item) {
    elements.modalTag.textContent = item.genre || '未分類';
    elements.modalTitle.textContent = item.title || '無題';
    elements.modalDesc.textContent = item.description || '詳細な説明文はありません。';
    
    if (item.image) {
        elements.modalImage.src = item.image;
        elements.modalImage.classList.remove('hide');
        elements.modalImgPlaceholder.classList.add('hide');
    } else {
        elements.modalImage.classList.add('hide');
        elements.modalImgPlaceholder.classList.remove('hide');
    }

    // Provenance Details in Modal
    if (item.provenance) {
        const stageLabel = getStageLabel(item.provenance.stage);
        elements.modalProvenance.innerHTML = `
            <div class="modal-provenance-box">
                <div class="modal-prov-title">✅ 採択根拠（Provenance）: ${escapeHtml(stageLabel)}</div>
                <div class="modal-prov-reason">${escapeHtml(item.provenance.reason || 'クレンジング採択基準を満たしています')}</div>
                <div class="modal-prov-meta">判定ステージ: ${escapeHtml(item.provenance.stage || 'RULE')} ｜ 確信度: ${escapeHtml(item.provenance.confidence || 'HIGH')}</div>
            </div>
        `;
        elements.modalProvenance.style.display = 'block';
    } else {
        elements.modalProvenance.style.display = 'none';
    }

    elements.modalExternalLink.href = item.url || item.id || '#';
    elements.modal.classList.add('active');
}

function closeModal() {
    elements.modal.classList.remove('active');
}

// Stage Label Formatter
function getStageLabel(stage) {
    switch (stage) {
        case 'RULE': return 'ルール判定 (About/N-gram)';
        case 'TYPE': return '種別判定 (Type)';
        case 'LLM': return 'LLMセマンティック推論';
        case 'REVIEW': return '専門家査読 (Human Review)';
        default: return stage || 'クレンジング通過';
    }
}

// Navigation Tabs Switcher
function setupTabs() {
    if (!elements.tabBtnSearch || !elements.tabBtnProvenance) return;

    elements.tabBtnSearch.addEventListener('click', () => {
        elements.tabBtnSearch.classList.add('active');
        elements.tabBtnProvenance.classList.remove('active');
        elements.viewSearch.classList.remove('hide');
        elements.viewProvenance.classList.add('hide');
    });

    elements.tabBtnProvenance.addEventListener('click', () => {
        elements.tabBtnProvenance.classList.add('active');
        elements.tabBtnSearch.classList.remove('active');
        elements.viewProvenance.classList.remove('hide');
        elements.viewSearch.classList.add('hide');
        loadProvenanceData();
    });
}

// Provenance Data Loader (PRISMA Flow & Manifest)
let isProvenanceLoaded = false;
async function loadProvenanceData() {
    if (isProvenanceLoaded) return;

    // 1. Try to load Acquisition Manifest
    try {
        const manifestRes = await fetch('../data/acquisition_manifest.json').catch(() => fetch('data/acquisition_manifest.json'));
        if (manifestRes && manifestRes.ok) {
            const manifest = await manifestRes.json();
            const initCond = manifest.initial_condition || {};
            
            if (initCond.keywords && initCond.keywords.length > 0) {
                elements.provKeywords.textContent = initCond.keywords.join(', ');
            }
            if (initCond.target_ndc && initCond.target_ndc.length > 0) {
                elements.provTargetNdc.textContent = initCond.target_ndc.join(', ');
            }
            if (initCond.exclude_ndc && initCond.exclude_ndc.length > 0) {
                elements.provExcludeNdc.textContent = initCond.exclude_ndc.join(', ');
            }
            if (initCond.regex_patterns && initCond.regex_patterns.length > 0) {
                elements.provRegex.textContent = initCond.regex_patterns.join(' | ');
            }
        }
    } catch (e) {
        console.warn('Acquisition manifest loading error:', e);
    }

    // 2. Try to load PRISMA Flow Summary
    try {
        const prismaRes = await fetch('../data/prisma_flow_summary.json').catch(() => fetch('data/prisma_flow_summary.json'));
        if (prismaRes && prismaRes.ok) {
            const flow = await prismaRes.json();
            const counts = flow.counts || flow || {};
            
            const total = counts.initial_pool ?? counts.total_records ?? 0;
            const typeDisc = counts.type_excluded ?? counts.type_discarded ?? 0;
            const ruleDisc = counts.rule_excluded ?? counts.rule_ng ?? 0;
            const llmDisc = counts.llm_excluded ?? counts.llm_discarded ?? 0;
            const finalAd = counts.final_adopted ?? 0;

            if (elements.flowStatTotal) elements.flowStatTotal.textContent = `${total.toLocaleString()} 件`;
            if (elements.flowStatTypeDisc) elements.flowStatTypeDisc.textContent = `Type除外: ${typeDisc.toLocaleString()} 件`;
            if (elements.flowStatRuleDisc) elements.flowStatRuleDisc.textContent = `ルール除外: ${ruleDisc.toLocaleString()} 件`;
            if (elements.flowStatLlmDisc) elements.flowStatLlmDisc.textContent = `LLM/保留除外: ${llmDisc.toLocaleString()} 件`;
            if (elements.flowStatFinal) elements.flowStatFinal.textContent = `${finalAd.toLocaleString()} 件`;

            // Render Exclusion Reasons Ranking
            const topReasons = flow.top_drop_reasons || [];
            if (elements.containerTopDropReasons) {
                elements.containerTopDropReasons.innerHTML = '';
                if (topReasons.length === 0) {
                    elements.containerTopDropReasons.innerHTML = '<div style="color: var(--text-muted); font-size: 0.9rem;">除外理由の集計データはありません。</div>';
                } else {
                    topReasons.forEach(r => {
                        let reasonName = '';
                        let reasonCnt = 0;
                        let reasonRatio = '';

                        if (Array.isArray(r)) {
                            reasonName = r[0] || '除外理由';
                            reasonCnt = r[1] || 0;
                            const totalDisc = counts.final_discarded ?? (total - finalAd);
                            reasonRatio = totalDisc > 0 ? `${((reasonCnt / totalDisc) * 100).toFixed(1)}%` : '0%';
                        } else if (typeof r === 'object' && r !== null) {
                            reasonName = r.reason || '除外理由';
                            reasonCnt = r.count || 0;
                            reasonRatio = r.ratio || '0%';
                        }

                        const card = document.createElement('div');
                        card.className = 'reason-rank-card';
                        card.innerHTML = `
                            <div class="reason-rank-name" title="${escapeHtml(reasonName)}">${escapeHtml(reasonName)}</div>
                            <span class="reason-rank-badge">${reasonCnt.toLocaleString()} 件 (${escapeHtml(reasonRatio)})</span>
                        `;
                        elements.containerTopDropReasons.appendChild(card);
                    });
                }
            }
            isProvenanceLoaded = true;
        } else {
            // Fallback rendering from current records
            applyFallbackFlowStats();
        }
    } catch (e) {
        console.warn('PRISMA flow summary loading error:', e);
        applyFallbackFlowStats();
    }
}

function applyFallbackFlowStats() {
    const totalCount = state.allRecords.length;
    if (elements.flowStatTotal) elements.flowStatTotal.textContent = `${totalCount.toLocaleString()} 件+`;
    if (elements.flowStatFinal) elements.flowStatFinal.textContent = `${totalCount.toLocaleString()} 件`;
    if (elements.flowStatTypeDisc) elements.flowStatTypeDisc.textContent = `Type除外: 算出中`;
    if (elements.flowStatRuleDisc) elements.flowStatRuleDisc.textContent = `ルール除外: 算出中`;
    if (elements.flowStatLlmDisc) elements.flowStatLlmDisc.textContent = `LLM除外: 算出中`;
    
    if (elements.containerTopDropReasons && elements.containerTopDropReasons.children.length === 0) {
        elements.containerTopDropReasons.innerHTML = `
            <div class="reason-rank-card">
                <div class="reason-rank-name">非音楽資料（家譜・系図等）</div>
                <span class="reason-rank-badge">NDC除外</span>
            </div>
            <div class="reason-rank-card">
                <div class="reason-rank-name">美術資料（画譜等）</div>
                <span class="reason-rank-badge">NDC除外</span>
            </div>
            <div class="reason-rank-card">
                <div class="reason-rank-name">自然科学・技術系論文資料</div>
                <span class="reason-rank-badge">NDC除外</span>
            </div>
            <div class="reason-rank-card">
                <div class="reason-rank-name">画像・絵葉書（非書籍資料）</div>
                <span class="reason-rank-badge">Type除外</span>
            </div>
        `;
    }
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}
