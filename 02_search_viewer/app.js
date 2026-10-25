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
    modalExternalLink: document.getElementById('link-external-source')
};

// Initialize Application
document.addEventListener('DOMContentLoaded', () => {
    initTheme();
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
        elements.cardsGrid.innerHTML = `
            <div style="grid-column: 1 / -1; text-align: center; padding: 4rem 1rem; color: var(--text-muted);">
                <h3>該当する資料が見つかりませんでした</h3>
                <p style="margin-top: 0.5rem;">検索キーワードやフィルタ条件を緩和してみてください。</p>
            </div>
        `;
        return;
    }

    const start = (state.currentPage - 1) * state.pageSize;
    const end = start + state.pageSize;
    const pageItems = state.filteredRecords.slice(start, end);

    pageItems.forEach(item => {
        const card = document.createElement('div');
        card.className = 'item-card';
        
        card.innerHTML = `
            <div>
                <span class="card-tag">${escapeHtml(item.genre || '未分類')}</span>
                <h3 class="card-title">${escapeHtml(item.title || '無題')}</h3>
                <p class="card-description">${escapeHtml(item.description || '説明文なし')}</p>
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

    elements.modalExternalLink.href = item.url || item.id || '#';
    elements.modal.classList.add('active');
}

function closeModal() {
    elements.modal.classList.remove('active');
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
