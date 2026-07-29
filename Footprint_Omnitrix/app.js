const canvas = document.getElementById('footprint-canvas');
const ctx = canvas.getContext('2d');
const symbolSelect = document.getElementById('symbol-select');
const timeframeSelect = document.getElementById('timeframe-select');
const statusDiv = document.getElementById('status');
const themeToggle = document.getElementById('theme-toggle');
const modeBtns = document.querySelectorAll('.mode-btn');

let footprintData = {};
let currentSymbol = '';
let currentTimeframe = 1;
let currentMode = 'footprint';
let isSelectingAnchor = false;
let anchorTimestamp = null;

// TradingView Engine State
let activeIndicators = [
    { type: 'ema', period: 20, color: '#f5b041', pane: 'main' },
    { type: 'bollinger', period: 20, std: 2, color: '#3498db', pane: 'main' },
    { type: 'rsi', period: 14, color: '#9b59b6', pane: 'lower' }
];
let activeDrawings = [];
let currentDrawingMode = null; 
let tempDrawing = null; 
let bottomPanes = ['cvd']; // 'cvd', 'rsi', etc.

// Mathematical Library
function calculateSMA(data, period, key = 'close') {
    let result = new Array(data.length).fill(null);
    for (let i = period - 1; i < data.length; i++) {
        let sum = 0;
        for (let j = 0; j < period; j++) sum += data[i - j][key];
        result[i] = sum / period;
    }
    return result;
}

function calculateEMA(data, period, key = 'close') {
    let result = new Array(data.length).fill(null);
    if (data.length < period) return result;
    const k = 2 / (period + 1);
    let sum = 0;
    for (let i = 0; i < period; i++) sum += data[i][key];
    let ema = sum / period;
    result[period - 1] = ema;
    for (let i = period; i < data.length; i++) {
        ema = (data[i][key] - ema) * k + ema;
        result[i] = ema;
    }
    return result;
}

function calculateRSI(data, period, key = 'close') {
    let result = new Array(data.length).fill(null);
    if (data.length <= period) return result;
    let gains = 0, losses = 0;
    for (let i = 1; i <= period; i++) {
        const change = data[i][key] - data[i-1][key];
        if (change > 0) gains += change;
        else losses -= change;
    }
    let avgGain = gains / period;
    let avgLoss = losses / period;
    result[period] = avgLoss === 0 ? 100 : 100 - (100 / (1 + (avgGain / avgLoss)));
    
    for (let i = period + 1; i < data.length; i++) {
        const change = data[i][key] - data[i-1][key];
        let gain = change > 0 ? change : 0;
        let loss = change < 0 ? -change : 0;
        avgGain = ((avgGain * (period - 1)) + gain) / period;
        avgLoss = ((avgLoss * (period - 1)) + loss) / period;
        result[i] = avgLoss === 0 ? 100 : 100 - (100 / (1 + (avgGain / avgLoss)));
    }
    return result;
}

function calculateBollinger(data, period, stdDev, key = 'close') {
    let sma = calculateSMA(data, period, key);
    let upper = new Array(data.length).fill(null);
    let lower = new Array(data.length).fill(null);
    for (let i = period - 1; i < data.length; i++) {
        let sumSq = 0;
        for (let j = 0; j < period; j++) {
            sumSq += Math.pow(data[i - j][key] - sma[i], 2);
        }
        let std = Math.sqrt(sumSq / period);
        upper[i] = sma[i] + (stdDev * std);
        lower[i] = sma[i] - (stdDev * std);
    }
    return { sma, upper, lower };
}

function calculateCPR(candles) {
    if (candles.length === 0) return { p: 0, tc: 0, bc: 0 };
    let high = -Infinity;
    let low = Infinity;
    let close = candles[candles.length - 1].close;
    candles.forEach(c => {
        if (c.high > high) high = c.high;
        if (c.low < low) low = c.low;
    });
    const p = (high + low + close) / 3;
    const bc = (high + low) / 2;
    const tc = (p - bc) + p;
    return { p, tc, bc };
}

// Viewport state
let scaleX = 140; 
let scaleY = 2500; 
let offsetX = 0;
let offsetY = 0;
let isDraggingChart = false;
let isDraggingYAxis = false;
let isDraggingXAxis = false;
let lastDragX = 0;
let lastDragY = 0;

let mouseX = -1;
let mouseY = -1;
let mouseHover = false;

const AXIS_RIGHT = 75;
const AXIS_BOTTOM = 30;

let THEME = {
    bg: '#ffffff',
    grid: '#e0e3eb',
    text: '#131722',
    green: '#089981',
    red: '#f23645',
    blue: '#2962FF',
    volProfile: 'rgba(41, 98, 255, 0.15)',
    footprintBgGreen: 'rgba(8, 153, 129, 0.15)',
    footprintBgRed: 'rgba(242, 54, 69, 0.15)',
    textMuted: '#787b86',
    pocBg: '#131722',
    pocText: '#ffffff'
};

if (themeToggle) {
    themeToggle.addEventListener('click', () => {
        document.body.classList.toggle('dark-theme');
        if (document.body.classList.contains('dark-theme')) {
            THEME = {
                bg: '#131722', grid: '#2a2e39', text: '#d1d4dc',
                green: '#089981', red: '#f23645', blue: '#2962FF',
                volProfile: 'rgba(41, 98, 255, 0.15)',
                footprintBgGreen: 'rgba(8, 153, 129, 0.15)', footprintBgRed: 'rgba(242, 54, 69, 0.15)',
                textMuted: '#787b86', pocBg: '#d1d4dc', pocText: '#131722'
            };
        } else {
            THEME = {
                bg: '#ffffff', grid: '#e0e3eb', text: '#131722',
                green: '#089981', red: '#f23645', blue: '#2962FF',
                volProfile: 'rgba(41, 98, 255, 0.15)',
                footprintBgGreen: 'rgba(8, 153, 129, 0.15)', footprintBgRed: 'rgba(242, 54, 69, 0.15)',
                textMuted: '#787b86', pocBg: '#131722', pocText: '#ffffff'
            };
        }
        draw();
    });
}

document.querySelectorAll('.tool-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        if (!btn.hasAttribute('data-tool')) return;
        document.querySelectorAll('.tool-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentDrawingMode = btn.getAttribute('data-tool');
        tempDrawing = null;
    });
});

modeBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        modeBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentMode = btn.getAttribute('data-mode');
        
        if (currentMode === 'vp-anchored') {
            isSelectingAnchor = true;
            anchorTimestamp = null;
        } else {
            isSelectingAnchor = false;
        }
        draw();
    });
});

timeframeSelect.addEventListener('change', (e) => {
    currentTimeframe = parseInt(e.target.value);
    centerChart();
    draw();
});

function resizeCanvas() {
    canvas.width = canvas.parentElement.clientWidth;
    canvas.height = canvas.parentElement.clientHeight;
    draw();
}
window.addEventListener('resize', resizeCanvas);
resizeCanvas();

let ws = null;
function connectWS() {
    ws = new WebSocket('ws://localhost:8766');
    ws.onopen = () => {
        statusDiv.textContent = 'Connected';
        statusDiv.className = 'status connected';
    };
    ws.onclose = () => {
        statusDiv.textContent = 'Disconnected';
        statusDiv.className = 'status disconnected';
        setTimeout(connectWS, 3000);
    };
    ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === 'init') {
            footprintData = msg.data;
            updateSymbolDropdown();
        } else if (msg.type === 'update') {
            if (!footprintData[msg.symbol]) {
                footprintData[msg.symbol] = { candles: [] };
                updateSymbolDropdown();
            }
            const symbolData = footprintData[msg.symbol];
            const candles = symbolData.candles;

            if (msg.tick) {
                // Incoming live tick: only update active candle (candles[candles.length - 1])
                updateTickCandle(symbolData, msg.tick, 100);
            } else if (msg.candle) {
                // Candle update: check if updating current active candle or pushing a new candle
                if (candles.length > 0 && candles[candles.length - 1].timestamp === msg.candle.timestamp) {
                    candles[candles.length - 1] = msg.candle;
                } else if (candles.length === 0 || msg.candle.timestamp > candles[candles.length - 1].timestamp) {
                    candles.push(msg.candle);
                    if (candles.length > 60) candles.shift();
                    
                    if (msg.symbol === currentSymbol) {
                        const chartWidth = canvas.width - AXIS_RIGHT;
                        const maxX = (candles.length * scaleX);
                        if (offsetX < chartWidth - maxX + scaleX * 2) {
                            offsetX = chartWidth - maxX - 100;
                        }
                    }
                }
            }

            if (msg.symbol === currentSymbol) {
                draw();
                updatePanels(candles[candles.length - 1] || msg.candle, msg.tape);
            }
        }
    };
}
connectWS();

function updateTickCandle(symbolData, tick, maxTicks = 100) {
    if (!symbolData.candles) {
        symbolData.candles = [];
    }
    const candles = symbolData.candles;
    let activeCandle = candles.length > 0 ? candles[candles.length - 1] : null;

    if (!activeCandle || (activeCandle.tickCount || 0) >= maxTicks) {
        if (activeCandle) {
            activeCandle.isCompleted = true;
        }
        activeCandle = {
            timestamp: tick.timestamp || Math.floor(Date.now() / 1000),
            open: tick.price,
            high: tick.price,
            low: tick.price,
            close: tick.price,
            volume: tick.size || 1,
            tickCount: 1,
            isCompleted: false,
            footprint: {}
        };
        candles.push(activeCandle);
    } else {
        // Only update active candle (candles[candles.length - 1])
        activeCandle.high = Math.max(activeCandle.high, tick.price);
        activeCandle.low = Math.min(activeCandle.low, tick.price);
        activeCandle.close = tick.price;
        activeCandle.volume += (tick.size || 1);
        activeCandle.tickCount = (activeCandle.tickCount || 0) + 1;
    }
}

function updatePanels(candle, tape) {
    if (!candle) return;
    
    let totalVol = 0;
    let totalDelta = 0;
    if (footprintData[currentSymbol] && footprintData[currentSymbol].candles) {
        footprintData[currentSymbol].candles.forEach(c => {
            totalVol += (c.volume || 0);
            Object.values(c.footprint).forEach(fp => totalDelta += (fp.ask - fp.bid));
        });
    }
    
    const elVol = document.getElementById('stat-vol');
    const elDelta = document.getElementById('stat-delta');
    const elVwap = document.getElementById('stat-vwap');
    const elPace = document.getElementById('stat-pace');
    
    if (elVol) elVol.textContent = formatVol(totalVol);
    if (elDelta) {
        elDelta.textContent = (totalDelta > 0 ? '+' : '') + formatVol(totalDelta);
        elDelta.style.color = totalDelta >= 0 ? THEME.green : THEME.red;
    }
    if (elVwap && candle.vwap) {
        elVwap.textContent = candle.vwap.toFixed(2);
    }
    
    if (tape && tape.length > 0) {
        const latestTs = tape[tape.length-1].ts;
        let recentVol = 0;
        tape.forEach(t => {
            if (latestTs - t.ts <= 1000) recentVol += t.size;
        });
        if (elPace) elPace.textContent = formatVol(recentVol);
        
        const tc = document.getElementById('tape-container');
        if (tc) {
            tc.innerHTML = '';
            [...tape].reverse().forEach(t => {
                const row = document.createElement('div');
                row.className = 'tape-row ' + t.side.toLowerCase() + (t.iceberg ? ' iceberg' : '');
                
                const sz = document.createElement('div'); sz.textContent = t.size;
                const pr = document.createElement('div'); pr.textContent = t.price.toFixed(2);
                const tm = document.createElement('div'); 
                const d = new Date(t.ts);
                tm.textContent = `${d.getHours().toString().padStart(2,'0')}:${d.getMinutes().toString().padStart(2,'0')}:${d.getSeconds().toString().padStart(2,'0')}`;
                
                row.appendChild(sz);
                row.appendChild(pr);
                row.appendChild(tm);
                tc.appendChild(row);
            });
        }
    }
}

function updateSymbolDropdown() {
    const symbols = Object.keys(footprintData).sort();
    if (symbols.length === 0) return;
    const currentValue = symbolSelect.value;
    symbolSelect.innerHTML = '';
    symbols.forEach(sym => {
        const opt = document.createElement('option');
        opt.value = sym; opt.textContent = sym;
        symbolSelect.appendChild(opt);
    });
    if (symbols.includes(currentValue)) {
        symbolSelect.value = currentValue;
    } else {
        symbolSelect.value = symbols[0];
        currentSymbol = symbols[0];
        centerChart();
    }
}

symbolSelect.addEventListener('change', (e) => {
    currentSymbol = e.target.value;
    centerChart();
});

function centerChart() {
    if (!currentSymbol || !footprintData[currentSymbol] || footprintData[currentSymbol].candles.length === 0) return;
    const candles = getDisplayCandles(footprintData[currentSymbol].candles, currentTimeframe);
    if (candles.length === 0) return;
    const lastCandle = candles[candles.length - 1];
    const chartHeight = canvas.height - AXIS_BOTTOM;
    const chartWidth = canvas.width - AXIS_RIGHT;
    offsetY = (chartHeight / 2) - (lastCandle.close * scaleY);
    offsetX = chartWidth - (candles.length * scaleX) - 100;
    draw();
}

canvas.addEventListener('mousedown', (e) => {
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const PANE_HEIGHT = 80;
    const numPanes = bottomPanes.length;
    const chartWidth = canvas.width - AXIS_RIGHT;
    const chartHeight = canvas.height - AXIS_BOTTOM - (numPanes * PANE_HEIGHT);
    
    // Anchor Selection Logic
    if (isSelectingAnchor && mx < chartWidth && my < chartHeight) {
        const timeIndex = Math.floor((mx - offsetX) / scaleX);
        const candles = getDisplayCandles(footprintData[currentSymbol].candles, currentTimeframe);
        if (timeIndex >= 0 && timeIndex < candles.length) {
            anchorTimestamp = candles[timeIndex].timestamp;
            isSelectingAnchor = false;
            draw();
        }
        return;
    }
    
    if (currentDrawingMode && currentDrawingMode !== 'cursor' && mx < chartWidth && my < chartHeight) {
        const timeIndex = (mx - offsetX) / scaleX;
        const price = (chartHeight - my - offsetY) / scaleY;
        
        if (currentDrawingMode === 'pen') {
            tempDrawing = { type: 'pen', points: [{time: timeIndex, price: price}], color: THEME.blue };
        } else if (currentDrawingMode === 'trendline' || currentDrawingMode === 'ray' || currentDrawingMode === 'fib' || currentDrawingMode === 'gann') {
            if (!tempDrawing) {
                tempDrawing = { type: currentDrawingMode, start: {time: timeIndex, price: price}, end: {time: timeIndex, price: price}, color: THEME.blue };
            } else {
                tempDrawing.end = {time: timeIndex, price: price};
                activeDrawings.push(tempDrawing);
                tempDrawing = null;
                currentDrawingMode = 'cursor';
                document.querySelectorAll('.tool-btn').forEach(b => b.classList.remove('active'));
                const curBtn = document.querySelector('.tool-btn[title="Cursor"]');
                if (curBtn) curBtn.classList.add('active');
            }
        }
        draw();
        if (currentDrawingMode === 'pen' || tempDrawing) return;
    }

    lastDragX = e.clientX;
    lastDragY = e.clientY;
    
    if (!currentDrawingMode || currentDrawingMode === 'cursor') {
        if (mx > chartWidth && my < chartHeight) isDraggingYAxis = true;
        else if (my > chartHeight && mx < chartWidth) isDraggingXAxis = true;
        else if (mx < chartWidth && my < chartHeight) isDraggingChart = true;
    }
});

window.addEventListener('mouseup', () => {
    isDraggingChart = false;
    isDraggingYAxis = false;
    isDraggingXAxis = false;
    
    if (tempDrawing && tempDrawing.type === 'pen') {
        activeDrawings.push(tempDrawing);
        tempDrawing = null;
        currentDrawingMode = 'cursor';
        document.querySelectorAll('.tool-btn').forEach(b => b.classList.remove('active'));
        const curBtn = document.querySelector('.tool-btn[title="Cursor"]');
        if (curBtn) curBtn.classList.add('active');
    }
    
    draw();
});

canvas.addEventListener('dblclick', () => {
    scaleY = 2500;
    scaleX = 140;
    centerChart();
});

window.addEventListener('mouseenter', () => { mouseHover = true; });
window.addEventListener('mouseleave', () => {
    mouseHover = false;
    isDraggingChart = false;
    isDraggingYAxis = false;
    isDraggingXAxis = false;
    if (tempDrawing && tempDrawing.type === 'pen') {
        activeDrawings.push(tempDrawing);
        tempDrawing = null;
    }
    draw();
});

window.addEventListener('mousemove', (e) => {
    const rect = canvas.getBoundingClientRect();
    mouseX = e.clientX - rect.left;
    mouseY = e.clientY - rect.top;
    const PANE_HEIGHT = 80;
    const numPanes = bottomPanes.length;
    const chartWidth = canvas.width - AXIS_RIGHT;
    const chartHeight = canvas.height - AXIS_BOTTOM - (numPanes * PANE_HEIGHT);
    
    if (tempDrawing && mouseX < chartWidth && mouseY < chartHeight) {
        const timeIndex = (mouseX - offsetX) / scaleX;
        const price = (chartHeight - mouseY - offsetY) / scaleY;
        
        if (tempDrawing.type === 'pen') {
            tempDrawing.points.push({time: timeIndex, price: price});
        } else if (tempDrawing.type === 'trendline' || tempDrawing.type === 'ray' || tempDrawing.type === 'fib' || tempDrawing.type === 'gann') {
            tempDrawing.end = {time: timeIndex, price: price};
        }
        draw();
        if (tempDrawing.type === 'pen') return;
    }
    
    if (isDraggingChart) {
        offsetX += (e.clientX - lastDragX);
        offsetY += (e.clientY - lastDragY);
        lastDragX = e.clientX;
        lastDragY = e.clientY;
    } else if (isDraggingYAxis) {
        const dy = e.clientY - lastDragY;
        const zoomFactor = dy > 0 ? 0.95 : 1.05;
        const priceAtCenter = (chartHeight - (chartHeight/2) - offsetY) / scaleY;
        scaleY *= zoomFactor;
        offsetY = (chartHeight - (chartHeight/2)) - (priceAtCenter * scaleY);
        lastDragY = e.clientY;
    } else if (isDraggingXAxis) {
        const dx = e.clientX - lastDragX;
        const zoomFactor = dx > 0 ? 1.05 : 0.95;
        const timeAtCenter = ((chartWidth/2) - offsetX) / scaleX;
        scaleX = Math.max(20, scaleX * zoomFactor);
        offsetX = (chartWidth/2) - (timeAtCenter * scaleX);
        lastDragX = e.clientX;
    }
    
    if (isSelectingAnchor) canvas.style.cursor = 'crosshair';
    else if (currentDrawingMode && currentDrawingMode !== 'cursor') canvas.style.cursor = 'crosshair';
    else if (mouseX > chartWidth && mouseY < chartHeight) canvas.style.cursor = 'ns-resize';
    else if (mouseY > chartHeight && mouseX < chartWidth) canvas.style.cursor = 'ew-resize';
    else canvas.style.cursor = 'crosshair';
    
    draw();
});

canvas.addEventListener('wheel', (e) => {
    e.preventDefault();
    const zoomFactor = e.deltaY > 0 ? 0.9 : 1.1;
    const chartWidth = canvas.width - AXIS_RIGHT;
    const chartHeight = canvas.height - AXIS_BOTTOM;
    
    if (mouseX > chartWidth) {
        const priceAtMouse = (chartHeight - mouseY - offsetY) / scaleY;
        scaleY *= zoomFactor;
        offsetY = (chartHeight - mouseY) - (priceAtMouse * scaleY);
    } 
    else if (mouseY > chartHeight) {
        const timeAtMouse = (mouseX - offsetX) / scaleX;
        scaleX = Math.max(20, scaleX * zoomFactor);
        offsetX = mouseX - (timeAtMouse * scaleX);
    }
    else {
        if (e.shiftKey) {
            const timeAtMouse = (mouseX - offsetX) / scaleX;
            scaleX = Math.max(20, scaleX * zoomFactor);
            offsetX = mouseX - (timeAtMouse * scaleX);
        } else {
            const priceAtMouse = (chartHeight - mouseY - offsetY) / scaleY;
            scaleY *= zoomFactor;
            offsetY = (chartHeight - mouseY) - (priceAtMouse * scaleY);
        }
    }
    draw();
});

function formatPrice(p) { return p.toFixed(2); }
function formatTime(ms) {
    const d = new Date(ms * 1000);
    return d.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit' });
}
function formatVol(v) {
    if (v === 0) return "";
    if (v >= 1000) return (v / 1000).toFixed(2) + "K";
    return v.toString();
}

function getDisplayCandles(baseCandles, timeframeMinutes) {
    if (timeframeMinutes === 1 || baseCandles.length === 0) return baseCandles;
    let aggregated = [];
    let currentAgg = null;
    let periodMs = timeframeMinutes * 60;
    
    baseCandles.forEach(c => {
        const periodStart = Math.floor(c.timestamp / periodMs) * periodMs;
        if (!currentAgg || currentAgg.timestamp !== periodStart) {
            if (currentAgg) aggregated.push(currentAgg);
            currentAgg = {
                timestamp: periodStart,
                open: c.open,
                high: c.high,
                low: c.low,
                close: c.close,
                footprint: {}
            };
        } else {
            currentAgg.high = Math.max(currentAgg.high, c.high);
            currentAgg.low = Math.min(currentAgg.low, c.low);
            currentAgg.close = c.close;
        }
        
        for (let price in c.footprint) {
            if (!currentAgg.footprint[price]) currentAgg.footprint[price] = { bid: 0, ask: 0 };
            currentAgg.footprint[price].bid += c.footprint[price].bid;
            currentAgg.footprint[price].ask += c.footprint[price].ask;
        }
    });
    if (currentAgg) aggregated.push(currentAgg);
    return aggregated;
}

// ----------------------------------------------------
// RENDERING FUNCTIONS
// ----------------------------------------------------

function drawGrid(chartWidth, chartHeight, minPrice, maxPrice, step, candles) {
    ctx.strokeStyle = THEME.grid;
    ctx.lineWidth = 1;
    ctx.beginPath();
    const startPrice = Math.floor(minPrice / step) * step;
    for (let p = startPrice; p <= maxPrice; p += step) {
        const py = chartHeight - (p * scaleY + offsetY);
        if (py >= 0 && py <= chartHeight) {
            ctx.moveTo(0, Math.round(py) + 0.5);
            ctx.lineTo(chartWidth, Math.round(py) + 0.5);
        }
    }
    const skip = Math.max(1, Math.floor(120 / scaleX));
    if (candles) {
        ctx.setLineDash([2, 4]);
        for (let i = 0; i < candles.length; i += skip) {
            const x = offsetX + (i * scaleX) + scaleX/2;
            if (x >= 0 && x <= chartWidth) {
                ctx.moveTo(Math.round(x) + 0.5, 0);
                ctx.lineTo(Math.round(x) + 0.5, chartHeight);
            }
        }
        ctx.setLineDash([]);
    }
    ctx.stroke();
}

function drawAxes(chartWidth, chartHeight, minPrice, maxPrice, step, candles) {
    ctx.fillStyle = THEME.bg;
    ctx.fillRect(chartWidth, 0, AXIS_RIGHT, canvas.height); 
    ctx.fillRect(0, chartHeight, canvas.width, AXIS_BOTTOM);
    
    ctx.strokeStyle = THEME.grid;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(chartWidth + 0.5, 0); ctx.lineTo(chartWidth + 0.5, canvas.height);
    ctx.moveTo(0, chartHeight + 0.5); ctx.lineTo(canvas.width, chartHeight + 0.5);
    ctx.stroke();
    
    const startPrice = Math.floor(minPrice / step) * step;
    ctx.fillStyle = THEME.text;
    ctx.font = '12px -apple-system, BlinkMacSystemFont, "Trebuchet MS", Roboto, Ubuntu, sans-serif';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';
    
    for (let p = startPrice; p <= maxPrice; p += step) {
        const py = chartHeight - (p * scaleY + offsetY);
        if (py >= 0 && py <= chartHeight) {
            ctx.fillText(formatPrice(p), chartWidth + 6, py);
        }
    }
    
    if (candles && candles.length > 0) {
        ctx.textAlign = 'center';
        const skip = Math.max(1, Math.floor(120 / scaleX));
        for (let i = 0; i < candles.length; i += skip) {
            const x = offsetX + (i * scaleX) + scaleX/2;
            if (x >= 0 && x <= chartWidth) {
                const label = formatTime(candles[i].timestamp);
                ctx.fillText(label, x, chartHeight + AXIS_BOTTOM/2);
            }
        }
    }
}

function drawCandlestick(candle, x, chartHeight) {
    const openY = chartHeight - (candle.open * scaleY + offsetY);
    const closeY = chartHeight - (candle.close * scaleY + offsetY);
    const highY = chartHeight - (candle.high * scaleY + offsetY);
    const lowY = chartHeight - (candle.low * scaleY + offsetY);
    
    const candleWidth = Math.min(10, scaleX * 0.15);
    const candleCenterX = x + (scaleX * 0.1);
    
    const isBullish = candle.close >= candle.open;
    const color = isBullish ? THEME.green : THEME.red;
    
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(Math.round(candleCenterX) + 0.5, Math.round(highY));
    ctx.lineTo(Math.round(candleCenterX) + 0.5, Math.round(lowY));
    ctx.stroke();
    
    ctx.fillStyle = color;
    const bodyTop = Math.min(openY, closeY);
    const bodyHeight = Math.max(1, Math.abs(closeY - openY));
    ctx.fillRect(Math.round(candleCenterX - candleWidth/2), Math.round(bodyTop), candleWidth, bodyHeight);
}

function drawFootprintData(ctx, candle, x, chartHeight, tickSize, maxVol) {
    const fpKeys = Object.keys(candle.footprint).sort((a,b) => parseFloat(b) - parseFloat(a));
    const candleWidth = Math.min(10, scaleX * 0.15);
    const candleCenterX = x + (scaleX * 0.1);
    const footprintStartX = candleCenterX + (candleWidth / 2) + 4;
    const boxWidth = (scaleX * 0.8 - candleWidth - 8) / 2;
    const boxHeight = scaleY * tickSize;
    
    let pocPrice = null;
    let pocVol = -1;
    let totalVolBar = 0;
    let totalDelta = 0;
    
    fpKeys.forEach(priceStr => {
        const vols = candle.footprint[priceStr];
        const totalVol = vols.bid + vols.ask;
        totalVolBar += totalVol;
        totalDelta += (vols.ask - vols.bid);
        if (totalVol > pocVol) {
            pocVol = totalVol;
            pocPrice = parseFloat(priceStr);
        }
    });

    const imbalances = { bid: {}, ask: {} };
    fpKeys.forEach(priceStr => {
        const price = parseFloat(priceStr);
        const pUp = (price + tickSize).toFixed(2);
        const pDown = (price - tickSize).toFixed(2);
        
        if (candle.footprint[pDown]) {
            const bidDown = candle.footprint[pDown].bid;
            const askHere = candle.footprint[priceStr].ask;
            if (askHere > 0 && bidDown >= 0) {
                if (bidDown === 0) { if (askHere > 5) imbalances.ask[priceStr] = true; } 
                else if (askHere / bidDown > 3) imbalances.ask[priceStr] = true;
            }
        }
        if (candle.footprint[pUp]) {
            const askUp = candle.footprint[pUp].ask;
            const bidHere = candle.footprint[priceStr].bid;
            if (bidHere > 0 && askUp >= 0) {
                if (askUp === 0) { if (bidHere > 5) imbalances.bid[priceStr] = true; } 
                else if (bidHere / askUp > 3) imbalances.bid[priceStr] = true;
            }
        }
    });

    const fontSize = Math.max(8, Math.min(12, boxHeight * 0.7));
    ctx.font = `${fontSize}px -apple-system, BlinkMacSystemFont, "Trebuchet MS", Roboto, Ubuntu, sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';

    fpKeys.forEach(priceStr => {
        const price = parseFloat(priceStr);
        const vols = candle.footprint[priceStr];
        const pY = chartHeight - (price * scaleY + offsetY) - boxHeight/2;
        if (pY + boxHeight < 0 || pY > chartHeight) return;
        const isPoc = (price === pocPrice);
        
        // BID
        if (isPoc) ctx.fillStyle = THEME.pocBg;
        else if (imbalances.bid[priceStr]) ctx.fillStyle = THEME.red;
        else if (vols.bid > 0) ctx.fillStyle = THEME.footprintBgRed;
        else ctx.fillStyle = 'transparent';
        
        if (vols.bid > 0 || isPoc) {
            ctx.fillRect(footprintStartX, pY, boxWidth, boxHeight);
            ctx.fillStyle = (isPoc || imbalances.bid[priceStr]) ? THEME.pocText : THEME.text;
            const bidStr = formatVol(vols.bid);
            if (bidStr) ctx.fillText(bidStr, footprintStartX + boxWidth/2, pY + boxHeight/2);
        }
        
        // ASK
        if (isPoc) ctx.fillStyle = THEME.pocBg;
        else if (imbalances.ask[priceStr]) ctx.fillStyle = THEME.green;
        else if (vols.ask > 0) ctx.fillStyle = THEME.footprintBgGreen;
        else ctx.fillStyle = 'transparent';
        
        if (vols.ask > 0 || isPoc) {
            ctx.fillRect(footprintStartX + boxWidth, pY, boxWidth, boxHeight);
            ctx.fillStyle = (isPoc || imbalances.ask[priceStr]) ? THEME.pocText : THEME.text;
            const askStr = formatVol(vols.ask);
            if (askStr) ctx.fillText(askStr, footprintStartX + boxWidth + boxWidth/2, pY + boxHeight/2);
        }
        
        ctx.fillStyle = 'rgba(0,0,0,0.05)';
        ctx.fillRect(footprintStartX + boxWidth - 1, pY, 2, boxHeight);
        
        if (isPoc) {
            ctx.strokeStyle = THEME.textMuted;
            ctx.lineWidth = 1;
            ctx.strokeRect(footprintStartX, pY, boxWidth * 2, boxHeight);
        }
    });

    if (scaleX > 60 && fpKeys.length > 0) {
        const lowestPrice = parseFloat(fpKeys[fpKeys.length - 1]);
        const pY = chartHeight - (lowestPrice * scaleY + offsetY) - boxHeight/2;
        const bottomY = pY + boxHeight + 15;
        if (bottomY < chartHeight - 40 && bottomY > 0) {
            ctx.fillStyle = THEME.text;
            ctx.font = '11px -apple-system, BlinkMacSystemFont, "Trebuchet MS", Roboto, Ubuntu, sans-serif';
            ctx.textAlign = 'right';
            ctx.fillText("Delta", x + scaleX/2 - 4, bottomY);
            ctx.fillText("Total", x + scaleX/2 - 4, bottomY + 14);
            ctx.textAlign = 'left';
            ctx.fillStyle = totalDelta >= 0 ? THEME.green : THEME.red;
            ctx.fillText((totalDelta > 0 ? "+" : "") + formatVol(totalDelta), x + scaleX/2 + 4, bottomY);
            ctx.fillStyle = THEME.text;
            ctx.font = 'bold 11px -apple-system, BlinkMacSystemFont, "Trebuchet MS", Roboto, Ubuntu, sans-serif';
            ctx.fillText(formatVol(totalVolBar), x + scaleX/2 + 4, bottomY + 14);
        }
    }
    
    // Stacked Imbalances
    const fpKeysAsc = [...fpKeys].reverse();
    let currentBidStack = [];
    let currentAskStack = [];
    fpKeysAsc.forEach(priceStr => {
        if (imbalances.bid[priceStr]) {
            currentBidStack.push(priceStr);
        } else {
            if (currentBidStack.length >= 3) {
                currentBidStack.forEach(p => {
                    const pyStack = chartHeight - (parseFloat(p) * scaleY + offsetY) - boxHeight/2;
                    ctx.strokeStyle = THEME.red; ctx.lineWidth = 2;
                    ctx.strokeRect(footprintStartX, pyStack, boxWidth, boxHeight);
                });
            }
            currentBidStack = [];
        }
        if (imbalances.ask[priceStr]) {
            currentAskStack.push(priceStr);
        } else {
            if (currentAskStack.length >= 3) {
                currentAskStack.forEach(p => {
                    const pyStack = chartHeight - (parseFloat(p) * scaleY + offsetY) - boxHeight/2;
                    ctx.strokeStyle = THEME.green; ctx.lineWidth = 2;
                    ctx.strokeRect(footprintStartX + boxWidth, pyStack, boxWidth, boxHeight);
                });
            }
            currentAskStack = [];
        }
    });
    if (currentBidStack.length >= 3) {
        currentBidStack.forEach(p => {
            const pyStack = chartHeight - (parseFloat(p) * scaleY + offsetY) - boxHeight/2;
            ctx.strokeStyle = THEME.red; ctx.lineWidth = 2;
            ctx.strokeRect(footprintStartX, pyStack, boxWidth, boxHeight);
        });
    }
    if (currentAskStack.length >= 3) {
        currentAskStack.forEach(p => {
            const pyStack = chartHeight - (parseFloat(p) * scaleY + offsetY) - boxHeight/2;
            ctx.strokeStyle = THEME.green; ctx.lineWidth = 2;
            ctx.strokeRect(footprintStartX + boxWidth, pyStack, boxWidth, boxHeight);
        });
    }

    // Unfinished Auctions
    if (fpKeys.length > 0) {
        const topPriceStr = fpKeys[0];
        const bottomPriceStr = fpKeys[fpKeys.length - 1];
        if (candle.footprint[topPriceStr].bid > 0) {
            const py = chartHeight - (parseFloat(topPriceStr) * scaleY + offsetY) - boxHeight/2;
            ctx.fillStyle = THEME.red;
            ctx.fillRect(footprintStartX - 4, py, 4, boxHeight);
        }
        if (candle.footprint[bottomPriceStr].ask > 0) {
            const py = chartHeight - (parseFloat(bottomPriceStr) * scaleY + offsetY) - boxHeight/2;
            ctx.fillStyle = THEME.green;
            ctx.fillRect(footprintStartX - 4, py, 4, boxHeight);
        }
    }
}

function drawClusterData(ctx, candle, x, chartHeight, tickSize, maxVol) {
    const candleWidth = Math.min(10, scaleX * 0.15);
    const candleCenterX = x + (scaleX * 0.1);
    const boxHeight = scaleY * tickSize;
    
    Object.keys(candle.footprint).forEach(priceStr => {
        const price = parseFloat(priceStr);
        const vols = candle.footprint[priceStr];
        const pY = chartHeight - (price * scaleY + offsetY);
        if (pY + boxHeight < 0 || pY - boxHeight > chartHeight) return;
        
        const total = vols.bid + vols.ask;
        if (total === 0) return;
        
        const maxRadius = Math.max(3, (scaleX * 1.0) / 2);
        const radius = Math.max(3, Math.min(maxRadius, (total / maxVol) * maxRadius));
        const cx = candleCenterX + (scaleX * 0.5);
        
        const askRatio = vols.ask / total;
        const bidRatio = vols.bid / total;
        const askAngle = askRatio * 2 * Math.PI;
        
        if (askRatio > 0) {
            ctx.beginPath();
            ctx.moveTo(cx, pY);
            ctx.arc(cx, pY, radius, -Math.PI/2, -Math.PI/2 + askAngle);
            ctx.closePath();
            ctx.fillStyle = THEME.green;
            ctx.fill();
        }
        
        if (bidRatio > 0) {
            ctx.beginPath();
            ctx.moveTo(cx, pY);
            ctx.arc(cx, pY, radius, -Math.PI/2 + askAngle, -Math.PI/2 + 2*Math.PI);
            ctx.closePath();
            ctx.fillStyle = THEME.red;
            ctx.fill();
        }
        
        ctx.beginPath();
        ctx.arc(cx, pY, radius, 0, 2 * Math.PI);
        ctx.strokeStyle = THEME.textMuted;
        ctx.lineWidth = 1;
        ctx.stroke();
        
        if (scaleX > 60) {
            ctx.fillStyle = '#ffffff';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            let fontSize = Math.max(8, Math.min(10, radius * 0.8));
            if (radius > 10) {
                ctx.font = `bold ${fontSize}px "Inter", Arial`;
                ctx.fillText(formatVol(total), cx, pY);
            }
        }
    });
}

const HEAT_COLORS = [];
for (let i = 0; i <= 100; i++) {
    const ratio = i / 100;
    if (ratio < 0.02) HEAT_COLORS.push('transparent');
    else if (ratio < 0.2) HEAT_COLORS.push(`rgba(0, 0, ${Math.floor(100 + ratio*5*155)}, 0.4)`);
    else if (ratio < 0.4) HEAT_COLORS.push(`rgba(0, ${Math.floor((ratio-0.2)*5*255)}, 255, 0.6)`);
    else if (ratio < 0.6) HEAT_COLORS.push(`rgba(${Math.floor((ratio-0.4)*5*255)}, 255, ${Math.floor(255 - (ratio-0.4)*5*255)}, 0.8)`);
    else if (ratio < 0.8) HEAT_COLORS.push(`rgba(255, ${Math.floor(255 - (ratio-0.6)*5*100)}, 0, 0.9)`);
    else HEAT_COLORS.push(`rgba(255, ${Math.floor(155 - (ratio-0.8)*5*155)}, ${Math.floor((ratio-0.8)*5*255)}, 1.0)`);
}

function drawHeatmap(ctx, chartWidth, chartHeight, candles, tickSize) {
    let absoluteMaxVol = 1;
    candles.forEach(c => {
        Object.values(c.footprint).forEach(v => {
            const tot = v.bid + v.ask;
            if (tot > absoluteMaxVol) absoluteMaxVol = tot;
        });
    });

    const boxHeight = scaleY * tickSize;
    for (let i = 0; i < candles.length; i++) {
        const candle = candles[i];
        const x = offsetX + (i * scaleX);
        if (x + scaleX < 0 || x > chartWidth) continue;
        
        Object.keys(candle.footprint).forEach(priceStr => {
            const price = parseFloat(priceStr);
            const vols = candle.footprint[priceStr];
            const pY = chartHeight - (price * scaleY + offsetY) - boxHeight/2;
            if (pY + boxHeight < 0 || pY > chartHeight) return;
            const total = vols.bid + vols.ask;
            if (total === 0) return;
            
            const colorIndex = Math.min(100, Math.floor((total / absoluteMaxVol) * 100));
            ctx.fillStyle = HEAT_COLORS[colorIndex];
            ctx.fillRect(x, Math.floor(pY), scaleX, Math.ceil(boxHeight) + 1);
        });
    }
}

function drawVolumeProfile(ctx, chartWidth, chartHeight, candles, tickSize, isAnchored, anchorTs) {
    const vp = {};
    let maxVpVol = 0;
    let totalVPVol = 0;
    
    candles.forEach(c => {
        if (isAnchored && anchorTs && c.timestamp < anchorTs) return;
        Object.keys(c.footprint).forEach(priceStr => {
            if (!vp[priceStr]) vp[priceStr] = { bid: 0, ask: 0, total: 0 };
            const v = c.footprint[priceStr];
            vp[priceStr].bid += v.bid;
            vp[priceStr].ask += v.ask;
            vp[priceStr].total += (v.bid + v.ask);
            totalVPVol += (v.bid + v.ask);
            if (vp[priceStr].total > maxVpVol) maxVpVol = vp[priceStr].total;
        });
    });
    
    if (totalVPVol === 0) return;
    
    const vpWidth = chartWidth * 0.25; 
    const boxHeight = scaleY * tickSize;
    
    const sortedPrices = Object.keys(vp).map(p => parseFloat(p)).sort((a,b) => a - b);
    
    let pocPrice = null;
    let pocVol = 0;
    sortedPrices.forEach(p => {
        const pStr = p.toFixed(2);
        if (vp[pStr].total > pocVol) {
            pocVol = vp[pStr].total;
            pocPrice = p;
        }
    });

    let vaTotal = pocVol;
    const targetVA = totalVPVol * 0.70;
    let upperIdx = sortedPrices.indexOf(pocPrice) + 1;
    let lowerIdx = sortedPrices.indexOf(pocPrice) - 1;
    
    while (vaTotal < targetVA && (upperIdx < sortedPrices.length || lowerIdx >= 0)) {
        const upperVol = upperIdx < sortedPrices.length ? vp[sortedPrices[upperIdx].toFixed(2)].total : -1;
        const lowerVol = lowerIdx >= 0 ? vp[sortedPrices[lowerIdx].toFixed(2)].total : -1;
        
        if (upperVol >= lowerVol && upperVol !== -1) {
            vaTotal += upperVol;
            upperIdx++;
        } else if (lowerVol !== -1) {
            vaTotal += lowerVol;
            lowerIdx--;
        } else {
            break;
        }
    }
    
    const vaHigh = upperIdx > 0 ? sortedPrices[upperIdx - 1] : pocPrice;
    const vaLow = lowerIdx < sortedPrices.length - 1 ? sortedPrices[lowerIdx + 1] : pocPrice;

    Object.keys(vp).forEach(priceStr => {
        const price = parseFloat(priceStr);
        const pY = chartHeight - (price * scaleY + offsetY) - boxHeight/2;
        if (pY + boxHeight < 0 || pY > chartHeight) return;
        
        const data = vp[priceStr];
        const barW = (data.total / maxVpVol) * vpWidth;
        const bidW = (data.bid / data.total) * barW;
        const askW = (data.ask / data.total) * barW;
        
        const startX = chartWidth - barW;
        
        const inVA = (price >= vaLow && price <= vaHigh);
        ctx.globalAlpha = inVA ? 0.8 : 0.3;
        
        ctx.fillStyle = THEME.red;
        ctx.fillRect(startX, pY, bidW, boxHeight);
        ctx.fillStyle = THEME.green;
        ctx.fillRect(startX + bidW, pY, askW, boxHeight);
        
        if (price === pocPrice) {
            ctx.globalAlpha = 1.0;
            ctx.strokeStyle = THEME.pocBg;
            ctx.lineWidth = 1.5;
            ctx.strokeRect(startX, pY, barW, boxHeight);
            
            ctx.setLineDash([4, 4]);
            ctx.beginPath();
            ctx.moveTo(0, pY + boxHeight/2);
            ctx.lineTo(chartWidth, pY + boxHeight/2);
            ctx.stroke();
            ctx.setLineDash([]);
        }
    });
    ctx.globalAlpha = 1.0;
    
    if (isAnchored && anchorTs) {
        const cIdx = candles.findIndex(c => c.timestamp === anchorTs);
        if (cIdx !== -1) {
            const ax = offsetX + (cIdx * scaleX) + scaleX/2;
            ctx.setLineDash([5, 5]);
            ctx.strokeStyle = THEME.highlight;
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.moveTo(ax, 0); ctx.lineTo(ax, chartHeight);
            ctx.stroke();
            ctx.setLineDash([]);
        }
    }
}

function drawCumulativeDelta(ctx, chartWidth, chartHeight, candles) {
    const paneHeight = 80;
    const paneTop = chartHeight - paneHeight;
    
    ctx.strokeStyle = THEME.grid;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, paneTop + 0.5); ctx.lineTo(chartWidth, paneTop + 0.5);
    ctx.stroke();
    
    let cumDelta = 0;
    const cvdData = [];
    let minCvd = 0;
    let maxCvd = 0;
    
    candles.forEach(c => {
        let barDelta = 0;
        Object.values(c.footprint).forEach(fp => barDelta += (fp.ask - fp.bid));
        cumDelta += barDelta;
        cvdData.push(cumDelta);
        if (cumDelta > maxCvd) maxCvd = cumDelta;
        if (cumDelta < minCvd) minCvd = cumDelta;
    });
    
    if (cvdData.length === 0) return;
    
    const cvdRange = Math.max(1, maxCvd - minCvd);
    
    ctx.beginPath();
    ctx.lineWidth = 2;
    let firstX = null;
    let lastX = null;
    for (let i = 0; i < cvdData.length; i++) {
        const x = offsetX + (i * scaleX) + scaleX/2;
        if (x + scaleX/2 < 0 || x - scaleX/2 > chartWidth) continue;
        
        const cd = cvdData[i];
        const normalizedY = paneTop + 10 + ((maxCvd - cd) / cvdRange) * (paneHeight - 20);
        
        if (firstX === null) {
            ctx.moveTo(x, normalizedY);
            firstX = x;
        } else {
            ctx.lineTo(x, normalizedY);
        }
        lastX = x;
    }
    ctx.strokeStyle = THEME.blue;
    ctx.stroke();
    
    if (firstX !== null && lastX !== null) {
        ctx.lineTo(lastX, chartHeight);
        ctx.lineTo(firstX, chartHeight);
        ctx.fillStyle = THEME.volProfile; 
        ctx.fill();
    }
    
    ctx.fillStyle = THEME.text;
    ctx.font = '10px -apple-system, BlinkMacSystemFont, "Trebuchet MS", Roboto, Ubuntu, sans-serif';
    ctx.textAlign = 'left';
    ctx.fillText("CVD", chartWidth + 6, paneTop + 10);
    ctx.fillText(formatVol(maxCvd), chartWidth + 6, paneTop + 25);
    ctx.fillText(formatVol(minCvd), chartWidth + 6, chartHeight - 10);
}

function drawVWAP(ctx, chartWidth, chartHeight, candles) {
    ctx.lineWidth = 2;
    
    ctx.beginPath();
    ctx.strokeStyle = '#ff9800'; 
    let firstX = null;
    for (let i = 0; i < candles.length; i++) {
        if (!candles[i].vwap) continue;
        const x = offsetX + (i * scaleX) + scaleX/2;
        if (x + scaleX/2 < 0 || x - scaleX/2 > chartWidth) continue;
        const y = chartHeight - (candles[i].vwap * scaleY + offsetY);
        
        if (firstX === null) { ctx.moveTo(x, y); firstX = x; }
        else { ctx.lineTo(x, y); }
    }
    ctx.stroke();

    const drawBand = (multiplier, color) => {
        ctx.beginPath();
        ctx.strokeStyle = color;
        ctx.setLineDash([4, 4]);
        firstX = null;
        for (let i = 0; i < candles.length; i++) {
            if (!candles[i].vwap) continue;
            const x = offsetX + (i * scaleX) + scaleX/2;
            if (x + scaleX/2 < 0 || x - scaleX/2 > chartWidth) continue;
            const bandVal = candles[i].vwap + (candles[i].std * multiplier);
            const y = chartHeight - (bandVal * scaleY + offsetY);
            
            if (firstX === null) { ctx.moveTo(x, y); firstX = x; }
            else { ctx.lineTo(x, y); }
        }
        ctx.stroke();
        ctx.setLineDash([]);
    };
    
    drawBand(1, 'rgba(41, 98, 255, 0.5)');
    drawBand(-1, 'rgba(41, 98, 255, 0.5)');
    drawBand(2, 'rgba(255, 0, 0, 0.5)');
    drawBand(-2, 'rgba(0, 255, 0, 0.5)');
}

function drawIcebergs(ctx, chartWidth, chartHeight, candles) {
    candles.forEach((c, i) => {
        if (c.icebergs && c.icebergs.length > 0) {
            const x = offsetX + (i * scaleX) + scaleX/2;
            if (x + scaleX/2 < 0 || x - scaleX/2 > chartWidth) return;
            
            c.icebergs.forEach(ice => {
                const y = chartHeight - (ice.price * scaleY + offsetY);
                
                ctx.beginPath();
                ctx.moveTo(x, y - 8);
                ctx.lineTo(x + 8, y);
                ctx.lineTo(x, y + 8);
                ctx.lineTo(x - 8, y);
                ctx.closePath();
                
                ctx.fillStyle = ice.side === 'BID' ? 'rgba(0, 255, 0, 0.8)' : 'rgba(255, 0, 0, 0.8)';
                ctx.fill();
                ctx.strokeStyle = '#FFF';
                ctx.lineWidth = 1;
                ctx.stroke();
            });
        }
    });
}

function drawCrosshair(chartWidth, chartHeight, candles) {
    if (mouseHover && mouseX >= 0 && mouseX <= chartWidth && mouseY >= 0 && mouseY <= chartHeight && !isDraggingChart && !isDraggingYAxis && !isDraggingXAxis) {
        ctx.setLineDash([4, 4]);
        ctx.strokeStyle = THEME.textMuted;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(mouseX + 0.5, 0); ctx.lineTo(mouseX + 0.5, chartHeight);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(0, mouseY + 0.5); ctx.lineTo(chartWidth, mouseY + 0.5);
        ctx.stroke();
        ctx.setLineDash([]);
        
        const priceAtCursor = (chartHeight - mouseY - offsetY) / scaleY;
        ctx.fillStyle = THEME.pocBg;
        ctx.fillRect(chartWidth, mouseY - 10, AXIS_RIGHT, 21);
        ctx.fillStyle = THEME.pocText;
        ctx.textAlign = 'left';
        ctx.textBaseline = 'middle';
        ctx.fillText(formatPrice(priceAtCursor), chartWidth + 6, mouseY);
        
        const timeIndex = Math.floor((mouseX - offsetX) / scaleX);
        let timeLabel = '-';
        if (timeIndex >= 0 && timeIndex < candles.length) timeLabel = formatTime(candles[timeIndex].timestamp);
        const lblWidth = ctx.measureText(timeLabel).width + 16;
        ctx.fillStyle = THEME.pocBg;
        ctx.fillRect(mouseX - lblWidth/2, chartHeight, lblWidth, AXIS_BOTTOM);
        ctx.fillStyle = THEME.pocText;
        ctx.textAlign = 'center';
        ctx.fillText(timeLabel, mouseX, chartHeight + AXIS_BOTTOM/2);
    }
}

function drawDrawings(ctx, chartWidth, chartHeight) {
    const allDrawings = [...activeDrawings];
    if (tempDrawing) allDrawings.push(tempDrawing);
    
    allDrawings.forEach(d => {
        ctx.beginPath();
        ctx.lineWidth = 2;
        ctx.strokeStyle = d.color;
        ctx.setLineDash([]);
        
        if (d.type === 'pen') {
            if (d.points.length === 0) return;
            d.points.forEach((pt, i) => {
                const x = offsetX + (pt.time * scaleX);
                const y = chartHeight - (pt.price * scaleY + offsetY);
                if (i === 0) ctx.moveTo(x, y);
                else ctx.lineTo(x, y);
            });
            ctx.stroke();
        } else if (d.type === 'trendline' || d.type === 'ray') {
            const startX = offsetX + (d.start.time * scaleX);
            const startY = chartHeight - (d.start.price * scaleY + offsetY);
            let endX = offsetX + (d.end.time * scaleX);
            let endY = chartHeight - (d.end.price * scaleY + offsetY);
            
            if (d.type === 'ray') {
                const dx = endX - startX;
                const dy = endY - startY;
                if (dx !== 0 || dy !== 0) {
                    endX = startX + dx * 1000;
                    endY = startY + dy * 1000;
                }
            }
            
            ctx.moveTo(startX, startY);
            ctx.lineTo(endX, endY);
            ctx.stroke();
            
            ctx.fillStyle = d.color;
            ctx.beginPath(); ctx.arc(startX, startY, 4, 0, Math.PI*2); ctx.fill();
            if (d.type === 'trendline') {
                ctx.beginPath(); ctx.arc(endX, endY, 4, 0, Math.PI*2); ctx.fill();
            }
        } else if (d.type === 'fib') {
            const startX = offsetX + (d.start.time * scaleX);
            const startY = chartHeight - (d.start.price * scaleY + offsetY);
            const endX = offsetX + (d.end.time * scaleX);
            const endY = chartHeight - (d.end.price * scaleY + offsetY);
            
            ctx.moveTo(startX, startY);
            ctx.lineTo(endX, endY);
            ctx.setLineDash([4,4]);
            ctx.stroke();
            ctx.setLineDash([]);
            
            const diff = d.start.price - d.end.price;
            const levels = [
                {lvl: 0, c: '#787b86'}, {lvl: 0.236, c: '#f44336'}, {lvl: 0.382, c: '#81c784'}, 
                {lvl: 0.5, c: '#4caf50'}, {lvl: 0.618, c: '#00bcd4'}, {lvl: 0.786, c: '#64b5f6'}, 
                {lvl: 1, c: '#787b86'}
            ];
            
            levels.forEach(lv => {
                const p = d.start.price - (diff * lv.lvl);
                const py = chartHeight - (p * scaleY + offsetY);
                ctx.beginPath();
                ctx.strokeStyle = lv.c;
                ctx.moveTo(startX, py);
                ctx.lineTo(startX + 1000, py);
                ctx.stroke();
                
                ctx.fillStyle = lv.c;
                ctx.font = '10px Arial';
                ctx.fillText(lv.lvl + " (" + p.toFixed(2) + ")", startX + 10, py - 4);
            });
        } else if (d.type === 'gann') {
            const startX = offsetX + (d.start.time * scaleX);
            const startY = chartHeight - (d.start.price * scaleY + offsetY);
            const endX = offsetX + (d.end.time * scaleX);
            const endY = chartHeight - (d.end.price * scaleY + offsetY);
            
            const dx = endX - startX;
            const dy = endY - startY;
            if (dx === 0) return;
            
            const slope = dy / dx;
            const gannAngles = [1/8, 1/4, 1/3, 1/2, 1, 2, 3, 4, 8];
            const colors = ['#f44336', '#e91e63', '#9c27b0', '#673ab7', '#3f51b5', '#2196f3', '#03a9f4', '#00bcd4', '#009688'];
            
            gannAngles.forEach((ratio, i) => {
                ctx.beginPath();
                ctx.strokeStyle = colors[i];
                ctx.moveTo(startX, startY);
                // Draw line to right edge
                const projectedDx = chartWidth - startX;
                const projectedDy = (slope * ratio) * projectedDx;
                ctx.lineTo(chartWidth, startY + projectedDy);
                ctx.stroke();
                
                ctx.fillStyle = colors[i];
                ctx.font = '10px Arial';
                ctx.fillText(`1x${ratio >= 1 ? ratio : '1/'+(1/ratio)}`, startX + 50, startY + (slope * ratio) * 50 - 5);
            });
            
            ctx.fillStyle = THEME.blue;
            ctx.beginPath(); ctx.arc(startX, startY, 4, 0, Math.PI*2); ctx.fill();
        }
    });
}

function drawIndicators(ctx, chartWidth, chartHeight, candles) {
    activeIndicators.forEach(ind => {
        if (ind.pane !== 'main') return;
        
        ctx.lineWidth = 1.5;
        ctx.strokeStyle = ind.color || THEME.blue;
        
        let dataLine = [];
        if (ind.type === 'sma') dataLine = calculateSMA(candles, ind.period, 'close');
        else if (ind.type === 'ema') dataLine = calculateEMA(candles, ind.period, 'close');
        
        if (dataLine.length > 0) {
            ctx.beginPath();
            let firstX = null;
            for (let i = 0; i < candles.length; i++) {
                if (dataLine[i] === null) continue;
                const x = offsetX + (i * scaleX) + scaleX/2;
                if (x + scaleX/2 < 0 || x - scaleX/2 > chartWidth) continue;
                const y = chartHeight - (dataLine[i] * scaleY + offsetY);
                if (firstX === null) { ctx.moveTo(x, y); firstX = x; }
                else { ctx.lineTo(x, y); }
            }
            ctx.stroke();
        }
        
        if (ind.type === 'bollinger') {
            const bb = calculateBollinger(candles, ind.period, ind.std, 'close');
            
            // Draw SMA
            ctx.beginPath(); ctx.strokeStyle = ind.color;
            let firstX = null;
            for (let i = 0; i < candles.length; i++) {
                if (bb.sma[i] === null) continue;
                const x = offsetX + (i * scaleX) + scaleX/2;
                if (x + scaleX/2 < 0 || x - scaleX/2 > chartWidth) continue;
                const y = chartHeight - (bb.sma[i] * scaleY + offsetY);
                if (firstX === null) { ctx.moveTo(x, y); firstX = x; }
                else { ctx.lineTo(x, y); }
            }
            ctx.stroke();
            
            // Draw Upper and Lower
            ctx.beginPath(); ctx.strokeStyle = 'rgba(100, 150, 255, 0.5)';
            firstX = null;
            for (let i = 0; i < candles.length; i++) {
                if (bb.upper[i] === null) continue;
                const x = offsetX + (i * scaleX) + scaleX/2;
                if (x + scaleX/2 < 0 || x - scaleX/2 > chartWidth) continue;
                const y = chartHeight - (bb.upper[i] * scaleY + offsetY);
                if (firstX === null) { ctx.moveTo(x, y); firstX = x; }
                else { ctx.lineTo(x, y); }
            }
            ctx.stroke();
            
            ctx.beginPath();
            firstX = null;
            for (let i = 0; i < candles.length; i++) {
                if (bb.lower[i] === null) continue;
                const x = offsetX + (i * scaleX) + scaleX/2;
                if (x + scaleX/2 < 0 || x - scaleX/2 > chartWidth) continue;
                const y = chartHeight - (bb.lower[i] * scaleY + offsetY);
                if (firstX === null) { ctx.moveTo(x, y); firstX = x; }
                else { ctx.lineTo(x, y); }
            }
            ctx.stroke();
        } else if (ind.type === 'cpr') {
            const cpr = calculateCPR(candles);
            
            const drawCprLine = (val, color, label) => {
                const y = chartHeight - (val * scaleY + offsetY);
                if (y < 0 || y > chartHeight) return;
                ctx.beginPath();
                ctx.strokeStyle = color;
                ctx.setLineDash([2, 4]);
                ctx.moveTo(0, y);
                ctx.lineTo(chartWidth, y);
                ctx.stroke();
                ctx.setLineDash([]);
                
                ctx.fillStyle = color;
                ctx.font = '10px Arial';
                ctx.textAlign = 'right';
                ctx.fillText(`${label} (${val.toFixed(2)})`, chartWidth - 10, y - 5);
            };
            
            drawCprLine(cpr.p, '#9c27b0', 'P');
            drawCprLine(cpr.tc, '#3f51b5', 'TC');
            drawCprLine(cpr.bc, '#3f51b5', 'BC');
        }
    });
}

function drawLowerPanes(ctx, chartWidth, totalHeight, candles) {
    const PANE_HEIGHT = 80;
    
    bottomPanes.forEach((paneType, index) => {
        const paneTop = totalHeight - AXIS_BOTTOM - ((bottomPanes.length - index) * PANE_HEIGHT);
        
        // Draw Pane Border
        ctx.strokeStyle = THEME.grid;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(0, paneTop + 0.5); ctx.lineTo(chartWidth, paneTop + 0.5);
        ctx.stroke();
        
        if (paneType === 'cvd') {
            let cumDelta = 0;
            const cvdData = [];
            let minCvd = 0;
            let maxCvd = 0;
            candles.forEach(c => {
                let barDelta = 0;
                Object.values(c.footprint).forEach(fp => barDelta += (fp.ask - fp.bid));
                cumDelta += barDelta;
                cvdData.push(cumDelta);
                if (cumDelta > maxCvd) maxCvd = cumDelta;
                if (cumDelta < minCvd) minCvd = cumDelta;
            });
            if (cvdData.length === 0) return;
            const cvdRange = Math.max(1, maxCvd - minCvd);
            ctx.beginPath();
            ctx.lineWidth = 2;
            let firstX = null; let lastX = null;
            for (let i = 0; i < cvdData.length; i++) {
                const x = offsetX + (i * scaleX) + scaleX/2;
                if (x + scaleX/2 < 0 || x - scaleX/2 > chartWidth) continue;
                const cd = cvdData[i];
                const normalizedY = paneTop + 10 + ((maxCvd - cd) / cvdRange) * (PANE_HEIGHT - 20);
                if (firstX === null) { ctx.moveTo(x, normalizedY); firstX = x; }
                else { ctx.lineTo(x, normalizedY); }
                lastX = x;
            }
            ctx.strokeStyle = THEME.blue; ctx.stroke();
            if (firstX !== null && lastX !== null) {
                ctx.lineTo(lastX, paneTop + PANE_HEIGHT);
                ctx.lineTo(firstX, paneTop + PANE_HEIGHT);
                ctx.fillStyle = THEME.volProfile; ctx.fill();
            }
            ctx.fillStyle = THEME.text; ctx.textAlign = 'left';
            ctx.fillText("CVD", chartWidth + 6, paneTop + 10);
            ctx.fillText(formatVol(maxCvd), chartWidth + 6, paneTop + 25);
            ctx.fillText(formatVol(minCvd), chartWidth + 6, paneTop + PANE_HEIGHT - 10);

            // CVD Divergence Detection
            const win = 2;
            const swingHighs = [];
            const swingLows = [];
            for (let i = win; i < candles.length - win; i++) {
                let isSH = true, isSL = true;
                for (let k = 1; k <= win; k++) {
                    if (candles[i-k].high > candles[i].high || candles[i+k].high > candles[i].high) isSH = false;
                    if (candles[i-k].low < candles[i].low || candles[i+k].low < candles[i].low) isSL = false;
                }
                if (isSH) swingHighs.push(i);
                if (isSL) swingLows.push(i);
            }
            ctx.save();
            ctx.font = "10px sans-serif";
            for (let j = 1; j < swingHighs.length; j++) {
                const i1 = swingHighs[j-1], i2 = swingHighs[j];
                if (candles[i2].high >= candles[i1].high && cvdData[i2] < cvdData[i1]) {
                    const x1 = offsetX + (i1 * scaleX) + scaleX/2;
                    const x2 = offsetX + (i2 * scaleX) + scaleX/2;
                    const y1 = paneTop + 10 + ((maxCvd - cvdData[i1]) / cvdRange) * (PANE_HEIGHT - 20);
                    const y2 = paneTop + 10 + ((maxCvd - cvdData[i2]) / cvdRange) * (PANE_HEIGHT - 20);
                    ctx.strokeStyle = THEME.red; ctx.lineWidth = 1.5; ctx.setLineDash([3, 3]);
                    ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke(); ctx.setLineDash([]);
                    ctx.fillStyle = THEME.red; ctx.fillText("BEAR DIV", x2 - 20, y2 - 4);
                }
            }
            for (let j = 1; j < swingLows.length; j++) {
                const i1 = swingLows[j-1], i2 = swingLows[j];
                if (candles[i2].low <= candles[i1].low && cvdData[i2] > cvdData[i1]) {
                    const x1 = offsetX + (i1 * scaleX) + scaleX/2;
                    const x2 = offsetX + (i2 * scaleX) + scaleX/2;
                    const y1 = paneTop + 10 + ((maxCvd - cvdData[i1]) / cvdRange) * (PANE_HEIGHT - 20);
                    const y2 = paneTop + 10 + ((maxCvd - cvdData[i2]) / cvdRange) * (PANE_HEIGHT - 20);
                    ctx.strokeStyle = THEME.green; ctx.lineWidth = 1.5; ctx.setLineDash([3, 3]);
                    ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke(); ctx.setLineDash([]);
                    ctx.fillStyle = THEME.green; ctx.fillText("BULL DIV", x2 - 20, y2 + 12);
                }
            }
            ctx.restore();
        } else if (paneType === 'rsi') {
            const rsiInd = activeIndicators.find(ind => ind.type === 'rsi');
            if (!rsiInd) return;
            const rsiData = calculateRSI(candles, rsiInd.period, 'close');
            ctx.beginPath();
            ctx.lineWidth = 2;
            ctx.strokeStyle = rsiInd.color;
            let firstX = null;
            for (let i = 0; i < candles.length; i++) {
                if (rsiData[i] === null) continue;
                const x = offsetX + (i * scaleX) + scaleX/2;
                if (x + scaleX/2 < 0 || x - scaleX/2 > chartWidth) continue;
                const normalizedY = paneTop + 10 + ((100 - rsiData[i]) / 100) * (PANE_HEIGHT - 20);
                if (firstX === null) { ctx.moveTo(x, normalizedY); firstX = x; }
                else { ctx.lineTo(x, normalizedY); }
            }
            ctx.stroke();
            
            // Draw 70 and 30 lines
            ctx.setLineDash([2, 2]);
            ctx.strokeStyle = THEME.textMuted;
            ctx.beginPath();
            ctx.moveTo(0, paneTop + 10 + (30/100)*(PANE_HEIGHT-20)); ctx.lineTo(chartWidth, paneTop + 10 + (30/100)*(PANE_HEIGHT-20));
            ctx.moveTo(0, paneTop + 10 + (70/100)*(PANE_HEIGHT-20)); ctx.lineTo(chartWidth, paneTop + 10 + (70/100)*(PANE_HEIGHT-20));
            ctx.stroke();
            ctx.setLineDash([]);
            
            ctx.fillStyle = THEME.text; ctx.textAlign = 'left';
            ctx.fillText("RSI", chartWidth + 6, paneTop + 10);
            ctx.fillText("70", chartWidth + 6, paneTop + 10 + (30/100)*(PANE_HEIGHT-20));
            ctx.fillText("30", chartWidth + 6, paneTop + 10 + (70/100)*(PANE_HEIGHT-20));
        }
    });
}

// ----------------------------------------------------
// MAIN DRAW LOOP
// ----------------------------------------------------

function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const PANE_HEIGHT = 80;
    const numPanes = bottomPanes.length;
    const chartWidth = canvas.width - AXIS_RIGHT;
    const chartHeight = canvas.height - AXIS_BOTTOM - (numPanes * PANE_HEIGHT);
    const minPrice = -offsetY / scaleY;
    const maxPrice = (chartHeight - offsetY) / scaleY;
    const priceDiff = maxPrice - minPrice;
    
    let step = 0.01;
    if (priceDiff > 10) step = 1.0;
    else if (priceDiff > 5) step = 0.5;
    else if (priceDiff > 1) step = 0.1;
    else if (priceDiff > 0.5) step = 0.05;
    
    const candles = footprintData[currentSymbol] ? getDisplayCandles(footprintData[currentSymbol].candles, currentTimeframe) : [];
    
    drawGrid(chartWidth, chartHeight, minPrice, maxPrice, step, candles);
    
    if (candles.length === 0) {
        drawAxes(chartWidth, chartHeight, minPrice, maxPrice, step, null);
        return;
    }
    
    const tickSize = 0.01;
    let maxVol = 1;
    let lastTradedPrice = 0;
    candles.forEach(c => {
        lastTradedPrice = c.close;
        Object.values(c.footprint).forEach(fp => {
            if (fp.bid > maxVol) maxVol = fp.bid;
            if (fp.ask > maxVol) maxVol = fp.ask;
            // For clusters we need max total volume per node
            if (fp.bid + fp.ask > maxVol) maxVol = fp.bid + fp.ask;
        });
    });

    if (currentMode === 'heatmap' || currentMode === 'cluster') drawHeatmap(ctx, chartWidth, chartHeight, candles, tickSize);
    
    ctx.save();
    ctx.beginPath();
    ctx.rect(0, 0, chartWidth, chartHeight);
    ctx.clip();
    
    if (currentMode === 'cluster') {
        ctx.beginPath();
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 1;
        let firstLine = true;
        for (let i = 0; i < candles.length; i++) {
            const candle = candles[i];
            const x = offsetX + (i * scaleX);
            if (x + scaleX < 0 || x > chartWidth) continue;
            const cx = x + (scaleX * 0.1) + (scaleX * 0.5);
            const cY = chartHeight - (candle.close * scaleY + offsetY);
            if (firstLine) { ctx.moveTo(cx, cY); firstLine = false; }
            else { ctx.lineTo(cx, cY); }
        }
        ctx.stroke();
    }
    
    for (let i = 0; i < candles.length; i++) {
        const candle = candles[i];
        const x = offsetX + (i * scaleX);
        if (x + scaleX < 0 || x > chartWidth) continue;
        
        if (currentMode !== 'cluster') {
            drawCandlestick(candle, x, chartHeight);
        }
        
        if (currentMode === 'footprint') {
            drawFootprintData(ctx, candle, x, chartHeight, tickSize, maxVol);
        } else if (currentMode === 'cluster') {
            drawClusterData(ctx, candle, x, chartHeight, tickSize, maxVol);
        }
    }
    
    if (currentMode === 'vp-fixed') {
        drawVolumeProfile(ctx, chartWidth, chartHeight, candles, tickSize, false, null);
    } else if (currentMode === 'vp-anchored') {
        drawVolumeProfile(ctx, chartWidth, chartHeight, candles, tickSize, true, anchorTimestamp);
    }
    
    drawVWAP(ctx, chartWidth, chartHeight, candles);
    drawIndicators(ctx, chartWidth, chartHeight, candles);
    drawDrawings(ctx, chartWidth, chartHeight);
    drawIcebergs(ctx, chartWidth, chartHeight, candles);
    
    ctx.restore();
    
    drawLowerPanes(ctx, chartWidth, canvas.height, candles);
    
    drawAxes(chartWidth, chartHeight, minPrice, maxPrice, step, candles);
    
    // Draw LTP
    if (lastTradedPrice > 0) {
        const ltpY = chartHeight - (lastTradedPrice * scaleY + offsetY);
        if (ltpY >= 0 && ltpY <= chartHeight) {
            ctx.setLineDash([2, 2]);
            ctx.strokeStyle = THEME.red;
            ctx.beginPath();
            ctx.moveTo(0, Math.round(ltpY) + 0.5); ctx.lineTo(chartWidth, Math.round(ltpY) + 0.5);
            ctx.stroke();
            ctx.setLineDash([]);
            ctx.fillStyle = THEME.red;
            ctx.fillRect(chartWidth, ltpY - 10, AXIS_RIGHT, 21);
            ctx.fillStyle = '#FFF';
            ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
            ctx.fillText(formatPrice(lastTradedPrice), chartWidth + 6, ltpY);
        }
    }
    
    drawCrosshair(chartWidth, chartHeight, candles);
}

// UI Hooks for Indicators
const btnIndicators = document.getElementById('btn-indicators');
const indModal = document.getElementById('indicator-modal');
const closeModal = document.getElementById('close-modal');

if (btnIndicators && indModal) {
    btnIndicators.addEventListener('click', () => {
        indModal.style.display = 'flex';
    });
    closeModal.addEventListener('click', () => {
        indModal.style.display = 'none';
    });
    document.querySelectorAll('.ind-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const type = e.target.getAttribute('data-type');
            const pane = e.target.getAttribute('data-pane');
            if (type && pane) {
                if (pane === 'lower') {
                    if (!bottomPanes.includes(type)) bottomPanes.push(type);
                    if (!activeIndicators.find(i => i.type === type)) {
                        activeIndicators.push({ type: type, period: 14, color: '#e74c3c', pane: 'lower' });
                    }
                } else {
                    let color = '#2962FF';
                    if (type === 'sma') color = '#f5b041';
                    if (type === 'ema') color = '#9b59b6';
                    if (type === 'cpr') color = '#9c27b0';
                    activeIndicators.push({ type: type, period: 20, color: color, pane: 'main', std: 2 });
                }
                draw();
                indModal.style.display = 'none';
            }
        });
    });
}

