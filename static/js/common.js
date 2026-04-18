/* AI字体生产工具 - 公共函数 */

// 显示提示消息
function showToast(message, type = 'info', duration = 3000) {
    const toast = document.createElement('div');
    toast.className = 'toast';
    if (type === 'error') toast.style.backgroundColor = '#b08888';
    else if (type === 'success') toast.style.backgroundColor = '#8faa8e';
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), duration);
}

// 显示加载状态
function showLoading(message = '处理中...') {
    let loading = document.getElementById('loadingOverlay');
    if (!loading) {
        loading = document.createElement('div');
        loading.id = 'loadingOverlay';
        loading.className = 'loading';
        loading.innerHTML = `<div class="loading-text">${message}</div>`;
        document.body.appendChild(loading);
    } else {
        loading.querySelector('.loading-text').textContent = message;
        loading.style.display = 'flex';
    }
}

// 隐藏加载状态
function hideLoading() {
    const loading = document.getElementById('loadingOverlay');
    if (loading) loading.style.display = 'none';
}

// API 请求封装
async function apiRequest(url, options = {}) {
    try {
        const response = await fetch(url, {
            ...options,
            headers: { 'Content-Type': 'application/json', ...options.headers }
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || '请求失败');
        return data;
    } catch (error) {
        console.error('API请求错误:', error);
        showToast(error.message, 'error');
        throw error;
    }
}

// 轮询进度
function pollProgress(url, interval, callbacks) {
    const { onProgress, onComplete, onError } = callbacks;
    const timer = setInterval(async () => {
        try {
            const data = await apiRequest(url);
            if (onProgress) onProgress(data);
            if (data.status === 'completed' || data.status === 'done') {
                clearInterval(timer);
                if (onComplete) onComplete(data);
            } else if (data.status === 'error' || data.status === 'failed') {
                clearInterval(timer);
                if (onError) onError(data);
            }
        } catch (e) { console.warn('轮询错误:', e); }
    }, interval);
    return timer;
}

// FontLab 命名
function fontlabName(code, char) {
    let prefix = code > 0xFFFF ? 'u' + code.toString(16).toUpperCase().padStart(5, '0') : 'uni' + code.toString(16).toUpperCase().padStart(4, '0');
    return char ? prefix + '_' + char + '.png' : prefix + '.png';
}

function formatDuration(seconds) {
    if (seconds < 60) return Math.round(seconds) + '秒';
    if (seconds < 3600) return Math.floor(seconds / 60) + '分' + Math.round(seconds % 60) + '秒';
    return Math.floor(seconds / 3600) + '时' + Math.floor((seconds % 3600) / 60) + '分';
}

function appendLog(container, text) {
    const line = document.createElement('div');
    line.textContent = text;
    container.appendChild(line);
    container.scrollTop = container.scrollHeight;
}

// ===== 路径历史记录 =====
const PATH_HISTORY_KEY = 'ai_font_path_history';

function getPathHistory(inputId) {
    try {
        const all = JSON.parse(localStorage.getItem(PATH_HISTORY_KEY) || '{}');
        return all[inputId] || [];
    } catch { return []; }
}

function savePathHistory(inputId, path) {
    if (!path) return;
    try {
        const all = JSON.parse(localStorage.getItem(PATH_HISTORY_KEY) || '{}');
        let list = all[inputId] || [];
        // 去重，新的放最前面
        list = list.filter(p => p !== path);
        list.unshift(path);
        if (list.length > 10) list = list.slice(0, 10);
        all[inputId] = list;
        localStorage.setItem(PATH_HISTORY_KEY, JSON.stringify(all));
    } catch {}
}

function getLastPath(inputId) {
    const hist = getPathHistory(inputId);
    return hist.length > 0 ? hist[0] : '';
}

// 页面加载时恢复上次路径（对带 data-persist 的输入框）
function restorePaths() {
    document.querySelectorAll('input[data-persist]').forEach(input => {
        const last = getLastPath(input.id);
        if (last) {
            input.value = last;
        }
    });
}

// ===== 文件/目录浏览器 =====
let _browseTarget = null;
let _browseType = 'dir';
let _browseExtensions = [];

async function browseFile(inputId, extensions) {
    _browseTarget = inputId;
    _browseType = 'file';
    _browseExtensions = extensions || [];
    document.getElementById('browseTitle').textContent = '选择文件';
    const startPath = document.getElementById(inputId).value || getLastPath(inputId) || 'C:\\';
    document.getElementById('browseModal').style.display = 'flex';
    await loadBrowseItems(startPath);
}

async function browseDir(inputId) {
    _browseTarget = inputId;
    _browseType = 'dir';
    _browseExtensions = [];
    document.getElementById('browseTitle').textContent = '选择目录';
    const startPath = document.getElementById(inputId).value || getLastPath(inputId) || 'C:\\';
    document.getElementById('browseModal').style.display = 'flex';
    await loadBrowseItems(startPath);
}

async function loadBrowseItems(path) {
    const list = document.getElementById('browseList');
    if (list) list.innerHTML = '<div style="padding:20px;text-align:center;color:#999">加载中...</div>';
    try {
        const data = await apiRequest('/api/browse', {
            method: 'POST',
            body: JSON.stringify({ path, type: _browseType, extensions: _browseExtensions })
        });
        if (!data.success) return;
        // 文件路径时浏览其父目录
        if (data.type === 'file' && data.selected) {
            const sep = data.selected.includes('\\') ? '\\' : '/';
            const parts = data.selected.split(sep);
            parts.pop();
            const parentDir = parts.join(sep);
            if (parentDir) {
                loadBrowseItems(parentDir);
                return;
            }
        }
        if (!data.items) return;

        document.getElementById('browseCurrent').textContent = data.current;
        document.getElementById('browseInput').value = data.current;
        if (list) list.innerHTML = '';

        // 1. 历史记录区
        const history = _browseTarget ? getPathHistory(_browseTarget) : [];
        if (history.length > 1) {
            const histSection = document.createElement('div');
            histSection.style.cssText = 'padding:4px 12px 8px;border-bottom:1px solid #e0ddd8;margin-bottom:4px;';
            histSection.innerHTML = '<div style="font-size:11px;color:#999;margin-bottom:4px">历史记录</div>';
            history.slice(0, 8).forEach(p => {
                const item = document.createElement('div');
                item.style.cssText = 'padding:5px 8px;cursor:pointer;border-radius:4px;font-size:11px;font-family:monospace;color:#5a5a5a;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;';
                item.textContent = p;
                item.title = p;
                item.onmouseenter = () => item.style.background = '#f0ede8';
                item.onmouseleave = () => item.style.background = '';
                item.onclick = () => loadBrowseItems(p);
                histSection.appendChild(item);
            });
            list.appendChild(histSection);
        }

        // 2. 目录模式：确认选择当前目录
        if (_browseType === 'dir') {
            const confirmDiv = document.createElement('div');
            confirmDiv.style.cssText = 'padding:10px 12px;cursor:pointer;border-radius:4px;font-size:13px;display:flex;align-items:center;gap:8px;background:#f0ede8;border:1px solid #d8d4cf;margin-bottom:4px;font-weight:600;color:#5a5a5a;';
            confirmDiv.innerHTML = '<span>✅</span><span>选择当前目录</span>';
            confirmDiv.onmouseenter = () => confirmDiv.style.background = '#e8e4df';
            confirmDiv.onmouseleave = () => confirmDiv.style.background = '#f0ede8';
            confirmDiv.onclick = () => {
                _applyBrowseValue(data.current);
            };
            list.appendChild(confirmDiv);
        }

        // 3. 盘符 + 文件列表
        data.items.forEach(item => {
            if (item.type === 'drives') {
                const section = document.createElement('div');
                section.style.cssText = 'padding:4px 12px;display:flex;gap:8px;flex-wrap:wrap;margin-bottom:4px;';
                item.drives.forEach(d => {
                    const btn = document.createElement('span');
                    btn.textContent = d.name.replace('\\', '');
                    btn.style.cssText = 'padding:4px 10px;border:1px solid #d8d4cf;border-radius:4px;font-size:12px;cursor:pointer;background:#fff;color:#5a5a5a;';
                    btn.onmouseenter = () => btn.style.background = '#f0ede8';
                    btn.onmouseleave = () => btn.style.background = '#fff';
                    btn.onclick = () => loadBrowseItems(d.path);
                    section.appendChild(btn);
                });
                list.appendChild(section);
                return;
            }

            const div = document.createElement('div');
            div.style.cssText = 'padding:8px 12px;cursor:pointer;border-radius:4px;font-size:13px;display:flex;align-items:center;gap:8px;';
            const icon = item.type === 'parent' ? '⬆' : (item.type === 'dir' ? '📁' : '📄');
            div.innerHTML = `<span>${icon}</span><span>${item.name}</span>`;
            div.onmouseenter = () => div.style.background = '#f0ede8';
            div.onmouseleave = () => div.style.background = '';
            div.onclick = () => {
                if (item.type === 'dir' || item.type === 'parent') {
                    loadBrowseItems(item.path);
                } else if (item.type === 'file') {
                    _applyBrowseValue(item.path);
                }
            };
            list.appendChild(div);
        });
    } catch (e) {
        console.error('loadBrowseItems error:', e);
        if (list) list.innerHTML = '<div style="padding:20px;text-align:center;color:#999">加载失败: ' + (e.message || e) + '</div>';
    }
}

// 应用选择的路径
function _applyBrowseValue(path) {
    if (!_browseTarget || !path) return;
    document.getElementById(_browseTarget).value = path;
    savePathHistory(_browseTarget, path);
    document.getElementById('browseModal').style.display = 'none';
}

function closeBrowse() {
    document.getElementById('browseModal').style.display = 'none';
}

function confirmBrowse() {
    if (!_browseTarget) return;
    const val = document.getElementById('browseInput').value;
    if (val) {
        document.getElementById(_browseTarget).value = val;
        savePathHistory(_browseTarget, val);
    }
    document.getElementById('browseModal').style.display = 'none';
}

// 页面加载时自动恢复路径
document.addEventListener('DOMContentLoaded', restorePaths);
