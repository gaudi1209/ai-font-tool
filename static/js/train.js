/* AI模型训练 - 前端逻辑 */

let pollTimer = null;
let lastLogOffset = 0;

// 手动输入路径回车确认
document.addEventListener('DOMContentLoaded', () => {
    const browseInput = document.getElementById('browseInput');
    if (browseInput) {
        browseInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && _browseTarget) {
                document.getElementById(_browseTarget).value = browseInput.value;
                document.getElementById('browseModal').style.display = 'none';
            }
        });
    }

    apiRequest('/api/train/status').then(data => {
        updateStatus(data);
        if (data.status === 'training' || data.status === 'preparing') startPolling();
        // 回填上次训练参数
        if (data.last_params && Object.keys(data.last_params).length > 0) {
            fillLastParams(data.last_params);
        }
    }).catch(() => {});
});

// 切换手动输入框显示
function toggleCharCountInput() {
    const mode = document.getElementById('charCountMode').value;
    document.getElementById('charCountCustom').style.display = mode === 'custom' ? '' : 'none';
}

// 获取取字数量参数（null 表示全部）
function getCharCountParam() {
    const mode = document.getElementById('charCountMode').value;
    if (mode === 'all') return null;
    if (mode === 'custom') return parseInt(document.getElementById('charCountCustom').value) || 1000;
    return parseInt(mode);
}

// 准备训练数据
async function prepareData() {
    const params = {
        ref_font: document.getElementById('refFont').value,
        source_font: document.getElementById('sourceFont').value,
        output_dir: document.getElementById('outputDir').value,
        char_count: getCharCountParam(),
    };

    if (!params.ref_font || !params.source_font || !params.output_dir) {
        showToast('请填写参考字体、源字体和输出目录', 'error');
        return;
    }

    showLoading('准备训练数据...');
    try {
        const data = await apiRequest('/api/train/prepare', {
            method: 'POST',
            body: JSON.stringify(params)
        });
        hideLoading();

        if (data.success) {
            showToast(`数据准备完成: ${data.char_count} 个字符`, 'success');
            // 更新输出目录为新创建的时间戳目录
            if (data.data_dir) {
                document.getElementById('outputDir').value = data.data_dir;
            }
            document.getElementById('statusText').textContent = '数据已准备';
            appendLog(document.getElementById('logTerminal'),
                `[${new Date().toLocaleTimeString()}] 数据准备完成: ${data.char_count} 字符 → ${data.data_dir}`);
        } else {
            showToast('数据准备失败: ' + data.error, 'error');
        }
    } catch (e) { hideLoading(); }
}

// 打开准备数据目录
function openPrepareDir() {
    const outputDir = document.getElementById('outputDir').value;
    if (!outputDir) {
        showToast('请先填写输出目录', 'error');
        return;
    }
    fetch('/api/open_dir', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: outputDir })
    })
    .then(r => r.json())
    .then(data => {
        if (!data.success) showToast(data.error || '打开失败', 'error');
    })
    .catch(() => showToast('打开失败', 'error'));
}

// 开始训练
async function startTraining() {
    const params = {
        base_checkpoint: document.getElementById('baseCheckpoint').value,
        source_font: document.getElementById('sourceFont').value,
        ref_font: document.getElementById('refFont').value,
        output_dir: document.getElementById('outputDir').value,
        epochs: parseInt(document.getElementById('epochs').value),
        batch_size: parseInt(document.getElementById('batchSize').value),
        lora_r: parseInt(document.getElementById('loraR').value),
        lora_alpha: parseInt(document.getElementById('loraAlpha').value),
        cfg: parseFloat(document.getElementById('cfg').value),
        num_fonts: parseInt(document.getElementById('numFonts').value),
        num_chars: parseInt(document.getElementById('numChars').value),
        max_chars_per_font: parseInt(document.getElementById('maxCharsPerFont').value),
        num_workers: parseInt(document.getElementById('numWorkers').value),
    };

    if (!params.base_checkpoint || !params.output_dir) {
        showToast('请填写基础模型路径和输出目录', 'error');
        return;
    }

    try {
        const data = await apiRequest('/api/train/start', {
            method: 'POST',
            body: JSON.stringify(params)
        });
        if (data.success) {
            showToast('训练已启动', 'success');
            document.getElementById('logTerminal').innerHTML = '';
            lastLogOffset = 0;
            startPolling();
        } else {
            showToast(data.error || '启动失败', 'error');
        }
    } catch (e) {}
}

async function stopTraining() {
    try {
        const data = await apiRequest('/api/train/stop', { method: 'POST' });
        if (data.success) { showToast('训练已停止', 'success'); stopPolling(); updateStatus({ status: 'idle' }); }
    } catch (e) {}
}

function startPolling() {
    stopPolling();
    pollTimer = setInterval(async () => {
        try {
            const data = await apiRequest('/api/train/status');
            updateStatus(data);
            const logs = await apiRequest(`/api/train/logs?offset=${lastLogOffset}&limit=50`);
            if (logs.lines && logs.lines.length > 0) {
                const terminal = document.getElementById('logTerminal');
                logs.lines.forEach(line => appendLog(terminal, line));
                lastLogOffset += logs.lines.length;
            }
            if (data.status === 'completed' || data.status === 'error' || data.status === 'idle') stopPolling();
        } catch (e) {}
    }, 2000);
}

function stopPolling() { if (pollTimer) { clearInterval(pollTimer); pollTimer = null; } }

function updateStatus(data) {
    const dot = document.getElementById('statusDot');
    const text = document.getElementById('statusText');
    dot.className = 'status-dot';
    switch (data.status) {
        case 'training': dot.classList.add('running'); text.textContent = '训练中'; break;
        case 'preparing': dot.classList.add('running'); text.textContent = '准备数据中'; break;
        case 'completed':
            dot.classList.add('completed'); text.textContent = '训练完成';
            // 训练完成时自动填入 checkpoint 路径
            if (data.last_params && data.last_params.output_dir) {
                autoFillCheckpoint(data.last_params.output_dir);
            }
            break;
        case 'error': dot.classList.add('error'); text.textContent = '错误: ' + (data.error || ''); break;
        default: text.textContent = '就绪';
    }
    if (data.total_epochs > 0) {
        document.getElementById('epochDisplay').textContent = `${data.epoch}/${data.total_epochs}`;
        document.getElementById('progressBar').style.width = (data.epoch / data.total_epochs * 100).toFixed(1) + '%';
    }
    if (data.loss) document.getElementById('lossDisplay').textContent = data.loss.toFixed(4);
    if (data.lr) document.getElementById('lrDisplay').textContent = data.lr.toExponential(2);
    if (data.elapsed > 0) document.getElementById('timeDisplay').textContent = formatDuration(data.elapsed);
}

// ===== 继续训练 =====
async function continueTraining() {
    const checkpointPath = document.getElementById('lastCheckpoint').value;
    const addEpochs = parseInt(document.getElementById('continueEpochs').value) || 50;
    if (!checkpointPath) { showToast('请先选择 Checkpoint 文件', 'error'); return; }

    // 从 checkpoint 路径推导 output_dir（checkpoint 所在目录）
    const outputDir = checkpointPath.replace(/[/\\][^/\\]+$/, '');

    try {
        const status = await apiRequest('/api/train/status');
        if (status.status === 'training' || status.status === 'preparing') {
            showToast('训练正在进行中，请先停止', 'error'); return;
        }

        // 后端会自动读取 checkpoint epoch 并调整 total_epochs
        const lastParams = status.last_params || {};
        const params = {
            base_checkpoint: document.getElementById('baseCheckpoint').value,
            source_font: document.getElementById('sourceFont').value || lastParams.source_font,
            ref_font: document.getElementById('refFont').value || lastParams.ref_font,
            output_dir: outputDir,
            epochs: addEpochs,  // 后端会自动加上 checkpoint epoch
            add_epochs: addEpochs,
            batch_size: parseInt(document.getElementById('batchSize').value) || lastParams.batch_size,
            lora_r: parseInt(document.getElementById('loraR').value) || lastParams.lora_r,
            lora_alpha: parseInt(document.getElementById('loraAlpha').value) || lastParams.lora_alpha,
            cfg: parseFloat(document.getElementById('cfg').value) || lastParams.cfg,
            num_fonts: parseInt(document.getElementById('numFonts').value) || lastParams.num_fonts,
            num_chars: parseInt(document.getElementById('numChars').value) || lastParams.num_chars,
            max_chars_per_font: parseInt(document.getElementById('maxCharsPerFont').value) || lastParams.max_chars_per_font,
            num_workers: parseInt(document.getElementById('numWorkers').value),
        };

        const data = await apiRequest('/api/train/start', {
            method: 'POST', body: JSON.stringify(params)
        });
        if (data.success) {
            showToast(`继续训练: 追加 ${addEpochs} 轮`, 'success');
            document.getElementById('logTerminal').innerHTML = '';
            lastLogOffset = 0;
            startPolling();
        } else {
            showToast(data.error || '启动失败', 'error');
        }
    } catch (e) {}
}

// ===== 测试生成 =====
async function testGenerate() {
    const checkpointPath = document.getElementById('lastCheckpoint').value;
    if (!checkpointPath) { showToast('请先选择 Checkpoint 文件', 'error'); return; }

    // 从 checkpoint 路径推导 output_dir
    const outputDir = checkpointPath.replace(/[/\\][^/\\]+$/, '');

    const params = {
        output_dir: outputDir,
        ref_font: document.getElementById('refFont').value,
        source_font: document.getElementById('sourceFont').value,
    };
    if (!params.ref_font || !params.source_font) {
        showToast('请填写学习字库和源字体路径', 'error'); return;
    }

    showLoading('正在生成测试字符（加载模型中，约需30秒）...');
    try {
        const data = await apiRequest('/api/train/test_generate', {
            method: 'POST', body: JSON.stringify(params)
        });
        hideLoading();

        if (data.success) {
            renderTestCards(data);
            showToast(`生成完成: ${data.existing_count} 已有 + ${data.new_count} 新字`, 'success');
        } else {
            showToast('生成失败: ' + data.error, 'error');
        }
    } catch (e) {
        hideLoading();
        showToast('生成失败: ' + (e.message || e), 'error');
    }
}

function renderTestCards(data) {
    const area = document.getElementById('testResultArea');
    const grid = document.getElementById('testCardGrid');
    const title = document.getElementById('testResultTitle');

    area.style.display = 'flex';
    title.textContent = `测试生成: ${data.existing_count} 已有 + ${data.new_count} 新字`;
    grid.innerHTML = '';

    const existing = data.results.filter(r => r.type === 'existing');
    const newChars = data.results.filter(r => r.type === 'new');

    if (existing.length > 0) {
        const label = document.createElement('div');
        label.className = 'test-section-label';
        label.textContent = `已有字符 (${existing.length})`;
        grid.appendChild(label);
        existing.forEach(r => grid.appendChild(createTestCard(r)));
    }
    if (newChars.length > 0) {
        const label = document.createElement('div');
        label.className = 'test-section-label';
        label.textContent = `全新字符 (${newChars.length})`;
        grid.appendChild(label);
        newChars.forEach(r => grid.appendChild(createTestCard(r)));
    }
}

function createTestCard(item) {
    const card = document.createElement('div');
    card.className = 'test-card';

    const imgUrl = item.compare_image
        ? `/api/image?path=${encodeURIComponent(item.compare_image)}`
        : item.gen_image
            ? `/api/image?path=${encodeURIComponent(item.gen_image)}`
            : '';

    card.innerHTML = `
        <div class="card-img">
            ${imgUrl ? `<img src="${imgUrl}" loading="lazy">` : '<div style="color:#666;display:flex;align-items:center;justify-content:center;height:100%;font-size:12px">无图片</div>'}
        </div>
        <div class="card-info">
            <span class="card-text">${item.char}</span>
            <span class="card-status ${item.type}">${item.type === 'existing' ? '已有' : '新字'}</span>
        </div>
    `;
    return card;
}

// ===== 回填上次训练参数 =====
function fillLastParams(params) {
    const fields = {
        'outputDir': params.output_dir,
        'refFont': params.ref_font,
        'sourceFont': params.source_font,
    };
    for (const [id, val] of Object.entries(fields)) {
        if (val) {
            const el = document.getElementById(id);
            if (el && !el.value) el.value = val;
        }
    }
    // 自动填充 checkpoint 路径
    if (params.output_dir) {
        const ckptPath = params.output_dir.replace(/[/\\]$/, '') + '/checkpoint-last.pth';
        const el = document.getElementById('lastCheckpoint');
        if (el && !el.value) el.value = ckptPath;
    }
}

// 训练完成后自动填入 checkpoint 路径
function autoFillCheckpoint(outputDir) {
    if (!outputDir) return;
    const ckptPath = outputDir.replace(/[/\\]$/, '') + '/checkpoint-last.pth';
    document.getElementById('lastCheckpoint').value = ckptPath;
    savePathHistory('lastCheckpoint', ckptPath);
}
